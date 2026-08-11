"""Unit tests for MiniMax provider (mocked HTTP, no network)."""
from __future__ import annotations

import json

from intelligence.contracts import ItemRef, SummarizeIn
from intelligence.providers.minimax import MinimaxProvider
from intelligence.text_normalize import extract_json, normalize_summary_text


def test_extract_json_fence():
    data = extract_json('前缀\n```json\n{"summary":"你好"}\n```\n')
    assert data == {"summary": "你好"}


def test_extract_json_with_think():
    raw = '<think>思考</think>\n{"summary":"摘要内容"}'
    assert extract_json(raw) == {"summary": "摘要内容"}


def test_normalize_summary_unwraps_json():
    raw = '{"summary":"2026年早盘必读：上证涨0.67%。央行印发\\"十五五\\"规划。"}'
    assert "早盘必读" in normalize_summary_text(raw)
    assert not normalize_summary_text(raw).startswith("{")


def test_normalize_summary_broken_quotes():
    raw = '{"summary":"央行印发"十五五"改革发展规划，市场关注。"}'
    out = normalize_summary_text(raw)
    assert "央行印发" in out
    assert "改革发展规划" in out
    assert not out.startswith("{")


def test_minimax_summarize_ok(monkeypatch):
    provider = MinimaxProvider(api_key="test-key", model="MiniMax-M3", strict=True)

    def fake_chat(**kwargs):
        return json.dumps({"summary": "这是摘要"}, ensure_ascii=False), {
            "provider": "minimax",
            "model": "MiniMax-M3",
            "latency_ms": 12.0,
        }

    monkeypatch.setattr(provider, "_chat", fake_chat)
    out = provider.summarize(
        SummarizeIn(item=ItemRef(id="1", title="标题", body="正文内容足够长用于测试"))
    )
    assert out.summary == "这是摘要"
    assert out.model_meta.get("provider") == "minimax"


def test_minimax_summarize_fallback(monkeypatch):
    provider = MinimaxProvider(api_key="test-key", strict=False)

    def boom(**kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(provider, "_chat", boom)
    out = provider.summarize(SummarizeIn(item=ItemRef(id="1", title="T", body="B")))
    assert out.model_meta.get("fallback") is True
    assert "T" in out.summary


def test_factory_minimax(monkeypatch):
    monkeypatch.setenv("AI_MOCK_MODE", "false")
    monkeypatch.setenv("AI_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "k")
    from pipeline.settings import get_settings

    get_settings.cache_clear()
    from intelligence.factory import create_provider

    p = create_provider()
    assert p.name == "minimax"
    get_settings.cache_clear()

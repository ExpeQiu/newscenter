"""MiniMax provider — OpenAI-compatible Chat Completions (国内默认 api.minimaxi.com)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from intelligence.contracts import (
    AskIn,
    AskOut,
    ClassifyIn,
    ClassifyOut,
    DigestIn,
    DigestOut,
    RecommendIn,
    RecommendItem,
    RecommendOut,
    SummarizeIn,
    SummarizeOut,
)
from intelligence.providers.mock import MockProvider
from intelligence.text_normalize import extract_json, normalize_summary_text, strip_think
from pipeline.settings import get_settings

logger = logging.getLogger("newsc.intelligence.minimax")


class MinimaxProvider:
    """调用 MiniMax OpenAI 兼容接口，失败时按 soft/strict 策略处理。"""

    name = "minimax"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        strict: bool | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or settings.minimax_base_url).rstrip("/")
        self.model = model or settings.minimax_model
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.strict = settings.ai_fallback_strict if strict is None else bool(strict)
        self._fallback = MockProvider()
        self.fallback_count = 0
        self.call_count = 0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> tuple[str, dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("MINIMAX_API_KEY missing")

        url = f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            # M3 可关 thinking，结构化任务更快更稳
            "thinking": {"type": "disabled"},
        }
        last_err: str | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, headers=self._headers(), json=body)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    if r.status_code >= 500:
                        last_err = f"http_{r.status_code}"
                        logger.warning(
                            "minimax_http skill=chat status=%s attempt=%s latency_ms=%.1f",
                            r.status_code,
                            attempt,
                            latency_ms,
                        )
                        time.sleep(min(2**attempt * 0.3, 3.0))
                        continue
                    if r.status_code >= 400:
                        detail = (r.text or "")[:300]
                        logger.warning(
                            "minimax_http_client_error status=%s body=%s",
                            r.status_code,
                            detail,
                        )
                        raise RuntimeError(f"minimax http {r.status_code}: {detail}")
                    data = r.json()
                    choices = data.get("choices") or []
                    if not choices:
                        raise RuntimeError("minimax empty choices")
                    msg = choices[0].get("message") or {}
                    content = msg.get("content") or ""
                    meta = {
                        "provider": self.name,
                        "model": self.model,
                        "latency_ms": round(latency_ms, 1),
                        "usage": data.get("usage") or {},
                    }
                    return str(content), meta
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                logger.warning("minimax_chat_fail attempt=%s err=%s", attempt, exc)
                time.sleep(min(2**attempt * 0.3, 3.0))
        raise RuntimeError(f"minimax exhausted: {last_err}")

    def _on_fallback(self, skill: str, err: Exception) -> None:
        self.fallback_count += 1
        logger.warning(
            "minimax_fallback skill=%s strict=%s err=%s fallback_count=%s",
            skill,
            self.strict,
            err,
            self.fallback_count,
        )
        if self.strict:
            raise RuntimeError(f"minimax unavailable for skill={skill}: {err}") from err

    def summarize(self, payload: SummarizeIn) -> SummarizeOut:
        self.call_count += 1
        it = payload.item
        system = (
            "你是新闻摘要助手。只输出 JSON："
            '{"summary":"中文摘要，2-4句，客观简洁"}'
        )
        user = (
            f"标题: {it.title}\n"
            f"来源: {it.source_type}\n"
            f"URL: {it.url or ''}\n"
            f"正文:\n{(it.body or '')[:6000]}"
        )
        try:
            content, meta = self._chat(system=system, user=user, max_tokens=800)
            data = extract_json(content)
            if isinstance(data, dict) and data.get("summary"):
                return SummarizeOut(
                    summary=normalize_summary_text(str(data["summary"])),
                    model_meta=meta,
                )
            text = normalize_summary_text(strip_think(content))
            if text:
                return SummarizeOut(summary=text[:800], model_meta=meta)
            raise RuntimeError("empty summary")
        except Exception as exc:  # noqa: BLE001
            self._on_fallback("summarize", exc)
            out = self._fallback.summarize(payload)
            out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name, "error": str(exc)[:200]}
            return out

    def classify(self, payload: ClassifyIn) -> ClassifyOut:
        self.call_count += 1
        it = payload.item
        if it.category_locked and it.ai_category:
            return ClassifyOut(
                category=it.ai_category,
                tags=[],
                confidence=1.0,
                skipped=True,
                model_meta={"provider": self.name, "reason": "category_locked"},
            )
        system = (
            "你是内容分类助手。只输出 JSON："
            '{"category":"一级分类","tags":["标签"],"confidence":0.0到1.0}\n'
            "分类优先用：科技/财经/政治/社会/视频/综合。"
        )
        user = f"标题: {it.title}\n来源: {it.source_type}\n正文:\n{(it.body or it.summary or '')[:4000]}"
        try:
            content, meta = self._chat(system=system, user=user, max_tokens=400)
            data = extract_json(content)
            if not isinstance(data, dict) or not data.get("category"):
                raise RuntimeError("invalid classify json")
            tags = data.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            conf = float(data.get("confidence") or 0.6)
            return ClassifyOut(
                category=str(data["category"]).strip(),
                tags=[str(t).strip() for t in tags if str(t).strip()][:8],
                confidence=max(0.0, min(1.0, conf)),
                model_meta=meta,
            )
        except Exception as exc:  # noqa: BLE001
            self._on_fallback("classify", exc)
            out = self._fallback.classify(payload)
            out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name, "error": str(exc)[:200]}
            return out

    def digest(self, payload: DigestIn) -> DigestOut:
        self.call_count += 1
        lines = []
        for i, it in enumerate(payload.items[:40], 1):
            lines.append(
                f"{i}. id={it.id} | {it.title or '无标题'} | "
                f"cat={it.ai_category or '-'} | {(it.summary or it.body or '')[:240]}"
            )
        system = (
            "你是每日资讯主编。只输出 JSON："
            '{"markdown":"中文 Markdown 日报","highlights":["要点标题",...]}\n'
            "markdown 含标题与分点洞察，highlights 3-7 条。"
        )
        user = f"日期: {payload.digest_date.isoformat()}\n条目:\n" + ("\n".join(lines) or "(无)")
        try:
            content, meta = self._chat(system=system, user=user, max_tokens=2500, temperature=0.4)
            data = extract_json(content)
            if isinstance(data, dict) and data.get("markdown"):
                highlights = data.get("highlights") or []
                if not isinstance(highlights, list):
                    highlights = []
                return DigestOut(
                    markdown=str(data["markdown"]).strip(),
                    highlights=[str(h).strip() for h in highlights if str(h).strip()][:12],
                    model_meta={**meta, "count": len(payload.items)},
                )
            text = strip_think(content)
            if text:
                return DigestOut(markdown=text, highlights=[], model_meta={**meta, "count": len(payload.items)})
            raise RuntimeError("empty digest")
        except Exception as exc:  # noqa: BLE001
            self._on_fallback("digest", exc)
            out = self._fallback.digest(payload)
            out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name, "error": str(exc)[:200]}
            return out

    def recommend(self, payload: RecommendIn) -> RecommendOut:
        self.call_count += 1
        cands = []
        for it in payload.candidates[:40]:
            cands.append(
                {
                    "id": it.id,
                    "title": it.title,
                    "category": it.ai_category,
                    "summary": (it.summary or "")[:200],
                }
            )
        system = (
            "你是个性化荐读助手。只输出 JSON："
            '{"items":[{"id":"...","score":0到1,"reason":"一句中文理由"}]}\n'
            "最多 7 条，按 score 降序；id 必须来自候选。"
        )
        user = (
            f"日期: {payload.as_of.isoformat()}\n"
            f"用户信号: {json.dumps(payload.user_signals, ensure_ascii=False)}\n"
            f"候选: {json.dumps(cands, ensure_ascii=False)}"
        )
        try:
            content, meta = self._chat(system=system, user=user, max_tokens=1200)
            data = extract_json(content)
            items_raw = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items_raw, list):
                raise RuntimeError("invalid recommend json")
            allowed = {c["id"] for c in cands}
            items: list[RecommendItem] = []
            for row in items_raw:
                if not isinstance(row, dict):
                    continue
                rid = str(row.get("id") or "")
                if rid not in allowed:
                    continue
                items.append(
                    RecommendItem(
                        id=rid,
                        score=float(row.get("score") or 0.5),
                        reason=str(row.get("reason") or "推荐阅读"),
                    )
                )
            if not items:
                raise RuntimeError("no valid recommend items")
            items.sort(key=lambda x: x.score, reverse=True)
            return RecommendOut(items=items[:7], model_meta=meta)
        except Exception as exc:  # noqa: BLE001
            self._on_fallback("recommend", exc)
            out = self._fallback.recommend(payload)
            out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name, "error": str(exc)[:200]}
            return out

    def ask(self, payload: AskIn) -> AskOut:
        self.call_count += 1
        system = (
            "你是 NewsC 阅读助手。只输出 JSON："
            '{"answer":"中文回答","citations":["引用"]}\n'
            "基于给定上下文回答；不确定时说明。"
        )
        user = (
            f"上下文: {json.dumps(payload.context or {}, ensure_ascii=False)}\n"
            f"问题: {payload.question}"
        )
        try:
            content, meta = self._chat(system=system, user=user, max_tokens=1200, temperature=0.4)
            data = extract_json(content)
            if isinstance(data, dict) and data.get("answer"):
                cites = data.get("citations") or []
                if not isinstance(cites, list):
                    cites = []
                return AskOut(
                    answer=str(data["answer"]).strip(),
                    citations=[str(c) for c in cites if str(c).strip()][:8],
                    model_meta=meta,
                )
            text = strip_think(content)
            if text:
                return AskOut(answer=text, citations=[], model_meta=meta)
            raise RuntimeError("empty ask")
        except Exception as exc:  # noqa: BLE001
            self._on_fallback("ask", exc)
            out = self._fallback.ask(payload)
            out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name, "error": str(exc)[:200]}
            return out


def minimax_reachable(base_url: str, api_key: str, timeout: float = 3.0) -> bool:
    """轻量探活：有 key 且能连上主机（不强制扣费调用）。"""
    if not (api_key or "").strip():
        return False
    try:
        root = base_url.rstrip("/")
        # OpenAI 兼容根通常无 models；连 TCP/TLS 即可
        with httpx.Client(timeout=timeout) as client:
            r = client.get(root.replace("/v1", "") + "/", follow_redirects=True)
            return r.status_code < 500
    except Exception:  # noqa: BLE001
        return False

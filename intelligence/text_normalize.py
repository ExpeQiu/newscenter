"""轻量文本规范化（避免 provider 间循环依赖）。"""
from __future__ import annotations

import json
import re
from typing import Any

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)
_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.I)


def strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    raw = strip_think(text)
    if not raw:
        return None
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = raw.find(open_c)
        end = raw.rfind(close_c)
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def normalize_summary_text(text: str) -> str:
    """模型偶发把整段 JSON 当摘要；尽量抽出 summary 字段纯文本。"""
    raw = strip_think(text)
    if not raw:
        return ""
    if raw.startswith("{") and '"summary"' in raw:
        data = extract_json(raw)
        if isinstance(data, dict) and data.get("summary"):
            return str(data["summary"]).strip()
        m = re.search(r'"summary"\s*:\s*"', raw)
        if m:
            start = m.end()
            close = raw.rfind("}")
            end = raw.rfind('"', 0, close if close > start else len(raw))
            if end > start:
                return (
                    raw[start:end]
                    .replace('\\"', '"')
                    .replace("\\n", "\n")
                    .strip()
                )
    return re.sub(r"^【摘要】\s*", "", raw).strip()

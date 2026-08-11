"""订阅源刷新周期：规范化、默认值与到期判断。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 存库 / YAML 的规范值 → 分钟数；manual 表示仅手动触发
REFRESH_MINUTES: dict[str, int | None] = {
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "3h": 180,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "manual": None,
}

REFRESH_LABELS: dict[str, str] = {
    "15m": "每 15 分钟",
    "30m": "每 30 分钟",
    "1h": "每 1 小时",
    "3h": "每 3 小时",
    "6h": "每 6 小时",
    "12h": "每 12 小时",
    "1d": "每天",
    "manual": "仅手动",
}

DEFAULT_REFRESH_BY_TYPE: dict[str, str] = {
    "web": "1h",
    "rss": "1h",
    "social": "1h",
    "bilibili": "6h",
    "youtube": "6h",
    "digest": "1d",
}

# 兼容别名 / 数字分钟
_ALIASES: dict[str, str] = {
    "15min": "15m",
    "30min": "30m",
    "60m": "1h",
    "60min": "1h",
    "hourly": "1h",
    "daily": "1d",
    "day": "1d",
    "none": "manual",
    "off": "manual",
}


def default_refresh_interval(stype: str) -> str:
    return DEFAULT_REFRESH_BY_TYPE.get((stype or "").strip().lower(), "1h")


def canonicalize_refresh_interval(
    raw: Any,
    *,
    stype: str | None = None,
    fallback: str | None = None,
) -> str:
    """将用户输入规范为预设 key；无法识别时回落到类型默认或 fallback。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if fallback and fallback in REFRESH_MINUTES:
            return fallback
        return default_refresh_interval(stype or "")

    if isinstance(raw, (int, float)):
        minutes = int(raw)
        for key, val in REFRESH_MINUTES.items():
            if val == minutes:
                return key
        # 就近匹配预设
        best = "1h"
        best_diff = abs(60 - minutes)
        for key, val in REFRESH_MINUTES.items():
            if val is None:
                continue
            diff = abs(val - minutes)
            if diff < best_diff:
                best = key
                best_diff = diff
        logger.info("refresh_interval_coerce minutes=%s -> %s", minutes, best)
        return best

    s = str(raw).strip().lower().replace(" ", "")
    if s in REFRESH_MINUTES:
        return s
    if s in _ALIASES:
        return _ALIASES[s]
    if s.endswith("min") and s[:-3].isdigit():
        return canonicalize_refresh_interval(int(s[:-3]), stype=stype, fallback=fallback)
    if s.endswith("m") and s[:-1].isdigit():
        return canonicalize_refresh_interval(int(s[:-1]), stype=stype, fallback=fallback)
    if s.endswith("h") and s[:-1].isdigit():
        return canonicalize_refresh_interval(int(s[:-1]) * 60, stype=stype, fallback=fallback)
    if s.endswith("d") and s[:-1].isdigit():
        return canonicalize_refresh_interval(int(s[:-1]) * 1440, stype=stype, fallback=fallback)

    logger.warning("refresh_interval_unknown raw=%r fallback=%s", raw, fallback or stype)
    if fallback and fallback in REFRESH_MINUTES:
        return fallback
    return default_refresh_interval(stype or "")


def refresh_interval_minutes(key: str) -> int | None:
    return REFRESH_MINUTES.get(key)


def refresh_interval_label(key: str) -> str:
    return REFRESH_LABELS.get(key, key or "—")


def parse_last_fetched(cursor: dict[str, Any] | None) -> datetime | None:
    if not cursor:
        return None
    raw = cursor.get("last_fetched_at") or cursor.get("last_run_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def source_is_due(
    *,
    refresh_interval: str,
    cursor: dict[str, Any] | None,
    now: datetime | None = None,
) -> bool:
    """定时管道是否应采集该源。manual 永远不自动到期。"""
    minutes = refresh_interval_minutes(refresh_interval)
    if minutes is None:
        return False
    last = parse_last_fetched(cursor)
    if last is None:
        return True
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    return now_dt >= last + timedelta(minutes=minutes)


def stamp_last_fetched(cursor: dict[str, Any] | None, when: datetime | None = None) -> dict[str, Any]:
    ts = when or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    out = dict(cursor or {})
    out["last_fetched_at"] = ts.isoformat()
    return out

"""事件 / 宏观检索查询目录：YAML 加载与 local 合并。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from pipeline.refresh_interval import canonicalize_refresh_interval
from pipeline.settings import ROOT, get_settings

logger = logging.getLogger(__name__)

EventDimension = Literal["global", "china", "industry", "enterprise"]
MacroScope = Literal["global", "china", "industry"]
QueryKind = Literal["event", "macro"]

EVENT_DIMENSIONS = frozenset({"global", "china", "industry", "enterprise"})
MACRO_SCOPES = frozenset({"global", "china", "industry"})


class InsightQueriesError(Exception):
    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class InsightQuery:
    id: str
    kind: QueryKind
    enabled: bool
    query: str
    refresh_interval: str
    # event
    dimension: str | None = None
    industry: str | None = None
    entity: str | None = None
    # macro
    scope: str | None = None
    indicator_id: str | None = None
    label: str | None = None
    unit: str | None = None
    description: str | None = None


def _queries_file() -> Path:
    s = get_settings()
    raw = getattr(s, "insight_queries_file", None) or ""
    raw = str(raw).strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        return p
    return ROOT / "insight-queries.yml"


def _local_queries_file() -> Path | None:
    base = _queries_file()
    if base.name != "insight-queries.yml":
        return None
    return base.with_name("insight-queries.local.yml")


def _parse_query_dicts(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.exception("insight_queries parse failed file=%s", path)
        raise InsightQueriesError(f"查询配置无法解析: {exc}", status_code=500) from exc
    rows = raw.get("queries") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _merge_dicts(base: list[dict[str, Any]], local: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base + local:
        qid = str(row.get("id") or "").strip()
        if not qid:
            continue
        if qid not in by_id:
            order.append(qid)
            by_id[qid] = dict(row)
        else:
            by_id[qid] = {**by_id[qid], **row}
    out: list[dict[str, Any]] = []
    for qid in order:
        row = by_id[qid]
        if row.get("deleted") is True:
            continue
        out.append(row)
    return out


def _norm_str(raw: Any, *, max_len: int = 200) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return s[:max_len]


def _parse_one(row: dict[str, Any]) -> InsightQuery | None:
    qid = _norm_str(row.get("id"), max_len=64)
    if not qid:
        return None
    kind = str(row.get("kind") or "").strip().lower()
    if kind not in ("event", "macro"):
        logger.warning("insight_query_skip id=%s reason=bad_kind kind=%r", qid, kind)
        return None
    query = _norm_str(row.get("query"), max_len=500)
    if not query:
        logger.warning("insight_query_skip id=%s reason=empty_query", qid)
        return None
    enabled = bool(row.get("enabled", True))
    refresh = canonicalize_refresh_interval(
        row.get("refresh_interval"),
        stype="digest",
        fallback="1d",
    )
    if kind == "event":
        dim = str(row.get("dimension") or "").strip().lower()
        if dim not in EVENT_DIMENSIONS:
            logger.warning("insight_query_skip id=%s reason=bad_dimension dim=%r", qid, dim)
            return None
        return InsightQuery(
            id=qid,
            kind="event",
            enabled=enabled,
            query=query,
            refresh_interval=refresh,
            dimension=dim,
            industry=_norm_str(row.get("industry"), max_len=64),
            entity=_norm_str(row.get("entity"), max_len=120),
        )
    scope = str(row.get("scope") or "").strip().lower()
    if scope not in MACRO_SCOPES:
        logger.warning("insight_query_skip id=%s reason=bad_scope scope=%r", qid, scope)
        return None
    indicator_id = _norm_str(row.get("indicator_id"), max_len=64)
    if not indicator_id:
        logger.warning("insight_query_skip id=%s reason=missing_indicator_id", qid)
        return None
    return InsightQuery(
        id=qid,
        kind="macro",
        enabled=enabled,
        query=query,
        refresh_interval=refresh,
        scope=scope,
        industry=_norm_str(row.get("industry"), max_len=64),
        indicator_id=indicator_id,
        label=_norm_str(row.get("label"), max_len=200) or indicator_id,
        unit=_norm_str(row.get("unit"), max_len=32) or "",
        description=_norm_str(row.get("description"), max_len=500),
    )


def load_queries(*, kind: QueryKind | None = None, enabled_only: bool = True) -> list[InsightQuery]:
    """加载合并后的查询列表。"""
    base_path = _queries_file()
    local_path = _local_queries_file()
    base = _parse_query_dicts(base_path)
    local = _parse_query_dicts(local_path) if local_path else []
    merged = _merge_dicts(base, local)
    out: list[InsightQuery] = []
    for row in merged:
        q = _parse_one(row)
        if q is None:
            continue
        if enabled_only and not q.enabled:
            continue
        if kind and q.kind != kind:
            continue
        out.append(q)
    logger.info(
        "insight_queries_loaded base=%s local=%s count=%s kind=%s",
        base_path,
        local_path if local_path and local_path.is_file() else None,
        len(out),
        kind or "all",
    )
    return out


def queries_config_path() -> Path:
    return _queries_file()

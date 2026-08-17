"""事件 / 宏观检索管线：按 YAML 查询目录检索并入库。"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy.orm import Session

from intelligence.contracts import RetrieveEventsIn, RetrieveMacroIn
from intelligence.factory import create_provider
from pipeline.insight_queries import InsightQuery, QueryKind, load_queries
from pipeline.models import ControlSetting, InsightEvent, MacroIndicator, MacroObservation
from pipeline.refresh_interval import source_is_due, stamp_last_fetched

logger = logging.getLogger(__name__)

CURSORS_KEY = "insight_cursors"


def _parse_dt(raw: str | None, *, fallback: datetime | None = None) -> datetime:
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
    return fallback or datetime.now(timezone.utc)


def _hash_event(*, title: str, occurred_at: datetime, dimension: str, query_id: str) -> str:
    key = f"{query_id}|{dimension}|{occurred_at.date().isoformat()}|{title.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _hash_obs(*, indicator_id: str, observed_at: datetime, period_label: str, value: str) -> str:
    key = f"{indicator_id}|{observed_at.isoformat()}|{period_label}|{value}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _load_cursors(db: Session) -> dict[str, Any]:
    row = db.get(ControlSetting, CURSORS_KEY)
    if not row or not isinstance(row.value, dict):
        return {}
    return dict(row.value)


def _save_cursors(db: Session, cursors: dict[str, Any]) -> None:
    row = db.get(ControlSetting, CURSORS_KEY)
    if row is None:
        row = ControlSetting(key=CURSORS_KEY, value=cursors)
        db.add(row)
    else:
        row.value = cursors


def _upsert_event(
    db: Session,
    *,
    q: InsightQuery,
    title: str,
    summary: str,
    occurred_at: datetime,
    industry: str | None,
    entity: str | None,
    source_urls: list[str],
    raw: dict[str, Any],
) -> bool:
    content_hash = _hash_event(
        title=title,
        occurred_at=occurred_at,
        dimension=q.dimension or "",
        query_id=q.id,
    )
    existing = db.query(InsightEvent).filter(InsightEvent.content_hash == content_hash).one_or_none()
    if existing:
        return False
    db.add(
        InsightEvent(
            id=str(uuid4()),
            occurred_at=occurred_at,
            dimension=q.dimension or "global",
            industry=industry or q.industry,
            entity=entity or q.entity,
            title=title[:500],
            summary=summary[:2000],
            source_urls=source_urls[:8],
            query_id=q.id,
            content_hash=content_hash,
            raw=raw,
        )
    )
    return True


def _to_decimal(val: float | None) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _ensure_indicator(
    db: Session,
    *,
    q: InsightQuery,
    label: str,
    unit: str,
    description: str | None,
) -> MacroIndicator:
    indicator_id = q.indicator_id or ""
    ind = db.get(MacroIndicator, indicator_id)
    if ind is None:
        ind = MacroIndicator(
            indicator_id=indicator_id,
            label=label or indicator_id,
            scope=q.scope or "global",
            industry=q.industry,
            unit=unit or "",
            description=description,
        )
        db.add(ind)
        db.flush()
        return ind
    ind.label = label or ind.label
    ind.scope = q.scope or ind.scope
    ind.industry = q.industry if q.industry is not None else ind.industry
    if unit:
        ind.unit = unit
    if description:
        ind.description = description
    return ind


def _upsert_macro_observation(
    db: Session,
    *,
    indicator_id: str,
    value: float | None,
    value_text: str | None,
    observed_at: datetime,
    period_label: str,
    source_urls: list[str],
    raw: dict[str, Any],
) -> bool:
    period = (period_label or "").strip()[:64]
    content_hash = _hash_obs(
        indicator_id=indicator_id,
        observed_at=observed_at,
        period_label=period,
        value=value_text or (str(value) if value is not None else ""),
    )
    existing = None
    if period:
        existing = (
            db.query(MacroObservation)
            .filter(
                MacroObservation.indicator_id == indicator_id,
                MacroObservation.period_label == period,
            )
            .one_or_none()
        )
    if existing is None:
        existing = (
            db.query(MacroObservation)
            .filter(
                MacroObservation.indicator_id == indicator_id,
                MacroObservation.observed_at == observed_at,
                MacroObservation.period_label == period,
            )
            .one_or_none()
        )
    if existing:
        existing.observed_at = observed_at
        existing.value = _to_decimal(value)
        existing.value_text = value_text
        existing.source_urls = source_urls[:8]
        existing.content_hash = content_hash
        existing.raw = raw
        return False
    db.add(
        MacroObservation(
            id=str(uuid4()),
            indicator_id=indicator_id,
            observed_at=observed_at,
            value=_to_decimal(value),
            value_text=value_text,
            period_label=period,
            source_urls=source_urls[:8],
            content_hash=content_hash,
            raw=raw,
        )
    )
    return True


def _run_event_query(db: Session, provider: Any, q: InsightQuery) -> dict[str, Any]:
    t0 = time.perf_counter()
    out = provider.retrieve_events(
        RetrieveEventsIn(
            query_id=q.id,
            query=q.query,
            dimension=q.dimension or "global",
            industry=q.industry,
            entity=q.entity,
        )
    )
    inserted = 0
    for ev in out.events:
        title = (ev.title or "").strip()
        if not title:
            continue
        if _upsert_event(
            db,
            q=q,
            title=title,
            summary=(ev.summary or "").strip(),
            occurred_at=_parse_dt(ev.occurred_at),
            industry=ev.industry,
            entity=ev.entity,
            source_urls=list(ev.source_urls or []),
            raw=ev.model_dump(),
        ):
            inserted += 1
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "insight_event_query id=%s hits=%s inserted=%s elapsed_ms=%s provider=%s",
        q.id,
        len(out.events),
        inserted,
        elapsed_ms,
        (out.model_meta or {}).get("provider"),
    )
    return {
        "query_id": q.id,
        "kind": "event",
        "hits": len(out.events),
        "inserted": inserted,
        "elapsed_ms": elapsed_ms,
        "model_meta": out.model_meta,
    }


def _run_macro_query(db: Session, provider: Any, q: InsightQuery) -> dict[str, Any]:
    t0 = time.perf_counter()
    out = provider.retrieve_macro(
        RetrieveMacroIn(
            query_id=q.id,
            query=q.query,
            scope=q.scope or "global",
            indicator_id=q.indicator_id or "",
            label=q.label or "",
            unit=q.unit or "",
            industry=q.industry,
        )
    )
    _ensure_indicator(
        db,
        q=q,
        label=out.label or q.label or q.indicator_id or "",
        unit=out.unit if out.unit is not None else (q.unit or ""),
        description=out.description or q.description,
    )
    # 同一 period_label 只保留一条（模型常返回同月多口径）
    by_period: dict[str, Any] = {}
    no_period: list[Any] = []
    for obs in out.observations:
        period = (obs.period_label or "").strip()
        if period:
            by_period[period] = obs
        else:
            no_period.append(obs)
    deduped = list(by_period.values()) + no_period

    inserted = 0
    for obs in deduped:
        if _upsert_macro_observation(
            db,
            indicator_id=q.indicator_id or "",
            value=obs.value,
            value_text=obs.value_text,
            observed_at=_parse_dt(obs.observed_at),
            period_label=obs.period_label or "",
            source_urls=list(obs.source_urls or []),
            raw=obs.model_dump(),
        ):
            inserted += 1
        db.flush()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    logger.info(
        "insight_macro_query id=%s hits=%s inserted=%s elapsed_ms=%s provider=%s",
        q.id,
        len(out.observations),
        inserted,
        elapsed_ms,
        (out.model_meta or {}).get("provider"),
    )
    return {
        "query_id": q.id,
        "kind": "macro",
        "hits": len(out.observations),
        "inserted": inserted,
        "elapsed_ms": elapsed_ms,
        "model_meta": out.model_meta,
    }


def run_insight_retrieve(
    db: Session,
    *,
    kind: Literal["event", "macro", "all"] = "all",
    force: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    """执行检索入库。force=True 忽略 refresh_interval。"""
    run_id = run_id or str(uuid4())
    provider = create_provider()
    kinds: list[QueryKind] | list[None]
    if kind == "all":
        queries = load_queries(enabled_only=True)
    else:
        queries = load_queries(kind=kind, enabled_only=True)

    cursors = _load_cursors(db)
    results: list[dict[str, Any]] = []
    skipped = 0
    errors = 0

    logger.info(
        "insight_retrieve_start run_id=%s kind=%s force=%s queries=%s provider=%s",
        run_id,
        kind,
        force,
        len(queries),
        getattr(provider, "name", "?"),
    )

    for q in queries:
        cursor = cursors.get(q.id) if isinstance(cursors.get(q.id), dict) else None
        if not force and not source_is_due(refresh_interval=q.refresh_interval, cursor=cursor):
            skipped += 1
            logger.info("insight_query_skip id=%s reason=not_due interval=%s", q.id, q.refresh_interval)
            continue
        try:
            if q.kind == "event":
                stat = _run_event_query(db, provider, q)
            else:
                stat = _run_macro_query(db, provider, q)
            results.append(stat)
            cursors[q.id] = stamp_last_fetched(cursor)
            _save_cursors(db, cursors)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.exception("insight_query_fail id=%s err=%s", q.id, exc)
            results.append({"query_id": q.id, "kind": q.kind, "error": str(exc)[:300]})
            db.rollback()
            cursors = _load_cursors(db)

    inserted = sum(int(r.get("inserted") or 0) for r in results)
    hits = sum(int(r.get("hits") or 0) for r in results)
    summary = {
        "pipeline_id": "insight",
        "run_id": run_id,
        "kind": kind,
        "force": force,
        "provider": getattr(provider, "name", None),
        "queries_total": len(queries),
        "queries_run": len(results),
        "queries_skipped": skipped,
        "errors": errors,
        "hits": hits,
        "inserted": inserted,
        "results": results,
    }
    logger.info(
        "insight_retrieve_done run_id=%s run=%s skipped=%s errors=%s hits=%s inserted=%s",
        run_id,
        summary["queries_run"],
        skipped,
        errors,
        hits,
        inserted,
    )
    return summary

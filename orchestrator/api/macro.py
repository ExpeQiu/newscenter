"""宏观 / 行业数据 API。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import MacroIndicator, MacroObservation

router = APIRouter(tags=["macro"])


def _indicator_dict(row: MacroIndicator) -> dict[str, Any]:
    return {
        "indicator_id": row.indicator_id,
        "label": row.label,
        "scope": row.scope,
        "industry": row.industry,
        "unit": row.unit,
        "description": row.description,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _obs_dict(row: MacroObservation) -> dict[str, Any]:
    return {
        "id": row.id,
        "indicator_id": row.indicator_id,
        "observed_at": row.observed_at.isoformat() if row.observed_at else None,
        "value": float(row.value) if row.value is not None else None,
        "value_text": row.value_text,
        "period_label": row.period_label,
        "source_urls": row.source_urls or [],
    }


@router.get("/macro/indicators")
def list_indicators(
    db: Session = Depends(get_db),
    scope: Optional[str] = None,
    industry: Optional[str] = None,
) -> dict[str, Any]:
    q = db.query(MacroIndicator)
    if scope:
        q = q.filter(MacroIndicator.scope == scope.strip().lower())
    if industry:
        q = q.filter(MacroIndicator.industry == industry.strip())
    rows = q.order_by(MacroIndicator.scope, MacroIndicator.label).all()
    return {"indicators": [_indicator_dict(r) for r in rows], "count": len(rows)}


@router.get("/macro/observations")
def list_observations(
    db: Session = Depends(get_db),
    indicator_id: str = Query(...),
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(60, ge=1, le=200),
) -> dict[str, Any]:
    q = db.query(MacroObservation).filter(MacroObservation.indicator_id == indicator_id)
    if from_ts:
        q = q.filter(MacroObservation.observed_at >= from_ts)
    if to_ts:
        q = q.filter(MacroObservation.observed_at <= to_ts)
    rows = q.order_by(MacroObservation.observed_at.desc()).limit(limit).all()
    return {"observations": [_obs_dict(r) for r in rows], "count": len(rows)}


@router.get("/macro/snapshot")
def macro_snapshot(
    db: Session = Depends(get_db),
    scope: Optional[str] = None,
    industry: Optional[str] = None,
) -> dict[str, Any]:
    """各指标最新观测，供数据页首屏。"""
    q = db.query(MacroIndicator)
    if scope:
        q = q.filter(MacroIndicator.scope == scope.strip().lower())
    if industry:
        q = q.filter(MacroIndicator.industry == industry.strip())
    indicators = q.order_by(MacroIndicator.scope, MacroIndicator.label).all()
    items: list[dict[str, Any]] = []
    for ind in indicators:
        latest = (
            db.query(MacroObservation)
            .filter(MacroObservation.indicator_id == ind.indicator_id)
            .order_by(desc(MacroObservation.observed_at))
            .first()
        )
        hist = (
            db.query(MacroObservation)
            .filter(MacroObservation.indicator_id == ind.indicator_id)
            .order_by(desc(MacroObservation.observed_at))
            .limit(12)
            .all()
        )
        items.append(
            {
                **_indicator_dict(ind),
                "latest": _obs_dict(latest) if latest else None,
                "history": [_obs_dict(h) for h in reversed(hist)],
            }
        )
    return {"items": items, "count": len(items)}

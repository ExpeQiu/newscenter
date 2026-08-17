"""事件时间轴 API。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import InsightEvent

router = APIRouter(tags=["events"])


def _event_dict(row: InsightEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "dimension": row.dimension,
        "industry": row.industry,
        "entity": row.entity,
        "title": row.title,
        "summary": row.summary,
        "source_urls": row.source_urls or [],
        "query_id": row.query_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/events")
def list_events(
    db: Session = Depends(get_db),
    dimension: Optional[str] = None,
    industry: Optional[str] = None,
    entity: Optional[str] = None,
    from_ts: Optional[datetime] = Query(None, alias="from"),
    to_ts: Optional[datetime] = Query(None, alias="to"),
    limit: int = Query(80, ge=1, le=200),
) -> dict[str, Any]:
    q = db.query(InsightEvent)
    if dimension:
        q = q.filter(InsightEvent.dimension == dimension.strip().lower())
    if industry:
        q = q.filter(InsightEvent.industry == industry.strip())
    if entity:
        q = q.filter(InsightEvent.entity == entity.strip())
    if from_ts:
        q = q.filter(InsightEvent.occurred_at >= from_ts)
    if to_ts:
        q = q.filter(InsightEvent.occurred_at <= to_ts)
    rows = q.order_by(InsightEvent.occurred_at.desc()).limit(limit).all()
    return {"events": [_event_dict(r) for r in rows], "count": len(rows)}


@router.get("/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    row = db.get(InsightEvent, event_id)
    if not row:
        raise HTTPException(404, "event not found")
    return _event_dict(row)

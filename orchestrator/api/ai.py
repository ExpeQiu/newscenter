"""AI process / ask endpoints."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from intelligence.worker import (
    ask as ai_ask,
    enqueue_digest_and_recommend,
    process_item,
    process_pending,
)
from orchestrator.api.helpers import item_dict
from pipeline.db import get_db
from pipeline.models import Item

logger = logging.getLogger("newsc.orchestrator")
router = APIRouter(tags=["ai"])


class ProcessBody(BaseModel):
    limit: int = 20
    include_digest: bool = True


@router.post("/ai/jobs/process")
def ai_process(body: ProcessBody = ProcessBody(), db: Session = Depends(get_db)) -> dict[str, Any]:
    enqueued: list[str] = []
    if body.include_digest:
        enqueued = enqueue_digest_and_recommend(db)
    result = process_pending(db, limit=body.limit)
    result["enqueued_digest_jobs"] = enqueued
    logger.info(
        "ai_process provider=%s processed=%s degraded=%s failed=%s enqueued=%s",
        result.get("provider"),
        result.get("processed"),
        result.get("degraded"),
        result.get("failed"),
        len(enqueued),
    )
    return result


class ItemProcessBody(BaseModel):
    force: bool = False


@router.post("/ai/items/{item_id}/process")
def ai_process_item(
    item_id: str,
    body: ItemProcessBody = ItemProcessBody(),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """为单条条目入队并处理 summarize / classify，写回摘要与分类。"""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    try:
        result = process_item(db, item_id, force=body.force)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    db.refresh(item)
    logger.info(
        "ai_process_item item_id=%s provider=%s processed=%s failed=%s force=%s has_summary=%s",
        item_id,
        result.get("provider"),
        result.get("processed"),
        result.get("failed"),
        body.force,
        bool((item.summary or "").strip()),
    )
    return {
        **result,
        "item": item_dict(item, db),
    }


class AskBody(BaseModel):
    question: str
    item_id: Optional[str] = None


@router.post("/ai/ask")
def ask_endpoint(body: AskBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(400, "question required")
    return ai_ask(db, item_id=body.item_id, question=body.question.strip())

"""HTTP ingest batch endpoint."""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.ingest import upsert_items
from pipeline.normalize import CollectItem

logger = logging.getLogger("newsc.orchestrator")
router = APIRouter(tags=["ingest"])


class IngestItemBody(BaseModel):
    source: str
    title: str = ""
    content: str = ""
    url: Optional[str] = None
    published_at: Optional[str] = None
    embed_provider: Optional[str] = None
    embed_id: Optional[str] = None
    embed_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    content_type: Optional[str] = None
    raw: dict[str, Any] = Field(default_factory=dict)


class IngestBatchBody(BaseModel):
    items: list[IngestItemBody] = Field(default_factory=list)
    source_name: Optional[str] = None
    run_id: Optional[str] = None
    enqueue_ai: bool = True


def collect_item_from_body(body: IngestItemBody) -> CollectItem:
    published = None
    if body.published_at:
        try:
            from datetime import datetime

            published = datetime.fromisoformat(body.published_at.replace("Z", "+00:00"))
        except ValueError:
            published = None
    return CollectItem(
        source=body.source,
        title=body.title,
        content=body.content,
        url=body.url,
        published_at=published,
        embed_provider=body.embed_provider,
        embed_id=body.embed_id,
        embed_url=body.embed_url,
        thumbnail_url=body.thumbnail_url,
        content_type=body.content_type,
        raw=body.raw or {},
    )


@router.post("/ingest/batch")
def ingest_batch(body: IngestBatchBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    run_id = body.run_id or str(uuid4())
    items = [collect_item_from_body(it) for it in body.items]
    logger.info(
        "ingest_batch start run_id=%s count=%s source_name=%s",
        run_id,
        len(items),
        body.source_name,
    )
    stats = upsert_items(
        db,
        items,
        run_id=run_id,
        source_name=body.source_name,
        enqueue_ai=body.enqueue_ai,
    )
    logger.info(
        "ingest_batch done run_id=%s inserted=%s skipped=%s",
        stats.get("run_id"),
        stats.get("inserted"),
        stats.get("skipped"),
    )
    return stats

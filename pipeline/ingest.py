"""Ingest CollectItems into PG with hash dedup and ai_jobs enqueue."""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from pipeline.models import AiJob, Item, PipelineRun, Source
from pipeline.normalize import CollectItem, content_hash, infer_content_type

logger = logging.getLogger("newsc.pipeline.ingest")


def ensure_source(db: Session, name: str, source_type: str, config: dict[str, Any] | None = None) -> Source:
    src = db.query(Source).filter(Source.name == name, Source.type == source_type).first()
    if src:
        return src
    src = Source(name=name, type=source_type, config=config or {})
    db.add(src)
    db.flush()
    return src


def upsert_items(
    db: Session,
    items: list[CollectItem],
    *,
    run_id: str | None = None,
    source_name: str | None = None,
    enqueue_ai: bool = True,
) -> dict[str, Any]:
    run_id = run_id or str(uuid4())
    inserted = 0
    skipped = 0
    source_obj: Source | None = None
    if source_name and items:
        source_obj = ensure_source(db, source_name, items[0].source)

    for it in items:
        h = content_hash(it)
        existing = db.query(Item).filter(Item.content_hash == h).first()
        if existing:
            skipped += 1
            logger.info(
                "skip_dup",
                extra={"run_id": run_id, "content_hash": h, "source": it.source},
            )
            continue
        row = Item(
            source_id=source_obj.id if source_obj else None,
            source_type=it.source,
            content_type=infer_content_type(it),
            url=it.url,
            title=it.title,
            body=it.content,
            content_hash=h,
            embed_provider=it.embed_provider,
            embed_id=it.embed_id,
            embed_url=it.embed_url,
            thumbnail_url=it.thumbnail_url,
            published_at=it.published_at,
            raw=it.raw,
        )
        db.add(row)
        db.flush()
        inserted += 1
        logger.info(
            "item_inserted",
            extra={"run_id": run_id, "content_hash": h, "item_id": row.id, "source": it.source},
        )
        if enqueue_ai:
            for job_type in ("summarize", "classify"):
                db.add(
                    AiJob(
                        job_type=job_type,
                        payload={"item_id": row.id},
                        status="pending",
                        run_id=run_id,
                    )
                )

    stats = {"inserted": inserted, "skipped": skipped, "total": len(items)}
    db.add(
        PipelineRun(
            run_id=run_id,
            pipeline_id="ingest",
            source=source_name or (items[0].source if items else None),
            stats=stats,
            status="ok",
        )
    )
    db.commit()
    return {"run_id": run_id, **stats}

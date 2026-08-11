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


def purge_source_items(db: Session, source_id: str) -> int:
    """删除某源下全部条目及相关 ai_jobs（marks/tags/recs 靠 FK CASCADE）。"""
    ids = [row[0] for row in db.query(Item.id).filter(Item.source_id == source_id).all()]
    if not ids:
        return 0
    # ai_jobs.payload.item_id 无 FK，需显式清理
    for iid in ids:
        db.query(AiJob).filter(AiJob.payload["item_id"].astext == iid).delete(
            synchronize_session=False
        )
    deleted = db.query(Item).filter(Item.source_id == source_id).delete(synchronize_session=False)
    logger.info("purge_source_items source_id=%s deleted=%s", source_id, deleted)
    return int(deleted or 0)


def upsert_items(
    db: Session,
    items: list[CollectItem],
    *,
    run_id: str | None = None,
    source_name: str | None = None,
    source_id: str | None = None,
    enqueue_ai: bool = True,
) -> dict[str, Any]:
    run_id = run_id or str(uuid4())
    inserted = 0
    skipped = 0
    source_obj: Source | None = None
    if source_id:
        source_obj = db.query(Source).filter(Source.id == source_id).first()
    elif source_name and items:
        source_obj = ensure_source(db, source_name, items[0].source)

    for it in items:
        h = content_hash(it)
        existing = db.query(Item).filter(Item.content_hash == h).first()
        if existing:
            # 去重跳过入库，但刷新展示用 meta（播放量/封面/发布时间）
            refreshed = False
            if it.raw:
                merged = {**(existing.raw or {}), **it.raw}
                if merged != (existing.raw or {}):
                    existing.raw = merged
                    refreshed = True
            if it.published_at and existing.published_at != it.published_at:
                existing.published_at = it.published_at
                refreshed = True
            if it.thumbnail_url and existing.thumbnail_url != it.thumbnail_url:
                existing.thumbnail_url = it.thumbnail_url
                refreshed = True
            skipped += 1
            logger.info(
                "skip_dup",
                extra={
                    "run_id": run_id,
                    "content_hash": h,
                    "source": it.source,
                    "meta_refreshed": refreshed,
                },
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

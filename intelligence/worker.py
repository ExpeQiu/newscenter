"""AI job worker — pull ai_jobs, call provider, write back to PG."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from intelligence.contracts import (
    AskIn,
    ClassifyIn,
    DigestIn,
    ItemRef,
    RecommendIn,
    SummarizeIn,
)
from intelligence.factory import create_provider
from intelligence.logging import get_logger, log_event
from pipeline.models import AiJob, Digest, Item, ItemTag, Mark, Recommendation, Tag

logger = get_logger()


def _item_ref(item: Item) -> ItemRef:
    return ItemRef(
        id=item.id,
        title=item.title or "",
        body=item.body or "",
        summary=item.summary,
        url=item.url,
        source_type=item.source_type or "rss",
        ai_category=item.ai_category,
        category_locked=bool(item.category_locked),
    )


def _ensure_tags(db: Session, item: Item, tag_names: list[str], origin: str = "ai") -> None:
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        exists = (
            db.query(ItemTag)
            .filter(ItemTag.item_id == item.id, ItemTag.tag_id == tag.id)
            .first()
        )
        if not exists:
            db.add(ItemTag(item_id=item.id, tag_id=tag.id, origin=origin))


def process_job(db: Session, job: AiJob, provider=None) -> dict[str, Any]:
    provider = provider or create_provider()
    job.status = "running"
    job.attempts = (job.attempts or 0) + 1
    job.run_id = job.run_id or str(uuid4())
    db.commit()

    log_event(
        logger,
        "job_start",
        job_id=job.id,
        job_type=job.job_type,
        run_id=job.run_id,
        provider=provider.name,
    )

    try:
        if job.job_type == "summarize":
            item_id = job.payload.get("item_id")
            item = db.query(Item).filter(Item.id == item_id).first()
            if not item:
                raise ValueError(f"item not found: {item_id}")
            out = provider.summarize(SummarizeIn(item=_item_ref(item)))
            item.summary = out.summary
            result = out.model_dump()

        elif job.job_type == "classify":
            item_id = job.payload.get("item_id")
            item = db.query(Item).filter(Item.id == item_id).first()
            if not item:
                raise ValueError(f"item not found: {item_id}")
            out = provider.classify(ClassifyIn(item=_item_ref(item)))
            if not out.skipped:
                item.ai_category = out.category
                _ensure_tags(db, item, out.tags, origin="ai")
            result = out.model_dump()

        elif job.job_type == "digest":
            d = date.fromisoformat(job.payload.get("date") or date.today().isoformat())
            items = (
                db.query(Item)
                .order_by(Item.fetched_at.desc())
                .limit(int(job.payload.get("limit") or 30))
                .all()
            )
            out = provider.digest(DigestIn(digest_date=d, items=[_item_ref(i) for i in items]))
            row = db.query(Digest).filter(Digest.digest_date == d).first()
            if row:
                row.markdown = out.markdown
                row.highlights = out.highlights
                row.run_id = job.run_id
                row.source = "intelligence"
            else:
                db.add(
                    Digest(
                        digest_date=d,
                        markdown=out.markdown,
                        highlights=out.highlights,
                        source="intelligence",
                        run_id=job.run_id,
                    )
                )
            result = out.model_dump()

        elif job.job_type == "recommend":
            d = date.fromisoformat(job.payload.get("date") or date.today().isoformat())
            starred_cats: list[str] = []
            for m in db.query(Mark).filter(Mark.is_starred.is_(True)).all():
                it = db.query(Item).filter(Item.id == m.item_id).first()
                if it and it.ai_category:
                    starred_cats.append(it.ai_category)
            candidates = db.query(Item).order_by(Item.fetched_at.desc()).limit(40).all()
            out = provider.recommend(
                RecommendIn(
                    user_signals={"starred_categories": list(set(starred_cats))},
                    candidates=[_item_ref(i) for i in candidates],
                    as_of=d,
                )
            )
            db.query(Recommendation).filter(Recommendation.as_of == d).delete()
            for rec in out.items:
                db.add(
                    Recommendation(
                        item_id=rec.id,
                        score=rec.score,
                        reason=rec.reason,
                        as_of=d,
                    )
                )
            result = out.model_dump()

        else:
            raise ValueError(f"unknown job_type: {job.job_type}")

        job.status = "done"
        job.error = None
        db.commit()
        log_event(logger, "job_done", job_id=job.id, job_type=job.job_type, run_id=job.run_id)
        return {"job_id": job.id, "status": "done", "result": result}

    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error = str(exc)
        db.commit()
        log_event(logger, "job_failed", job_id=job.id, error=str(exc))
        return {"job_id": job.id, "status": "failed", "error": str(exc)}


def process_pending(db: Session, *, limit: int = 20, job_types: list[str] | None = None) -> dict[str, Any]:
    provider = create_provider()
    q = db.query(AiJob).filter(AiJob.status == "pending").order_by(AiJob.created_at.asc())
    if job_types:
        q = q.filter(AiJob.job_type.in_(job_types))
    jobs = q.limit(limit).all()
    results = [process_job(db, job, provider=provider) for job in jobs]
    return {
        "provider": provider.name,
        "processed": len(results),
        "results": results,
    }


def ask(db: Session, *, item_id: str | None, question: str) -> dict[str, Any]:
    provider = create_provider()
    context: dict[str, Any] = {}
    if item_id:
        item = db.query(Item).filter(Item.id == item_id).first()
        if item:
            context = {
                "item_id": item.id,
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "category": item.ai_category,
            }
    out = provider.ask(AskIn(context=context, question=question))
    log_event(logger, "ask", provider=provider.name, item_id=item_id)
    return out.model_dump()


def enqueue_digest_and_recommend(db: Session, *, day: date | None = None) -> list[str]:
    day = day or date.today()
    ids: list[str] = []
    for job_type in ("digest", "recommend"):
        job = AiJob(
            job_type=job_type,
            payload={"date": day.isoformat()},
            status="pending",
            run_id=str(uuid4()),
        )
        db.add(job)
        db.flush()
        ids.append(job.id)
    db.commit()
    return ids

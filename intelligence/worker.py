"""AI job worker — pull ai_jobs, call provider, write back to PG."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import or_
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
from intelligence.text_normalize import normalize_summary_text
from pipeline.models import AiJob, Digest, Item, ItemTag, Mark, Recommendation, Tag
from pipeline.settings import get_settings

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


def _result_degraded(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    meta = result.get("model_meta") or {}
    return bool(isinstance(meta, dict) and meta.get("fallback"))


def recover_stale_running(db: Session, *, older_than_sec: int | None = None) -> int:
    """将超时仍为 running 的 job 回收为 pending，避免崩溃僵尸。"""
    settings = get_settings()
    sec = older_than_sec if older_than_sec is not None else settings.ai_job_stale_running_sec
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(60, int(sec)))
    rows = (
        db.query(AiJob)
        .filter(AiJob.status == "running")
        .filter(or_(AiJob.updated_at < cutoff, AiJob.updated_at.is_(None)))
        .all()
    )
    for job in rows:
        job.status = "pending"
        job.error = (job.error or "") + f" | recovered_stale_running@{cutoff.isoformat()}"
        log_event(logger, "job_recovered", job_id=job.id, job_type=job.job_type)
    if rows:
        db.commit()
    return len(rows)


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
        attempt=job.attempts,
    )

    try:
        if job.job_type == "summarize":
            item_id = job.payload.get("item_id")
            item = db.query(Item).filter(Item.id == item_id).first()
            if not item:
                raise ValueError(f"item not found: {item_id}")
            out = provider.summarize(SummarizeIn(item=_item_ref(item)))
            item.summary = normalize_summary_text(out.summary)
            result = out.model_dump()
            result["summary"] = item.summary

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

        degraded = _result_degraded(result)
        if degraded and get_settings().ai_fallback_strict:
            raise RuntimeError("provider fallback under AI_FALLBACK_STRICT")

        job.status = "done"
        job.error = "degraded:fallback" if degraded else None
        db.commit()
        log_event(
            logger,
            "job_done",
            job_id=job.id,
            job_type=job.job_type,
            run_id=job.run_id,
            degraded=degraded,
        )
        return {"job_id": job.id, "status": "done", "degraded": degraded, "result": result}

    except Exception as exc:  # noqa: BLE001
        max_attempts = max(1, int(get_settings().ai_job_max_attempts))
        if (job.attempts or 0) < max_attempts:
            job.status = "pending"
            job.error = f"retryable:{exc}"
            status = "pending_retry"
        else:
            job.status = "failed"
            job.error = str(exc)
            status = "failed"
        db.commit()
        log_event(
            logger,
            "job_failed",
            job_id=job.id,
            error=str(exc),
            status=status,
            attempts=job.attempts,
        )
        return {"job_id": job.id, "status": status, "error": str(exc)}


def process_pending(db: Session, *, limit: int = 20, job_types: list[str] | None = None) -> dict[str, Any]:
    recovered = recover_stale_running(db)
    provider = create_provider()
    max_attempts = max(1, int(get_settings().ai_job_max_attempts))
    q = (
        db.query(AiJob)
        .filter(
            or_(
                AiJob.status == "pending",
                (AiJob.status == "failed") & (AiJob.attempts < max_attempts),
            )
        )
        .order_by(AiJob.created_at.asc())
    )
    if job_types:
        q = q.filter(AiJob.job_type.in_(job_types))
    jobs = q.limit(limit).all()
    # failed 入队再跑前先翻回 pending，便于日志一致
    for job in jobs:
        if job.status == "failed":
            job.status = "pending"
    if jobs:
        db.commit()

    results = [process_job(db, job, provider=provider) for job in jobs]
    degraded = sum(1 for r in results if r.get("degraded"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    return {
        "provider": provider.name,
        "processed": len(results),
        "recovered_stale": recovered,
        "degraded": degraded,
        "failed": failed,
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
    degraded = bool((out.model_meta or {}).get("fallback"))
    log_event(logger, "ask", provider=provider.name, item_id=item_id, degraded=degraded)
    payload = out.model_dump()
    payload["degraded"] = degraded
    return payload


def enqueue_digest_and_recommend(db: Session, *, day: date | None = None) -> list[str]:
    """同日同类型若已有 pending/running/done 则跳过，避免重复 enqueue。"""
    day = day or date.today()
    day_s = day.isoformat()
    ids: list[str] = []
    for job_type in ("digest", "recommend"):
        existing = (
            db.query(AiJob)
            .filter(AiJob.job_type == job_type)
            .filter(AiJob.status.in_(("pending", "running")))
            .filter(AiJob.payload["date"].astext == day_s)
            .order_by(AiJob.created_at.desc())
            .first()
        )
        if existing:
            log_event(
                logger,
                "job_enqueue_skip",
                job_type=job_type,
                date=day_s,
                existing_id=existing.id,
                status=existing.status,
            )
            continue
        job = AiJob(
            job_type=job_type,
            payload={"date": day_s},
            status="pending",
            run_id=str(uuid4()),
        )
        db.add(job)
        db.flush()
        ids.append(job.id)
        log_event(logger, "job_enqueued", job_id=job.id, job_type=job_type, date=day_s)
    db.commit()
    return ids


def _item_needs_job(item: Item, job_type: str, *, force: bool) -> bool:
    if force:
        return True
    if job_type == "summarize":
        return not (item.summary or "").strip()
    if job_type == "classify":
        return not (item.ai_category or "").strip()
    return False


def enqueue_item_jobs(
    db: Session,
    item: Item,
    *,
    force: bool = False,
    job_types: tuple[str, ...] = ("summarize", "classify"),
) -> list[str]:
    """为单条条目入队 summarize/classify；已有 pending/running 则复用。"""
    run_id = str(uuid4())
    ids: list[str] = []
    for job_type in job_types:
        active = (
            db.query(AiJob)
            .filter(AiJob.job_type == job_type)
            .filter(AiJob.payload["item_id"].astext == item.id)
            .filter(AiJob.status.in_(("pending", "running")))
            .order_by(AiJob.created_at.desc())
            .first()
        )
        if active:
            ids.append(active.id)
            log_event(
                logger,
                "job_enqueue_reuse",
                job_id=active.id,
                job_type=job_type,
                item_id=item.id,
                status=active.status,
            )
            continue

        if not _item_needs_job(item, job_type, force=force):
            log_event(
                logger,
                "job_enqueue_skip",
                job_type=job_type,
                item_id=item.id,
                reason="already_done",
            )
            continue

        # 失败任务未达上限则翻回 pending 重试，否则新建
        max_attempts = max(1, int(get_settings().ai_job_max_attempts))
        failed = (
            db.query(AiJob)
            .filter(AiJob.job_type == job_type)
            .filter(AiJob.payload["item_id"].astext == item.id)
            .filter(AiJob.status == "failed")
            .filter(AiJob.attempts < max_attempts)
            .order_by(AiJob.created_at.desc())
            .first()
        )
        if failed and not force:
            failed.status = "pending"
            failed.error = (failed.error or "") + " | requeued_item_ai"
            ids.append(failed.id)
            log_event(logger, "job_requeued", job_id=failed.id, job_type=job_type, item_id=item.id)
            continue

        job = AiJob(
            job_type=job_type,
            payload={"item_id": item.id},
            status="pending",
            run_id=run_id,
        )
        db.add(job)
        db.flush()
        ids.append(job.id)
        log_event(logger, "job_enqueued", job_id=job.id, job_type=job_type, item_id=item.id)
    if ids:
        db.commit()
    return ids


def process_item(
    db: Session,
    item_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """入队并立即处理该条目的 summarize/classify。"""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise ValueError(f"item not found: {item_id}")

    recovered = recover_stale_running(db)
    enqueued = enqueue_item_jobs(db, item, force=force)
    provider = create_provider()

    jobs = (
        db.query(AiJob)
        .filter(AiJob.payload["item_id"].astext == item_id)
        .filter(AiJob.job_type.in_(("summarize", "classify")))
        .filter(AiJob.status == "pending")
        .order_by(AiJob.created_at.asc())
        .all()
    )
    results = [process_job(db, job, provider=provider) for job in jobs]
    db.refresh(item)

    degraded = sum(1 for r in results if r.get("degraded"))
    failed = sum(1 for r in results if r.get("status") == "failed")
    log_event(
        logger,
        "item_ai_done",
        item_id=item_id,
        provider=provider.name,
        processed=len(results),
        enqueued=len(enqueued),
        force=force,
        degraded=degraded,
        failed=failed,
        has_summary=bool((item.summary or "").strip()),
    )
    return {
        "provider": provider.name,
        "item_id": item_id,
        "force": force,
        "enqueued": enqueued,
        "processed": len(results),
        "recovered_stale": recovered,
        "degraded": degraded,
        "failed": failed,
        "summary": item.summary,
        "ai_category": item.ai_category,
        "results": results,
    }
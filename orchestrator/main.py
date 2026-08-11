"""NewsC FastAPI orchestrator."""
from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence.factory import create_provider  # noqa: E402
from intelligence.providers.openclaw import gateway_reachable  # noqa: E402
from intelligence.worker import (  # noqa: E402
    ask as ai_ask,
    enqueue_digest_and_recommend,
    process_pending,
)
from pipeline.db import get_db, init_db  # noqa: E402
from pipeline.ingest import upsert_items  # noqa: E402
from pipeline.models import Digest, Item, ItemTag, Mark, Recommendation, Source, Tag  # noqa: E402
from pipeline.normalize import CollectItem  # noqa: E402
from pipeline.settings import get_settings  # noqa: E402

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("newsc.orchestrator")

app = FastAPI(title="NewsC Orchestrator", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("orchestrator_started provider=%s", get_settings().resolved_provider())


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    provider = settings.resolved_provider()
    gw_ok: bool | None = None
    if provider == "openclaw":
        gw_ok = gateway_reachable(settings.openclaw_gateway_url)
    return {
        "ok": True,
        "service": "newsc-orchestrator",
        "ai_provider": provider,
        "ai_mock_mode": settings.ai_mock_mode,
        "openclaw_reachable": gw_ok,
    }


def _item_dict(item: Item, db: Session) -> dict[str, Any]:
    mark = item.marks
    tags = []
    for it in item.item_tags:
        if it.tag:
            tags.append({"name": it.tag.name, "origin": it.origin})
    return {
        "id": item.id,
        "source_type": item.source_type,
        "url": item.url,
        "title": item.title,
        "body": item.body,
        "summary": item.summary,
        "content_hash": item.content_hash,
        "embed_provider": item.embed_provider,
        "embed_id": item.embed_id,
        "embed_url": item.embed_url,
        "thumbnail_url": item.thumbnail_url,
        "ai_category": item.ai_category,
        "category_locked": item.category_locked,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
        "marks": {
            "is_read": mark.is_read if mark else False,
            "is_starred": mark.is_starred if mark else False,
            "is_archived": mark.is_archived if mark else False,
            "note": mark.note if mark else None,
        },
        "tags": tags,
    }


@app.get("/items")
def list_items(
    db: Session = Depends(get_db),
    source_type: Optional[str] = None,
    category: Optional[str] = None,
    unread: Optional[bool] = None,
    starred: Optional[bool] = None,
    archived: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    q = db.query(Item).order_by(Item.fetched_at.desc())
    if source_type:
        q = q.filter(Item.source_type == source_type)
    if category:
        q = q.filter(Item.ai_category == category)
    items = q.offset(offset).limit(limit * 2).all()  # over-fetch then filter marks
    out = []
    for item in items:
        d = _item_dict(item, db)
        m = d["marks"]
        if unread is True and m["is_read"]:
            continue
        if unread is False and not m["is_read"]:
            continue
        if starred is True and not m["is_starred"]:
            continue
        if archived is True and not m["is_archived"]:
            continue
        if archived is False and m["is_archived"]:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return {"items": out, "count": len(out)}


@app.get("/items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    return _item_dict(item, db)


class MarksPatch(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None
    note: Optional[str] = None


@app.patch("/items/{item_id}/marks")
def patch_marks(item_id: str, body: MarksPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    mark = db.query(Mark).filter(Mark.item_id == item_id).first()
    if not mark:
        mark = Mark(item_id=item_id)
        db.add(mark)
    if body.is_read is not None:
        mark.is_read = body.is_read
    if body.is_starred is not None:
        mark.is_starred = body.is_starred
    if body.is_archived is not None:
        mark.is_archived = body.is_archived
    if body.note is not None:
        mark.note = body.note
    db.commit()
    db.refresh(item)
    return _item_dict(item, db)


class TagsPatch(BaseModel):
    tags: list[str] = Field(default_factory=list)
    origin: str = "user"


@app.patch("/items/{item_id}/tags")
def patch_tags(item_id: str, body: TagsPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    # replace user tags
    for it in list(item.item_tags):
        if it.origin == "user":
            db.delete(it)
    for name in body.tags:
        name = name.strip()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(ItemTag(item_id=item_id, tag_id=tag.id, origin=body.origin))
    db.commit()
    db.refresh(item)
    return _item_dict(item, db)


class CategoryPatch(BaseModel):
    category: str
    lock: bool = True


@app.patch("/items/{item_id}/category")
def patch_category(item_id: str, body: CategoryPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    item.ai_category = body.category
    item.category_locked = body.lock
    db.commit()
    db.refresh(item)
    return _item_dict(item, db)


@app.get("/digests/today")
def digest_today(db: Session = Depends(get_db)) -> dict[str, Any]:
    d = date.today()
    row = db.query(Digest).filter(Digest.digest_date == d).first()
    if not row:
        return {"date": d.isoformat(), "markdown": None, "highlights": [], "empty": True}
    return {
        "date": d.isoformat(),
        "markdown": row.markdown,
        "highlights": row.highlights or [],
        "empty": False,
    }


@app.get("/recommendations")
def recommendations(db: Session = Depends(get_db), limit: int = 7) -> dict[str, Any]:
    d = date.today()
    rows = (
        db.query(Recommendation)
        .filter(Recommendation.as_of == d)
        .order_by(Recommendation.score.desc())
        .limit(limit)
        .all()
    )
    items = []
    for r in rows:
        item = db.query(Item).filter(Item.id == r.item_id).first()
        if not item:
            continue
        items.append(
            {
                "score": r.score,
                "reason": r.reason,
                "item": _item_dict(item, db),
            }
        )
    return {"as_of": d.isoformat(), "items": items}


@app.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(Source).order_by(Source.created_at.desc()).all()
    return {
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "enabled": s.enabled,
                "config": s.config,
            }
            for s in rows
        ]
    }


class SourceToggle(BaseModel):
    enabled: bool


@app.patch("/sources/{source_id}")
def toggle_source(source_id: str, body: SourceToggle, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "source not found")
    s.enabled = body.enabled
    db.commit()
    return {"id": s.id, "enabled": s.enabled}


@app.post("/pipelines/{pipeline_id}/run")
def run_pipeline(pipeline_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run_id = str(uuid4())
    logger.info("pipeline_run id=%s run_id=%s", pipeline_id, run_id)

    if pipeline_id in ("ingest", "rss"):
        from rss_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-rss", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "youtube":
        from youtube_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-youtube", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "bilibili":
        from bilibili_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-bilibili", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "all-demo":
        from bilibili_cli.collector import collect_demo as bili_demo
        from rss_cli.collector import collect_demo as rss_demo
        from youtube_cli.collector import collect_demo as yt_demo

        total = {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id}
        for name, fn in (("demo-rss", rss_demo), ("demo-youtube", yt_demo), ("demo-bilibili", bili_demo)):
            stats = upsert_items(db, fn(), run_id=run_id, source_name=name, enqueue_ai=True)
            total["inserted"] += stats["inserted"]
            total["skipped"] += stats["skipped"]
            total["total"] += stats["total"]
        return {"pipeline_id": pipeline_id, **total}

    raise HTTPException(404, f"unknown pipeline: {pipeline_id}")


class ProcessBody(BaseModel):
    limit: int = 20
    include_digest: bool = True


@app.post("/ai/jobs/process")
def ai_process(body: ProcessBody = ProcessBody(), db: Session = Depends(get_db)) -> dict[str, Any]:
    if body.include_digest:
        enqueue_digest_and_recommend(db)
    result = process_pending(db, limit=body.limit)
    logger.info("ai_process provider=%s processed=%s", result.get("provider"), result.get("processed"))
    return result


class AskBody(BaseModel):
    question: str
    item_id: Optional[str] = None


@app.post("/ai/ask")
def ask_endpoint(body: AskBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    if not body.question.strip():
        raise HTTPException(400, "question required")
    return ai_ask(db, item_id=body.item_id, question=body.question.strip())


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "orchestrator.main:app",
        host=s.orch_host,
        port=s.orch_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

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
from fastapi.responses import HTMLResponse
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
from pipeline.digest_sanitize import (  # noqa: E402
    sanitize_digest_html,
    sanitize_digest_html_document,
)
from pipeline.digest_vault import (  # noqa: E402
    DigestVaultError,
    delete_source as vault_delete_source,
    fmt_mtime,
    list_html_files,
    read_html_file,
    set_source_enabled as vault_set_enabled,
    upsert_source as vault_upsert_source,
    vault_status,
)
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
        "content_type": getattr(item, "content_type", None) or "news",
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
    content_type: Optional[str] = None,
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
    if content_type:
        q = q.filter(Item.content_type == content_type)
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


ALLOWED_DIGEST_SOURCES = frozenset({"openclaw", "hermes", "cli", "intelligence", "demo"})


class DigestPushBody(BaseModel):
    digest_date: Optional[date] = None
    html: str = ""
    markdown: str = ""
    highlights: list[str] = Field(default_factory=list)
    source: str = "cli"
    run_id: Optional[str] = None


def _raise_vault(exc: DigestVaultError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/digests/vault/status")
def digests_vault_status() -> dict[str, Any]:
    return vault_status()


@app.get("/digests/vault/files")
def digests_vault_files(
    source: Optional[str] = Query(None, description="来源 id；空=全部"),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="文件名/路径关键词"),
) -> dict[str, Any]:
    try:
        entries = list_html_files(source, limit=limit, q=q)
    except DigestVaultError as exc:
        _raise_vault(exc)
        return {"files": [], "count": 0}
    files = [
        {
            "source_id": e.source_id,
            "source_label": e.source_label,
            "name": e.name,
            "path": e.path,
            "mtime": fmt_mtime(e.mtime),
            "size": e.size,
        }
        for e in entries
    ]
    return {"files": files, "count": len(files)}


@app.get("/digests/vault/file")
def digests_vault_file(
    source: str = Query(..., min_length=1, description="来源 id"),
    path: str = Query(..., min_length=1, description="相对来源目录的文件路径"),
) -> dict[str, Any]:
    try:
        f = read_html_file(source, path)
    except DigestVaultError as exc:
        _raise_vault(exc)
        raise
    # 完整文档预览：保留 style（iframe 沙箱禁脚本）
    html = sanitize_digest_html_document(f.content)
    return {
        "source_id": f.source_id,
        "source_label": f.source_label,
        "name": f.name,
        "path": f.path,
        "mtime": fmt_mtime(f.mtime),
        "size": f.size,
        "html": html,
    }


@app.get("/digests/vault/raw", response_class=HTMLResponse)
def digests_vault_raw(
    source: str = Query(..., min_length=1, description="来源 id"),
    path: str = Query(..., min_length=1, description="相对来源目录的文件路径"),
) -> HTMLResponse:
    """按 text/html 返回完整日报，供 iframe src 直接渲染。"""
    try:
        f = read_html_file(source, path)
    except DigestVaultError as exc:
        _raise_vault(exc)
        raise
    html = sanitize_digest_html_document(f.content)
    logger.info(
        "digest_vault raw source=%s path=%s bytes=%d",
        f.source_id,
        f.path,
        len(html.encode("utf-8")),
    )
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@app.get("/digests/today")
def digest_today(db: Session = Depends(get_db)) -> dict[str, Any]:
    """今日洞察：DB markdown（AI）+ vault 最新 HTML（若有）。"""
    d = date.today()
    row = db.query(Digest).filter(Digest.digest_date == d).first()
    md = ((row.markdown or "").strip() or None) if row else None
    highlights = (row.highlights or []) if row else []
    db_html = ((row.html or "").strip() or None) if row else None
    db_source = row.source if row else None
    db_run = row.run_id if row else None

    vault_html = None
    vault_meta: dict[str, Any] = {}
    try:
        latest = list_html_files(limit=1)
        if latest:
            f = read_html_file(latest[0].source_id, latest[0].path)
            vault_html = sanitize_digest_html_document(f.content)
            vault_meta = {
                "source": f.source_id,
                "source_label": f.source_label,
                "path": f.path,
                "mtime": fmt_mtime(f.mtime),
            }
    except DigestVaultError as exc:
        logger.warning("digest_today vault skip: %s", exc)

    html = vault_html or db_html
    source = vault_meta.get("source") or db_source
    return {
        "date": d.isoformat(),
        "markdown": md,
        "html": html,
        "highlights": highlights,
        "source": source,
        "run_id": db_run,
        "vault": vault_meta or None,
        "empty": not (html or md),
    }


@app.post("/digests/push")
def digest_push(body: DigestPushBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """兼容旧 CLI 推送；主路径已改为 vault 直读 HTML。"""
    html_raw = (body.html or "").strip()
    markdown = (body.markdown or "").strip()
    if not html_raw and not markdown:
        raise HTTPException(400, "html or markdown required")

    source = (body.source or "cli").strip().lower()
    if source not in ALLOWED_DIGEST_SOURCES:
        raise HTTPException(400, f"invalid source: {source}")

    d = body.digest_date or date.today()
    run_id = body.run_id or str(uuid4())
    html = sanitize_digest_html(html_raw) if html_raw else ""

    row = db.query(Digest).filter(Digest.digest_date == d).first()
    created = False
    if row:
        if html:
            row.html = html
        if markdown:
            row.markdown = markdown
        if body.highlights:
            row.highlights = body.highlights
        row.source = source
        row.run_id = run_id
    else:
        created = True
        row = Digest(
            digest_date=d,
            html=html,
            markdown=markdown,
            highlights=body.highlights or [],
            source=source,
            run_id=run_id,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    html_bytes = len((row.html or "").encode("utf-8"))
    logger.info(
        "digest_push ok date=%s source=%s run_id=%s bytes=%s created=%s",
        d.isoformat(),
        source,
        run_id,
        html_bytes,
        created,
    )
    return {
        "ok": True,
        "digest_date": d.isoformat(),
        "id": row.id,
        "source": source,
        "run_id": run_id,
        "bytes": html_bytes,
        "created": created,
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
                "config": s.config or {},
            }
            for s in rows
        ]
    }


ALLOWED_SOURCE_TYPES = frozenset({"web", "rss", "social", "bilibili", "youtube"})
ALLOWED_SOCIAL_PLATFORMS = frozenset({"weibo", "x", "xiaohongshu", "other"})


def _source_dict(row: Source) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "enabled": row.enabled,
        "config": row.config or {},
    }


def _normalize_source_config(stype: str, config: dict[str, Any] | None, *, require: bool) -> dict[str, Any]:
    """按类型规范化 config；require=True 时校验必填字段。"""
    cfg = dict(config or {})
    if stype in ("web", "rss"):
        url = str(cfg.get("url") or "").strip()
        if require and not url:
            raise HTTPException(400, "config.url required")
        return {"url": url} if url else {}
    if stype == "social":
        platform = str(cfg.get("platform") or "other").strip().lower() or "other"
        if platform not in ALLOWED_SOCIAL_PLATFORMS:
            platform = "other"
        handle = str(cfg.get("handle") or "").strip().lstrip("@")
        if require and not handle:
            raise HTTPException(400, "config.handle required")
        out: dict[str, Any] = {"platform": platform}
        if handle:
            out["handle"] = handle
        return out if handle or not require else {}
    if stype in ("bilibili", "youtube"):
        account = str(cfg.get("account") or "").strip()
        if require and not account:
            raise HTTPException(400, "config.account required")
        return {"account": account} if account else {}
    return cfg


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    config: Optional[dict[str, Any]] = None


@app.post("/sources")
def create_source(body: SourceCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    stype = body.type.strip().lower()
    if stype not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(400, f"unsupported type: {stype}")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    existing = db.query(Source).filter(Source.name == name, Source.type == stype).first()
    if existing:
        raise HTTPException(409, "source already exists")
    config = _normalize_source_config(stype, body.config, require=True)
    row = Source(name=name, type=stype, config=config, enabled=body.enabled)
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("source_create id=%s type=%s name=%s", row.id, row.type, row.name)
    return _source_dict(row)


@app.patch("/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "source not found")
    if body.enabled is None and body.name is None and body.config is None:
        raise HTTPException(400, "nothing to update")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name required")
        clash = (
            db.query(Source)
            .filter(Source.name == name, Source.type == s.type, Source.id != s.id)
            .first()
        )
        if clash:
            raise HTTPException(409, "source already exists")
        s.name = name
    if body.config is not None:
        s.config = _normalize_source_config(s.type, body.config, require=True)
    if body.enabled is not None:
        s.enabled = body.enabled
    db.commit()
    db.refresh(s)
    logger.info(
        "source_update id=%s enabled=%s name=%s config_keys=%s",
        s.id,
        s.enabled,
        s.name,
        list((s.config or {}).keys()),
    )
    return _source_dict(s)


@app.delete("/sources/{source_id}")
def remove_source(source_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "source not found")
    logger.info("source_delete id=%s type=%s name=%s", source_id, s.type, s.name)
    db.query(Item).filter(Item.source_id == source_id).update({Item.source_id: None})
    db.delete(s)
    db.commit()
    return {"id": source_id, "deleted": True}


class VaultSourceBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=200)
    path: str = Field(..., min_length=1, max_length=2000)
    enabled: bool = True


class VaultSourceToggle(BaseModel):
    enabled: bool


@app.post("/digests/vault/sources")
def upsert_vault_source(body: VaultSourceBody) -> dict[str, Any]:
    try:
        return vault_upsert_source(
            source_id=body.id,
            label=body.label,
            path=body.path,
            enabled=body.enabled,
        )
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@app.patch("/digests/vault/sources/{source_id}")
def toggle_vault_source(source_id: str, body: VaultSourceToggle) -> dict[str, Any]:
    try:
        return vault_set_enabled(source_id, body.enabled)
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@app.delete("/digests/vault/sources/{source_id}")
def remove_vault_source(source_id: str) -> dict[str, Any]:
    try:
        return vault_delete_source(source_id)
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


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

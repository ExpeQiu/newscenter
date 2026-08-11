"""Digest vault + push + today."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from orchestrator.api.helpers import filter_vault_today, load_today_items, raise_vault, synthesize_today_markdown
from pipeline.db import get_db
from pipeline.digest_sanitize import sanitize_digest_html, sanitize_digest_html_document
from pipeline.digest_vault import (
    DigestVaultError,
    delete_source as vault_delete_source,
    fmt_mtime,
    set_source_enabled as vault_set_enabled,
    upsert_source as vault_upsert_source,
    vault_status,
)
from pipeline.models import Digest, Item
from pipeline.vault_store import (
    enrich_vault_status,
    list_html_files_smart,
    read_html_file_smart,
    sync_vault_to_db,
)

logger = logging.getLogger("newsc.orchestrator")
router = APIRouter(tags=["digests"])

ALLOWED_DIGEST_SOURCES = frozenset({"openclaw", "hermes", "cli", "intelligence", "demo"})


class DigestPushBody(BaseModel):
    digest_date: Optional[date] = None
    html: str = ""
    markdown: str = ""
    highlights: list[str] = Field(default_factory=list)
    source: str = "cli"
    run_id: Optional[str] = None


@router.get("/digests/vault/status")
def digests_vault_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    return enrich_vault_status(vault_status(), db)


@router.post("/digests/vault/ingest")
def digests_vault_ingest(db: Session = Depends(get_db)) -> dict[str, Any]:
    """扫描本机目录写入 digest_vault_*（推云前调用）。"""
    try:
        return sync_vault_to_db(db)
    except DigestVaultError as exc:
        raise_vault(exc)
        raise


@router.get("/digests/vault/files")
def digests_vault_files(
    source: Optional[str] = Query(None, description="来源 id；空=全部"),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="文件名/路径关键词"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        entries = list_html_files_smart(db, source, limit=limit, q=q)
    except DigestVaultError as exc:
        raise_vault(exc)
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


@router.get("/digests/vault/file")
def digests_vault_file(
    source: str = Query(..., min_length=1, description="来源 id"),
    path: str = Query(..., min_length=1, description="相对来源目录的文件路径"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        f = read_html_file_smart(db, source, path)
    except DigestVaultError as exc:
        raise_vault(exc)
        raise
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


@router.get("/digests/vault/raw", response_class=HTMLResponse)
def digests_vault_raw(
    source: str = Query(..., min_length=1, description="来源 id"),
    path: str = Query(..., min_length=1, description="相对来源目录的文件路径"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        f = read_html_file_smart(db, source, path)
    except DigestVaultError as exc:
        raise_vault(exc)
        raise
    html = sanitize_digest_html_document(f.content)
    logger.info(
        "digest_vault raw source=%s path=%s bytes=%d",
        f.source_id,
        f.path,
        len(html.encode("utf-8")),
    )
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.get("/digests/today")
def digest_today(db: Session = Depends(get_db)) -> dict[str, Any]:
    """今日洞察：优先 AI/推送的 Markdown 汇总；缺省时由近期条目合成高度总结。

    注意：目录 HTML 日报属于「日报」页，不再整篇塞进今日洞察（避免单篇 HTML 冒充全站总结）。
    """
    d = date.today()
    row = db.query(Digest).filter(Digest.digest_date == d).first()
    md = ((row.markdown or "").strip() or None) if row else None
    highlights = list(row.highlights or []) if row else []
    db_html = ((row.html or "").strip() or None) if row else None
    db_source = row.source if row else None
    db_run = row.run_id if row else None
    synthesized = False

    vault_meta: dict[str, Any] = {}
    vault_all: list[Any] = []
    vault_entries: list[Any] = []
    try:
        vault_all = list_html_files_smart(db, limit=20)
        vault_entries = filter_vault_today(vault_all, day=d)
        if vault_entries:
            latest = vault_entries[0]
            vault_meta = {
                "source": latest.source_id,
                "source_label": latest.source_label,
                "path": latest.path,
                "mtime": fmt_mtime(latest.mtime),
                "count": len(vault_entries),
            }
    except DigestVaultError as exc:
        logger.warning("digest_today vault list skip: %s", exc)

    if not md:
        items = load_today_items(db, day=d, limit=30)
        if items or vault_entries:
            md, synth_hl = synthesize_today_markdown(items, day=d, vault_entries=vault_entries)
            if not highlights:
                highlights = synth_hl
            synthesized = True
            db_source = db_source or "synthesized"
            logger.info(
                "digest_today synthesized date=%s items=%d vault_today=%d vault_all=%d md_len=%d",
                d.isoformat(),
                len(items),
                len(vault_entries),
                len(vault_all),
                len(md or ""),
            )
        else:
            md, synth_hl = synthesize_today_markdown([], day=d, vault_entries=[])
            synthesized = True
            db_source = db_source or "synthesized"
            highlights = synth_hl
            logger.info("digest_today empty window date=%s", d.isoformat())

    return {
        "date": d.isoformat(),
        "markdown": md,
        "html": db_html,  # 仅 CLI/推送 HTML；不含 vault 单篇
        "highlights": highlights,
        "source": db_source,
        "run_id": db_run,
        "vault": vault_meta or None,
        "synthesized": synthesized,
        "empty": not (db_html or md),
    }


@router.post("/digests/push")
def digest_push(body: DigestPushBody, db: Session = Depends(get_db)) -> dict[str, Any]:
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


class VaultSourceBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    label: str = Field(..., min_length=1, max_length=200)
    path: str = Field(..., min_length=1, max_length=2000)
    enabled: bool = True
    refresh_interval: Optional[str] = Field(None, max_length=32)


class VaultSourceToggle(BaseModel):
    enabled: bool


@router.post("/digests/vault/sources")
def upsert_vault_source(body: VaultSourceBody) -> dict[str, Any]:
    try:
        return vault_upsert_source(
            source_id=body.id,
            label=body.label,
            path=body.path,
            enabled=body.enabled,
            refresh_interval=body.refresh_interval,
        )
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.patch("/digests/vault/sources/{source_id}")
def toggle_vault_source(source_id: str, body: VaultSourceToggle) -> dict[str, Any]:
    try:
        return vault_set_enabled(source_id, body.enabled)
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.delete("/digests/vault/sources/{source_id}")
def remove_vault_source(source_id: str) -> dict[str, Any]:
    try:
        return vault_delete_source(source_id)
    except DigestVaultError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

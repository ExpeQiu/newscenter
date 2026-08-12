"""Subscription sources CRUD + collect helpers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from orchestrator.account_link import canonicalize_social, canonicalize_video
from pipeline.db import get_db
from pipeline.ingest import purge_source_items, upsert_items
from pipeline.models import Source
from pipeline.normalize import CollectItem
from pipeline.outbox import enqueue
from pipeline.runtime import is_cloud_runtime
from pipeline.refresh_interval import (
    canonicalize_refresh_interval,
    source_is_due,
    stamp_last_fetched,
)

logger = logging.getLogger("newsc.orchestrator")
router = APIRouter(tags=["sources"])

ALLOWED_SOURCE_TYPES = frozenset({"web", "rss", "social", "bilibili", "youtube"})
ALLOWED_SOCIAL_PLATFORMS = frozenset({"weibo", "x", "xiaohongshu", "other"})


def source_dict(row: Source) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "enabled": row.enabled,
        "config": row.config or {},
        "cursor": row.cursor or {},
    }


def _attach_refresh(
    out: dict[str, Any],
    cfg: dict[str, Any],
    *,
    stype: str,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    prev_ri = (previous or {}).get("refresh_interval")
    raw = cfg.get("refresh_interval", prev_ri)
    out["refresh_interval"] = canonicalize_refresh_interval(
        raw,
        stype=stype,
        fallback=str(prev_ri) if prev_ri else None,
    )
    return out


def normalize_source_config(
    stype: str,
    config: dict[str, Any] | None,
    *,
    require: bool,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = dict(config or {})
    prev = dict(previous or {})
    if stype in ("web", "rss"):
        url = str(cfg.get("url") if "url" in cfg else prev.get("url") or "").strip()
        if require and not url:
            raise HTTPException(400, "config.url required")
        out: dict[str, Any] = {"url": url} if url else {}
        return _attach_refresh(out, cfg, stype=stype, previous=previous) if out or require else {}
    if stype == "social":
        platform = str(
            cfg.get("platform") if "platform" in cfg else prev.get("platform") or "other"
        ).strip().lower() or "other"
        handle = str(
            cfg.get("handle") if "handle" in cfg else prev.get("handle") or ""
        ).strip()
        platform, handle = canonicalize_social(platform, handle)
        if platform not in ALLOWED_SOCIAL_PLATFORMS:
            platform = "other"
        handle = handle.lstrip("@")
        if require and not handle:
            raise HTTPException(400, "config.handle required")
        out = {"platform": platform}
        if handle:
            out["handle"] = handle
        if not handle and not require:
            return {}
        return _attach_refresh(out, cfg, stype=stype, previous=previous)
    if stype in ("bilibili", "youtube"):
        account = str(
            cfg.get("account") if "account" in cfg else prev.get("account") or ""
        ).strip()
        account = canonicalize_video(stype, account)
        if require and not account:
            raise HTTPException(400, "config.account required")
        out = {"account": account} if account else {}
        return _attach_refresh(out, cfg, stype=stype, previous=previous) if out or require else {}
    return _attach_refresh(dict(cfg), cfg, stype=stype, previous=previous)


def source_identity_key(stype: str, config: dict[str, Any] | None) -> tuple[str, ...]:
    cfg = config or {}
    if stype in ("bilibili", "youtube"):
        return ("account", str(cfg.get("account") or "").strip())
    if stype in ("web", "rss"):
        return ("url", str(cfg.get("url") or "").strip())
    if stype == "social":
        return (
            "social",
            str(cfg.get("platform") or "").strip().lower(),
            str(cfg.get("handle") or "").strip().lstrip("@"),
        )
    return ("cfg", repr(sorted((cfg or {}).items())))


def _advance_cursor(src: Source, items: list[CollectItem]) -> None:
    """用本批最新 published_at 推进增量游标。"""
    latest: datetime | None = None
    for it in items:
        if it.published_at is None:
            continue
        ts = it.published_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if latest is None or ts > latest:
            latest = ts
    if latest is None:
        return
    prev = (src.cursor or {}).get("since")
    if prev:
        try:
            prev_dt = datetime.fromisoformat(str(prev).replace("Z", "+00:00"))
            if prev_dt.tzinfo is None:
                prev_dt = prev_dt.replace(tzinfo=timezone.utc)
            if latest <= prev_dt:
                return
        except ValueError:
            pass
    src.cursor = {**(src.cursor or {}), "since": latest.isoformat()}


def collect_one_source(db: Session, src: Source, run_id: str) -> dict[str, Any]:
    """采集单个启用源并入库；失败抛异常由调用方处理。"""
    cfg = src.config or {}
    cursor = src.cursor or {}
    since = str(cursor.get("since") or "").strip() or None
    items: list[CollectItem] = []
    if src.type == "rss":
        url = str(cfg.get("url") or "").strip()
        if not url:
            return {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id, "skipped_reason": "empty_url"}
        from rss_cli.collector import collect_feed

        items = collect_feed(url, since=since)
    elif src.type == "web":
        url = str(cfg.get("url") or "").strip()
        if not url:
            return {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id, "skipped_reason": "empty_url"}
        from rss_cli.collector import collect_page

        items = collect_page(url, source_label=src.name)
    elif src.type == "youtube":
        from youtube_cli.collector import collect_by_account

        items = collect_by_account(str(cfg.get("account") or ""), source_label=src.name, since=since)
    elif src.type == "bilibili":
        from bilibili_cli.collector import collect_by_account

        items = collect_by_account(str(cfg.get("account") or ""), source_label=src.name, since=since)
    elif src.type == "social":
        from social_cli.collector import collect_by_social

        items = collect_by_social(
            platform=str(cfg.get("platform") or "other"),
            handle=str(cfg.get("handle") or ""),
            source_label=src.name,
        )
    else:
        return {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id, "skipped_reason": "unsupported_type"}

    if not items:
        src.cursor = stamp_last_fetched(src.cursor)
        db.commit()
        logger.info("source_collect_empty id=%s type=%s", src.id, src.type)
        return {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id}

    child_run = f"{run_id[:8]}-{src.id[:8]}-{uuid4().hex[:8]}"
    stats = upsert_items(
        db,
        items,
        run_id=child_run,
        source_name=src.name,
        source_id=src.id,
        enqueue_ai=True,
    )
    _advance_cursor(src, items)
    src.cursor = stamp_last_fetched(src.cursor)
    db.commit()
    logger.info(
        "source_collect_ok id=%s type=%s inserted=%s skipped=%s cursor=%s",
        src.id,
        src.type,
        stats.get("inserted"),
        stats.get("skipped"),
        (src.cursor or {}).get("since"),
    )
    return stats


def run_enabled_sources(db: Session, run_id: str) -> dict[str, Any]:
    rows = db.query(Source).filter(Source.enabled.is_(True)).all()
    total = {
        "inserted": 0,
        "skipped": 0,
        "total": 0,
        "run_id": run_id,
        "sources_run": 0,
        "sources_deferred": 0,
    }
    errors: list[dict[str, str]] = []
    now = datetime.now(timezone.utc)

    for src in rows:
        cfg = dict(src.config or {})
        interval = canonicalize_refresh_interval(
            cfg.get("refresh_interval"),
            stype=src.type,
        )
        # 旧源可能缺字段：写回规范值，便于 UI / 云端一致
        if cfg.get("refresh_interval") != interval:
            cfg["refresh_interval"] = interval
            src.config = cfg
            flag_modified(src, "config")
            db.add(src)
        if not source_is_due(refresh_interval=interval, cursor=src.cursor, now=now):
            total["sources_deferred"] += 1
            logger.info(
                "source_collect_deferred id=%s type=%s interval=%s last=%s",
                src.id,
                src.type,
                interval,
                (src.cursor or {}).get("last_fetched_at"),
            )
            continue
        try:
            stats = collect_one_source(db, src, run_id=run_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "source_collect_fail id=%s type=%s err=%s",
                src.id,
                src.type,
                exc,
            )
            errors.append({"source_id": src.id, "error": str(exc)[:200]})
            continue

        if stats.get("skipped_reason") == "unsupported_type":
            continue
        total["inserted"] += int(stats.get("inserted") or 0)
        total["skipped"] += int(stats.get("skipped") or 0)
        total["total"] += int(stats.get("total") or 0)
        total["sources_run"] += 1

    total["errors"] = errors
    db.commit()
    logger.info(
        "pipeline_sources done run_id=%s sources_run=%s deferred=%s inserted=%s",
        run_id,
        total["sources_run"],
        total["sources_deferred"],
        total["inserted"],
    )
    return {"pipeline_id": "sources", **total}


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(..., min_length=1, max_length=50)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SourceUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    config: Optional[dict[str, Any]] = None


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)) -> dict[str, Any]:
    rows = db.query(Source).order_by(Source.created_at.desc()).all()
    return {"sources": [source_dict(s) for s in rows]}


@router.post("/sources")
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
    config = normalize_source_config(stype, body.config, require=True)
    row = Source(name=name, type=stype, config=config, enabled=body.enabled)
    db.add(row)
    db.flush()
    enqueue(
        db,
        "source.upsert",
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "config": row.config or {},
            "enabled": row.enabled,
        },
    )
    db.commit()
    db.refresh(row)
    logger.info(
        "source_create id=%s type=%s name=%s refresh=%s cloud=%s",
        row.id,
        row.type,
        row.name,
        (row.config or {}).get("refresh_interval"),
        is_cloud_runtime(),
    )
    out = source_dict(row)
    # 云端禁止外采写库；仅本机即时重采
    if (
        not is_cloud_runtime()
        and row.enabled
        and row.type in ("rss", "web", "youtube", "bilibili", "social")
    ):
        try:
            out["resync"] = collect_one_source(db, row, run_id=str(uuid4()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("source_create_resync_fail id=%s err=%s", row.id, exc)
            out["resync_error"] = str(exc)[:200]
    return out


@router.patch("/sources/{source_id}")
def update_source(source_id: str, body: SourceUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "source not found")
    if body.enabled is None and body.name is None and body.config is None:
        raise HTTPException(400, "nothing to update")
    old_identity = source_identity_key(s.type, s.config)
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
    identity_changed = False
    if body.config is not None:
        new_cfg = normalize_source_config(
            s.type, body.config, require=True, previous=s.config
        )
        if source_identity_key(s.type, new_cfg) != old_identity:
            identity_changed = True
        s.config = new_cfg
    if body.enabled is not None:
        s.enabled = body.enabled
    purged = 0
    if identity_changed:
        purged = purge_source_items(db, s.id)
        s.cursor = None
    enqueue(
        db,
        "source.upsert",
        {
            "id": s.id,
            "name": s.name,
            "type": s.type,
            "config": s.config or {},
            "enabled": s.enabled,
        },
    )
    db.commit()
    db.refresh(s)
    logger.info(
        "source_update id=%s enabled=%s name=%s identity_changed=%s purged=%s refresh=%s config_keys=%s cloud=%s",
        s.id,
        s.enabled,
        s.name,
        identity_changed,
        purged,
        (s.config or {}).get("refresh_interval"),
        list((s.config or {}).keys()),
        is_cloud_runtime(),
    )
    out = source_dict(s)
    out["identity_changed"] = identity_changed
    out["purged_items"] = purged
    if (
        not is_cloud_runtime()
        and identity_changed
        and s.enabled
        and s.type in ("rss", "web", "youtube", "bilibili", "social")
    ):
        try:
            out["resync"] = collect_one_source(db, s, run_id=str(uuid4()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("source_update_resync_fail id=%s err=%s", s.id, exc)
            out["resync_error"] = str(exc)[:200]
    return out


@router.delete("/sources/{source_id}")
def remove_source(source_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    s = db.query(Source).filter(Source.id == source_id).first()
    if not s:
        raise HTTPException(404, "source not found")
    logger.info("source_delete id=%s type=%s name=%s cloud=%s", source_id, s.type, s.name, is_cloud_runtime())
    purged = purge_source_items(db, source_id)
    enqueue(db, "source.delete", {"id": source_id})
    db.delete(s)
    db.commit()
    return {"id": source_id, "deleted": True, "purged_items": purged}

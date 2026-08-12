"""日报 vault 入库：本机扫描目录 → PostgreSQL，云端读库。"""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pipeline.digest_vault import (
    DigestFileContent,
    DigestFileEntry,
    DigestSource,
    DigestVaultError,
    HTML_EXTS,
    IGNORE_NAMES,
    MAX_DEPTH,
    MAX_FILE_BYTES,
    MAX_SCAN_FILES,
    _clean_rel,
    get_source,
    load_sources,
)
from pipeline.models import DigestVaultFile, DigestVaultSource
from pipeline.refresh_interval import canonicalize_refresh_interval, source_is_due

logger = logging.getLogger(__name__)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mtime_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def db_file_count(db: Session, source_id: str) -> int:
    return (
        db.query(DigestVaultFile)
        .filter(DigestVaultFile.source_id == source_id)
        .count()
    )


def list_sources_from_db(db: Session) -> list[DigestVaultSource]:
    return (
        db.query(DigestVaultSource)
        .order_by(DigestVaultSource.id.asc())
        .all()
    )


def list_html_files_from_db(
    db: Session,
    source_id: str | None = None,
    *,
    limit: int = 50,
    q: str | None = None,
) -> list[DigestFileEntry]:
    limit = max(1, min(int(limit), 200))
    needle = (q or "").strip().lower()
    query = db.query(DigestVaultFile)
    if source_id:
        sid = (source_id or "").strip()
        src_row = db.query(DigestVaultSource).filter(DigestVaultSource.id == sid).first()
        if src_row and not src_row.enabled:
            raise DigestVaultError(f"来源已禁用: {sid}", status_code=400)
        query = query.filter(DigestVaultFile.source_id == sid)
    else:
        disabled_ids = [
            r.id
            for r in db.query(DigestVaultSource).filter(DigestVaultSource.enabled.is_(False)).all()
        ]
        if disabled_ids:
            query = query.filter(~DigestVaultFile.source_id.in_(disabled_ids))

    rows = query.order_by(DigestVaultFile.mtime.desc()).limit(limit * 3).all()
    out: list[DigestFileEntry] = []
    for row in rows:
        if needle and needle not in (row.name or "").lower() and needle not in (row.rel_path or "").lower():
            continue
        out.append(
            DigestFileEntry(
                source_id=row.source_id,
                source_label=row.source_label or row.source_id,
                name=row.name or Path(row.rel_path).name,
                path=row.rel_path,
                mtime=row.mtime.timestamp() if row.mtime else 0.0,
                size=int(row.size or 0),
            )
        )
        if len(out) >= limit:
            break
    return out


def read_html_file_from_db(db: Session, source_id: str, rel: str) -> DigestFileContent:
    sid = (source_id or "").strip()
    cleaned = _clean_rel(rel)
    if not sid or not cleaned:
        raise DigestVaultError("参数无效", status_code=400)
    if ".." in cleaned.split("/"):
        raise DigestVaultError("非法路径", status_code=400)

    src_row = db.query(DigestVaultSource).filter(DigestVaultSource.id == sid).first()
    if src_row and not src_row.enabled:
        raise DigestVaultError(f"来源已禁用: {sid}", status_code=400)

    row = (
        db.query(DigestVaultFile)
        .filter(DigestVaultFile.source_id == sid, DigestVaultFile.rel_path == cleaned)
        .first()
    )
    if not row:
        raise DigestVaultError("文件不存在", status_code=404)
    return DigestFileContent(
        source_id=row.source_id,
        source_label=row.source_label or (src_row.label if src_row else sid),
        name=row.name or Path(row.rel_path).name,
        path=row.rel_path,
        mtime=row.mtime.timestamp() if row.mtime else 0.0,
        size=int(row.size or 0),
        content=row.html or "",
    )


def _walk_html(src: DigestSource) -> list[tuple[str, Path, float, int]]:
    """返回 (rel_path, path, mtime, size)。"""
    found: list[tuple[str, Path, float, int]] = []
    scanned = 0
    root = src.path.resolve()

    def walk(dir_path: Path, depth: int) -> None:
        nonlocal scanned
        if depth > MAX_DEPTH or scanned >= MAX_SCAN_FILES:
            return
        try:
            children = list(dir_path.iterdir())
        except OSError:
            return
        for child in children:
            if scanned >= MAX_SCAN_FILES:
                return
            if child.name in IGNORE_NAMES or child.name.startswith("._"):
                continue
            try:
                if child.is_dir():
                    walk(child, depth + 1)
                    continue
                if not child.is_file() or child.suffix.lower() not in HTML_EXTS:
                    continue
                scanned += 1
                st = child.stat()
                if st.st_size > MAX_FILE_BYTES:
                    logger.warning(
                        "vault_store skip oversized source=%s path=%s size=%d",
                        src.id,
                        child,
                        st.st_size,
                    )
                    continue
                rel = child.relative_to(root).as_posix()
                found.append((rel, child, st.st_mtime, int(st.st_size)))
            except OSError:
                continue

    walk(root, 0)
    return found


def sync_vault_to_db(db: Session, *, force: bool = False) -> dict[str, Any]:
    """扫描 yaml 来源目录，写入 digest_vault_* 表。

    force=False 时按各源 refresh_interval + synced_at 跳过未到期来源。
    """
    t0 = time.perf_counter()
    sources = load_sources()
    upserted = 0
    deleted = 0
    skipped = 0
    deferred = 0
    errors: list[str] = []

    for src in sources:
        now = datetime.now(tz=timezone.utc)
        row = db.query(DigestVaultSource).filter(DigestVaultSource.id == src.id).first()
        if row is None:
            row = DigestVaultSource(id=src.id)
            db.add(row)
        row.label = src.label
        row.enabled = bool(src.enabled)
        row.origin_path = str(src.path)

        if not src.enabled:
            row.file_count = db_file_count(db, src.id)
            row.synced_at = now
            continue

        interval = canonicalize_refresh_interval(
            getattr(src, "refresh_interval", None),
            stype="digest",
        )
        cursor = {"last_fetched_at": row.synced_at.isoformat()} if row.synced_at else None
        if not force and not source_is_due(refresh_interval=interval, cursor=cursor, now=now):
            deferred += 1
            skipped += 1
            logger.info(
                "vault_store deferred source=%s interval=%s last=%s",
                src.id,
                interval,
                row.synced_at,
            )
            continue

        if not src.path.is_dir():
            skipped += 1
            row.file_count = db_file_count(db, src.id)
            row.synced_at = now
            logger.warning("vault_store skip unreadable source=%s path=%s", src.id, src.path)
            continue

        seen: set[str] = set()
        for rel, path, mtime, size in _walk_html(src):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"{src.id}:{rel}:{exc}")
                continue
            digest = _sha256_text(text)
            seen.add(rel)
            existing = (
                db.query(DigestVaultFile)
                .filter(DigestVaultFile.source_id == src.id, DigestVaultFile.rel_path == rel)
                .first()
            )
            if existing and existing.content_hash == digest:
                existing.mtime = _mtime_dt(mtime)
                existing.size = size
                existing.source_label = src.label
                existing.name = path.name
                continue
            if existing is None:
                existing = DigestVaultFile(source_id=src.id, rel_path=rel)
                db.add(existing)
            existing.source_label = src.label
            existing.name = path.name
            existing.mtime = _mtime_dt(mtime)
            existing.size = size
            existing.content_hash = digest
            existing.html = text
            upserted += 1

        stale = (
            db.query(DigestVaultFile)
            .filter(DigestVaultFile.source_id == src.id)
            .all()
        )
        for f in stale:
            if f.rel_path not in seen:
                db.delete(f)
                deleted += 1

        row.file_count = len(seen)
        row.synced_at = now

    # 清理 yaml 中已不存在的来源（避免测试/旧配置残留上云）
    yaml_ids = {s.id for s in sources}
    for orphan in db.query(DigestVaultSource).all():
        if orphan.id in yaml_ids:
            continue
        n = (
            db.query(DigestVaultFile)
            .filter(DigestVaultFile.source_id == orphan.id)
            .delete(synchronize_session=False)
        )
        deleted += int(n or 0)
        db.delete(orphan)
        logger.info("vault_store prune orphan source=%s files=%s", orphan.id, n)

    db.commit()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    result = {
        "status": "ok",
        "sources": len(sources),
        "upserted": upserted,
        "deleted": deleted,
        "skipped": skipped,
        "deferred": deferred,
        "force": force,
        "errors": errors[:20],
        "elapsed_ms": round(elapsed_ms, 1),
    }
    logger.info(
        "vault_store sync sources=%d upserted=%d deleted=%d skipped=%d deferred=%d force=%s elapsed_ms=%.1f",
        len(sources),
        upserted,
        deleted,
        skipped,
        deferred,
        force,
        elapsed_ms,
    )
    return result


def enrich_vault_status(status: dict[str, Any], db: Session) -> dict[str, Any]:
    """目录不可读时，用库内文件数标记 readable，并补全仅存在于库中的来源。"""
    sources = list(status.get("sources") or [])
    by_id = {str(s.get("id")): s for s in sources if s.get("id")}

    for row in list_sources_from_db(db):
        count = int(row.file_count or 0)
        if count <= 0:
            count = db_file_count(db, row.id)
        if row.id in by_id:
            item = by_id[row.id]
            if not item.get("readable") and row.enabled and count > 0:
                item["readable"] = True
                item["storage"] = "db"
            elif item.get("readable"):
                item.setdefault("storage", "fs")
            item["db_file_count"] = count
        else:
            sources.append(
                {
                    "id": row.id,
                    "label": row.label or row.id,
                    "path": row.origin_path or "",
                    "enabled": bool(row.enabled),
                    "readable": bool(row.enabled) and count > 0,
                    "storage": "db",
                    "db_file_count": count,
                }
            )

    any_ok = any(bool(s.get("readable")) for s in sources)
    status["sources"] = sources
    status["readable"] = any_ok
    status["status"] = "ok" if any_ok else status.get("status") or "unavailable"
    if any_ok and not status.get("message"):
        status["message"] = ""
    elif not any_ok:
        status["message"] = status.get("message") or "无可用日报来源（目录或数据库）"
    return status


def list_html_files_smart(
    db: Session | None,
    source_id: str | None = None,
    *,
    limit: int = 50,
    q: str | None = None,
) -> list[DigestFileEntry]:
    """优先读本地目录；目录不可用时回退数据库。"""
    from pipeline.digest_vault import list_html_files

    if source_id:
        try:
            src = get_source(source_id)
        except DigestVaultError as exc:
            if "已禁用" in str(exc):
                raise
        else:
            if src.path.is_dir():
                return list_html_files(source_id, limit=limit, q=q)
        if db is None:
            raise DigestVaultError(f"未知来源或目录不可读: {source_id}", status_code=404)
        return list_html_files_from_db(db, source_id, limit=limit, q=q)

    fs_entries = list_html_files(None, limit=limit, q=q)
    if db is None:
        return fs_entries

    fs_source_ids = {e.source_id for e in fs_entries}
    yaml_ids = {s.id for s in load_sources() if s.enabled and s.path.is_dir()}
    covered = fs_source_ids | yaml_ids
    db_extra = list_html_files_from_db(db, None, limit=limit, q=q)
    merged = list(fs_entries)
    for e in db_extra:
        if e.source_id in covered:
            continue
        merged.append(e)
    merged.sort(key=lambda x: x.mtime, reverse=True)
    return merged[: max(1, min(int(limit), 200))]


def read_html_file_smart(db: Session | None, source_id: str, rel: str) -> DigestFileContent:
    from pipeline.digest_vault import read_html_file

    try:
        src = get_source(source_id)
    except DigestVaultError as exc:
        if "已禁用" in str(exc):
            raise
    else:
        if src.path.is_dir():
            return read_html_file(source_id, rel)
    if db is None:
        raise DigestVaultError("文件不存在或目录不可读", status_code=404)
    return read_html_file_from_db(db, source_id, rel)

"""日报 HTML vault：按配置来源只读扫描指定目录（参考 AgentCenter outputs）。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from pipeline.settings import ROOT, get_settings

logger = logging.getLogger(__name__)

HTML_EXTS = frozenset({".html", ".htm"})
IGNORE_NAMES = frozenset({".DS_Store", ".git", ".obsidian", "__pycache__", ".trash"})
MAX_SCAN_FILES = 5000
MAX_DEPTH = 8
MAX_FILE_BYTES = 2_000_000


class DigestVaultError(Exception):
    def __init__(self, message: str, *, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DigestSource:
    id: str
    label: str
    path: Path
    enabled: bool = True


@dataclass
class DigestFileEntry:
    source_id: str
    source_label: str
    name: str
    path: str  # relative to source root
    mtime: float
    size: int


@dataclass
class DigestFileContent:
    source_id: str
    source_label: str
    name: str
    path: str
    mtime: float
    size: int
    content: str


def _sources_file() -> Path:
    s = get_settings()
    raw = (s.digest_sources_file or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = ROOT / p
        return p
    return ROOT / "digest-sources.yml"


def load_sources() -> list[DigestSource]:
    path = _sources_file()
    if not path.is_file():
        logger.warning("digest_vault sources missing file=%s", path)
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.exception("digest_vault sources parse failed file=%s", path)
        raise DigestVaultError(f"来源配置无法解析: {exc}", status_code=500) from exc

    items = raw.get("sources") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []

    out: list[DigestSource] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or sid).strip()
        path_raw = str(item.get("path") or "").strip().strip('"').strip("'")
        enabled = bool(item.get("enabled", True))
        if not sid or not path_raw or sid in seen:
            continue
        seen.add(sid)
        p = Path(path_raw).expanduser()
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        else:
            p = p.resolve()
        out.append(DigestSource(id=sid, label=label or sid, path=p, enabled=enabled))
    logger.info("digest_vault load_sources count=%d file=%s", len(out), path)
    return out


def get_source(source_id: str) -> DigestSource:
    sid = (source_id or "").strip()
    for src in load_sources():
        if src.id == sid:
            if not src.enabled:
                raise DigestVaultError(f"来源已禁用: {sid}", status_code=400)
            return src
    raise DigestVaultError(f"未知来源: {sid}", status_code=404)


def vault_status() -> dict[str, Any]:
    path = _sources_file()
    sources = []
    try:
        loaded = load_sources()
    except DigestVaultError as exc:
        return {
            "status": "error",
            "readable": False,
            "config_file": str(path),
            "message": str(exc),
            "sources": [],
        }

    for src in loaded:
        readable = src.enabled and src.path.is_dir()
        sources.append(
            {
                "id": src.id,
                "label": src.label,
                "path": str(src.path),
                "enabled": src.enabled,
                "readable": readable,
            }
        )
    any_ok = any(s["readable"] for s in sources)
    return {
        "status": "ok" if any_ok else "unavailable",
        "readable": any_ok,
        "config_file": str(path),
        "message": "" if any_ok else "无可用日报来源目录",
        "sources": sources,
    }


def _clean_rel(rel: str) -> str:
    return (rel or "").replace("\\", "/").strip().strip("/")


def resolve_safe(src: DigestSource, rel: str) -> Path:
    cleaned = _clean_rel(rel)
    if ".." in cleaned.split("/"):
        raise DigestVaultError("非法路径", status_code=400)
    root = src.path.resolve()
    if not root.is_dir():
        raise DigestVaultError(f"来源目录不可读: {src.id}", status_code=503)
    if not cleaned:
        return root
    candidate = (root / cleaned).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DigestVaultError("非法路径", status_code=400) from exc
    return candidate


def _is_html(path: Path) -> bool:
    return path.suffix.lower() in HTML_EXTS


def list_html_files(
    source_id: str | None = None,
    *,
    limit: int = 50,
    q: str | None = None,
) -> list[DigestFileEntry]:
    t0 = time.perf_counter()
    limit = max(1, min(int(limit), 200))
    needle = (q or "").strip().lower()
    sources = load_sources()
    if source_id:
        sources = [get_source(source_id)]
    else:
        sources = [s for s in sources if s.enabled]

    found: list[DigestFileEntry] = []
    scanned = 0

    def walk(src: DigestSource, dir_path: Path, depth: int) -> None:
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
                    walk(src, child, depth + 1)
                    continue
                if not child.is_file() or not _is_html(child):
                    continue
                scanned += 1
                rel = child.relative_to(src.path.resolve()).as_posix()
                if needle and needle not in child.name.lower() and needle not in rel.lower():
                    continue
                st = child.stat()
                found.append(
                    DigestFileEntry(
                        source_id=src.id,
                        source_label=src.label,
                        name=child.name,
                        path=rel,
                        mtime=st.st_mtime,
                        size=st.st_size,
                    )
                )
            except OSError:
                continue

    for src in sources:
        if not src.path.is_dir():
            logger.warning("digest_vault skip unreadable source=%s path=%s", src.id, src.path)
            continue
        walk(src, src.path.resolve(), 0)

    found.sort(key=lambda e: e.mtime, reverse=True)
    result = found[:limit]
    logger.info(
        "digest_vault list source=%s q=%r scanned=%d hits=%d elapsed_ms=%.1f",
        source_id or "all",
        needle,
        scanned,
        len(result),
        (time.perf_counter() - t0) * 1000,
    )
    return result


def read_html_file(source_id: str, rel: str) -> DigestFileContent:
    t0 = time.perf_counter()
    src = get_source(source_id)
    path = resolve_safe(src, rel)
    if not path.is_file():
        raise DigestVaultError("文件不存在", status_code=404)
    if not _is_html(path):
        raise DigestVaultError("仅支持 HTML", status_code=400)
    try:
        st = path.stat()
    except OSError as exc:
        raise DigestVaultError(f"无法读取文件: {exc}", status_code=500) from exc
    if st.st_size > MAX_FILE_BYTES:
        raise DigestVaultError("文件过大", status_code=413)
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise DigestVaultError(f"无法读取文件: {exc}", status_code=500) from exc

    rel_path = path.relative_to(src.path.resolve()).as_posix()
    logger.info(
        "digest_vault read source=%s path=%r size=%d elapsed_ms=%.1f",
        src.id,
        rel_path,
        st.st_size,
        (time.perf_counter() - t0) * 1000,
    )
    return DigestFileContent(
        source_id=src.id,
        source_label=src.label,
        name=path.name,
        path=rel_path,
        mtime=st.st_mtime,
        size=st.st_size,
        content=content,
    )


def fmt_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _read_raw_sources() -> list[dict[str, Any]]:
    path = _sources_file()
    if not path.is_file():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.exception("digest_vault sources parse failed file=%s", path)
        raise DigestVaultError(f"来源配置无法解析: {exc}", status_code=500) from exc
    items = raw.get("sources") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]


def _write_raw_sources(items: list[dict[str, Any]]) -> Path:
    path = _sources_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"sources": items}
    text = (
        "# NewsC 日报来源（参考 AgentCenter 输出物：定义目录 → 只读 HTML）\n"
        "# path 可为绝对路径，或相对仓库根目录\n\n"
        + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    )
    path.write_text(text, encoding="utf-8")
    logger.info("digest_vault write_sources count=%d file=%s", len(items), path)
    return path


def _validate_source_id(source_id: str) -> str:
    sid = (source_id or "").strip()
    if not sid or len(sid) > 64:
        raise DigestVaultError("id 无效", status_code=400)
    if any(c in sid for c in ("/", "\\", "..", " ")):
        raise DigestVaultError("id 含非法字符", status_code=400)
    return sid


def upsert_source(
    *,
    source_id: str,
    label: str,
    path: str,
    enabled: bool = True,
) -> dict[str, Any]:
    sid = _validate_source_id(source_id)
    label_s = (label or sid).strip()
    path_raw = (path or "").strip().strip('"').strip("'")
    if not path_raw:
        raise DigestVaultError("path 不能为空", status_code=400)
    if ".." in Path(path_raw).parts:
        raise DigestVaultError("path 含非法片段", status_code=400)

    items = _read_raw_sources()
    found = False
    for item in items:
        if str(item.get("id") or "").strip() == sid:
            item["label"] = label_s
            item["path"] = path_raw
            item["enabled"] = bool(enabled)
            found = True
            break
    if not found:
        items.append({"id": sid, "label": label_s, "path": path_raw, "enabled": bool(enabled)})

    cfg = _write_raw_sources(items)
    p = Path(path_raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    readable = bool(enabled) and p.is_dir()
    logger.info(
        "digest_vault upsert id=%s enabled=%s readable=%s file=%s",
        sid,
        enabled,
        readable,
        cfg,
    )
    return {
        "id": sid,
        "label": label_s,
        "path": str(p),
        "enabled": bool(enabled),
        "readable": readable,
    }


def set_source_enabled(source_id: str, enabled: bool) -> dict[str, Any]:
    sid = _validate_source_id(source_id)
    items = _read_raw_sources()
    for item in items:
        if str(item.get("id") or "").strip() == sid:
            return upsert_source(
                source_id=sid,
                label=str(item.get("label") or sid),
                path=str(item.get("path") or ""),
                enabled=bool(enabled),
            )
    raise DigestVaultError(f"未知来源: {sid}", status_code=404)


def delete_source(source_id: str) -> dict[str, Any]:
    sid = _validate_source_id(source_id)
    items = _read_raw_sources()
    next_items = [i for i in items if str(i.get("id") or "").strip() != sid]
    if len(next_items) == len(items):
        raise DigestVaultError(f"未知来源: {sid}", status_code=404)
    _write_raw_sources(next_items)
    logger.info("digest_vault delete id=%s", sid)
    return {"id": sid, "deleted": True}

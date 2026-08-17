"""日报 HTML vault：按配置来源只读扫描指定目录（参考 AgentCenter outputs）。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from pipeline.refresh_interval import canonicalize_refresh_interval, refresh_interval_label
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
    refresh_interval: str = "1d"
    tags: tuple[str, ...] = ()


def _normalize_tags(raw: Any) -> tuple[str, ...]:
    """解析标签：支持 YAML 列表，或逗号/中文逗号分隔字符串。"""
    if raw is None:
        return ()
    parts: list[str] = []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace("，", ",").split(",")]
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            s = str(item or "").strip()
            if not s:
                continue
            if "," in s or "，" in s:
                parts.extend(p.strip() for p in s.replace("，", ",").split(","))
            else:
                parts.append(s)
    else:
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p or p in seen:
            continue
        if len(p) > 32:
            p = p[:32]
        seen.add(p)
        out.append(p)
        if len(out) >= 20:
            break
    return tuple(out)


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


def _local_sources_file() -> Path | None:
    """同目录 digest-sources.local.yml；单测自定义 DIGEST_SOURCES_FILE 时不叠加。"""
    base = _sources_file()
    if base.name != "digest-sources.yml":
        return None
    return base.with_name("digest-sources.local.yml")


def _parse_source_dicts(path: Path) -> list[dict[str, Any]]:
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


def _merge_source_dicts(base: list[dict[str, Any]], overlay: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    deleted: set[str] = set()
    for item in base + overlay:
        sid = str(item.get("id") or "").strip()
        if not sid:
            continue
        if item.get("deleted") is True:
            deleted.add(sid)
            by_id.pop(sid, None)
            continue
        deleted.discard(sid)
        if sid not in by_id and sid not in order:
            order.append(sid)
        by_id[sid] = item
    return [by_id[sid] for sid in order if sid in by_id and sid not in deleted]


def _dicts_to_sources(items: list[dict[str, Any]]) -> list[DigestSource]:
    out: list[DigestSource] = []
    seen: set[str] = set()
    for item in items:
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or sid).strip()
        path_raw = str(item.get("path") or "").strip().strip('"').strip("'")
        enabled = bool(item.get("enabled", True))
        refresh = canonicalize_refresh_interval(
            item.get("refresh_interval"),
            stype="digest",
        )
        tags = _normalize_tags(item.get("tags"))
        if not sid or not path_raw or sid in seen:
            continue
        seen.add(sid)
        p = Path(path_raw).expanduser()
        if not p.is_absolute():
            p = (ROOT / p).resolve()
        else:
            p = p.resolve()
        out.append(
            DigestSource(
                id=sid,
                label=label or sid,
                path=p,
                enabled=enabled,
                refresh_interval=refresh,
                tags=tags,
            )
        )
    return out


def load_sources() -> list[DigestSource]:
    path = _sources_file()
    if not path.is_file():
        logger.warning("digest_vault sources missing file=%s", path)
        base_items: list[dict[str, Any]] = []
    else:
        base_items = _parse_source_dicts(path)

    local = _local_sources_file()
    overlay: list[dict[str, Any]] = []
    if local and local.is_file():
        overlay = _parse_source_dicts(local)

    merged = _merge_source_dicts(base_items, overlay)
    out = _dicts_to_sources(merged)
    logger.info(
        "digest_vault load_sources count=%d file=%s local=%s",
        len(out),
        path,
        local if local and local.is_file() else None,
    )
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
                "refresh_interval": src.refresh_interval,
                "refresh_label": refresh_interval_label(src.refresh_interval),
                "tags": list(src.tags),
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
    """合并 base + local，供 upsert 读写；写回目标见 _writable_sources_file。"""
    base = _parse_source_dicts(_sources_file()) if _sources_file().is_file() else []
    local = _local_sources_file()
    overlay = _parse_source_dicts(local) if local and local.is_file() else []
    return _merge_source_dicts(base, overlay)


def _writable_sources_file() -> Path:
    """单测自定义文件直接写回；默认仓库写 local，避免污染已提交的 demo 配置。"""
    local = _local_sources_file()
    if local is not None:
        return local
    return _sources_file()


def _write_raw_sources(items: list[dict[str, Any]]) -> Path:
    path = _writable_sources_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    # 默认路径：base 保留 demo，变更写入 local（含删除墓碑）
    local = _local_sources_file()
    if local is not None and path == local:
        base_items = _parse_source_dicts(_sources_file()) if _sources_file().is_file() else []
        base_by_id = {
            str(i.get("id") or "").strip(): i
            for i in base_items
            if str(i.get("id") or "").strip()
        }
        merged_ids = {str(i.get("id") or "").strip() for i in items if str(i.get("id") or "").strip()}
        to_write: list[dict[str, Any]] = []
        for item in items:
            sid = str(item.get("id") or "").strip()
            if not sid:
                continue
            if sid not in base_by_id:
                to_write.append(item)
                continue
            if item != base_by_id.get(sid):
                to_write.append(item)
        for sid, base_item in base_by_id.items():
            if sid not in merged_ids:
                to_write.append({"id": sid, "deleted": True})
        items = to_write

    payload = {"sources": items}
    text = (
        "# NewsC 日报来源（本机覆盖 / 可写配置）\n"
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
    refresh_interval: str | None = None,
    tags: Any = None,
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
    prev_refresh: str | None = None
    prev_tags: tuple[str, ...] = ()
    for item in items:
        if str(item.get("id") or "").strip() == sid:
            prev_refresh = str(item.get("refresh_interval") or "") or None
            prev_tags = _normalize_tags(item.get("tags"))
            item["label"] = label_s
            item["path"] = path_raw
            item["enabled"] = bool(enabled)
            item["refresh_interval"] = canonicalize_refresh_interval(
                refresh_interval if refresh_interval is not None else prev_refresh,
                stype="digest",
                fallback=prev_refresh,
            )
            if tags is not None:
                item["tags"] = list(_normalize_tags(tags))
            found = True
            break
    refresh = canonicalize_refresh_interval(
        refresh_interval if refresh_interval is not None else prev_refresh,
        stype="digest",
        fallback=prev_refresh,
    )
    tag_list = list(_normalize_tags(tags)) if tags is not None else list(prev_tags)
    if not found:
        items.append(
            {
                "id": sid,
                "label": label_s,
                "path": path_raw,
                "enabled": bool(enabled),
                "refresh_interval": refresh,
                "tags": tag_list,
            }
        )

    cfg = _write_raw_sources(items)
    p = Path(path_raw).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    else:
        p = p.resolve()
    readable = bool(enabled) and p.is_dir()
    logger.info(
        "digest_vault upsert id=%s enabled=%s readable=%s refresh=%s tags=%s file=%s",
        sid,
        enabled,
        readable,
        refresh,
        tag_list,
        cfg,
    )
    return {
        "id": sid,
        "label": label_s,
        "path": str(p),
        "enabled": bool(enabled),
        "readable": readable,
        "refresh_interval": refresh,
        "refresh_label": refresh_interval_label(refresh),
        "tags": tag_list,
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
                refresh_interval=str(item.get("refresh_interval") or "") or None,
                tags=item.get("tags"),
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

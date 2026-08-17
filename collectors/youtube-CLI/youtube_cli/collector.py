"""YouTube collector — demo + video_id / channel metadata (no download)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from time import mktime
from typing import Any

import feedparser
import httpx

from pipeline.normalize import CollectItem

logger = logging.getLogger("newsc.youtube_cli.collector")

# Public well-known sample video ids for embed demos
DEMO = [
    {
        "title": "Me at the zoo",
        "content": "YouTube 历史上第一条公开视频。NewsC 以 iframe 嵌入播放，不下载媒体。",
        "video_id": "jNQXAC9IVRw",
    },
    {
        "title": "Demo: Never Gonna Give You Up",
        "content": "经典示例视频，用于验证嵌入播放与摘要管线。",
        "video_id": "dQw4w9WgXcQ",
    },
]

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")
_YT_INITIAL_DATA_RE = re.compile(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", re.DOTALL)
_YT_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsC/1.0; +https://github.com/newsc)"}


def collect_demo() -> list[CollectItem]:
    now = datetime.now(timezone.utc)
    items: list[CollectItem] = []
    for d in DEMO:
        vid = d["video_id"]
        items.append(
            CollectItem(
                source="youtube",
                title=d["title"],
                content=d["content"],
                url=f"https://www.youtube.com/watch?v={vid}",
                published_at=now,
                embed_provider="youtube",
                embed_id=vid,
                embed_url=f"https://www.youtube.com/embed/{vid}",
                thumbnail_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                raw={"demo": True},
            )
        )
    return items


def collect_by_video_id(video_id: str, *, title: str | None = None) -> list[CollectItem]:
    vid = (video_id or "").strip()
    if not _VIDEO_ID_RE.match(vid):
        raise ValueError(f"invalid youtube video_id: {video_id!r}")
    now = datetime.now(timezone.utc)
    return [
        CollectItem(
            source="youtube",
            title=title or f"YouTube {vid}",
            content=f"Embed metadata for https://www.youtube.com/watch?v={vid}",
            url=f"https://www.youtube.com/watch?v={vid}",
            published_at=now,
            embed_provider="youtube",
            embed_id=vid,
            embed_url=f"https://www.youtube.com/embed/{vid}",
            thumbnail_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            raw={"video_id": vid},
        )
    ]


def _parse_struct_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(mktime(value), tz=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _video_id_from_entry(entry: Any) -> str | None:
    vid = getattr(entry, "yt_videoid", None) or ""
    if _VIDEO_ID_RE.match(str(vid)):
        return str(vid)
    link = getattr(entry, "link", None) or ""
    m = re.search(r"(?:v=|/shorts/)([A-Za-z0-9_-]{11})", link)
    return m.group(1) if m else None


def resolve_channel_id(account: str, *, timeout: float = 30.0) -> str:
    """Resolve @handle / channel URL / UC… id to channel_id."""
    acc = (account or "").strip()
    if not acc:
        raise ValueError("empty youtube account")
    if acc.startswith("http"):
        if "/channel/" in acc:
            m = re.search(r"/channel/(UC[\w-]{22})", acc)
            if m:
                return m.group(1)
        m = re.search(r"youtube\.com/@([^/?#]+)", acc)
        if m:
            acc = m.group(1)
        else:
            raise ValueError(f"unsupported youtube url: {account!r}")
    acc = acc.lstrip("@")
    if _CHANNEL_ID_RE.match(acc):
        return acc

    page_url = f"https://www.youtube.com/@{acc}"
    logger.info("youtube_resolve_channel account=%s url=%s", acc, page_url)
    with httpx.Client(headers=_YT_HEADERS, follow_redirects=True, timeout=timeout) as client:
        resp = client.get(page_url)
        resp.raise_for_status()
        html = resp.text

    # Prefer externalId (channel canonical id on handle pages)
    m = re.search(r'"externalId":"(UC[\w-]{22})"', html)
    if m:
        return m.group(1)
    m = re.search(r"channel_id=(UC[\w-]{22})", html)
    if m:
        return m.group(1)
    m = re.search(r'"channelId":"(UC[\w-]{22})"', html)
    if m:
        return m.group(1)
    raise ValueError(f"cannot resolve channel_id for @{acc}")


def _iter_lockup_videos(node: Any) -> list[dict[str, Any]]:
    """从 ytInitialData 提取 lockupViewModel 视频列表（部分频道 Atom 404 时用）。"""
    found: list[dict[str, Any]] = []

    def walk(o: Any) -> None:
        if isinstance(o, dict):
            lv = o.get("lockupViewModel")
            if isinstance(lv, dict) and lv.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                vid = str(lv.get("contentId") or "")
                if _VIDEO_ID_RE.match(vid):
                    meta_vm = ((lv.get("metadata") or {}).get("lockupMetadataViewModel") or {})
                    title = ((meta_vm.get("title") or {}).get("content") or "").strip()
                    rows = (
                        ((meta_vm.get("metadata") or {}).get("contentMetadataViewModel") or {}).get(
                            "metadataRows"
                        )
                        or []
                    )
                    parts: list[str] = []
                    for row in rows:
                        for part in row.get("metadataParts") or []:
                            text = ((part.get("text") or {}).get("content") or "").strip()
                            if text:
                                parts.append(text)
                    found.append(
                        {
                            "video_id": vid,
                            "title": title or f"YouTube {vid}",
                            "meta_parts": parts,
                        }
                    )
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(node)
    # 保持出现顺序并去重
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in found:
        vid = row["video_id"]
        if vid in seen:
            continue
        seen.add(vid)
        out.append(row)
    return out


def collect_channel_page(
    channel_id: str,
    *,
    source_label: str = "",
    account: str = "",
    limit: int = 30,
    timeout: float = 30.0,
) -> list[CollectItem]:
    """Atom 不可用时，从 /@handle/videos 的 ytInitialData 拉标题与 video_id。"""
    cid = (channel_id or "").strip()
    bare = (account or "").lstrip("@")
    if bare:
        page_url = f"https://www.youtube.com/@{bare}/videos"
    else:
        page_url = f"https://www.youtube.com/channel/{cid}/videos"
    logger.info("youtube_page_fetch channel_id=%s url=%s limit=%s", cid, page_url, limit)
    with httpx.Client(headers=_YT_HEADERS, follow_redirects=True, timeout=timeout) as client:
        resp = client.get(page_url)
        resp.raise_for_status()
        html = resp.text
    m = _YT_INITIAL_DATA_RE.search(html)
    if not m:
        logger.warning("youtube_page_no_ytInitialData url=%s", page_url)
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.warning("youtube_page_json_fail url=%s err=%s", page_url, exc)
        return []
    channel_title = source_label or (f"@{bare}" if bare else cid)
    author = f"@{bare}" if bare else channel_title
    now = datetime.now(timezone.utc)
    items: list[CollectItem] = []
    for row in _iter_lockup_videos(data)[:limit]:
        vid = row["video_id"]
        title = row["title"]
        parts = row.get("meta_parts") or []
        views = next((p for p in parts if "view" in p.lower() or "次观看" in p), None)
        published_label = next((p for p in parts if p is not views), None)
        content_bits = [f"{channel_title}: {title}"]
        if published_label:
            content_bits.append(published_label)
        if views:
            content_bits.append(views)
        items.append(
            CollectItem(
                source="youtube",
                title=title,
                content=" · ".join(content_bits),
                url=f"https://www.youtube.com/watch?v={vid}",
                published_at=now,
                embed_provider="youtube",
                embed_id=vid,
                embed_url=f"https://www.youtube.com/embed/{vid}",
                thumbnail_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                raw={
                    "account": bare or None,
                    "channel_id": cid,
                    "channel_title": channel_title,
                    "author": author,
                    "video_id": vid,
                    "views": views,
                    "published_label": published_label,
                    "via": "channel_page",
                },
            )
        )
    logger.info(
        "youtube_page_done channel_id=%s account=%s items=%s",
        cid,
        bare,
        len(items),
    )
    return items


def collect_channel_feed(
    channel_id: str,
    *,
    source_label: str = "",
    account: str = "",
    limit: int = 30,
    since: str | None = None,
) -> list[CollectItem]:
    """Pull recent videos via public Atom feed；404/空则回退频道页解析。"""
    cid = (channel_id or "").strip()
    if not _CHANNEL_ID_RE.match(cid):
        raise ValueError(f"invalid youtube channel_id: {channel_id!r}")
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            since_dt = None
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    logger.info("youtube_feed_fetch channel_id=%s limit=%s since=%s", cid, limit, since)
    parsed = feedparser.parse(feed_url)
    feed_status = getattr(parsed, "status", None)
    channel_title = getattr(parsed.feed, "title", "") or source_label or account
    items: list[CollectItem] = []
    for entry in parsed.entries[:limit]:
        vid = _video_id_from_entry(entry)
        if not vid:
            continue
        published = _parse_struct_time(getattr(entry, "published_parsed", None))
        if published is None:
            published = _parse_struct_time(getattr(entry, "updated_parsed", None))
        if since_dt and published and published <= since_dt:
            continue
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
        title = getattr(entry, "title", "") or f"YouTube {vid}"
        bare = account.lstrip("@") if account else ""
        items.append(
            CollectItem(
                source="youtube",
                title=title,
                content=str(summary)[:4000] or f"{channel_title}: {title}",
                url=f"https://www.youtube.com/watch?v={vid}",
                published_at=published,
                embed_provider="youtube",
                embed_id=vid,
                embed_url=f"https://www.youtube.com/embed/{vid}",
                thumbnail_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                raw={
                    "account": bare or None,
                    "channel_id": cid,
                    "channel_title": channel_title,
                    "author": f"@{bare}" if bare else channel_title,
                    "video_id": vid,
                    "feed_id": getattr(entry, "id", None),
                    "via": "atom_feed",
                },
            )
        )
    logger.info(
        "youtube_feed_done channel_id=%s channel=%s status=%s items=%s",
        cid,
        channel_title,
        feed_status,
        len(items),
    )
    if items:
        return items
    logger.info(
        "youtube_feed_empty_fallback_page channel_id=%s status=%s",
        cid,
        feed_status,
    )
    return collect_channel_page(
        cid,
        source_label=source_label,
        account=account,
        limit=limit,
    )


def collect_by_account(
    account: str, *, source_label: str = "", limit: int = 30, since: str | None = None
) -> list[CollectItem]:
    """解析频道并拉 Atom；watch/shorts URL 或频道解析失败的 11 位串才当 video_id。

    注意：YouTube handle 也可能恰好 11 位（如 huanyihe777），不可优先当 video_id，
    否则会写入占位标题/摘要，列表上看不出真实主题。
    """
    acc = (account or "").strip()
    if not acc:
        return []
    bare = acc.lstrip("@")

    # 明确视频链接 → 单条
    if acc.startswith("http") and ("watch?v=" in acc or "/shorts/" in acc):
        m = re.search(r"(?:v=|/shorts/)([A-Za-z0-9_-]{11})", acc)
        if m:
            return collect_by_video_id(m.group(1), title=source_label or None)

    try:
        channel_id = resolve_channel_id(acc)
        return collect_channel_feed(
            channel_id,
            source_label=source_label,
            account=bare,
            limit=limit,
            since=since,
        )
    except Exception as exc:  # noqa: BLE001
        # 11 位歧义串：频道解析失败后再回退为 video_id
        if _VIDEO_ID_RE.match(bare) and not _CHANNEL_ID_RE.match(bare):
            logger.info(
                "youtube_fallback_video_id account=%s channel_err=%s",
                bare,
                exc,
            )
            return collect_by_video_id(bare, title=source_label or None)
        logger.warning("youtube_channel_collect_fail account=%s err=%s", bare, exc)
        now = datetime.now(timezone.utc)
        url = acc if acc.startswith("http") else f"https://www.youtube.com/@{bare}"
        return [
            CollectItem(
                source="youtube",
                title=source_label or f"YouTube @{bare}",
                content=f"Channel collect failed for @{bare}: {exc}",
                url=url,
                published_at=now,
                raw={"account": bare, "kind": "channel_error", "error": str(exc)[:200]},
            )
        ]

"""YouTube collector — demo + video_id / channel metadata (no download)."""
from __future__ import annotations

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


def collect_channel_feed(
    channel_id: str,
    *,
    source_label: str = "",
    account: str = "",
    limit: int = 30,
) -> list[CollectItem]:
    """Pull recent videos via public Atom feed (no API key / no media download)."""
    cid = (channel_id or "").strip()
    if not _CHANNEL_ID_RE.match(cid):
        raise ValueError(f"invalid youtube channel_id: {channel_id!r}")
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    logger.info("youtube_feed_fetch channel_id=%s limit=%s", cid, limit)
    parsed = feedparser.parse(feed_url)
    channel_title = getattr(parsed.feed, "title", "") or source_label or account
    items: list[CollectItem] = []
    for entry in parsed.entries[:limit]:
        vid = _video_id_from_entry(entry)
        if not vid:
            continue
        published = _parse_struct_time(getattr(entry, "published_parsed", None))
        if published is None:
            published = _parse_struct_time(getattr(entry, "updated_parsed", None))
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None) or ""
        title = getattr(entry, "title", "") or f"YouTube {vid}"
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
                    "account": account.lstrip("@") if account else None,
                    "channel_id": cid,
                    "channel_title": channel_title,
                    "video_id": vid,
                    "feed_id": getattr(entry, "id", None),
                },
            )
        )
    logger.info(
        "youtube_feed_done channel_id=%s channel=%s items=%s",
        cid,
        channel_title,
        len(items),
    )
    return items


def collect_by_account(account: str, *, source_label: str = "", limit: int = 30) -> list[CollectItem]:
    """account 为 11 位 video_id 时拉单条；否则解析频道并拉 Atom 更新。"""
    acc = (account or "").strip()
    if not acc:
        return []
    bare = acc.lstrip("@")
    if _VIDEO_ID_RE.match(bare) and not _CHANNEL_ID_RE.match(bare):
        return collect_by_video_id(bare, title=source_label or None)
    try:
        channel_id = resolve_channel_id(acc)
        return collect_channel_feed(
            channel_id,
            source_label=source_label,
            account=bare,
            limit=limit,
        )
    except Exception as exc:  # noqa: BLE001
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

"""Bilibili collector — demo + bvid / mid space videos (no download)."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from pipeline.normalize import CollectItem

logger = logging.getLogger("newsc.bilibili_cli.collector")

DEMO = [
    {
        "title": "【演示】B站嵌入播放样例 BV1GJ411x7h7",
        "content": "使用 Bilibili player 嵌入；无法嵌入时详情页降级为外链。",
        "bvid": "BV1GJ411x7h7",
    },
]

_BVID_RE = re.compile(r"^BV[A-Za-z0-9]+$", re.I)
_MID_RE = re.compile(r"^\d{1,16}$")
_SPACE_URL_RE = re.compile(r"space\.bilibili\.com/(\d+)")
_HEADERS = {
    # Mobile UA is less aggressive on space arc/search rate limits than desktop Chrome.
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 BiliApp/7.0.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def collect_demo() -> list[CollectItem]:
    now = datetime.now(timezone.utc)
    items: list[CollectItem] = []
    for d in DEMO:
        bvid = d["bvid"]
        items.append(
            CollectItem(
                source="bilibili",
                title=d["title"],
                content=d["content"],
                url=f"https://www.bilibili.com/video/{bvid}",
                published_at=now,
                embed_provider="bilibili",
                embed_id=bvid,
                embed_url=f"https://player.bilibili.com/player.html?bvid={bvid}&high_quality=1",
                thumbnail_url=None,
                raw={"demo": True, "bvid": bvid},
            )
        )
    return items


def collect_by_bvid(bvid: str, *, title: str | None = None) -> list[CollectItem]:
    bv = (bvid or "").strip()
    if not _BVID_RE.match(bv):
        raise ValueError(f"invalid bilibili bvid: {bvid!r}")
    now = datetime.now(timezone.utc)
    return [
        CollectItem(
            source="bilibili",
            title=title or f"Bilibili {bv}",
            content=f"Embed metadata for https://www.bilibili.com/video/{bv}",
            url=f"https://www.bilibili.com/video/{bv}",
            published_at=now,
            embed_provider="bilibili",
            embed_id=bv,
            embed_url=f"https://player.bilibili.com/player.html?bvid={bv}&high_quality=1",
            thumbnail_url=None,
            raw={"bvid": bv},
        )
    ]


def resolve_mid(account: str) -> str:
    """Resolve mid from digits / space URL / plain account string."""
    acc = (account or "").strip()
    if not acc:
        raise ValueError("empty bilibili account")
    m = _SPACE_URL_RE.search(acc)
    if m:
        return m.group(1)
    if acc.startswith("http"):
        m = re.search(r"/(\d{1,16})(?:[/?#]|$)", acc)
        if m:
            return m.group(1)
        raise ValueError(f"unsupported bilibili url: {account!r}")
    if _MID_RE.match(acc):
        return acc
    raise ValueError(f"bilibili account must be mid or space URL, got {account!r}")


def _item_from_vlist(v: dict[str, Any], *, mid: str, up_name: str) -> CollectItem | None:
    bvid = str(v.get("bvid") or "").strip()
    if not _BVID_RE.match(bvid):
        return None
    title = str(v.get("title") or f"Bilibili {bvid}")
    desc = str(v.get("description") or v.get("desc") or "")[:4000]
    created = v.get("created")
    published = None
    if isinstance(created, (int, float)) and created > 0:
        published = datetime.fromtimestamp(int(created), tz=timezone.utc)
    pic = str(v.get("pic") or "").strip() or None
    if pic and pic.startswith("//"):
        pic = "https:" + pic
    return CollectItem(
        source="bilibili",
        title=title,
        content=desc or f"{up_name}: {title}",
        url=f"https://www.bilibili.com/video/{bvid}",
        published_at=published,
        embed_provider="bilibili",
        embed_id=bvid,
        embed_url=f"https://player.bilibili.com/player.html?bvid={bvid}&high_quality=1",
        thumbnail_url=pic,
        raw={
            "mid": mid,
            "up_name": up_name,
            "bvid": bvid,
            "aid": v.get("aid"),
            "length": v.get("length"),
            "play": v.get("play"),
            "comment": v.get("comment"),
            "video_review": v.get("video_review"),
        },
    )


def collect_space_videos(
    mid: str,
    *,
    source_label: str = "",
    limit: int = 30,
    timeout: float = 30.0,
    retries: int = 3,
    since: str | None = None,
) -> list[CollectItem]:
    """Pull recent uploads via public space arc/search (no media download)."""
    mid = resolve_mid(mid)
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            since_dt = None
    space_url = f"https://space.bilibili.com/{mid}"
    m_space = f"https://m.bilibili.com/space/{mid}"
    headers = {**_HEADERS, "Referer": m_space, "Origin": "https://m.bilibili.com"}
    logger.info("bilibili_space_fetch mid=%s limit=%s", mid, limit)

    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        # Warm cookies — reduces -412 / -799 bans on arc/search
        client.get(m_space)
        client.get(space_url)

        up_name = source_label or f"mid:{mid}"
        try:
            card = client.get(f"https://api.bilibili.com/x/web-interface/card?mid={mid}")
            card.raise_for_status()
            cjson = card.json()
            if cjson.get("code") == 0:
                name = (((cjson.get("data") or {}).get("card") or {}).get("name")) or ""
                if name:
                    up_name = name
        except Exception as exc:  # noqa: BLE001
            logger.warning("bilibili_card_fail mid=%s err=%s", mid, exc)

        ps = min(max(limit, 1), 50)
        payload: dict[str, Any] | None = None
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            search = client.get(
                "https://api.bilibili.com/x/space/arc/search",
                params={"mid": mid, "ps": ps, "pn": 1, "order": "pubdate"},
            )
            ctype = search.headers.get("content-type") or ""
            if search.status_code == 412 or "application/json" not in ctype:
                last_err = RuntimeError(
                    f"arc/search banned or non-json status={search.status_code}"
                )
                logger.warning(
                    "bilibili_arc_nonjson mid=%s attempt=%s status=%s",
                    mid,
                    attempt,
                    search.status_code,
                )
                time.sleep(min(2 ** attempt, 12))
                continue
            search.raise_for_status()
            payload = search.json()
            code = payload.get("code")
            if code == 0:
                break
            last_err = RuntimeError(
                f"arc/search code={code} msg={payload.get('message')}"
            )
            logger.warning(
                "bilibili_arc_retry mid=%s attempt=%s code=%s msg=%s",
                mid,
                attempt,
                code,
                payload.get("message"),
            )
            # -799 rate limit / -412 ban: backoff
            time.sleep(min(2 ** attempt, 12))
            payload = None
        if payload is None:
            raise last_err or RuntimeError("arc/search failed")
        vlist = (((payload.get("data") or {}).get("list") or {}).get("vlist")) or []

    items: list[CollectItem] = []
    for v in vlist[:limit]:
        if not isinstance(v, dict):
            continue
        item = _item_from_vlist(v, mid=mid, up_name=up_name)
        if item:
            if since_dt and item.published_at and item.published_at <= since_dt:
                continue
            items.append(item)
    logger.info(
        "bilibili_space_done mid=%s up=%s items=%s since=%s",
        mid,
        up_name,
        len(items),
        since,
    )
    return items


def collect_by_account(
    account: str, *, source_label: str = "", limit: int = 30, since: str | None = None
) -> list[CollectItem]:
    """account 为 BVxxx 时拉单条；否则按 mid / 空间 URL 拉投稿更新。"""
    acc = (account or "").strip()
    if not acc:
        return []
    if _BVID_RE.match(acc):
        return collect_by_bvid(acc, title=source_label or None)
    mid = resolve_mid(acc)
    return collect_space_videos(mid, source_label=source_label, limit=limit, since=since)

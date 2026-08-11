"""RSS / web collector — demo + feed URL + HTML page."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

import feedparser
import httpx

from pipeline.normalize import CollectItem

logger = logging.getLogger("newsc.rss_cli.collector")

DEMO_ITEMS = [
    {
        "title": "本地 AI 助手如何改变信息消费",
        "content": "随着本地运行的 LLM 与 Agent 网关普及，个人资讯站可以把摘要与分类放在设备侧完成，降低延迟并保护隐私。",
        "url": "https://example.com/news/local-ai-reading",
        "content_type": "news",
    },
    {
        "title": "开源情报采集的模块化实践",
        "content": "每类信源独立采集器、统一 hash 去重与增量游标，是可维护情报管道的基础。财经市场波动仍需人工复核。",
        "url": "https://example.com/news/modular-collectors",
        "content_type": "news",
    },
    {
        "title": "晨报产品的交互原则",
        "content": "摘要先行、决策成本要低、视频链接嵌入即播。首页应是今日洞察而不是监控仪表盘。",
        "url": "https://example.com/news/morning-digest-ux",
        "content_type": "news",
    },
    {
        "title": "信息流版式参考图",
        "content": "演示图片类型条目：用于内容类型筛选「图片」。",
        "url": "https://picsum.photos/seed/newsc/1200/675.jpg",
        "content_type": "image",
        "thumbnail_url": "https://picsum.photos/seed/newsc/640/360.jpg",
    },
]

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DATE_RE = re.compile(r'Global\.date\s*=\s*"(\d{8})"', re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']|'
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
    re.I,
)
_MAIN_BLOCK_RE = re.compile(
    r'(?:id=["\']block_\d+["\']|class=["\'][^"\']*content-main[^"\']*["\']|'
    r"<article\b|<main\b|id=[\"']content[\"']|class=[\"'][^\"']*\barticle\b[^\"']*[\"'])"
    r"[\s\S]{200,50000}",
    re.I,
)


def collect_demo() -> list[CollectItem]:
    now = datetime.now(timezone.utc)
    return [
        CollectItem(
            source="rss",
            title=d["title"],
            content=d["content"],
            url=d["url"],
            published_at=now,
            content_type=d.get("content_type"),
            thumbnail_url=d.get("thumbnail_url"),
            raw={"demo": True, "content_type": d.get("content_type")},
        )
        for d in DEMO_ITEMS
    ]


def collect_feed(url: str, *, limit: int = 30) -> list[CollectItem]:
    parsed = feedparser.parse(url)
    items: list[CollectItem] = []
    for entry in parsed.entries[:limit]:
        published = None
        if getattr(entry, "published", None):
            try:
                published = parsedate_to_datetime(entry.published)
            except Exception:  # noqa: BLE001
                published = None
        content = ""
        if getattr(entry, "summary", None):
            content = entry.summary
        elif getattr(entry, "description", None):
            content = entry.description
        items.append(
            CollectItem(
                source="rss",
                title=getattr(entry, "title", "") or "",
                content=content,
                url=getattr(entry, "link", None),
                published_at=published,
                raw={"id": getattr(entry, "id", None)},
            )
        )
    return items


def _decode_html(resp: httpx.Response) -> str:
    ctype = (resp.headers.get("content-type") or "").lower()
    raw = resp.content
    for enc in ("utf-8", "gbk", "gb2312", "big5"):
        if enc in ctype:
            try:
                return raw.decode(enc)
            except Exception:  # noqa: BLE001
                break
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    if m:
        try:
            return raw.decode(m.group(1), errors="ignore")
        except Exception:  # noqa: BLE001
            pass
    return raw.decode("utf-8", errors="ignore")


def _strip_to_text(html: str, *, limit: int = 8000) -> str:
    cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", cleaned)
    cleaned = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", cleaned)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</(div|h[1-6]|li|tr)>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = cleaned.replace("\xa0", " ").replace("&nbsp", " ")
    cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:limit]


def _page_title(html: str) -> str:
    m = _META_OG_RE.search(html)
    if m:
        return unescape((m.group(1) or m.group(2) or "").strip())
    m = _TITLE_RE.search(html)
    if m:
        return unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    return ""


def _extract_main_html(html: str) -> str:
    m = _MAIN_BLOCK_RE.search(html)
    if m:
        chunk = m.group(0)
        # drop leading tag/attr fragment so strip starts at real content
        gt = chunk.find(">")
        return chunk[gt + 1 :] if gt != -1 else chunk
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", html)
    return m.group(1) if m else html


def _canonicalize_web_url(url: str, html: str) -> tuple[str, str | None]:
    """If page exposes Global.date and looks like a daily index, pin to dated URL."""
    dates = _DATE_RE.findall(html)
    if not dates:
        return url, None
    # Pages may embed an old default then overwrite; prefer the latest YYYYMMDD.
    date = max(dates)
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path.endswith((".shtml", ".html", ".htm")):
        return url, date
    if not path.endswith("/"):
        path = path + "/"
    dated = f"{parsed.scheme}://{parsed.netloc}{path}{date}.shtml"
    return dated, date


def collect_page(url: str, *, source_label: str = "", timeout: float = 30.0) -> list[CollectItem]:
    """Fetch a web page and extract title + main text (no media download)."""
    target = (url or "").strip()
    if not target:
        return []
    logger.info("web_page_fetch url=%s", target)
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        resp = client.get(target)
        resp.raise_for_status()
        html = _decode_html(resp)
        canonical, date = _canonicalize_web_url(str(resp.url), html)
        if canonical != str(resp.url):
            logger.info(
                "web_page_canonical from=%s to=%s date=%s", resp.url, canonical, date
            )
            try:
                resp2 = client.get(canonical)
                if resp2.status_code == 200 and len(resp2.content) > 500:
                    html = _decode_html(resp2)
                    target = canonical
                else:
                    target = str(resp.url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("web_page_dated_fail url=%s err=%s", canonical, exc)
                target = str(resp.url)
        else:
            target = canonical

    title = _page_title(html) or source_label or target
    if date and date not in title:
        title = f"{title} · {date[:4]}-{date[4:6]}-{date[6:]}"
    main_html = _extract_main_html(html)
    text = _strip_to_text(main_html)
    if len(text) < 40:
        text = _strip_to_text(html)
    if len(text) < 20:
        raise RuntimeError(f"web page extract empty: {target}")

    published = None
    if date:
        try:
            published = datetime(
                int(date[:4]), int(date[4:6]), int(date[6:8]), tzinfo=timezone.utc
            )
        except ValueError:
            published = None
    if published is None:
        published = datetime.now(timezone.utc)

    item = CollectItem(
        source="web",
        title=title[:300],
        content=text,
        url=target,
        published_at=published,
        content_type="news",
        raw={"kind": "web_page", "source_url": url, "date": date},
    )
    logger.info("web_page_done url=%s title=%s chars=%s", target, title[:80], len(text))
    return [item]

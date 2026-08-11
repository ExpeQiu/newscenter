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

# 优先更具体的主栏；content-main 常含侧栏，放后面并由去噪剥离
_MAIN_SELECTORS: list[re.Pattern[str]] = [
    re.compile(
        r'<div[^>]*class=["\'][^"\']*content-main-fl[^"\']*["\'][^>]*>[\s\S]*?'
        r'(?=<div[^>]*class=["\'][^"\']*content-main-fr|<!--\s*content-main|</div>\s*</div>\s*<!--)',
        re.I,
    ),
    re.compile(
        r'<(?:article|main)\b[^>]*>[\s\S]{200,80000}?</(?:article|main)>',
        re.I,
    ),
    re.compile(
        r'<div[^>]*(?:id|class)=["\'][^"\']*(?:article-content|news-content|newscont|main-content|'
        r'post-content|entry-content|content-main|正文)[^"\']*["\'][^>]*>[\s\S]{200,80000}',
        re.I,
    ),
    re.compile(r'<div[^>]*id=["\']block_\d+["\'][^>]*>[\s\S]{120,40000}</div>', re.I),
]

_NOISE_TAG_RE = re.compile(
    r"<(aside|nav|footer|header|form|iframe|svg)\b[^>]*>[\s\S]*?</\1>",
    re.I,
)
# 按 class/id 关键字剥离广告、侧栏、悬浮、分享、页脚等（非贪婪到同层闭合较难，迭代剥离）
_NOISE_ATTR_RE = re.compile(
    r"<(?:div|section|ul|dl|table)\b[^>]*(?:id|class)=[\"'][^\"']*(?:"
    r"side(?:bar|nav)?|sidenav|nav-r|nav-content|topHeader|top-bg|"
    r"ad-banner|banner-ad|top-banner|foot(?:er)?|"
    r"content-main-fr|recommend|hot-news|hotlist|login|register|share|bdshare|"
    r"ad(?:s|vert|link|box|_|\b)|float|fixed|popup|modal|toolbar|backtop|qrcode|"
    r"app-download|download-app|copyright|friendlink|友情链接"
    r")[^\"']*[\"'][^>]*>",
    re.I,
)

_BOILERPLATE_CUT_RE = re.compile(
    r"(?:"
    r"免责声明|法律声明|风险提示|版权所有|Copyright\s+\w|"
    r"关于同花顺|软件下载|友情链接|投资者关系|联系我们|招聘英才|网友意见箱|"
    r"回顶部|扫码关注|下载APP|立即下载|开通会员|相关推荐|热门推荐|猜你喜欢|"
    r"责任编辑[:：]|来源[:：]\s*$"
    r")",
    re.I | re.M,
)

_NOISE_LINE_RE = re.compile(
    r"^(?:"
    r"[|｜]+|"
    r"更多>?|"
    r"查看.+>|"
    r"登录|注册|首页|资讯|行情|数据|"
    r"代码|简称|事项|原因|"
    r"全球市场|热点资讯|投资机会|公司资讯|"
    r"-->|"
    r"Copyright\.?$|"
    r"浙江同花顺.+"
    r")$",
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


def collect_feed(url: str, *, limit: int = 30, since: str | None = None) -> list[CollectItem]:
    since_dt = None
    if since:
        try:
            since_dt = parsedate_to_datetime(since) if "," in since else None
        except Exception:  # noqa: BLE001
            since_dt = None
        if since_dt is None:
            try:
                from datetime import datetime

                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = None

    parsed = feedparser.parse(url)
    items: list[CollectItem] = []
    for entry in parsed.entries[:limit]:
        published = None
        if getattr(entry, "published", None):
            try:
                published = parsedate_to_datetime(entry.published)
            except Exception:  # noqa: BLE001
                published = None
        if since_dt and published and published <= since_dt:
            continue
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


def _drop_element_from(html: str, start: int) -> str:
    """从 start 处的开标签起，按标签栈删除整块元素；失败则删到下一个同级开/闭标签。"""
    m = re.match(r"<([a-z0-9]+)\b[^>]*>", html[start:], re.I)
    if not m:
        return html[:start] + html[start + 1 :]
    tag = m.group(1).lower()
    i = start + m.end()
    if html[start : start + m.end()].endswith("/>"):
        return html[:start] + html[start + m.end() :]
    depth = 1
    open_re = re.compile(rf"<{tag}\b[^>]*>", re.I)
    close_re = re.compile(rf"</{tag}\s*>", re.I)
    while i < len(html) and depth > 0:
        mo = open_re.search(html, i)
        mc = close_re.search(html, i)
        if mc is None:
            return html[:start] + html[i:]
        if mo and mo.start() < mc.start():
            depth += 1
            i = mo.end()
        else:
            depth -= 1
            i = mc.end()
    return html[:start] + html[i:]


def _remove_noise_html(html: str) -> str:
    """剥离脚本样式、语义噪音标签，以及广告/侧栏/页脚等区块。"""
    out = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    out = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", out)
    out = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", out)
    out = _NOISE_TAG_RE.sub(" ", out)
    # 迭代删除带噪音 class/id 的块（侧栏、广告、悬浮等）
    for _ in range(40):
        m = _NOISE_ATTR_RE.search(out)
        if not m:
            break
        nxt = _drop_element_from(out, m.start())
        if nxt == out:
            out = out[: m.start()] + out[m.end() :]
        else:
            out = nxt
    return out


def _trim_boilerplate_text(text: str) -> str:
    """正文末尾常见页脚/推荐截断，并丢掉导航残片行。"""
    if not text:
        return ""
    cut = _BOILERPLATE_CUT_RE.search(text)
    if cut and cut.start() > 200:
        text = text[: cut.start()].rstrip()

    lines: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        if _NOISE_LINE_RE.match(s):
            continue
        if len(s) <= 2 and s in {"|", "｜", "·", "-", "—"}:
            continue
        lines.append(s)
    # 折叠空行
    out: list[str] = []
    for ln in lines:
        if ln == "" and (not out or out[-1] == ""):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _strip_to_text(html: str, *, limit: int = 12000) -> str:
    cleaned = _remove_noise_html(html)
    cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</p>", "\n", cleaned)
    cleaned = re.sub(r"(?i)</(div|h[1-6]|li|tr|dd|dt)>", "\n", cleaned)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = cleaned.replace("\xa0", " ").replace("&nbsp", " ")
    cleaned = re.sub(r"[ \t\f\v]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return _trim_boilerplate_text(cleaned.strip())[:limit]


def _page_title(html: str) -> str:
    m = _META_OG_RE.search(html)
    if m:
        return unescape((m.group(1) or m.group(2) or "").strip())
    m = _TITLE_RE.search(html)
    if m:
        return unescape(re.sub(r"\s+", " ", m.group(1)).strip())
    return ""


def _slice_element_at(html: str, start: int) -> str:
    """从 start 开标签截取完整元素（含开闭标签）。"""
    m = re.match(r"<([a-z0-9]+)\b[^>]*>", html[start:], re.I)
    if not m:
        return ""
    tag = m.group(1).lower()
    if html[start : start + m.end()].endswith("/>"):
        return html[start : start + m.end()]
    depth = 1
    i = start + m.end()
    open_re = re.compile(rf"<{tag}\b[^>]*>", re.I)
    close_re = re.compile(rf"</{tag}\s*>", re.I)
    while i < len(html) and depth > 0:
        mo = open_re.search(html, i)
        mc = close_re.search(html, i)
        if mc is None:
            return html[start:i]
        if mo and mo.start() < mc.start():
            depth += 1
            i = mo.end()
        else:
            depth -= 1
            i = mc.end()
    return html[start:i]


def _salvage_lead_html(html: str) -> str:
    """保留可能被装饰容器包住的金句 / 收盘指数等导语块。"""
    parts: list[str] = []
    for m in re.finditer(
        r'<div[^>]*id=["\']block_\d+["\'][^>]*>([\s\S]*?)</div>',
        html,
        re.I,
    ):
        inner = m.group(1)
        text = unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        if 16 <= len(text) <= 320 and (
            "——" in text or "—" in text or "&mdash;" in inner or "mdash" in inner.lower()
        ):
            parts.append(f"<div>{inner}</div>")

    m2 = re.search(r'<div[^>]*class=["\'][^"\']*\byestoday\b[^"\']*["\'][^>]*>', html, re.I)
    if m2:
        chunk = _slice_element_at(html, m2.start())
        if "收盘" in chunk or "指数" in chunk:
            parts.append(chunk)

    return "\n".join(parts)


def _extract_main_html(html: str) -> str:
    """抽取主内容 HTML；去噪后优先 content 主栏，避免侧栏/页脚。"""
    lead = _salvage_lead_html(html)
    cleaned = _remove_noise_html(html)

    def _score(body: str) -> int:
        text_len = len(re.sub(r"<[^>]+>", "", body))
        low = body.lower()
        penalty = 0
        if "content-main-fr" in low or "sidenav" in low or "sideNav" in body:
            penalty += 2000
        if "免责声明" in body or "Copyright" in body:
            penalty += 800
        return text_len - penalty

    candidates: list[tuple[int, str, str]] = []

    # 1) 整页 content 容器（含收盘指数 + 左栏正文；侧栏已去）
    m = re.search(
        r'<div[^>]*class=["\'](?:[^"\']*\s)?content(?:\s[^"\']*)?["\'][^>]*>[\s\S]{200,120000}',
        cleaned,
        re.I,
    )
    if m:
        chunk = m.group(0)
        gt = chunk.find(">")
        body = chunk[gt + 1 :] if gt != -1 else chunk
        candidates.append((_score(body), "content", body))

    for label, sel in (
        ("content-main-fl", _MAIN_SELECTORS[0]),
        ("article", _MAIN_SELECTORS[1]),
        ("article-like", _MAIN_SELECTORS[2]),
        ("block", _MAIN_SELECTORS[3]),
    ):
        for sm in sel.finditer(cleaned):
            chunk = sm.group(0)
            gt = chunk.find(">")
            body = chunk[gt + 1 :] if gt != -1 else chunk
            candidates.append((_score(body), label, body))

    best = ""
    label = "body"
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        score, label, best = candidates[0]
        if score < 120:
            best = ""
        else:
            logger.info("web_page_main_hit label=%s score=%s chars=%s", label, score, len(best))

    if not best:
        m = re.search(r"(?is)<body[^>]*>(.*)</body>", cleaned)
        logger.info("web_page_main_fallback=body")
        best = m.group(1) if m else cleaned

    if lead:
        # 避免 lead 已包含在 best 中时重复
        lead_txt = re.sub(r"<[^>]+>", "", lead)
        best_txt = re.sub(r"<[^>]+>", "", best)
        if lead_txt.strip() and lead_txt.strip()[:40] not in best_txt:
            best = lead + "\n" + best
            logger.info("web_page_lead_prepended chars=%s", len(lead))
    return best


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

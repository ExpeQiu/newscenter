"""RSS collector — demo + feed URL."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from pipeline.normalize import CollectItem

DEMO_ITEMS = [
    {
        "title": "本地 AI 助手如何改变信息消费",
        "content": "随着本地运行的 LLM 与 Agent 网关普及，个人资讯站可以把摘要与分类放在设备侧完成，降低延迟并保护隐私。",
        "url": "https://example.com/news/local-ai-reading",
    },
    {
        "title": "开源情报采集的模块化实践",
        "content": "每类信源独立采集器、统一 hash 去重与增量游标，是可维护情报管道的基础。财经市场波动仍需人工复核。",
        "url": "https://example.com/news/modular-collectors",
    },
    {
        "title": "晨报产品的交互原则",
        "content": "摘要先行、决策成本要低、视频链接嵌入即播。首页应是今日洞察而不是监控仪表盘。",
        "url": "https://example.com/news/morning-digest-ux",
    },
]


def collect_demo() -> list[CollectItem]:
    now = datetime.now(timezone.utc)
    return [
        CollectItem(
            source="rss",
            title=d["title"],
            content=d["content"],
            url=d["url"],
            published_at=now,
            raw={"demo": True},
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

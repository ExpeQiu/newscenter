"""Bilibili demo collector — player embed metadata."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.normalize import CollectItem

DEMO = [
    {
        "title": "【演示】B站嵌入播放样例 BV1GJ411x7h7",
        "content": "使用 Bilibili player 嵌入；无法嵌入时详情页降级为外链。",
        "bvid": "BV1GJ411x7h7",
    },
]


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

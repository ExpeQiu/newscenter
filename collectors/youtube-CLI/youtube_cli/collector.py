"""YouTube demo collector — embed metadata only."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline.normalize import CollectItem

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

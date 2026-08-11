"""Normalize + content hash helpers."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# news | image | video （可扩展）
CONTENT_TYPES = ("news", "image", "video")


class CollectItem(BaseModel):
    source: str
    title: str = ""
    content: str = ""
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    embed_provider: Optional[str] = None
    embed_id: Optional[str] = None
    embed_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    content_type: Optional[str] = None  # 显式指定；空则推断
    raw: dict[str, Any] = Field(default_factory=dict)


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


_IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp|svg)(\?|$)", re.I)


def infer_content_type(item: CollectItem) -> str:
    """Infer content_type: news | image | video."""
    explicit = (item.content_type or item.raw.get("content_type") or "").strip().lower()
    if explicit in CONTENT_TYPES:
        return explicit
    if item.embed_provider in ("youtube", "bilibili") or item.source in ("youtube", "bilibili"):
        return "video"
    url = item.url or ""
    if _IMAGE_EXT.search(url) or (item.raw.get("mime") or "").startswith("image/"):
        return "image"
    return "news"


def content_hash(item: CollectItem) -> str:
    """Hash of url+title+normalized body (or embed id)."""
    key_parts = [
        _norm(item.url or ""),
        _norm(item.title),
        _norm(item.content)[:2000],
        _norm(item.embed_provider or ""),
        _norm(item.embed_id or ""),
    ]
    blob = "|".join(key_parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()

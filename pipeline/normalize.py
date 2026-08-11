"""Normalize + content hash helpers."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
    raw: dict[str, Any] = Field(default_factory=dict)


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


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

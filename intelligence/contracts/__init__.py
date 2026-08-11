"""AI capability contracts (Pydantic)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field


class ItemRef(BaseModel):
    id: str
    title: str = ""
    body: str = ""
    summary: Optional[str] = None
    url: Optional[str] = None
    source_type: str = "rss"
    ai_category: Optional[str] = None
    category_locked: bool = False


class SummarizeIn(BaseModel):
    item: ItemRef


class SummarizeOut(BaseModel):
    summary: str
    model_meta: dict[str, Any] = Field(default_factory=dict)


class ClassifyIn(BaseModel):
    item: ItemRef


class ClassifyOut(BaseModel):
    category: str
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    skipped: bool = False
    model_meta: dict[str, Any] = Field(default_factory=dict)


class DigestIn(BaseModel):
    digest_date: date
    items: list[ItemRef]


class DigestOut(BaseModel):
    markdown: str
    highlights: list[str] = Field(default_factory=list)
    model_meta: dict[str, Any] = Field(default_factory=dict)


class RecommendIn(BaseModel):
    user_signals: dict[str, Any] = Field(default_factory=dict)
    candidates: list[ItemRef]
    as_of: date


class RecommendItem(BaseModel):
    id: str
    score: float
    reason: str


class RecommendOut(BaseModel):
    items: list[RecommendItem]
    model_meta: dict[str, Any] = Field(default_factory=dict)


class AskIn(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)
    question: str


class AskOut(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    model_meta: dict[str, Any] = Field(default_factory=dict)

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


class RetrieveEventsIn(BaseModel):
    query_id: str
    query: str
    dimension: str
    industry: Optional[str] = None
    entity: Optional[str] = None


class RetrievedEvent(BaseModel):
    title: str
    summary: str = ""
    occurred_at: Optional[str] = None  # ISO8601
    industry: Optional[str] = None
    entity: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)


class RetrieveEventsOut(BaseModel):
    events: list[RetrievedEvent] = Field(default_factory=list)
    model_meta: dict[str, Any] = Field(default_factory=dict)


class RetrieveMacroIn(BaseModel):
    query_id: str
    query: str
    scope: str
    indicator_id: str
    label: str = ""
    unit: str = ""
    industry: Optional[str] = None


class RetrievedObservation(BaseModel):
    value: Optional[float] = None
    value_text: Optional[str] = None
    observed_at: Optional[str] = None  # ISO8601
    period_label: str = ""
    source_urls: list[str] = Field(default_factory=list)


class RetrieveMacroOut(BaseModel):
    observations: list[RetrievedObservation] = Field(default_factory=list)
    label: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    model_meta: dict[str, Any] = Field(default_factory=dict)

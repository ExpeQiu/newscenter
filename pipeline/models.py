"""SQLAlchemy models for newsc."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid4())


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # rss|youtube|bilibili
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    cursor: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["Item"]] = relationship(back_populates="source")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_items_content_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sources.id"), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="rss")
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embed_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embed_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embed_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    source: Mapped[Optional[Source]] = relationship(back_populates="items")
    marks: Mapped[Optional["Mark"]] = relationship(back_populates="item", uselist=False)
    item_tags: Mapped[list["ItemTag"]] = relationship(back_populates="item")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class ItemTag(Base):
    __tablename__ = "item_tags"
    __table_args__ = (UniqueConstraint("item_id", "tag_id", name="uq_item_tag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("items.id", ondelete="CASCADE"))
    tag_id: Mapped[str] = mapped_column(String(36), ForeignKey("tags.id", ondelete="CASCADE"))
    origin: Mapped[str] = mapped_column(String(20), default="ai")  # user|ai

    item: Mapped[Item] = relationship(back_populates="item_tags")
    tag: Mapped[Tag] = relationship()


class Mark(Base):
    __tablename__ = "marks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("items.id", ondelete="CASCADE"), unique=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    item: Mapped[Item] = relationship(back_populates="marks")


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "item_id", name="uq_collection_item"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(String(36), ForeignKey("collections.id", ondelete="CASCADE"))
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("items.id", ondelete="CASCADE"))


class Digest(Base):
    __tablename__ = "digests"
    __table_args__ = (UniqueConstraint("digest_date", name="uq_digest_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, default="")
    highlights: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("items.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiJob(Base):
    __tablename__ = "ai_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # summarize|classify|digest|recommend
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    pipeline_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

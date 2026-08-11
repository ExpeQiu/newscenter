"""initial newsc schema

Revision ID: 0001
Revises:
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default="{}"),
        sa.Column("cursor", postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("source_type", sa.String(50), server_default="rss"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), server_default=""),
        sa.Column("body", sa.Text(), server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embed_provider", sa.String(50), nullable=True),
        sa.Column("embed_id", sa.String(100), nullable=True),
        sa.Column("embed_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("ai_category", sa.String(100), nullable=True),
        sa.Column("category_locked", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("raw", postgresql.JSONB(), server_default="{}"),
        sa.UniqueConstraint("content_hash", name="uq_items_content_hash"),
    )
    op.create_index("ix_items_content_hash", "items", ["content_hash"])
    op.create_table(
        "tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        "item_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE")),
        sa.Column("origin", sa.String(20), server_default="ai"),
        sa.UniqueConstraint("item_id", "tag_id", name="uq_item_tag"),
    )
    op.create_table(
        "marks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE"), unique=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_starred", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "collections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
    )
    op.create_table(
        "collection_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("collection_id", sa.String(36), sa.ForeignKey("collections.id", ondelete="CASCADE")),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.UniqueConstraint("collection_id", "item_id", name="uq_collection_item"),
    )
    op.create_table(
        "digests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("digest_date", sa.Date(), nullable=False),
        sa.Column("markdown", sa.Text(), server_default=""),
        sa.Column("highlights", postgresql.JSONB(), server_default="[]"),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("digest_date", name="uq_digest_date"),
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column("score", sa.Float(), server_default="0"),
        sa.Column("reason", sa.Text(), server_default=""),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("pipeline_id", sa.String(100), nullable=False),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("stats", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(20), server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    for t in (
        "pipeline_runs",
        "ai_jobs",
        "recommendations",
        "digests",
        "collection_items",
        "collections",
        "marks",
        "item_tags",
        "tags",
        "items",
        "sources",
    ):
        op.drop_table(t)

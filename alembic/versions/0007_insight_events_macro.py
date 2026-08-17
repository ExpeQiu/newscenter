"""insight_events + macro_indicators + macro_observations

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insight_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dimension", sa.String(32), nullable=False),
        sa.Column("industry", sa.String(64), nullable=True),
        sa.Column("entity", sa.String(120), nullable=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_urls", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("query_id", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("content_hash", name="uq_insight_events_content_hash"),
    )
    op.create_index("ix_insight_events_occurred_at", "insight_events", ["occurred_at"])
    op.create_index("ix_insight_events_dimension", "insight_events", ["dimension"])
    op.create_index("ix_insight_events_industry", "insight_events", ["industry"])
    op.create_index("ix_insight_events_entity", "insight_events", ["entity"])
    op.create_index("ix_insight_events_query_id", "insight_events", ["query_id"])
    op.create_index("ix_insight_events_content_hash", "insight_events", ["content_hash"])

    op.create_table(
        "macro_indicators",
        sa.Column("indicator_id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False, server_default=""),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("industry", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_macro_indicators_scope", "macro_indicators", ["scope"])
    op.create_index("ix_macro_indicators_industry", "macro_indicators", ["industry"])

    op.create_table(
        "macro_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "indicator_id",
            sa.String(64),
            sa.ForeignKey("macro_indicators.indicator_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=True),
        sa.Column("value_text", sa.String(120), nullable=True),
        sa.Column("period_label", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_urls", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("raw", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "indicator_id",
            "observed_at",
            "period_label",
            name="uq_macro_obs_indicator_time_period",
        ),
    )
    op.create_index("ix_macro_observations_indicator_id", "macro_observations", ["indicator_id"])
    op.create_index("ix_macro_observations_observed_at", "macro_observations", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_macro_observations_observed_at", table_name="macro_observations")
    op.drop_index("ix_macro_observations_indicator_id", table_name="macro_observations")
    op.drop_table("macro_observations")
    op.drop_index("ix_macro_indicators_industry", table_name="macro_indicators")
    op.drop_index("ix_macro_indicators_scope", table_name="macro_indicators")
    op.drop_table("macro_indicators")
    op.drop_index("ix_insight_events_content_hash", table_name="insight_events")
    op.drop_index("ix_insight_events_query_id", table_name="insight_events")
    op.drop_index("ix_insight_events_entity", table_name="insight_events")
    op.drop_index("ix_insight_events_industry", table_name="insight_events")
    op.drop_index("ix_insight_events_dimension", table_name="insight_events")
    op.drop_index("ix_insight_events_occurred_at", table_name="insight_events")
    op.drop_table("insight_events")

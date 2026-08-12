"""cloud_outbox + control_settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("origin", sa.String(20), nullable=False, server_default="cloud"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cloud_outbox_kind", "cloud_outbox", ["kind"])
    op.create_index("ix_cloud_outbox_status", "cloud_outbox", ["status"])

    op.create_table(
        "control_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("control_settings")
    op.drop_index("ix_cloud_outbox_status", table_name="cloud_outbox")
    op.drop_index("ix_cloud_outbox_kind", table_name="cloud_outbox")
    op.drop_table("cloud_outbox")

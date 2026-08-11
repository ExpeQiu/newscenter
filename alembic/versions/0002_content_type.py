"""initial content_type on items

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("content_type", sa.String(50), server_default="news", nullable=False),
    )
    op.create_index("ix_items_content_type", "items", ["content_type"])


def downgrade() -> None:
    op.drop_index("ix_items_content_type", table_name="items")
    op.drop_column("items", "content_type")

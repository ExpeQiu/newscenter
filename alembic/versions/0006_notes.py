"""note_columns + notes

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "note_columns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("name", name="uq_note_columns_name"),
    )
    op.create_table(
        "notes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("column_id", sa.String(36), sa.ForeignKey("note_columns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("digest_date", sa.Date(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_notes_column_id", "notes", ["column_id"])
    op.create_index("ix_notes_item_id", "notes", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_notes_item_id", table_name="notes")
    op.drop_index("ix_notes_column_id", table_name="notes")
    op.drop_table("notes")
    op.drop_table("note_columns")

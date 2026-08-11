"""digest vault HTML 入库表

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "digest_vault_sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("label", sa.String(200), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("origin_path", sa.Text(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "digest_vault_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=False, server_default=""),
        sa.Column("rel_path", sa.Text(), nullable=False),
        sa.Column("name", sa.String(500), nullable=False, server_default=""),
        sa.Column("mtime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("html", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("source_id", "rel_path", name="uq_vault_file_source_path"),
    )
    op.create_index("ix_digest_vault_files_source_id", "digest_vault_files", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_digest_vault_files_source_id", table_name="digest_vault_files")
    op.drop_table("digest_vault_files")
    op.drop_table("digest_vault_sources")

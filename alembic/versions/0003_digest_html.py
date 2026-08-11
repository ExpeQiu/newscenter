"""digests html + source columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("digests", sa.Column("html", sa.Text(), server_default="", nullable=False))
    op.add_column("digests", sa.Column("source", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("digests", "source")
    op.drop_column("digests", "html")

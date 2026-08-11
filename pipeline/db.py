"""DB engine and session helpers."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from pipeline.settings import get_settings

_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_content_type_column() -> None:
    """Idempotent column + backfill for existing DBs created before content_type."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE items ADD COLUMN IF NOT EXISTS content_type VARCHAR(50) DEFAULT 'news'"
            )
        )
        conn.execute(
            text(
                """
                UPDATE items SET content_type = 'video'
                WHERE (content_type IS NULL OR content_type = '' OR content_type = 'news')
                  AND (
                    embed_provider IN ('youtube', 'bilibili')
                    OR source_type IN ('youtube', 'bilibili')
                  )
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE items SET content_type = 'news'
                WHERE content_type IS NULL OR content_type = ''
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_items_content_type ON items (content_type)"))


def _ensure_digest_html_columns() -> None:
    """Idempotent digests.html / digests.source for DBs created before HTML push."""
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE digests ADD COLUMN IF NOT EXISTS html TEXT DEFAULT ''"))
        conn.execute(text("ALTER TABLE digests ADD COLUMN IF NOT EXISTS source VARCHAR(50)"))


def init_db() -> None:
    from pipeline.models import Base

    Base.metadata.create_all(bind=engine)
    try:
        _ensure_content_type_column()
        _ensure_digest_html_columns()
    except Exception:  # noqa: BLE001 — table may not exist yet on brand-new empty
        Base.metadata.create_all(bind=engine)
        _ensure_content_type_column()
        _ensure_digest_html_columns()

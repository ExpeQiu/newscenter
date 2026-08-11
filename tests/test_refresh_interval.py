"""Unit tests for refresh_interval helpers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline.refresh_interval import (
    canonicalize_refresh_interval,
    source_is_due,
    stamp_last_fetched,
)


def test_canonicalize_defaults_and_aliases() -> None:
    assert canonicalize_refresh_interval(None, stype="web") == "1h"
    assert canonicalize_refresh_interval(None, stype="youtube") == "6h"
    assert canonicalize_refresh_interval(None, stype="digest") == "1d"
    assert canonicalize_refresh_interval("daily") == "1d"
    assert canonicalize_refresh_interval("60m") == "1h"
    assert canonicalize_refresh_interval(180) == "3h"
    assert canonicalize_refresh_interval("manual") == "manual"


def test_source_is_due_respects_interval() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    assert source_is_due(refresh_interval="1h", cursor=None, now=now) is True
    assert source_is_due(refresh_interval="manual", cursor=None, now=now) is False

    recent = stamp_last_fetched({}, when=now - timedelta(minutes=30))
    assert source_is_due(refresh_interval="1h", cursor=recent, now=now) is False

    old = stamp_last_fetched({}, when=now - timedelta(hours=2))
    assert source_is_due(refresh_interval="1h", cursor=old, now=now) is True

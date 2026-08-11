"""Worker resilience: enqueue idempotency + stale recovery helpers."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

from intelligence.worker import enqueue_digest_and_recommend, recover_stale_running
from pipeline.models import AiJob


def test_enqueue_digest_skips_pending(monkeypatch):
    day = date.today()
    existing = AiJob(
        job_type="digest",
        payload={"date": day.isoformat()},
        status="pending",
    )
    existing.id = "job-existing"

    class _Q:
        def __init__(self, row):
            self.row = row

        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return self.row

    db = MagicMock()
    # first call digest -> existing; recommend -> None then add
    calls = {"n": 0}

    def query(model):
        calls["n"] += 1
        if model is AiJob and calls["n"] == 1:
            return _Q(existing)
        return _Q(None)

    db.query.side_effect = query
    ids = enqueue_digest_and_recommend(db, day=day)
    # digest skipped; recommend may be enqueued
    assert "job-existing" not in ids


def test_recover_stale_running():
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    job = AiJob(job_type="summarize", payload={}, status="running", attempts=1)
    job.id = "stale-1"
    job.updated_at = old

    class _Q:
        def filter(self, *a, **k):
            return self

        def all(self):
            return [job]

    db = MagicMock()
    db.query.return_value = _Q()
    n = recover_stale_running(db, older_than_sec=60)
    assert n == 1
    assert job.status == "pending"
    db.commit.assert_called()


def test_item_needs_job():
    from intelligence.worker import _item_needs_job
    from pipeline.models import Item

    item = Item(title="t", body="b", summary="", ai_category=None)
    assert _item_needs_job(item, "summarize", force=False) is True
    assert _item_needs_job(item, "classify", force=False) is True

    item.summary = "已有摘要"
    item.ai_category = "财经"
    assert _item_needs_job(item, "summarize", force=False) is False
    assert _item_needs_job(item, "classify", force=False) is False
    assert _item_needs_job(item, "summarize", force=True) is True

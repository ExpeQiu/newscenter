"""Unit tests for insight queries + mock retrieve upsert."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from intelligence.providers.mock import MockProvider
from pipeline import insight_queries as iq
from pipeline.insight_retrieve import run_insight_retrieve
from pipeline.models import Base, InsightEvent, MacroIndicator, MacroObservation
from pipeline.settings import get_settings


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):  # noqa: ANN001
    return "JSON"


@pytest.fixture()
def queries_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "insight-queries.yml"
    cfg.write_text(
        """
queries:
  - id: event-global-t
    kind: event
    enabled: true
    dimension: global
    query: "global events"
    refresh_interval: 1d
  - id: event-disabled
    kind: event
    enabled: false
    dimension: china
    query: "china"
    refresh_interval: 1d
  - id: macro-cn-cpi-t
    kind: macro
    enabled: true
    scope: china
    indicator_id: cn.cpi.yoy
    label: 中国 CPI 同比
    unit: "%"
    query: "china cpi"
    refresh_interval: 1d
""",
        encoding="utf-8",
    )
    local = tmp_path / "insight-queries.local.yml"
    local.write_text(
        """
queries:
  - id: event-disabled
    deleted: true
  - id: event-industry-t
    kind: event
    enabled: true
    dimension: industry
    industry: AI
    query: "ai industry"
    refresh_interval: manual
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("INSIGHT_QUERIES_FILE", str(cfg))
    get_settings.cache_clear()
    return cfg


def test_load_queries_merge_and_filter(queries_cfg: Path) -> None:
    all_q = iq.load_queries(enabled_only=False)
    ids = {q.id for q in all_q}
    assert "event-global-t" in ids
    assert "event-industry-t" in ids
    assert "event-disabled" not in ids  # deleted via local
    assert "macro-cn-cpi-t" in ids

    events = iq.load_queries(kind="event", enabled_only=True)
    assert {q.id for q in events} == {"event-global-t", "event-industry-t"}
    macros = iq.load_queries(kind="macro", enabled_only=True)
    assert len(macros) == 1
    assert macros[0].indicator_id == "cn.cpi.yoy"


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Base.metadata.tables["control_settings"],
            Base.metadata.tables["insight_events"],
            Base.metadata.tables["macro_indicators"],
            Base.metadata.tables["macro_observations"],
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_mock_retrieve_upsert_dedupe(
    queries_cfg: Path,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pipeline.insight_retrieve.create_provider", lambda: MockProvider())

    first = run_insight_retrieve(db_session, kind="all", force=True)
    assert first["errors"] == 0
    assert first["inserted"] > 0
    events_n = db_session.query(InsightEvent).count()
    obs_n = db_session.query(MacroObservation).count()
    assert events_n >= 2
    assert obs_n >= 1
    assert db_session.get(MacroIndicator, "cn.cpi.yoy") is not None

    second = run_insight_retrieve(db_session, kind="all", force=True)
    assert second["inserted"] == 0
    assert db_session.query(InsightEvent).count() == events_n
    assert db_session.query(MacroObservation).count() == obs_n

    # refresh_interval 未到期应跳过（manual 的 industry 查询 force=False 也跳过）
    third = run_insight_retrieve(db_session, kind="all", force=False)
    assert third["queries_skipped"] >= 1

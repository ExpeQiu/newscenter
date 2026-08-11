"""vault HTML 入库与 DB 回退读取。"""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.db import SessionLocal, init_db
from pipeline import digest_vault as vault
from pipeline.vault_store import (
    enrich_vault_status,
    list_html_files_smart,
    read_html_file_smart,
    sync_vault_to_db,
)


@pytest.fixture()
def vault_cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    (html_dir / "a.html").write_text("<html><body>Hello DB</body></html>", encoding="utf-8")
    cfg = tmp_path / "sources.yml"
    cfg.write_text(
        f"""
sources:
  - id: unit-db
    label: UnitDB
    path: "{html_dir.as_posix()}"
    enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGEST_SOURCES_FILE", str(cfg))
    vault.get_settings.cache_clear()
    return html_dir


def test_sync_and_db_fallback(vault_cfg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    db = SessionLocal()
    try:
        result = sync_vault_to_db(db)
        assert result["status"] == "ok"
        assert result["upserted"] >= 1

        # 模拟云端：目录不可读
        missing = vault_cfg.parent / "gone"
        cfg = Path(vault.get_settings().digest_sources_file)
        # DIGEST_SOURCES_FILE 已指向 tmp；改 path 到不存在目录
        cfg.write_text(
            f"""
sources:
  - id: unit-db
    label: UnitDB
    path: "{missing.as_posix()}"
    enabled: true
""",
            encoding="utf-8",
        )
        vault.get_settings.cache_clear()

        status = enrich_vault_status(vault.vault_status(), db)
        assert status["readable"] is True
        unit = next(s for s in status["sources"] if s["id"] == "unit-db")
        assert unit["readable"] is True
        assert unit.get("storage") == "db"

        files = list_html_files_smart(db, "unit-db", limit=10)
        assert len(files) >= 1
        content = read_html_file_smart(db, "unit-db", "a.html")
        assert "Hello DB" in content.content
    finally:
        db.close()
        vault.get_settings.cache_clear()

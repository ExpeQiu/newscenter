"""Unit tests for digest HTML vault (no API / DB)."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import digest_vault as vault


def test_list_and_read_local_demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    (html_dir / "a.html").write_text("<html><body>Hello A</body></html>", encoding="utf-8")
    (html_dir / "b.htm").write_text("<html><body>Hello B</body></html>", encoding="utf-8")
    (html_dir / "skip.txt").write_text("nope", encoding="utf-8")

    cfg = tmp_path / "sources.yml"
    cfg.write_text(
        f"""
sources:
  - id: unit
    label: Unit
    path: "{html_dir.as_posix()}"
    enabled: true
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGEST_SOURCES_FILE", str(cfg))
    vault.get_settings.cache_clear()

    status = vault.vault_status()
    assert status["readable"] is True
    assert any(s["id"] == "unit" and s["readable"] for s in status["sources"])

    files = vault.list_html_files("unit", limit=10)
    assert len(files) == 2
    assert {f.name for f in files} == {"a.html", "b.htm"}

    content = vault.read_html_file("unit", "a.html")
    assert "Hello A" in content.content

    with pytest.raises(vault.DigestVaultError):
        vault.read_html_file("unit", "../a.html")

    vault.get_settings.cache_clear()


def test_path_escape_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    outside = tmp_path / "secret.html"
    outside.write_text("<html>secret</html>", encoding="utf-8")
    (html_dir / "ok.html").write_text("<html>ok</html>", encoding="utf-8")

    cfg = tmp_path / "sources.yml"
    cfg.write_text(
        f"""
sources:
  - id: unit
    label: Unit
    path: "{html_dir.as_posix()}"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DIGEST_SOURCES_FILE", str(cfg))
    vault.get_settings.cache_clear()

    with pytest.raises(vault.DigestVaultError):
        vault.resolve_safe(vault.get_source("unit"), "../secret.html")

    vault.get_settings.cache_clear()


def test_upsert_toggle_delete_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    (html_dir / "a.html").write_text("<html>ok</html>", encoding="utf-8")
    cfg = tmp_path / "sources.yml"
    cfg.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setenv("DIGEST_SOURCES_FILE", str(cfg))
    vault.get_settings.cache_clear()

    created = vault.upsert_source(
        source_id="demo",
        label="Demo",
        path=str(html_dir),
        enabled=True,
    )
    assert created["id"] == "demo"
    assert created["readable"] is True

    disabled = vault.set_source_enabled("demo", False)
    assert disabled["enabled"] is False

    deleted = vault.delete_source("demo")
    assert deleted["deleted"] is True
    assert vault.vault_status()["sources"] == []

    vault.get_settings.cache_clear()

"""Unit tests for digest CLI helpers (no API required)."""
from digest_cli.client import DEMO_HTML, api_base


def test_demo_html_nonempty():
    assert "<article" in DEMO_HTML
    assert "Demo" in DEMO_HTML


def test_api_base_default(monkeypatch):
    monkeypatch.delenv("NEWSC_API_URL", raising=False)
    assert api_base() == "http://127.0.0.1:8787"
    assert api_base("http://x:9/") == "http://x:9"

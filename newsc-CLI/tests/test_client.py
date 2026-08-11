"""Unit tests for newsc client helpers."""
from newsc_cli.client import api_base


def test_api_base_default():
    assert api_base(None).startswith("http")

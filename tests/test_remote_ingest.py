"""Unit tests for remote ingest payload helpers."""
from pipeline.normalize import CollectItem
from pipeline.remote_ingest import items_to_payload


def test_items_to_payload_json_serializable():
    items = [
        CollectItem(source="rss", title="T", content="C", url="http://x"),
    ]
    payload = items_to_payload(items)
    assert payload[0]["source"] == "rss"
    assert payload[0]["title"] == "T"

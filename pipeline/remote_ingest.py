"""HTTP ingest helper for collector CLIs (POST /ingest/batch)."""
from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import httpx

from pipeline.normalize import CollectItem

DEFAULT_API_URL = "http://127.0.0.1:8787"


def api_base(url: str | None = None) -> str:
    return (url or os.environ.get("NEWSC_API_URL") or DEFAULT_API_URL).rstrip("/")


def items_to_payload(items: list[CollectItem]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in items:
        d = it.model_dump(mode="json")
        out.append(d)
    return out


def ingest_batch_http(
    items: list[CollectItem],
    *,
    source_name: str | None = None,
    run_id: str | None = None,
    enqueue_ai: bool = True,
    api_url: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    rid = run_id or str(uuid4())
    base = api_base(api_url)
    payload = {
        "items": items_to_payload(items),
        "source_name": source_name,
        "run_id": rid,
        "enqueue_ai": enqueue_ai,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base}/ingest/batch", json=payload)
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"ingest failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()

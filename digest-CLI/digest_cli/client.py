"""HTTP client for NewsC digests API."""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8787"


def api_base(url: str | None = None) -> str:
    return (url or os.environ.get("NEWSC_API_URL") or DEFAULT_API_URL).rstrip("/")


def push_digest(
    *,
    html: str = "",
    markdown: str = "",
    digest_date: str | None = None,
    source: str = "cli",
    highlights: list[str] | None = None,
    run_id: str | None = None,
    api_url: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "html": html,
        "markdown": markdown,
        "source": source,
        "highlights": highlights or [],
    }
    if digest_date and digest_date != "today":
        payload["digest_date"] = digest_date
    if run_id:
        payload["run_id"] = run_id

    base = api_base(api_url)
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{base}/digests/push", json=payload)
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"push failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()


def get_today(*, api_url: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    base = api_base(api_url)
    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{base}/digests/today")
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"get failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()


def vault_status(*, api_url: str | None = None, timeout: float = 15.0) -> dict[str, Any]:
    base = api_base(api_url)
    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{base}/digests/vault/status")
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"vault status failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()


def vault_files(
    *,
    source: str | None = None,
    limit: int = 50,
    q: str | None = None,
    api_url: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    base = api_base(api_url)
    params: dict[str, Any] = {"limit": limit}
    if source:
        params["source"] = source
    if q:
        params["q"] = q
    with httpx.Client(timeout=timeout) as client:
        r = client.get(f"{base}/digests/vault/files", params=params)
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"vault files failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()


def vault_file(
    *,
    source: str,
    path: str,
    api_url: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    base = api_base(api_url)
    with httpx.Client(timeout=timeout) as client:
        r = client.get(
            f"{base}/digests/vault/file",
            params={"source": source, "path": path},
        )
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"vault file failed {r.status_code}: {r.text[:500]}",
                request=r.request,
                response=r,
            )
        return r.json()


DEMO_HTML = """<article class="newsc-digest-demo">
  <h1>今日洞察 · Demo</h1>
  <p>这是 NewsC digest-CLI 的离线样例 HTML 日报，由 <code>newsc-digest push --demo</code> 推送。</p>
  <ul>
    <li>采集管道已就绪</li>
    <li>Agent 可通过 CLI 推送 HTML</li>
    <li>Web 优先渲染 html 字段</li>
  </ul>
</article>
"""

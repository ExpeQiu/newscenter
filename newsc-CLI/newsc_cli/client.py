"""HTTP client for NewsC orchestrator."""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_URL = "http://127.0.0.1:8787"


def api_base(url: str | None = None) -> str:
    return (url or os.environ.get("NEWSC_API_URL") or DEFAULT_API_URL).rstrip("/")


class NewsCClient:
    def __init__(self, api_url: str | None = None, timeout: float = 60.0) -> None:
        self.base = api_base(api_url)
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
    ) -> Any:
        with httpx.Client(timeout=self.timeout) as client:
            r = client.request(
                method,
                f"{self.base}{path}",
                params=params,
                json=json_body,
            )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"{method} {path} failed {r.status_code}: {r.text[:500]}",
                    request=r.request,
                    response=r,
                )
            if r.status_code == 204 or not r.content:
                return {}
            return r.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def pipeline_run(self, pipeline_id: str) -> dict[str, Any]:
        return self._request("POST", f"/pipelines/{pipeline_id}/run")

    def ai_process(self, *, limit: int = 20, include_digest: bool = True) -> dict[str, Any]:
        return self._request(
            "POST",
            "/ai/jobs/process",
            json_body={"limit": limit, "include_digest": include_digest},
        )

    def vault_status(self) -> dict[str, Any]:
        return self._request("GET", "/digests/vault/status")

    def vault_files(
        self,
        *,
        source: str | None = None,
        limit: int = 50,
        q: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if source:
            params["source"] = source
        if q:
            params["q"] = q
        return self._request("GET", "/digests/vault/files", params=params)

    def vault_file(self, *, source: str, path: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/digests/vault/file",
            params={"source": source, "path": path},
        )

    def vault_ingest(self) -> dict[str, Any]:
        return self._request("POST", "/digests/vault/ingest")

    def digest_today(self) -> dict[str, Any]:
        return self._request("GET", "/digests/today")

    def items(self, *, limit: int = 20) -> dict[str, Any]:
        return self._request("GET", "/items", params={"limit": limit})

    def sources_list(self) -> dict[str, Any]:
        return self._request("GET", "/sources")

    def source_create(
        self,
        *,
        name: str,
        type_: str,
        config: dict[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/sources",
            json_body={"name": name, "type": type_, "config": config, "enabled": enabled},
        )

    def source_update(
        self,
        source_id: str,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if config is not None:
            body["config"] = config
        if enabled is not None:
            body["enabled"] = enabled
        return self._request("PATCH", f"/sources/{source_id}", json_body=body)

    def source_delete(self, source_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/sources/{source_id}")

    def vault_source_upsert(
        self,
        *,
        source_id: str,
        label: str,
        path: str,
        enabled: bool = True,
        refresh_interval: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": source_id,
            "label": label,
            "path": path,
            "enabled": enabled,
        }
        if refresh_interval is not None:
            body["refresh_interval"] = refresh_interval
        return self._request(
            "POST",
            "/digests/vault/sources",
            json_body=body,
        )

    def vault_source_set_enabled(self, source_id: str, enabled: bool) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/digests/vault/sources/{source_id}",
            json_body={"enabled": enabled},
        )

    def vault_source_delete(self, source_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/digests/vault/sources/{source_id}")

    def ingest_batch(
        self,
        *,
        items: list[dict[str, Any]],
        source_name: str | None = None,
        run_id: str | None = None,
        enqueue_ai: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"items": items, "enqueue_ai": enqueue_ai}
        if source_name:
            body["source_name"] = source_name
        if run_id:
            body["run_id"] = run_id
        return self._request("POST", "/ingest/batch", json_body=body)

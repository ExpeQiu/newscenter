"""OpenClaw provider — adapts Gateway; falls back to Mock on failure when soft."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from intelligence.contracts import (
    AskIn,
    AskOut,
    ClassifyIn,
    ClassifyOut,
    DigestIn,
    DigestOut,
    RecommendIn,
    RecommendOut,
    SummarizeIn,
    SummarizeOut,
)
from intelligence.providers.mock import MockProvider

logger = logging.getLogger("newsc.intelligence.openclaw")


class OpenClawProvider:
    """Best-effort HTTP adapter.

    OpenClaw Gateway primarily exposes WS/Control UI. For MVP we POST to
    hooks/tools endpoints when available; otherwise fall back to Mock with
    model_meta.fallback=true so the pipeline stays green.
    """

    name = "openclaw"

    def __init__(self, gateway_url: str, token: str = "", timeout: float = 30.0) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._fallback = MockProvider()

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _try_hook(self, skill: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = f"{self.gateway_url}/hooks/agent"
        body = {"skill": skill, "payload": payload}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, headers=self._headers(), json=body)
                if r.status_code >= 400:
                    logger.warning("openclaw_hook_http skill=%s status=%s", skill, r.status_code)
                    return None
                data = r.json()
                if isinstance(data, dict):
                    return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("openclaw_hook_fail skill=%s err=%s", skill, exc)
        return None

    def summarize(self, payload: SummarizeIn) -> SummarizeOut:
        data = self._try_hook("newsc-summarize", payload.model_dump(mode="json"))
        if data and "summary" in data:
            return SummarizeOut(summary=str(data["summary"]), model_meta={"provider": self.name, **data.get("model_meta", {})})
        out = self._fallback.summarize(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def classify(self, payload: ClassifyIn) -> ClassifyOut:
        data = self._try_hook("newsc-classify", payload.model_dump(mode="json"))
        if data and "category" in data:
            return ClassifyOut(
                category=str(data["category"]),
                tags=list(data.get("tags") or []),
                confidence=float(data.get("confidence") or 0.5),
                model_meta={"provider": self.name},
            )
        out = self._fallback.classify(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def digest(self, payload: DigestIn) -> DigestOut:
        data = self._try_hook("newsc-digest", payload.model_dump(mode="json"))
        if data and "markdown" in data:
            return DigestOut(
                markdown=str(data["markdown"]),
                highlights=list(data.get("highlights") or []),
                model_meta={"provider": self.name},
            )
        out = self._fallback.digest(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def recommend(self, payload: RecommendIn) -> RecommendOut:
        data = self._try_hook("newsc-recommend", payload.model_dump(mode="json"))
        if data and "items" in data:
            from intelligence.contracts import RecommendItem

            items = [RecommendItem.model_validate(x) for x in data["items"]]
            return RecommendOut(items=items, model_meta={"provider": self.name})
        out = self._fallback.recommend(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def ask(self, payload: AskIn) -> AskOut:
        data = self._try_hook("newsc-ask", payload.model_dump(mode="json"))
        if data and "answer" in data:
            return AskOut(
                answer=str(data["answer"]),
                citations=list(data.get("citations") or []),
                model_meta={"provider": self.name},
            )
        out = self._fallback.ask(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out


def gateway_reachable(gateway_url: str, timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(gateway_url.rstrip("/") + "/")
            return r.status_code < 500
    except Exception:  # noqa: BLE001
        return False

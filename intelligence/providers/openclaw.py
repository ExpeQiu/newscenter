"""OpenClaw provider — adapts Gateway; falls back to Mock on failure when soft."""
from __future__ import annotations

import logging
import time
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
    RetrieveEventsIn,
    RetrieveEventsOut,
    RetrieveMacroIn,
    RetrieveMacroOut,
    SummarizeIn,
    SummarizeOut,
)
from intelligence.providers.mock import MockProvider
from pipeline.settings import get_settings

logger = logging.getLogger("newsc.intelligence.openclaw")


class OpenClawProvider:
    """Best-effort HTTP adapter with limited retry.

    OpenClaw Gateway primarily exposes WS/Control UI. For MVP we POST to
    hooks/tools endpoints when available; otherwise fall back to Mock with
    model_meta.fallback=true so the pipeline stays green (unless strict).
    """

    name = "openclaw"

    def __init__(
        self,
        gateway_url: str,
        token: str = "",
        timeout: float = 30.0,
        *,
        max_retries: int = 2,
        strict: bool | None = None,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.strict = get_settings().ai_fallback_strict if strict is None else bool(strict)
        self._fallback = MockProvider()
        self.fallback_count = 0
        self.call_count = 0

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _try_hook(self, skill: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        url = f"{self.gateway_url}/hooks/agent"
        body = {"skill": skill, "payload": payload}
        last_err: str | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, headers=self._headers(), json=body)
                    latency_ms = (time.perf_counter() - t0) * 1000
                    if r.status_code >= 500:
                        last_err = f"http_{r.status_code}"
                        logger.warning(
                            "openclaw_hook_http skill=%s status=%s attempt=%s latency_ms=%.1f",
                            skill,
                            r.status_code,
                            attempt,
                            latency_ms,
                        )
                        time.sleep(min(2**attempt * 0.2, 2.0))
                        continue
                    if r.status_code >= 400:
                        logger.warning(
                            "openclaw_hook_http skill=%s status=%s latency_ms=%.1f",
                            skill,
                            r.status_code,
                            latency_ms,
                        )
                        return None
                    data = r.json()
                    if isinstance(data, dict):
                        data.setdefault("model_meta", {})
                        if isinstance(data["model_meta"], dict):
                            data["model_meta"]["latency_ms"] = round(latency_ms, 1)
                        return data
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                logger.warning(
                    "openclaw_hook_fail skill=%s attempt=%s err=%s",
                    skill,
                    attempt,
                    exc,
                )
                time.sleep(min(2**attempt * 0.2, 2.0))
        if last_err:
            logger.warning("openclaw_hook_exhausted skill=%s last_err=%s", skill, last_err)
        return None

    def _on_fallback(self, skill: str) -> None:
        self.fallback_count += 1
        logger.warning(
            "openclaw_fallback skill=%s strict=%s fallback_count=%s",
            skill,
            self.strict,
            self.fallback_count,
        )
        if self.strict:
            raise RuntimeError(f"openclaw unavailable for skill={skill} (AI_FALLBACK_STRICT)")

    def summarize(self, payload: SummarizeIn) -> SummarizeOut:
        self.call_count += 1
        data = self._try_hook("newsc-summarize", payload.model_dump(mode="json"))
        if data and "summary" in data:
            return SummarizeOut(
                summary=str(data["summary"]),
                model_meta={"provider": self.name, **(data.get("model_meta") or {})},
            )
        self._on_fallback("newsc-summarize")
        out = self._fallback.summarize(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def classify(self, payload: ClassifyIn) -> ClassifyOut:
        self.call_count += 1
        data = self._try_hook("newsc-classify", payload.model_dump(mode="json"))
        if data and "category" in data:
            return ClassifyOut(
                category=str(data["category"]),
                tags=list(data.get("tags") or []),
                confidence=float(data.get("confidence") or 0.5),
                model_meta={"provider": self.name, **(data.get("model_meta") or {})},
            )
        self._on_fallback("newsc-classify")
        out = self._fallback.classify(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def digest(self, payload: DigestIn) -> DigestOut:
        self.call_count += 1
        data = self._try_hook("newsc-digest", payload.model_dump(mode="json"))
        if data and "markdown" in data:
            return DigestOut(
                markdown=str(data["markdown"]),
                highlights=list(data.get("highlights") or []),
                model_meta={"provider": self.name, **(data.get("model_meta") or {})},
            )
        self._on_fallback("newsc-digest")
        out = self._fallback.digest(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def recommend(self, payload: RecommendIn) -> RecommendOut:
        self.call_count += 1
        data = self._try_hook("newsc-recommend", payload.model_dump(mode="json"))
        if data and "items" in data:
            from intelligence.contracts import RecommendItem

            items = [RecommendItem.model_validate(x) for x in data["items"]]
            return RecommendOut(
                items=items,
                model_meta={"provider": self.name, **(data.get("model_meta") or {})},
            )
        self._on_fallback("newsc-recommend")
        out = self._fallback.recommend(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def ask(self, payload: AskIn) -> AskOut:
        self.call_count += 1
        data = self._try_hook("newsc-ask", payload.model_dump(mode="json"))
        if data and "answer" in data:
            return AskOut(
                answer=str(data["answer"]),
                citations=list(data.get("citations") or []),
                model_meta={"provider": self.name, **(data.get("model_meta") or {})},
            )
        self._on_fallback("newsc-ask")
        out = self._fallback.ask(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def retrieve_events(self, payload: RetrieveEventsIn) -> RetrieveEventsOut:
        self.call_count += 1
        data = self._try_hook("newsc-retrieve-events", payload.model_dump(mode="json"))
        if data and isinstance(data.get("events"), list):
            return RetrieveEventsOut.model_validate(
                {
                    "events": data["events"],
                    "model_meta": {"provider": self.name, **(data.get("model_meta") or {})},
                }
            )
        self._on_fallback("newsc-retrieve-events")
        out = self._fallback.retrieve_events(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out

    def retrieve_macro(self, payload: RetrieveMacroIn) -> RetrieveMacroOut:
        self.call_count += 1
        data = self._try_hook("newsc-retrieve-macro", payload.model_dump(mode="json"))
        if data and isinstance(data.get("observations"), list):
            return RetrieveMacroOut.model_validate(
                {
                    "observations": data["observations"],
                    "label": data.get("label"),
                    "unit": data.get("unit"),
                    "description": data.get("description"),
                    "model_meta": {"provider": self.name, **(data.get("model_meta") or {})},
                }
            )
        self._on_fallback("newsc-retrieve-macro")
        out = self._fallback.retrieve_macro(payload)
        out.model_meta = {**out.model_meta, "fallback": True, "wanted": self.name}
        return out


def gateway_reachable(gateway_url: str, timeout: float = 2.0) -> bool:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(gateway_url.rstrip("/") + "/")
            return r.status_code < 500
    except Exception:  # noqa: BLE001
        return False

"""NewsC FastAPI orchestrator."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intelligence.factory import create_provider  # noqa: E402
from intelligence.providers.minimax import minimax_reachable  # noqa: E402
from intelligence.providers.openclaw import gateway_reachable  # noqa: E402
from orchestrator.api import ai, cloud_sync, digests, events, ingest, items, macro, notes, pipelines, sources  # noqa: E402
from orchestrator.auth import ApiTokenMiddleware  # noqa: E402
from pipeline.db import init_db  # noqa: E402
from pipeline.settings import get_settings  # noqa: E402

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("newsc.orchestrator")

app = FastAPI(title="NewsC Orchestrator", version="0.2.0")
_origins = get_settings().cors_origins_list()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(ApiTokenMiddleware)

app.include_router(items.router)
app.include_router(notes.router)
app.include_router(digests.router)
app.include_router(events.router)
app.include_router(macro.router)
app.include_router(sources.router)
app.include_router(ingest.router)
app.include_router(ai.router)
app.include_router(pipelines.router)
app.include_router(cloud_sync.router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info(
        "orchestrator_started provider=%s cors=%s auth=%s",
        get_settings().resolved_provider(),
        _origins,
        bool((get_settings().orch_api_token or "").strip()),
    )


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    provider = settings.resolved_provider()
    gw_ok: bool | None = None
    mm_ok: bool | None = None
    if provider == "openclaw":
        gw_ok = gateway_reachable(settings.openclaw_gateway_url)
    if provider == "minimax":
        mm_ok = minimax_reachable(settings.minimax_base_url, settings.resolved_minimax_api_key())
    return {
        "ok": True,
        "service": "newsc-orchestrator",
        "ai_provider": provider,
        "ai_mock_mode": settings.ai_mock_mode,
        "ai_fallback_strict": settings.ai_fallback_strict,
        "auth_required": bool((settings.orch_api_token or "").strip()),
        "openclaw_reachable": gw_ok,
        "minimax_reachable": mm_ok,
        "minimax_model": settings.minimax_model if provider == "minimax" else None,
        "provider_name": create_provider().name,
    }


def main() -> None:
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "orchestrator.main:app",
        host=s.orch_host,
        port=s.orch_port,
        reload=False,
    )


if __name__ == "__main__":
    main()

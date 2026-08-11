"""Optional API token auth for mutating orchestrator endpoints."""
from __future__ import annotations

import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pipeline.settings import get_settings

logger = logging.getLogger("newsc.orchestrator.auth")

# 健康检查与只读 GET 不强制鉴权；写接口在 token 配置时校验
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


class ApiTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        settings = get_settings()
        token = (settings.orch_api_token or "").strip()
        if not token:
            return await call_next(request)

        path = request.url.path
        if request.method in SAFE_METHODS or path in PUBLIC_PATHS:
            return await call_next(request)

        provided = ""
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
        if not provided:
            provided = (request.headers.get("x-api-token") or "").strip()

        if provided != token:
            logger.warning("auth_reject method=%s path=%s", request.method, path)
            return JSONResponse({"detail": "unauthorized"}, status_code=401)

        return await call_next(request)

from __future__ import annotations

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "0:0:0:0:0:0:0:1"}
PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/api/auth",
}


def bind_requires_auth(host: str) -> bool:
    return host not in LOOPBACK_HOSTS


def extract_api_key(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def keys_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    if len(provided) != len(expected):
        return False
    return hmac.compare_digest(provided, expected)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, enabled: bool, api_key: str | None) -> None:  # noqa: ANN001
        super().__init__(app)
        self.enabled = enabled
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        path = request.url.path
        if not self.enabled or path in PUBLIC_PATHS or not path.startswith("/api"):
            return await call_next(request)
        if self.api_key and keys_match(extract_api_key(request), self.api_key):
            return await call_next(request)
        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)


def auth_enabled_from_env() -> bool:
    host = os.environ.get("RAG_EVAL_HOST", "127.0.0.1")
    return bind_requires_auth(host)

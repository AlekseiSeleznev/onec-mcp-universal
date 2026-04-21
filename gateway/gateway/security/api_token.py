from __future__ import annotations

import hmac
from collections.abc import Iterable

from starlette.requests import Request
from starlette.responses import JSONResponse

DEFAULT_TOKEN_PROTECTED_PATHS = {
    "/api/register",
    "/api/unregister",
    "/api/epf-heartbeat",
    "/api/export-bsl",
    "/api/export-cancel",
}


def extract_bearer_token(request: Request) -> str | None:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("authorization", "")
    if not auth:
        return None
    scheme, _, value = auth.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def require_api_token(request: Request, expected_token: str | None) -> JSONResponse | None:
    """Validate Bearer token when token auth is enabled (non-empty expected token)."""
    expected = (expected_token or "").strip()
    if not expected:
        return None

    provided = extract_bearer_token(request)
    if not provided:
        return JSONResponse(
            {"ok": False, "error": "Missing or invalid Authorization header (expected Bearer token)."},
            status_code=401,
        )
    if not hmac.compare_digest(provided, expected):
        return JSONResponse({"ok": False, "error": "Invalid API token."}, status_code=403)
    return None


def request_needs_api_token(
    request: Request,
    *,
    mutating_actions: Iterable[str],
    protected_paths: Iterable[str] = DEFAULT_TOKEN_PROTECTED_PATHS,
) -> bool:
    """Return True when this HTTP request targets a mutating API endpoint."""
    path = request.url.path
    protected = set(protected_paths)
    if path in protected:
        return True
    if path.startswith("/api/action/"):
        action = path[len("/api/action/"):].strip("/")
        return action in set(mutating_actions)
    return False

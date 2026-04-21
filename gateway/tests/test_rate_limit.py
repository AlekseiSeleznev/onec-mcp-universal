"""Tests for REST/dashboard rate limiting."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.security.rate_limit import _FixedWindowLimiter, build_rate_limit_guard


def _request(path: str, *, method: str = "GET", client: tuple[str, int] | None = ("127.0.0.1", 5000)) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
    }
    if client is not None:
        scope["client"] = client
    return Request(scope)


def _ok_response() -> JSONResponse:
    return JSONResponse({"ok": True}, status_code=200)


def test_fixed_window_limiter_increments_and_throttles():
    limiter = _FixedWindowLimiter()

    with patch("gateway.security.rate_limit.time.time", side_effect=[120, 121, 122]):
        assert limiter.allow("127.0.0.1:read", 2) == (True, 0)
        assert limiter.allow("127.0.0.1:read", 2) == (True, 0)
        allowed, retry_after = limiter.allow("127.0.0.1:read", 2)

    assert allowed is False
    assert retry_after == 58


def test_fixed_window_limiter_resets_between_windows():
    limiter = _FixedWindowLimiter()

    with patch("gateway.security.rate_limit.time.time", side_effect=[120, 180]):
        assert limiter.allow("127.0.0.1:read", 1) == (True, 0)
        assert limiter.allow("127.0.0.1:read", 1) == (True, 0)

    limiter.reset()
    with patch("gateway.security.rate_limit.time.time", return_value=180):
        assert limiter.allow("127.0.0.1:read", 1) == (True, 0)


@pytest.mark.asyncio
async def test_rate_limit_guard_disabled_short_circuits():
    guard = build_rate_limit_guard(
        enabled=False,
        read_rpm=1,
        mutating_rpm=1,
        mutating_actions={"remove"},
    )
    call_next = AsyncMock(return_value=_ok_response())

    response = await guard(_request("/api/databases"), call_next)

    assert response.status_code == 200
    call_next.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/health", "/mcp", "/mcp/session", "/favicon.ico"])
async def test_rate_limit_guard_skips_exempt_and_non_api_routes(path: str):
    guard = build_rate_limit_guard(
        enabled=True,
        read_rpm=1,
        mutating_rpm=1,
        mutating_actions={"remove"},
    )
    call_next = AsyncMock(return_value=_ok_response())

    response = await guard(_request(path), call_next)

    assert response.status_code == 200
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_guard_allows_read_requests_and_uses_unknown_client_bucket():
    guard = build_rate_limit_guard(
        enabled=True,
        read_rpm=2,
        mutating_rpm=1,
        mutating_actions={"remove"},
    )
    call_next = AsyncMock(return_value=_ok_response())

    response = await guard(_request("/api/databases", client=None), call_next)

    assert response.status_code == 200
    call_next.assert_awaited_once()


@pytest.mark.asyncio
async def test_rate_limit_guard_throttles_mutating_requests_with_429():
    guard = build_rate_limit_guard(
        enabled=True,
        read_rpm=10,
        mutating_rpm=1,
        mutating_actions={"remove"},
    )
    call_next = AsyncMock(return_value=_ok_response())

    with patch("gateway.security.rate_limit.time.time", side_effect=[120, 121]):
        first = await guard(_request("/api/action/remove", method="POST"), call_next)
        second = await guard(_request("/api/action/remove", method="POST"), call_next)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["Retry-After"] == "59"
    payload = json.loads(second.body)
    assert payload["route_family"] == "mutating"
    assert payload["retry_after"] == 59

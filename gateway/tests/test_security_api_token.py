"""Tests for gateway.security.api_token helpers."""

from __future__ import annotations

from starlette.requests import Request

from gateway.security.api_token import (
    extract_bearer_token,
    request_needs_api_token,
    require_api_token,
)


def _request(path: str, auth_header: str | None = None) -> Request:
    headers = []
    if auth_header is not None:
        headers.append((b"authorization", auth_header.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


def test_extract_bearer_token():
    req = _request("/api/action/clear-cache", auth_header="Bearer secret")
    assert extract_bearer_token(req) == "secret"


def test_extract_bearer_token_rejects_wrong_scheme():
    req = _request("/api/action/clear-cache", auth_header="Basic secret")
    assert extract_bearer_token(req) is None


def test_require_api_token_disabled():
    req = _request("/api/action/clear-cache")
    assert require_api_token(req, "") is None


def test_require_api_token_missing_header():
    req = _request("/api/action/clear-cache")
    resp = require_api_token(req, "secret")
    assert resp is not None
    assert resp.status_code == 401


def test_require_api_token_invalid_token():
    req = _request("/api/action/clear-cache", auth_header="Bearer wrong")
    resp = require_api_token(req, "secret")
    assert resp is not None
    assert resp.status_code == 403


def test_require_api_token_valid_token():
    req = _request("/api/action/clear-cache", auth_header="Bearer secret")
    assert require_api_token(req, "secret") is None


def test_request_needs_api_token_for_protected_path():
    req = _request("/api/register")
    assert request_needs_api_token(req, mutating_actions={"clear-cache"})


def test_request_needs_api_token_for_epf_heartbeat():
    req = _request("/api/epf-heartbeat")
    assert request_needs_api_token(req, mutating_actions={"clear-cache"})


def test_request_needs_api_token_for_mutating_action():
    req = _request("/api/action/clear-cache")
    assert request_needs_api_token(req, mutating_actions={"clear-cache"})


def test_request_needs_api_token_for_readonly_action():
    req = _request("/api/action/db-status")
    assert not request_needs_api_token(req, mutating_actions={"clear-cache"})

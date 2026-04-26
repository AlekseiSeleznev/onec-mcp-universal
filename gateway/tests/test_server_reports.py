from __future__ import annotations

import json

import pytest


@pytest.fixture()
def test_client():
    from starlette.testclient import TestClient
    from gateway import server

    return TestClient(server._starlette, raise_server_exceptions=True)


def test_dashboard_reports_api_delegates_to_report_handler(test_client, tmp_path):
    async def fake_handler(name, arguments, **kwargs):
        assert name == "find_reports"
        assert arguments["database"] == "Z01"
        return json.dumps({"ok": True, "data": [{"title": "Расчетный листок"}]}, ensure_ascii=False)

    with _patch_report_handler(fake_handler):
        resp = test_client.post("/api/reports/find", json={"database": "Z01", "query": "Расчетный"})

    assert resp.status_code == 200
    assert resp.json()["data"][0]["title"] == "Расчетный листок"


def test_dashboard_reports_api_delegates_validate_all(test_client):
    async def fake_handler(name, arguments, **kwargs):
        assert name == "validate_all_reports"
        assert arguments["database"] == "Z01"
        return json.dumps({"ok": True, "counts": {"done": 1, "error": 0, "unsupported": 0}}, ensure_ascii=False)

    with _patch_report_handler(fake_handler):
        resp = test_client.post("/api/reports/validate-all", json={"database": "Z01"})

    assert resp.status_code == 200
    assert resp.json()["counts"]["done"] == 1


def test_dashboard_reports_api_wraps_non_json_handler_response(test_client):
    async def fake_handler(name, arguments, **kwargs):
        return "plain error"

    with _patch_report_handler(fake_handler):
        resp = test_client.post("/api/reports/find", json={"database": "Z01", "query": "Расчетный"})

    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "error": "plain error"}


def test_dashboard_reports_api_rejects_unknown_action_and_invalid_json(test_client):
    unknown = test_client.post("/api/reports/nope", json={})
    invalid = test_client.post(
        "/api/reports/find",
        content=b"not-json",
        headers={"content-type": "application/json"},
    )

    assert unknown.status_code == 404
    assert invalid.status_code == 400


class _patch_report_handler:
    def __init__(self, replacement):
        self.replacement = replacement
        self._patcher = None

    def __enter__(self):
        from unittest.mock import patch

        self._patcher = patch("gateway.server.try_handle_report_tool", self.replacement)
        return self._patcher.__enter__()

    def __exit__(self, exc_type, exc, tb):
        return self._patcher.__exit__(exc_type, exc, tb)

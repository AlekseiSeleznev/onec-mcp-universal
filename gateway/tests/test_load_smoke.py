"""Basic concurrent load smoke tests for gateway HTTP endpoints."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from starlette.testclient import TestClient


def test_concurrent_health_requests_smoke():
    from gateway import server

    def one_call() -> int:
        client = TestClient(server._starlette, raise_server_exceptions=False)
        try:
            return client.get("/health").status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(lambda _: one_call(), range(100)))

    assert all(code == 200 for code in statuses)


def test_concurrent_db_status_requests_smoke():
    from gateway import server

    def one_call() -> int:
        client = TestClient(server._starlette, raise_server_exceptions=False)
        try:
            return client.get("/api/action/db-status?name=ERP").status_code
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        statuses = list(pool.map(lambda _: one_call(), range(100)))

    assert all(code == 200 for code in statuses)

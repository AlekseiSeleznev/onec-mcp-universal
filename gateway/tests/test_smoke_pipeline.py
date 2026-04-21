"""Lightweight integration smoke tests for key gateway workflows."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp.types import CallToolResult, TextContent, Tool
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.backends.base import BackendBase
from gateway.backends.manager import BackendManager
from gateway.db_registry import DatabaseRegistry


class _FakeManager:
    def __init__(self) -> None:
        self.connected: set[str] = set()
        self.default_db: str | None = None

    async def remove_db_backends(self, db_name: str) -> None:
        self.connected.discard(db_name)
        if self.default_db == db_name:
            self.default_db = None

    def set_default_db(self, db_name: str) -> bool:
        if db_name not in self.connected:
            return False
        self.default_db = db_name
        return True

    def has_db(self, db_name: str) -> bool:
        return db_name in self.connected


class _SmokeBackend(BackendBase):
    def __init__(self, name: str, tool_names: list[str]):
        super().__init__(name)
        self.tools = [Tool(name=n, description=f"Tool {n}", inputSchema={"type": "object"}) for n in tool_names]

    async def start(self) -> None:
        self.available = True

    async def stop(self) -> None:
        self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return CallToolResult(content=[TextContent(type="text", text=f"{self.name}:{name}")])


class TestSmokePipelines:
    def test_mcp_list_tools_and_status_smoke(self, tmp_path, monkeypatch):
        from gateway import mcp_server

        manager = BackendManager()
        registry = DatabaseRegistry(state_file=tmp_path / "db_state.json")
        backend = _SmokeBackend("smoke", ["execute_query"])

        monkeypatch.setattr(mcp_server, "manager", manager)
        monkeypatch.setattr(mcp_server, "registry", registry)

        try:
            asyncio.run(manager.start_all([backend]))

            tools = asyncio.run(mcp_server.list_tools())
            tool_names = {t.name for t in tools}
            assert "get_server_status" in tool_names
            assert "execute_query" in tool_names

            status_result = asyncio.run(mcp_server.call_tool("get_server_status", {}))
            status_payload = json.loads(status_result.content[0].text)
            assert status_payload["smoke"]["ok"] is True
        finally:
            asyncio.run(manager.stop_all())

    def test_export_status_pipeline(self):
        from gateway import mcp_server, server

        server._export_jobs.clear()
        server._export_tasks.clear()
        mcp_server._index_jobs.clear()

        try:
            with patch("gateway.server.settings") as mock_settings, \
                 patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export:
                mock_settings.gateway_api_token = ""
                mock_settings.bsl_host_workspace = "/home/user/bsl"
                mock_settings.bsl_workspace = "/workspace"
                mock_export.return_value = "Выгрузка завершена: 42 BSL файлов. Индекс: 100 символов."

                client = TestClient(server._starlette, raise_server_exceptions=True)
                conn = "Srvr=srv;Ref=ERP;"

                start = client.post(
                    "/api/export-bsl",
                    json={"connection": conn, "output_dir": "/workspace/ERP"},
                )
                assert start.status_code == 200
                assert start.json()["ok"] is True

                # Background task updates status asynchronously; poll briefly.
                status_data = {"status": "running", "result": ""}
                for _ in range(20):
                    time.sleep(0.01)
                    status = client.post("/api/export-status", json={"connection": conn})
                    assert status.status_code == 200
                    status_data = status.json()
                    if status_data["status"] != "running":
                        break

                assert status_data["status"] == "done"
                assert "42 BSL" in status_data["result"]
        finally:
            server._export_jobs.clear()
            server._export_tasks.clear()
            mcp_server._index_jobs.clear()

    def test_database_lifecycle_pipeline(self, tmp_path, monkeypatch):
        from gateway import mcp_server, server

        fake_registry = DatabaseRegistry(state_file=tmp_path / "db_state.json")
        fake_manager = _FakeManager()

        async def _fake_connect(name: str, connection: str, project_path: str) -> str:
            fake_registry.register(name, connection, project_path, slug=name)
            fake_manager.connected.add(name)
            return f"Database '{name}' connected"

        monkeypatch.setattr(server, "_registry", fake_registry)
        monkeypatch.setattr(server, "_manager", fake_manager)
        monkeypatch.setattr(mcp_server, "_connect_database", _fake_connect)
        monkeypatch.setattr(server.settings, "gateway_api_token", "")

        with patch("gateway.docker_manager.stop_db_containers", return_value=None):
            client = TestClient(server._starlette, raise_server_exceptions=True)

            initial = client.get("/api/databases")
            assert initial.status_code == 200
            assert initial.json()["databases"] == []

            connect = client.post(
                "/api/action/connect-db",
                json={
                    "name": "ERP",
                    "connection": "Srvr=srv;Ref=ERP;",
                    "project_path": "/workspace/ERP",
                },
            )
            assert connect.status_code == 200
            assert connect.json()["ok"] is True

            listed_after_connect = client.get("/api/databases")
            assert listed_after_connect.status_code == 200
            rows_after_connect = listed_after_connect.json()["databases"]
            assert len(rows_after_connect) == 1
            assert rows_after_connect[0]["name"] == "ERP"
            assert rows_after_connect[0]["backend_connected"] is True

            switch = client.get("/api/action/switch?name=ERP")
            assert switch.status_code == 200
            assert switch.json()["ok"] is True

            status_connected = client.get("/api/action/db-status?name=ERP")
            assert status_connected.status_code == 200
            assert status_connected.json()["connected"] is True

            disconnect = client.get("/api/action/disconnect?name=ERP")
            assert disconnect.status_code == 200
            assert disconnect.json()["ok"] is True

            listed_after_disconnect = client.get("/api/databases")
            assert listed_after_disconnect.status_code == 200
            rows_after_disconnect = listed_after_disconnect.json()["databases"]
            assert len(rows_after_disconnect) == 1
            assert rows_after_disconnect[0]["backend_connected"] is False

            status_disconnected = client.get("/api/action/db-status?name=ERP")
            assert status_disconnected.status_code == 200
            assert status_disconnected.json()["connected"] is False

            remove = client.get("/api/action/remove?name=ERP")
            assert remove.status_code == 200
            assert remove.json()["ok"] is True

            assert fake_registry.get("ERP") is None

            listed_after_remove = client.get("/api/databases")
            assert listed_after_remove.status_code == 200
            assert listed_after_remove.json()["databases"] == []

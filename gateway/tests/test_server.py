"""Tests for gateway.server — HTTP endpoints, routing, build_backends, etc."""

from __future__ import annotations

import json
import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_status(ok: bool = True):
    return {"onec-toolkit": {"ok": ok, "tools": 5}}


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def starlette_app():
    """Return the Starlette sub-app directly (not the full ASGI App)."""
    from gateway import server
    return server._starlette


@pytest.fixture()
def test_client(starlette_app):
    """Sync test client without lifespan."""
    from starlette.testclient import TestClient
    return TestClient(starlette_app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def reset_rate_limit_guard():
    from gateway import server

    server._rate_limit_guard.reset()


@pytest.fixture(autouse=True)
def disable_live_docker_control_for_unit_tests():
    with patch(
        "gateway.server._docker_manager._request_json",
        side_effect=RuntimeError("docker-control disabled in server unit test"),
    ):
        yield


# ---------------------------------------------------------------------------
# /health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = _make_fake_status(ok=True)
            resp = test_client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_json(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = _make_fake_status(ok=True)
            resp = test_client.get("/health")
        assert "application/json" in resp.headers["content-type"]

    def test_health_ok_when_all_backends_ok(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = _make_fake_status(ok=True)
            resp = test_client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"
        assert "backends" in data

    def test_health_degraded_when_backend_down(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = _make_fake_status(ok=False)
            resp = test_client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"

    def test_health_multiple_backends_all_ok(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {
                "onec-toolkit": {"ok": True, "tools": 5},
                "platform-context": {"ok": True, "tools": 3},
            }
            resp = test_client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_multiple_backends_one_down(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {
                "onec-toolkit": {"ok": True, "tools": 5},
                "platform-context": {"ok": False, "tools": 0},
            }
            resp = test_client.get("/health")
        data = resp.json()
        assert data["status"] == "degraded"


# ---------------------------------------------------------------------------
# /api/databases endpoint
# ---------------------------------------------------------------------------


class TestDatabasesStatusApi:
    def test_databases_status_expires_stale_epf_and_enriches_backend_flag(self, test_client):
        dbs = [{"name": "db1", "epf_connected": True}]
        with patch("gateway.server._registry") as mock_reg, patch("gateway.server._manager") as mock_mgr, patch(
            "gateway.server.settings"
        ) as mock_settings:
            mock_settings.epf_heartbeat_ttl_seconds = 45
            mock_reg.list.return_value = dbs
            mock_mgr.has_db.return_value = True

            resp = test_client.get("/api/databases")

        assert resp.status_code == 200
        mock_reg.expire_stale_epf.assert_called_once_with(45)
        assert resp.json()["databases"][0]["backend_connected"] is True


class TestDashboardEndpoints:
    def test_dashboard_renders_with_runtime_summary(self, test_client):
        with patch("gateway.web_ui.render_dashboard", return_value="<html>dashboard</html>") as render_dashboard, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.server._registry") as registry, \
             patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_optional_services_status", return_value=[]), \
             patch("gateway.server.settings") as settings:
            manager.status.return_value = {"onec-toolkit": {"ok": True, "tools": 9}}
            registry.list.return_value = [{"name": "ERP"}]
            settings.onec_toolkit_url = "http://localhost:6003/mcp"
            settings.platform_context_url = "http://localhost:8081/sse"
            settings.enabled_backends = "onec-toolkit,platform-context"
            settings.export_host_url = "http://localhost:8082"
            settings.platform_path = "/opt/1cv8/x86_64/8.3.27.2074"
            settings.bsl_workspace = "/workspace"
            settings.bsl_host_workspace = "/home/as/Z"
            settings.bsl_lsp_command = ""
            settings.naparnik_api_key = ""
            settings.metadata_cache_ttl = 600
            settings.epf_heartbeat_ttl_seconds = 30
            settings.test_runner_url = "http://localhost:6789/mcp"
            settings.bsl_graph_url = "http://localhost:8888"
            settings.port = 8080
            settings.log_level = "INFO"
            with patch("gateway.profiler.profiler.get_stats", return_value={}), \
                 patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
                 patch("gateway.anonymizer.anonymizer.enabled", False):
                resp = test_client.get("/dashboard?lang=en")

        assert resp.status_code == 200
        assert "dashboard" in resp.text
        render_dashboard.assert_called_once()

    def test_dashboard_docs_route(self, test_client):
        with patch("gateway.web_ui.render_docs", return_value="<html>docs</html>") as render_docs:
            resp = test_client.get("/dashboard/docs?lang=en")
        assert resp.status_code == 200
        assert "docs" in resp.text
        render_docs.assert_called_once_with("en")

    def test_dashboard_diagnostics_route(self, test_client):
        with patch("gateway.server._collect_diagnostics", return_value={"gateway": {"version": "v1.8.5"}}):
            resp = test_client.get("/dashboard/diagnostics?lang=en")
        assert resp.status_code == 200
        assert "Diagnostics" in resp.text
        assert "v1.8.5" in resp.text

    def test_dashboard_invalid_lang_falls_back_to_ru(self, test_client):
        with patch("gateway.web_ui.render_dashboard", return_value="<html>dashboard</html>") as render_dashboard, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.server._registry") as registry, \
             patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_optional_services_status", return_value=[]), \
             patch("gateway.server.settings") as settings:
            manager.status.return_value = {"onec-toolkit": {"ok": True, "tools": 9}}
            registry.list.return_value = []
            settings.onec_toolkit_url = "http://localhost:6003/mcp"
            settings.platform_context_url = "http://localhost:8081/sse"
            settings.enabled_backends = "onec-toolkit"
            settings.export_host_url = ""
            settings.platform_path = "/opt/1cv8/x86_64/8.3.27.2074"
            settings.bsl_workspace = "/workspace"
            settings.bsl_host_workspace = "/home/as/Z"
            settings.bsl_lsp_command = ""
            settings.naparnik_api_key = ""
            settings.metadata_cache_ttl = 600
            settings.epf_heartbeat_ttl_seconds = 30
            settings.test_runner_url = "http://localhost:6789/mcp"
            settings.bsl_graph_url = "http://localhost:8888"
            settings.port = 8080
            settings.log_level = "INFO"
            with patch("gateway.profiler.profiler.get_stats", return_value={}), \
                 patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
                 patch("gateway.anonymizer.anonymizer.enabled", False):
                resp = test_client.get("/dashboard?lang=de")

        assert resp.status_code == 200
        assert render_dashboard.call_args.kwargs["lang"] == "ru"


# ---------------------------------------------------------------------------
# /api/export-bsl endpoint
# ---------------------------------------------------------------------------


class TestExportBslApi:
    def test_missing_connection_field(self, test_client):
        resp = test_client.post("/api/export-bsl", json={"output_dir": "/projects"})
        assert resp.status_code == 400
        assert "connection" in resp.json().get("error", "")

    def test_invalid_json_body(self, test_client):
        resp = test_client.post(
            "/api/export-bsl",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_valid_request_calls_run_export(self, test_client):
        with patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export, \
             patch("gateway.server.settings") as mock_settings:
            mock_settings.gateway_api_token = ""
            mock_settings.bsl_host_workspace = "/home/user/bsl"
            mock_settings.bsl_workspace = "/workspace"
            mock_export.return_value = "Export completed successfully."
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.get_active.return_value = None
                resp = test_client.post(
                    "/api/export-bsl",
                    json={"connection": "Srvr=srv;Ref=base;", "output_dir": "/workspace/test"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_export_returns_ok_true_even_on_error(self, test_client):
        # /api/export-bsl is fire-and-forget — always returns ok=True immediately.
        # Errors are visible via /api/export-status once background task completes.
        with patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export, \
             patch("gateway.server.settings") as mock_settings:
            mock_settings.gateway_api_token = ""
            mock_settings.bsl_host_workspace = "/home/user/bsl"
            mock_settings.bsl_workspace = "/workspace"
            mock_export.return_value = "ERROR: 1cv8 not found"
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.get_active.return_value = None
                resp = test_client.post(
                    "/api/export-bsl",
                    json={"connection": "Srvr=srv;Ref=base;", "output_dir": "/workspace/test"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_empty_connection_string(self, test_client):
        resp = test_client.post("/api/export-bsl", json={"connection": ""})
        assert resp.status_code == 400

    def test_default_output_dir_uses_runtime_workspace_mapping(self, test_client):
        connection = "Srvr=srv;Ref=ERPPur_Local;"
        with patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export, patch(
            "gateway.server.settings"
        ) as mock_settings, patch("gateway.server._read_env_value") as mock_env:
            mock_settings.gateway_api_token = ""
            mock_settings.bsl_workspace = "/workspace"
            mock_settings.bsl_host_workspace = "/home/user/legacy"
            mock_settings.port = 8080
            mock_env.side_effect = lambda k: (
                "/home/as/Z"
                if k in ("BSL_HOST_WORKSPACE", "BSL_WORKSPACE")
                else ""
            )
            mock_export.return_value = "Export completed successfully."

            resp = test_client.post(
                "/api/export-bsl",
                json={"connection": connection, "output_dir": "/projects"},
            )

        assert resp.status_code == 200
        for _ in range(50):
            if mock_export.await_count > 0:
                break
            time.sleep(0.01)
        mock_export.assert_awaited_once_with(connection, "/hostfs-home/as/Z/ERPPur_Local")

    def test_default_output_dir_without_ref_uses_workspace_root(self, test_client):
        connection = "Srvr=srv;"
        with patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export, patch(
            "gateway.server.settings"
        ) as mock_settings, patch("gateway.server._read_env_value") as mock_env:
            mock_settings.gateway_api_token = ""
            mock_settings.bsl_workspace = "/workspace"
            mock_settings.bsl_host_workspace = "/home/as/Z"
            mock_settings.port = 8080
            mock_env.side_effect = lambda k: "/home/as/Z" if k in ("BSL_HOST_WORKSPACE", "BSL_WORKSPACE") else ""
            mock_export.return_value = "Export completed successfully."

            resp = test_client.post(
                "/api/export-bsl",
                json={"connection": connection, "output_dir": "/projects"},
            )

        assert resp.status_code == 200
        for _ in range(50):
            if mock_export.await_count > 0:
                break
            time.sleep(0.01)
        mock_export.assert_awaited_once_with(connection, "/hostfs-home/as/Z")

    def test_export_rejects_when_workspace_missing(self, test_client, monkeypatch):
        monkeypatch.setattr("gateway.server.settings.gateway_api_token", "")
        with patch("gateway.server._read_env_value", return_value=""), patch("gateway.server.settings") as settings:
            settings.gateway_api_token = ""
            settings.bsl_host_workspace = ""
            settings.port = 8080
            resp = test_client.post("/api/export-bsl", json={"connection": "Srvr=srv;Ref=ERP;"})

        assert resp.status_code == 400
        assert "Папка выгрузки BSL не настроена" in resp.json()["error"]

    def test_export_conflict_when_job_already_running(self, test_client, monkeypatch):
        monkeypatch.setattr("gateway.server.settings.gateway_api_token", "")
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        try:
            gateway_server._export_jobs["Srvr=srv;Ref=ERP;"] = {"status": "running", "result": ""}
            with patch("gateway.server._read_env_value", side_effect=lambda key: "/home/as/Z" if key in ("BSL_HOST_WORKSPACE", "BSL_WORKSPACE") else ""), \
                 patch("gateway.server.settings") as settings:
                settings.gateway_api_token = ""
                settings.bsl_host_workspace = "/home/as/Z"
                settings.bsl_workspace = "/workspace"
                settings.port = 8080
                resp = test_client.post("/api/export-bsl", json={"connection": "Srvr=srv;Ref=ERP;"})
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)

        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# /api/register endpoint
# ---------------------------------------------------------------------------


class TestRegisterEpfApi:
    def test_missing_name_field(self, test_client):
        resp = test_client.post("/api/register", json={"connection": "Srvr=srv;"})
        assert resp.status_code == 400
        assert "name" in resp.json().get("error", "")

    def test_invalid_json_body(self, test_client):
        resp = test_client.post(
            "/api/register",
            content=b"bad json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_known_db_marks_connected(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="testdb",
            connection="Srvr=srv;Ref=base;",
            project_path="/projects/testdb",
            toolkit_port=7001,
            toolkit_url="http://localhost:7001/mcp",
            lsp_container="lsp-testdb",
        )
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = mock_db
            mock_reg.active_name = "testdb"
            mock_reg.mark_epf_connected = MagicMock()
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.has_db.return_value = True

                resp = test_client.post(
                    "/api/register",
                    json={"name": "testdb", "connection": "Srvr=srv;Ref=base;"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["database"] == "testdb"

    def test_returns_toolkit_poll_url(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;",
            project_path="/projects",
            toolkit_port=7002,
            toolkit_url="http://localhost:7002/mcp",
        )
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = mock_db
            mock_reg.active_name = "mydb"
            mock_reg.mark_epf_connected = MagicMock()
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.has_db.return_value = True

                resp = test_client.post("/api/register", json={"name": "mydb"})

        data = resp.json()
        assert "toolkit_poll_url" in data
        assert "7002" in data["toolkit_poll_url"]

    def test_register_epf_rebinds_toolkit_backend_to_channel(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;",
            project_path="/projects",
            toolkit_port=7002,
            toolkit_url="http://localhost:7002/mcp",
        )
        toolkit_backend = SimpleNamespace(rebind=AsyncMock())
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = mock_db
            mock_reg.active_name = "mydb"
            mock_reg.mark_epf_connected = MagicMock()
            mock_reg.update_runtime = MagicMock(return_value=True)
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.has_db.return_value = True
                mock_mgr.get_db_backend.return_value = toolkit_backend

                resp = test_client.post("/api/register", json={"name": "mydb", "channel": "z01-live"})

        assert resp.status_code == 200
        mock_reg.update_runtime.assert_called_once_with(
            "mydb",
            toolkit_url="http://localhost:7002/mcp?channel=z01-live",
            channel_id="z01-live",
        )
        toolkit_backend.rebind.assert_awaited_once_with("http://localhost:7002/mcp?channel=z01-live")
        assert resp.json()["toolkit_poll_url"] == "http://localhost:7002/1c/poll"

    def test_register_normalizes_stale_managed_project_path_without_reconnect(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="Z02",
            connection="Srvr=srv;Ref=Z02;",
            project_path="/workspace/Z02",
            slug="Z02",
            toolkit_port=6101,
            toolkit_url="http://localhost:6101/mcp",
            lsp_container="mcp-lsp-Z02",
        )

        with patch("gateway.server._registry") as mock_reg, \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server._manager") as mock_mgr, \
             patch("gateway.server._ensure_lsp_started", new=AsyncMock()) as ensure_lsp, \
             patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()) as rebuild_graph:
            mock_reg.get.return_value = mock_db
            mock_reg.active_name = "Z02"
            mock_reg.mark_epf_connected = MagicMock()
            mock_reg.update = MagicMock(return_value=True)
            mock_mgr.has_db.return_value = True

            resp = test_client.post("/api/register", json={"name": "Z02"})

        assert resp.status_code == 200
        mock_reg.update.assert_called_once_with("Z02", project_path="/hostfs-home/as/Z/Z02")
        ensure_lsp.assert_awaited_once_with("Srvr=srv;Ref=Z02;")
        rebuild_graph.assert_awaited_once()
        mock_reg.mark_epf_connected.assert_called_once_with("Z02")

    def test_existing_db_without_backend_triggers_reconnect(self, test_client):
        from gateway.db_registry import DatabaseInfo

        db_before = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/projects/mydb",
            slug="mydb",
        )
        db_after = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/projects/mydb",
            slug="mydb",
            toolkit_port=6100,
            toolkit_url="http://localhost:6100/mcp",
        )

        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.side_effect = [db_before, db_after, db_after]
            mock_reg.active_name = "mydb"
            mock_reg.mark_epf_connected = MagicMock()
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.has_db.return_value = False
                with patch("gateway.mcp_server._connect_database", new_callable=AsyncMock) as mock_connect:
                    mock_connect.return_value = "ok"
                    resp = test_client.post("/api/register", json={"name": "mydb"})

        assert resp.status_code == 200
        mock_connect.assert_awaited_once_with("mydb", "Srvr=srv;Ref=mydb;", "/projects/mydb")

    def test_existing_db_without_backend_rewrites_stale_home_root_project_path(self, test_client):
        from gateway.db_registry import DatabaseInfo

        db_before = DatabaseInfo(
            name="ERP_DEMO",
            connection="Srvr=srv;Ref=ERP_DEMO;",
            project_path="/home/as",
            slug="ERP_DEMO",
        )
        db_after = DatabaseInfo(
            name="ERP_DEMO",
            connection="Srvr=srv;Ref=ERP_DEMO;",
            project_path="/hostfs-home/as/Z/ERP_DEMO",
            slug="ERP_DEMO",
            toolkit_port=6100,
            toolkit_url="http://localhost:6100/mcp",
        )

        with patch("gateway.server._registry") as mock_reg, \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server._manager") as mock_mgr, \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")) as connect_db:
            mock_reg.get.side_effect = [db_before, db_after, db_after]
            mock_reg.active_name = "ERP_DEMO"
            mock_reg.mark_epf_connected = MagicMock()
            mock_mgr.has_db.return_value = False

            resp = test_client.post("/api/register", json={"name": "ERP_DEMO"})

        assert resp.status_code == 200
        connect_db.assert_awaited_once_with(
            "ERP_DEMO",
            "Srvr=srv;Ref=ERP_DEMO;",
            "/hostfs-home/as/Z/ERP_DEMO",
        )

    def test_unknown_db_without_connection_returns_ok(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = None

            resp = test_client.post(
                "/api/register",
                json={"name": "nonexistent"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_unknown_db_with_connection_autoconnects(self, test_client):
        from gateway.db_registry import DatabaseInfo

        db_after = DatabaseInfo(
            name="ERP",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/hostfs-home/as/Z/ERP",
            slug="ERP",
        )

        with patch("gateway.server._registry") as mock_reg, \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server._manager") as mock_mgr, \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")) as connect_db:
            mock_reg.get.side_effect = [None, db_after, db_after]
            mock_mgr.has_db.return_value = False
            resp = test_client.post(
                "/api/register",
                json={"name": "ERP", "connection": "Srvr=srv;Ref=ERP;"},
            )

        assert resp.status_code == 200
        connect_db.assert_awaited_once_with("ERP", "Srvr=srv;Ref=ERP;", "/hostfs-home/as/Z/ERP")

    def test_register_returns_500_when_autoconnect_fails(self, test_client):
        with patch("gateway.server._registry") as mock_reg, \
             patch("gateway.server._manager") as mock_mgr, \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ERROR: boom")):
            mock_reg.get.return_value = None
            mock_mgr.has_db.return_value = False
            resp = test_client.post(
                "/api/register",
                json={"name": "ERP", "connection": "Srvr=srv;Ref=ERP;"},
            )

        assert resp.status_code == 500
        assert resp.json()["ok"] is False

    def test_existing_db_without_backend_and_missing_connection_logs_warning(self, test_client):
        db = SimpleNamespace(
            name="db1",
            slug="db1",
            connection="",
            project_path="/projects/db1",
            toolkit_port=0,
            toolkit_url="",
        )
        with patch("gateway.server._registry") as registry, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.server.logger") as logger, \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")) as connect_db:
            registry.get.side_effect = [db, db, db]
            registry.active_name = ""
            manager.has_db.return_value = False

            resp = test_client.post("/api/register", json={"name": "db1"})

        assert resp.status_code == 200
        connect_db.assert_awaited_once_with("db1", "", "/projects/db1")
        logger.warning.assert_called_once()


# ---------------------------------------------------------------------------
# /api/unregister endpoint
# ---------------------------------------------------------------------------


class TestUnregisterEpfApi:
    def test_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/unregister",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_valid_name_marks_disconnected(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.mark_epf_disconnected.return_value = True

            resp = test_client.post("/api/unregister", json={"name": "mydb"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        mock_reg.mark_epf_disconnected.assert_called_once_with("mydb")

    def test_unregister_uses_grace_aware_registry_call(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.mark_epf_disconnected.return_value = True

            resp = test_client.post("/api/unregister", json={"name": "mydb"})

        assert resp.status_code == 200
        assert mock_reg.mark_epf_disconnected.call_args.kwargs == {}

    def test_empty_name_is_safe(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.mark_epf_disconnected.return_value = False

            resp = test_client.post("/api/unregister", json={})

        assert resp.status_code == 200
        mock_reg.mark_epf_disconnected.assert_not_called()


# ---------------------------------------------------------------------------
# /api/epf-heartbeat endpoint
# ---------------------------------------------------------------------------


class TestEpfHeartbeatApi:
    def test_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/epf-heartbeat",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_missing_name(self, test_client):
        resp = test_client.post("/api/epf-heartbeat", json={})
        assert resp.status_code == 400

    def test_unknown_db_returns_404(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.mark_epf_heartbeat.return_value = False
            resp = test_client.post("/api/epf-heartbeat", json={"name": "ghost"})
        assert resp.status_code == 404

    def test_marks_epf_alive(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.mark_epf_heartbeat.return_value = True
            resp = test_client.post("/api/epf-heartbeat", json={"name": "db1"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_reg.mark_epf_heartbeat.assert_called_once_with("db1")

    def test_heartbeat_rebinds_toolkit_backend_when_channel_supplied(self, test_client):
        db = SimpleNamespace(
            name="db1",
            toolkit_port=6100,
            toolkit_url="http://localhost:6100/mcp",
            channel_id="default",
            connected=True,
        )
        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.server._rebind_db_toolkit_backend", new=AsyncMock()
        ) as rebind:
            mock_reg.mark_epf_heartbeat.return_value = True
            mock_reg.get.return_value = db

            resp = test_client.post(
                "/api/epf-heartbeat",
                json={"name": "db1", "channel": "live-z01"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_reg.mark_epf_heartbeat.assert_called_once_with("db1")
        mock_reg.update_runtime.assert_called_once_with(
            "db1",
            toolkit_url="http://localhost:6100/mcp?channel=live-z01",
            channel_id="live-z01",
        )
        rebind.assert_awaited_once_with("db1", "http://localhost:6100/mcp?channel=live-z01")

    def test_heartbeat_normalizes_stale_managed_project_path(self, test_client):
        db = SimpleNamespace(
            name="Z02",
            slug="Z02",
            connection="Srvr=srv;Ref=Z02;",
            project_path="/workspace/Z02",
            toolkit_port=6101,
            toolkit_url="http://localhost:6101/mcp",
            connected=True,
        )
        with patch("gateway.server._registry") as mock_reg, \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server._manager") as mock_mgr, \
             patch("gateway.server._ensure_lsp_started", new=AsyncMock()) as ensure_lsp, \
             patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()) as rebuild_graph:
            mock_reg.mark_epf_heartbeat.return_value = True
            mock_reg.get.return_value = db
            mock_reg.update = MagicMock(return_value=True)
            mock_mgr.has_db.return_value = True

            resp = test_client.post("/api/epf-heartbeat", json={"name": "Z02"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_reg.update.assert_called_once_with("Z02", project_path="/hostfs-home/as/Z/Z02")
        ensure_lsp.assert_awaited_once_with("Srvr=srv;Ref=Z02;")
        rebuild_graph.assert_awaited_once()


# ---------------------------------------------------------------------------
# /api/action/{action} endpoint
# ---------------------------------------------------------------------------


class TestActionApi:
    def test_unknown_action(self, test_client):
        resp = test_client.get("/api/action/totally-unknown")
        assert resp.status_code == 404

    def test_clear_cache(self, test_client):
        with patch("gateway.metadata_cache.metadata_cache") as mock_cache:
            mock_cache.invalidate.return_value = "Cache cleared"
            resp = test_client.get("/api/action/clear-cache")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_toggle_anon_enable(self, test_client):
        from gateway.anonymizer import anonymizer
        anonymizer._enabled = False
        resp = test_client.get("/api/action/toggle-anon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        anonymizer._enabled = False  # restore

    def test_toggle_anon_disable(self, test_client):
        from gateway.anonymizer import anonymizer
        anonymizer._enabled = True
        resp = test_client.get("/api/action/toggle-anon")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_toggle_anon_emits_audit(self, test_client):
        from gateway.anonymizer import anonymizer
        anonymizer._enabled = False
        with patch("gateway.server._audit_action") as mock_audit:
            resp = test_client.get("/api/action/toggle-anon")
        assert resp.status_code == 200
        assert mock_audit.call_count == 1
        assert mock_audit.call_args.args[1] == "toggle-anon"
        assert mock_audit.call_args.args[2] is True
        anonymizer._enabled = False  # restore

    def test_switch_db_success(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            with patch("gateway.server._registry") as mock_reg:
                mock_mgr.set_default_db.return_value = True
                mock_reg.switch.return_value = True
                resp = test_client.get("/api/action/switch?name=testdb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_switch_db_missing_name(self, test_client):
        resp = test_client.get("/api/action/switch")
        assert resp.status_code == 400

    def test_switch_db_not_found(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.set_default_db.return_value = False
            resp = test_client.get("/api/action/switch?name=ghost")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False

    def test_db_status_connected(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.has_db.return_value = True
            resp = test_client.get("/api/action/db-status?name=mydb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True

    def test_db_status_disconnected(self, test_client):
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.has_db.return_value = False
            resp = test_client.get("/api/action/db-status?name=mydb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False

    def test_connect_db_missing_fields(self, test_client):
        resp = test_client.post("/api/action/connect-db", json={"name": "only-name"})
        assert resp.status_code == 400

    def test_connect_db_missing_fields_emits_audit(self, test_client):
        with patch("gateway.server._audit_action") as mock_audit:
            resp = test_client.post("/api/action/connect-db", json={"name": "only-name"})
        assert resp.status_code == 400
        assert mock_audit.call_count == 1
        assert mock_audit.call_args.args[1] == "connect-db"
        assert mock_audit.call_args.args[2] is False
        assert mock_audit.call_args.kwargs["reason"] == "missing_fields"

    def test_connect_db_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/action/connect-db",
            content=b"bad json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_connect_db_normalizes_home_project_path(self, test_client):
        with patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")) as mock_connect:
            with patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()):
                resp = test_client.post(
                    "/api/action/connect-db",
                    json={
                        "name": "mydb",
                        "connection": "Srvr=localhost;Ref=MYDB;",
                        "project_path": "/home/as/Z/MYDB",
                    },
                )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_connect.assert_awaited_once_with(
            "mydb",
            "Srvr=localhost;Ref=MYDB;",
            "/hostfs-home/as/Z/MYDB",
        )

    def test_edit_db_updates_connection(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.update.return_value = True

            resp = test_client.post(
                "/api/action/edit-db",
                json={"name": "mydb", "connection": "new-conn", "project_path": "/new/path"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        mock_reg.update.assert_called_once_with(
            "mydb",
            connection="new-conn",
            project_path="/new/path",
        )

    def test_edit_db_normalizes_home_project_path(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.update.return_value = True

            resp = test_client.post(
                "/api/action/edit-db",
                json={"name": "mydb", "project_path": "/home/as/Z/mydb"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_reg.update.assert_called_once_with(
            "mydb",
            connection=None,
            project_path="/hostfs-home/as/Z/mydb",
        )

    def test_edit_db_not_found(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.update.return_value = False

            resp = test_client.post(
                "/api/action/edit-db",
                json={"name": "ghost"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False

    def test_edit_db_missing_name(self, test_client):
        resp = test_client.post("/api/action/edit-db", json={})
        assert resp.status_code == 400

    def test_disconnect_missing_name(self, test_client):
        resp = test_client.get("/api/action/disconnect")
        assert resp.status_code == 400

    def test_disconnect_known_db(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(name="mydb", connection="Srvr=srv;", project_path="/projects")
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.remove_db_backends = AsyncMock()
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.get.return_value = mock_db
                resp = test_client.get("/api/action/disconnect?name=mydb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_disconnect_returns_error_payload(self, test_client):
        with patch("gateway.tool_handlers.db_lifecycle.disconnect_database", new=AsyncMock(return_value="ERROR: boom")):
            resp = test_client.get("/api/action/disconnect?name=mydb")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_remove_missing_name(self, test_client):
        resp = test_client.get("/api/action/remove")
        assert resp.status_code == 400

    def test_remove_known_db(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(name="mydb", connection="Srvr=srv;", project_path="/hostfs-home/as/Z/mydb")
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.remove_db_backends = AsyncMock()
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.get.return_value = mock_db
                mock_reg.remove = MagicMock()
                with patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()):
                    resp = test_client.get("/api/action/remove?name=mydb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_remove_known_db_emits_audit(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(name="mydb", connection="Srvr=srv;", project_path="/hostfs-home/as/Z/mydb")
        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.remove_db_backends = AsyncMock()
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.get.return_value = mock_db
                mock_reg.remove = MagicMock()
                with patch("gateway.server._audit_action") as mock_audit, patch(
                    "gateway.server._trigger_graph_rebuild", new=AsyncMock()
                ):
                    resp = test_client.get("/api/action/remove?name=mydb")
        assert resp.status_code == 200
        assert mock_audit.call_count == 1
        assert mock_audit.call_args.args[1] == "remove"
        assert mock_audit.call_args.args[2] is True
        assert mock_audit.call_args.kwargs["db"] == "mydb"

    def test_remove_unknown_db_returns_404(self, test_client):
        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.server._audit_action"
        ) as mock_audit:
            mock_reg.get.return_value = None
            resp = test_client.get("/api/action/remove?name=ghost")

        assert resp.status_code == 404
        assert resp.json()["ok"] is False
        assert mock_audit.call_args.args[1] == "remove"
        assert mock_audit.call_args.args[2] is False
        assert mock_audit.call_args.kwargs["reason"] == "not_found"

    def test_remove_purges_runtime_state_and_rebuilds_graph(self, test_client):
        from gateway import mcp_server
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/hostfs-home/as/Z/mydb",
            lsp_container="mcp-lsp-mydb",
        )
        server_task = MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())
        mcp_task = MagicMock(done=MagicMock(return_value=False), cancel=MagicMock())
        from gateway import server as gateway_server

        original_gateway_jobs = dict(gateway_server._export_jobs)
        original_gateway_tasks = dict(gateway_server._export_tasks)
        original_server_jobs = dict(mcp_server._export_jobs)
        original_server_tasks = dict(mcp_server._export_tasks)
        original_index_jobs = dict(mcp_server._index_jobs)
        try:
            gateway_server._export_jobs["Srvr=srv;Ref=mydb;"] = {"status": "running", "result": ""}
            gateway_server._export_tasks["Srvr=srv;Ref=mydb;"] = server_task
            mcp_server._export_jobs["Srvr=srv;Ref=mydb;"] = {"status": "running", "result": ""}
            mcp_server._export_tasks["Srvr=srv;Ref=mydb;"] = mcp_task
            mcp_server._index_jobs["Srvr=srv;Ref=mydb;"] = {"status": "done", "result": "ok"}

            with patch("gateway.server._registry") as mock_reg, patch(
                "gateway.server._manager"
            ) as mock_mgr, patch(
                "gateway.bsl_search.bsl_search.invalidate_paths", return_value=True
            ) as mock_invalidate, patch(
                "gateway.server._trigger_graph_rebuild", new=AsyncMock()
            ) as mock_rebuild:
                mock_reg.get.return_value = db
                mock_reg.remove = MagicMock(return_value=True)
                mock_mgr.remove_db_backends = AsyncMock()

                resp = test_client.get("/api/action/remove?name=mydb")

            assert resp.status_code == 200
            assert "Srvr=srv;Ref=mydb;" not in gateway_server._export_jobs
            assert "Srvr=srv;Ref=mydb;" not in gateway_server._export_tasks
            assert "Srvr=srv;Ref=mydb;" not in mcp_server._export_jobs
            assert "Srvr=srv;Ref=mydb;" not in mcp_server._export_tasks
            assert "Srvr=srv;Ref=mydb;" not in mcp_server._index_jobs
            server_task.cancel.assert_called_once()
            mcp_task.cancel.assert_called_once()
            mock_invalidate.assert_called_once_with(
                "/hostfs-home/as/Z/mydb",
                "mcp-lsp-mydb:/projects",
            )
            mock_rebuild.assert_awaited_once()
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_gateway_jobs)
            gateway_server._export_tasks.clear()
            gateway_server._export_tasks.update(original_gateway_tasks)
            mcp_server._export_jobs.clear()
            mcp_server._export_jobs.update(original_server_jobs)
            mcp_server._export_tasks.clear()
            mcp_server._export_tasks.update(original_server_tasks)
            mcp_server._index_jobs.clear()
            mcp_server._index_jobs.update(original_index_jobs)

    def test_remove_waits_for_runtime_cleanup_before_response(self, test_client):
        from gateway.db_registry import DatabaseInfo

        db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/hostfs-home/as/Z/mydb",
        )

        stop_calls = []

        def _stop(slug):
            stop_calls.append(slug)

        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._trigger_graph_rebuild", new=AsyncMock()
        ), patch(
            "gateway.server._audit_action"
        ), patch(
            "gateway.docker_manager.stop_db_containers", side_effect=_stop
        ):
            mock_reg.get.return_value = db
            mock_reg.remove = MagicMock(return_value=True)
            mock_mgr.remove_db_backends = AsyncMock()

            resp = test_client.get("/api/action/remove?name=mydb")

        assert resp.status_code == 200
        assert stop_calls == ["mydb"]

    def test_reconnect_missing_name(self, test_client):
        resp = test_client.get("/api/action/reconnect")
        assert resp.status_code == 400

    def test_reconnect_unknown_db(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = None
            resp = test_client.get("/api/action/reconnect?name=ghost")
        assert resp.status_code == 404

    def test_reconnect_unknown_db_emits_audit(self, test_client):
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = None
            with patch("gateway.server._audit_action") as mock_audit:
                resp = test_client.get("/api/action/reconnect?name=ghost")
        assert resp.status_code == 404
        assert mock_audit.call_count == 1
        assert mock_audit.call_args.args[1] == "reconnect"
        assert mock_audit.call_args.args[2] is False
        assert mock_audit.call_args.kwargs["reason"] == "not_found"

    def test_reconnect_already_connected(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(name="mydb", connection="Srvr=srv;", project_path="/projects")
        with patch("gateway.server._registry") as mock_reg:
            mock_reg.get.return_value = mock_db
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.has_db.return_value = True
                resp = test_client.get("/api/action/reconnect?name=mydb")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    @pytest.mark.asyncio
    async def test_reconnect_action_runs_background_success_path(self):
        from gateway import server

        db = SimpleNamespace(
            name="mydb",
            slug="mydb",
            project_path="/projects/mydb",
        )
        created = []
        request = SimpleNamespace(
            path_params={"action": "reconnect"},
            query_params={"name": "mydb"},
            method="POST",
            url=SimpleNamespace(path="/api/action/reconnect"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        def _fake_create_task(coro):
            created.append(coro)
            return MagicMock(cancel=MagicMock())

        async def _wait_passthrough(awaitable, timeout=None):
            return await awaitable

        loop = MagicMock()
        loop.run_in_executor.side_effect = [
            asyncio.sleep(0, result=(6100, "onec-toolkit-mydb")),
            asyncio.sleep(0, result="mcp-lsp-mydb"),
        ]

        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._manager"
        ) as manager, patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.asyncio.get_running_loop", return_value=loop
        ), patch(
            "gateway.server.asyncio.wait_for", side_effect=_wait_passthrough
        ):
            registry.get.return_value = db
            manager.has_db.return_value = False
            manager.add_db_backends = AsyncMock()

            resp = await server.action_api(request)
            await created[0]

        assert resp.status_code == 200
        registry.update_runtime.assert_called_once_with(
            "mydb",
            toolkit_port=6100,
            toolkit_url="http://localhost:6100/mcp",
            lsp_container="mcp-lsp-mydb",
            connected=False,
        )
        manager.add_db_backends.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconnect_action_rewrites_stale_project_path_before_start(self):
        from gateway import server

        db = SimpleNamespace(
            name="mydb",
            slug="mydb",
            project_path="/home/as",
        )
        created = []
        request = SimpleNamespace(
            path_params={"action": "reconnect"},
            query_params={"name": "mydb"},
            method="POST",
            url=SimpleNamespace(path="/api/action/reconnect"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        def _fake_create_task(coro):
            created.append(coro)
            return MagicMock(cancel=MagicMock())

        async def _wait_passthrough(awaitable, timeout=None):
            return await awaitable

        loop = MagicMock()
        loop.run_in_executor.side_effect = [
            asyncio.sleep(0, result=(6100, "onec-toolkit-mydb")),
            asyncio.sleep(0, result="mcp-lsp-mydb"),
        ]

        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._manager"
        ) as manager, patch(
            "gateway.server._read_env_value", return_value="/home/as/Z"
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.asyncio.get_running_loop", return_value=loop
        ), patch(
            "gateway.server.asyncio.wait_for", side_effect=_wait_passthrough
        ):
            registry.get.return_value = db
            manager.has_db.return_value = False
            manager.add_db_backends = AsyncMock()

            resp = await server.action_api(request)
            await created[0]

        assert resp.status_code == 200
        registry.update.assert_called_once_with("mydb", project_path="/hostfs-home/as/Z/mydb")

    @pytest.mark.asyncio
    async def test_reconnect_action_logs_background_failure(self):
        from gateway import server

        db = SimpleNamespace(
            name="mydb",
            slug="mydb",
            project_path="/projects/mydb",
        )
        created = []
        request = SimpleNamespace(
            path_params={"action": "reconnect"},
            query_params={"name": "mydb"},
            method="POST",
            url=SimpleNamespace(path="/api/action/reconnect"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        def _fake_create_task(coro):
            created.append(coro)
            return MagicMock(cancel=MagicMock())

        async def _wait_passthrough(awaitable, timeout=None):
            return await awaitable

        async def _boom():
            raise RuntimeError("start failed")

        loop = MagicMock()
        loop.run_in_executor.return_value = _boom()

        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._manager"
        ) as manager, patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.asyncio.get_running_loop", return_value=loop
        ), patch(
            "gateway.server.asyncio.wait_for", side_effect=_wait_passthrough
        ), patch(
            "gateway.server.logger"
        ) as logger:
            registry.get.return_value = db
            manager.has_db.return_value = False
            manager.add_db_backends = AsyncMock()

            resp = await server.action_api(request)
            await created[0]

        assert resp.status_code == 200
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect_action_runs_background_without_lsp_container(self):
        from gateway import server

        db = SimpleNamespace(
            name="mydb",
            slug="mydb",
            project_path="/projects/mydb",
        )
        created = []
        request = SimpleNamespace(
            path_params={"action": "reconnect"},
            query_params={"name": "mydb"},
            method="POST",
            url=SimpleNamespace(path="/api/action/reconnect"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        def _fake_create_task(coro):
            created.append(coro)
            return MagicMock(cancel=MagicMock())

        async def _wait_passthrough(awaitable, timeout=None):
            return await awaitable

        loop = MagicMock()
        loop.run_in_executor.side_effect = [
            asyncio.sleep(0, result=(6100, "onec-toolkit-mydb")),
            asyncio.sleep(0, result=""),
        ]

        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._manager"
        ) as manager, patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.asyncio.get_running_loop", return_value=loop
        ), patch(
            "gateway.server.asyncio.wait_for", side_effect=_wait_passthrough
        ):
            registry.get.return_value = db
            manager.has_db.return_value = False
            manager.add_db_backends = AsyncMock()

            resp = await server.action_api(request)
            await created[0]

        assert resp.status_code == 200
        assert manager.add_db_backends.await_args.args[2] is None

    def test_get_bsl_workspace_returns_os_and_placeholder(self, test_client):
        with patch("gateway.server._read_env_value", return_value="/home/as/Z"):
            resp = test_client.get("/api/action/get-bsl-workspace")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["value"] == "/home/as/Z"
        assert data["placeholder"]

    def test_get_report_settings_returns_runtime_defaults(self, test_client):
        with patch("gateway.server.settings.report_auto_analyze_enabled", True), \
             patch("gateway.server.settings.report_run_default_max_rows", 1200), \
             patch("gateway.server.settings.report_run_default_timeout_seconds", 15), \
             patch("gateway.server.settings.report_validate_default_max_rows", 7), \
             patch("gateway.server.settings.report_validate_default_timeout_seconds", 90):
            resp = test_client.post("/api/action/get-report-settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["auto_analyze_enabled"] is True
        assert data["run_default_max_rows"] == 1200
        assert data["run_default_timeout_seconds"] == 15
        assert data["validate_default_max_rows"] == 7
        assert data["validate_default_timeout_seconds"] == 90

    def test_reindex_bsl_uses_public_manager_accessor(self, test_client):
        from gateway.db_registry import DatabaseInfo
        from mcp.types import CallToolResult, TextContent

        mock_db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/projects/mydb",
            lsp_container="mcp-lsp-mydb",
        )
        mock_lsp = MagicMock()
        mock_lsp.call_tool = AsyncMock(
            return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
        )

        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.bsl_search.bsl_search.build_index", return_value="Indexed 10 symbols"
        ) as mock_build:
            mock_reg.get.return_value = mock_db
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.get_db_backend.return_value = mock_lsp
                resp = test_client.get("/api/action/reindex-bsl?name=mydb")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "Indexed 10 symbols" in data["message"]
        mock_build.assert_called_once_with("/projects/mydb", "mcp-lsp-mydb")
        mock_mgr.get_db_backend.assert_called_once_with("mydb", "lsp")

    def test_reindex_bsl_lsp_not_found(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/projects/mydb",
            lsp_container="mcp-lsp-mydb",
        )
        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.bsl_search.bsl_search.build_index", return_value="Indexed 10 symbols"
        ) as mock_build:
            mock_reg.get.return_value = mock_db
            with patch("gateway.server._manager") as mock_mgr:
                mock_mgr.get_db_backend.return_value = None
                resp = test_client.get("/api/action/reindex-bsl?name=mydb")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "Indexed 10 symbols" in data["message"]
        assert "LSP недоступен" in data["message"]
        mock_build.assert_called_once_with("/projects/mydb", "mcp-lsp-mydb")

    def test_reindex_bsl_without_lsp_container_uses_full_text_only_message(self, test_client):
        from gateway.db_registry import DatabaseInfo

        mock_db = DatabaseInfo(
            name="mydb",
            connection="Srvr=srv;Ref=mydb;",
            project_path="/projects/mydb",
            lsp_container="",
        )
        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.bsl_search.bsl_search.build_index", return_value="Indexed 10 symbols"
        ) as mock_build:
            mock_reg.get.return_value = mock_db
            resp = test_client.get("/api/action/reindex-bsl?name=mydb")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "Indexed 10 symbols" in data["message"]
        assert "LSP недоступен" in data["message"]
        mock_build.assert_called_once_with("/projects/mydb", "")

    def test_get_env(self, test_client):
        with patch(
            "gateway.server._read_env_file",
            return_value="PORT=8080\nDOCKER_CONTROL_TOKEN=secret\nANONYMIZER_SALT=salt\n",
        ):
            resp = test_client.get("/api/action/get-env")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "PORT=8080" in data["env"]
        assert "DOCKER_CONTROL_TOKEN=***hidden***" in data["env"]
        assert "ANONYMIZER_SALT=***hidden***" in data["env"]

    def test_save_env_emits_audit_without_content(self, test_client):
        content = "LOG_LEVEL=INFO\nDOCKER_CONTROL_TOKEN=***hidden***\nANONYMIZER_SALT=***hidden***\n"
        with patch("gateway.server._write_env_file", return_value={"ok": True, "message": "saved"}) as write_env:
            with patch(
                "gateway.server._read_env_value",
                side_effect=lambda key: {
                    "DOCKER_CONTROL_TOKEN": "actual-secret",
                    "ANONYMIZER_SALT": "actual-salt",
                }.get(key, ""),
            ):
                with patch("gateway.server._restart_gateway"):
                    with patch("gateway.server._audit_action") as mock_audit:
                        resp = test_client.post("/api/action/save-env", json={"content": content, "mode": "replace"})

        assert resp.status_code == 200
        assert write_env.call_args.args[0] == (
            "LOG_LEVEL=INFO\nDOCKER_CONTROL_TOKEN=actual-secret\nANONYMIZER_SALT=actual-salt\n"
        )
        assert mock_audit.call_count == 1
        assert mock_audit.call_args.args[1] == "save-env"
        assert mock_audit.call_args.args[2] is True
        assert mock_audit.call_args.kwargs["bytes"] == len(content)
        assert "content" not in mock_audit.call_args.kwargs

    def test_save_env_rejects_sparse_patch_without_replace_mode(self, test_client):
        current = (
            "PORT=8080\n"
            "LOG_LEVEL=INFO\n"
            "DOCKER_CONTROL_TOKEN=secret-token\n"
            "ANONYMIZER_SALT=secret-salt\n"
        )
        with patch("gateway.server._read_env_file", return_value=current), \
             patch("gateway.server._write_env_file", return_value={"ok": True, "message": "saved"}) as write_env, \
             patch("gateway.server._restart_gateway"), \
             patch("gateway.server._audit_action") as audit:
            resp = test_client.post("/api/action/save-env", json={"content": "PORT=9090\n"})

        assert resp.status_code == 400
        assert resp.json()["error"] == "partial env update rejected; submit the full .env content"
        write_env.assert_not_called()
        audit.assert_called_once()

    def test_save_env_invalid_json(self, test_client):
        with patch("gateway.server._audit_action") as audit:
            resp = test_client.post(
                "/api/action/save-env",
                content=b"bad",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 400
        audit.assert_called_once()

    def test_save_env_requires_content(self, test_client):
        with patch("gateway.server._audit_action") as audit:
            resp = test_client.post("/api/action/save-env", json={})
        assert resp.status_code == 400
        audit.assert_called_once()

    def test_save_bsl_workspace_requires_value(self, test_client):
        resp = test_client.post("/api/action/save-bsl-workspace", json={"value": ""})
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False
        assert "value required" in data["error"]

    def test_save_report_settings_applies_runtime_without_restart(self, test_client):
        payload = {
            "auto_analyze_enabled": False,
            "run_default_max_rows": 250,
            "run_default_timeout_seconds": 30,
            "validate_default_max_rows": 3,
            "validate_default_timeout_seconds": 120,
        }

        with patch("gateway.server._update_env_values", return_value={"ok": True, "message": "saved"}) as update_env, \
             patch("gateway.server._apply_report_settings_runtime") as apply_runtime, \
             patch("gateway.server._current_report_settings_payload", return_value=dict(payload)):
            resp = test_client.post("/api/action/save-report-settings", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["auto_analyze_enabled"] is False
        assert data["run_default_max_rows"] == 250
        assert data["run_default_timeout_seconds"] == 30
        assert data["validate_default_max_rows"] == 3
        assert data["validate_default_timeout_seconds"] == 120
        update_env.assert_called_once()
        apply_runtime.assert_called_once_with(payload)

    def test_save_report_settings_rejects_invalid_values(self, test_client):
        with patch("gateway.server._update_env_values") as update_env:
            resp = test_client.post(
                "/api/action/save-report-settings",
                json={"auto_analyze_enabled": True, "run_default_max_rows": -1},
            )

        assert resp.status_code == 400
        assert resp.json()["ok"] is False
        update_env.assert_not_called()

    def test_save_bsl_workspace_applies_runtime_without_restart(self, test_client):
        with patch("gateway.server._update_env_value", return_value={"ok": True, "message": "saved"}) as mock_update:
            with patch("gateway.server._read_env_value", return_value="http://localhost:8082"):
                with patch("gateway.server.settings.export_host_url", ""):
                    with patch(
                        "gateway.server._apply_bsl_workspace_runtime",
                        new=AsyncMock(return_value={"db_reconfigured": 1, "db_errors": 0, "errors": []}),
                    ) as mock_apply:
                        with patch(
                            "gateway.server._recreate_bsl_graph_runtime",
                            new=AsyncMock(return_value={"attempted": True, "ok": True}),
                        ) as mock_graph:
                            with patch("gateway.server._restart_gateway") as mock_restart:
                                resp = test_client.post(
                                    "/api/action/save-bsl-workspace",
                                    json={"value": "/home/as/Z2"},
                                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "сохранена и применена" in data["message"]
        assert "Базы обновлены: 1" in data["message"]
        assert "Граф пересоздан." in data["message"]

        assert mock_update.call_count >= 2
        mock_update.assert_any_call("BSL_HOST_WORKSPACE", "/home/as/Z2")
        mock_update.assert_any_call("BSL_WORKSPACE", "/home/as/Z2")
        mock_apply.assert_awaited_once_with("/home/as/Z2", "http://localhost:8082")
        mock_graph.assert_awaited_once()
        mock_restart.assert_not_called()

    def test_save_bsl_workspace_derives_export_url_from_host_root_prefix(self, test_client):
        def fake_update(key, value):
            return {"ok": True, "message": f"{key}={value}"}

        with patch("gateway.server._update_env_value", side_effect=fake_update) as mock_update, \
             patch("gateway.server._read_env_value", side_effect=lambda key: "/mnt/c/Users/as" if key == "HOST_ROOT_PREFIX" else ""), \
             patch("gateway.server.os.environ", {"HOST_ROOT_PREFIX": "/mnt/c/Users/as"}), \
             patch("gateway.server.settings.export_host_url", ""), \
             patch(
                 "gateway.server._apply_bsl_workspace_runtime",
                 new=AsyncMock(return_value={"db_reconfigured": 0, "db_errors": 1, "errors": ["db1: boom"]}),
             ) as mock_apply, \
             patch(
                 "gateway.server._recreate_bsl_graph_runtime",
                 new=AsyncMock(return_value={"attempted": True, "ok": False, "error": "boom"}),
             ) as mock_graph:
            resp = test_client.post("/api/action/save-bsl-workspace", json={"value": "C:/Users/as/Z"})

        assert resp.status_code == 200
        assert "ошибок 1" in resp.json()["message"]
        assert "Граф не удалось пересоздать автоматически." in resp.json()["message"]
        mock_update.assert_any_call("EXPORT_HOST_URL", "http://host.docker.internal:8082")
        mock_apply.assert_awaited_once_with("C:/Users/as/Z", "http://host.docker.internal:8082")
        mock_graph.assert_awaited_once()

    def test_diagnostics_action(self, test_client):
        with patch("gateway.server._collect_diagnostics", return_value={"gateway": {"version": "v1.0.1"}}):
            resp = test_client.get("/api/action/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "data" in data

    def test_docker_info_action(self, test_client):
        with patch("gateway.server._get_docker_system_info", return_value={"version": "24.0"}), patch(
            "gateway.server._get_container_info",
            return_value=[{"name": "onec-mcp-gw", "memory_usage_human": "86.66 MB"}],
        ):
            resp = test_client.get("/api/action/docker-info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["docker_system"]["version"] == "24.0"
        assert data["data"]["container_info"][0]["name"] == "onec-mcp-gw"


# ---------------------------------------------------------------------------
# API token auth (mutating endpoints)
# ---------------------------------------------------------------------------


class TestApiTokenAuth:
    def test_mutating_action_requires_token_when_configured(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.get("/api/action/clear-cache")
        assert resp.status_code == 401

    def test_mutating_action_rejects_wrong_token(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.get(
            "/api/action/clear-cache",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 403

    def test_mutating_action_accepts_valid_token(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        with patch("gateway.metadata_cache.metadata_cache") as mock_cache:
            mock_cache.invalidate.return_value = "Cache cleared"
            resp = test_client.get(
                "/api/action/clear-cache",
                headers={"Authorization": "Bearer secret-token"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_readonly_action_works_without_token(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.has_db.return_value = False
            resp = test_client.get("/api/action/db-status?name=mydb")

        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    def test_register_requires_token_when_configured(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.post("/api/register", json={"name": "mydb"})
        assert resp.status_code == 401

    def test_export_requires_token_when_configured(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.post("/api/export-bsl", json={"connection": "Srvr=srv;Ref=base;"})
        assert resp.status_code == 401

    def test_export_cancel_requires_token_when_configured(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.post("/api/export-cancel", json={"connection": "Srvr=srv;Ref=base;"})
        assert resp.status_code == 401

    def test_unregister_requires_token_when_configured(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        resp = test_client.post("/api/unregister", json={"name": "mydb"})
        assert resp.status_code == 401

    def test_export_accepts_valid_token(self, test_client, monkeypatch):
        from gateway import server
        monkeypatch.setattr(server.settings, "gateway_api_token", "secret-token")

        with patch("gateway.server.settings") as mock_settings:
            mock_settings.gateway_api_token = "secret-token"
            mock_settings.bsl_host_workspace = "/home/user/bsl"
            mock_settings.bsl_workspace = "/workspace"
            mock_settings.export_host_url = ""
            mock_settings.port = 8080
            with patch("gateway.mcp_server._run_export_bsl", new_callable=AsyncMock) as mock_export, \
                 patch("gateway.server._registry") as mock_reg:
                mock_reg.get_active.return_value = None
                mock_export.return_value = "Export completed successfully."
                resp = test_client.post(
                    "/api/export-bsl",
                    json={"connection": "Srvr=srv;Ref=base;", "output_dir": "/workspace/test"},
                    headers={"Authorization": "Bearer secret-token"},
                )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# _build_backends
# ---------------------------------------------------------------------------


class TestBuildBackends:
    def test_all_backends_enabled(self, monkeypatch):
        from gateway import server, config
        monkeypatch.setattr(
            config.settings,
            "enabled_backends",
            "onec-toolkit,platform-context,bsl-lsp-bridge",
        )
        monkeypatch.setattr(config.settings, "bsl_lsp_command", "/usr/local/bin/bsl-lsp")
        backends = server._build_backends()
        names = [b.name for b in backends]
        assert "onec-toolkit" in names
        assert "platform-context" in names
        assert "bsl-lsp-bridge" in names

    def test_only_toolkit_enabled(self, monkeypatch):
        from gateway import server, config
        monkeypatch.setattr(config.settings, "enabled_backends", "onec-toolkit")

        backends = server._build_backends()
        names = [b.name for b in backends]
        assert "onec-toolkit" in names
        assert "platform-context" not in names
        assert "bsl-lsp-bridge" not in names

    def test_empty_backends(self, monkeypatch):
        from gateway import server, config
        monkeypatch.setattr(config.settings, "enabled_backends", "")

        backends = server._build_backends()
        assert backends == []

    def test_lsp_direct_binary_mode(self, monkeypatch):
        from gateway import server, config
        from gateway.backends.stdio_backend import StdioBackend
        monkeypatch.setattr(config.settings, "enabled_backends", "bsl-lsp-bridge")
        monkeypatch.setattr(config.settings, "bsl_lsp_command", "/usr/local/bin/bsl-lsp")

        backends = server._build_backends()
        assert len(backends) == 1
        assert isinstance(backends[0], StdioBackend)
        assert backends[0].name == "bsl-lsp-bridge"

    def test_test_runner_enabled(self, monkeypatch):
        from gateway import server, config
        monkeypatch.setattr(config.settings, "enabled_backends", "test-runner")
        monkeypatch.setattr(config.settings, "test_runner_url", "http://runner:9000/sse")

        backends = server._build_backends()
        names = [b.name for b in backends]
        assert "test-runner" in names

    def test_lsp_gateway_mode_does_not_register_static_backend(self, monkeypatch):
        from gateway import server, config

        monkeypatch.setattr(config.settings, "enabled_backends", "bsl-lsp-bridge")
        monkeypatch.setattr(config.settings, "bsl_lsp_command", "")
        backends = server._build_backends()
        assert backends == []


class TestRestoreDatabases:
    @pytest.mark.asyncio
    async def test_restore_databases_returns_false_when_registry_state_empty(self):
        from gateway import server

        with patch("gateway.server._registry") as mock_reg:
            mock_reg.load_saved_state.return_value = []
            assert await server._restore_databases() is False

    @pytest.mark.asyncio
    async def test_restore_databases_reconnects_saved_database_and_restores_default(self):
        from gateway import server

        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.docker_manager.start_toolkit", return_value=(6101, "toolkit-db1")
        ), patch(
            "gateway.docker_manager.start_lsp", return_value="mcp-lsp-db1"
        ):
            mock_reg.load_saved_state.return_value = [
                {
                    "name": "db1",
                    "slug": "db1",
                    "connection": "Srvr=srv;Ref=db1;",
                    "project_path": "/projects/db1",
                }
            ]
            mock_reg.get_saved_active.return_value = "db1"
            mock_mgr.add_db_backends = AsyncMock()
            mock_mgr.set_default_db.return_value = True

            restored = await server._restore_databases()

        assert restored is True
        mock_reg.register.assert_called_once_with("db1", "Srvr=srv;Ref=db1;", "/projects/db1", slug="db1")
        mock_reg.update_runtime.assert_called_once()
        mock_mgr.add_db_backends.assert_awaited_once()
        mock_mgr.set_default_db.assert_called_once_with("db1")
        mock_reg.switch.assert_called_once_with("db1")

    @pytest.mark.asyncio
    async def test_restore_databases_removes_database_when_runtime_start_fails(self):
        from gateway import server

        with patch("gateway.server._registry") as mock_reg, patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.docker_manager.start_toolkit", side_effect=RuntimeError("docker boom")
        ):
            mock_reg.load_saved_state.return_value = [
                {
                    "name": "db1",
                    "connection": "Srvr=srv;Ref=db1;",
                    "project_path": "/projects/db1",
                }
            ]
            mock_reg.get_saved_active.return_value = None
            mock_mgr.add_db_backends = AsyncMock()

            restored = await server._restore_databases()

        assert restored is False
        mock_reg.remove.assert_called_once_with("db1")
        mock_mgr.add_db_backends.assert_not_called()


class TestLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_starts_backends_rebuilds_graph_and_stops_cleanly(self):
        from gateway import server

        fake_cleanup_task = MagicMock()
        fake_retry_task = MagicMock()
        created = []

        def _fake_create_task(coro):
            created.append(coro)
            coro.close()
            return fake_cleanup_task if len(created) == 1 else fake_retry_task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)
        fake_client = SimpleNamespace(close=MagicMock())

        with patch("gateway.server._build_backends", return_value=["b1"]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", return_value=2
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=True)
        ), patch(
            "gateway.server._trigger_graph_rebuild", new=AsyncMock()
        ) as mock_rebuild, patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._patch_toolkit_structured_output"
        ), patch(
            "gateway.docker_manager._client", fake_client
        ):
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {"onec-toolkit": {"ok": True}}
            mock_mgr.stop_all = AsyncMock()

            async with server.lifespan(server._starlette):
                pass

        mock_mgr.start_all.assert_awaited_once_with(["b1"])
        mock_rebuild.assert_awaited_once()
        fake_cleanup_task.cancel.assert_called_once()
        fake_retry_task.cancel.assert_called_once()
        fake_client.close.assert_called_once()
        mock_mgr.stop_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_handles_patch_and_cleanup_exceptions(self):
        from gateway import server

        fake_cleanup_task = MagicMock()
        fake_retry_task = MagicMock()

        def _fake_create_task(coro):
            coro.close()
            return fake_cleanup_task if not fake_cleanup_task.cancel.called else fake_retry_task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "gateway.docker_manager._patch_toolkit_structured_output",
            side_effect=RuntimeError("patch failed"),
        ), patch("gateway.server._build_backends", return_value=[]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", side_effect=RuntimeError("cleanup failed")
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=False)
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._client", None
        ):
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {}
            mock_mgr.stop_all = AsyncMock()

            async with server.lifespan(server._starlette):
                pass

        mock_mgr.stop_all.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lifespan_cleanup_loop_logs_removed_and_exceptions(self):
        from gateway import server

        created = []

        def _fake_create_task(coro):
            task = MagicMock()
            task.cancel = MagicMock()
            created.append(coro)
            return task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("gateway.server._build_backends", return_value=[]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", return_value=0
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=False)
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._patch_toolkit_structured_output"
        ), patch(
            "gateway.docker_manager._client", None
        ), patch(
            "gateway.server.logger"
        ) as logger:
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {}
            mock_mgr.stop_all = AsyncMock()
            mock_mgr.cleanup_stale_sessions.side_effect = [2, RuntimeError("cleanup boom")]

            cleaned = iter([(3, 1), RuntimeError("terminated boom")])

            def _cleanup_side_effect():
                value = next(cleaned)
                if isinstance(value, Exception):
                    raise value
                return value

            with patch("gateway.server._cleanup_terminated_mcp_sessions", side_effect=_cleanup_side_effect):
                async with server.lifespan(server._starlette):
                    pass

                cleanup_coro = created[0]
                created[1].close()

                async def _sleep_twice_then_cancel(_seconds):
                    calls = getattr(_sleep_twice_then_cancel, "calls", 0)
                    if calls >= 2:
                        raise asyncio.CancelledError()
                    _sleep_twice_then_cancel.calls = calls + 1
                    return None

                with patch("gateway.server.asyncio.sleep", side_effect=_sleep_twice_then_cancel):
                    with pytest.raises(asyncio.CancelledError):
                        await cleanup_coro

        assert any(
            "Cleaned up 2 stale sessions" in str(call.args[0])
            for call in logger.info.call_args_list
        )
        assert any(
            "Cleaned up 3 terminated MCP session(s)" in str(call.args[0])
            for call in logger.info.call_args_list
        )
        assert any(
            "Session cleanup error:" in str(call.args[0])
            for call in logger.warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_lifespan_backend_retry_loop_logs_recovery_and_exception(self):
        from gateway import server

        created = []

        def _fake_create_task(coro):
            task = MagicMock()
            task.cancel = MagicMock()
            created.append(coro)
            return task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("gateway.server._build_backends", return_value=[]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", return_value=0
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=False)
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._patch_toolkit_structured_output"
        ), patch(
            "gateway.docker_manager._client", None
        ), patch(
            "gateway.server.logger"
        ) as logger:
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {}
            mock_mgr.stop_all = AsyncMock()
            mock_mgr.retry_unavailable_backends = AsyncMock(side_effect=[1, RuntimeError("retry boom")])

            async with server.lifespan(server._starlette):
                pass

            retry_coro = created[1]
            created[0].close()

            async def _sleep_twice_then_cancel(_seconds):
                calls = getattr(_sleep_twice_then_cancel, "calls", 0)
                if calls >= 2:
                    raise asyncio.CancelledError()
                _sleep_twice_then_cancel.calls = calls + 1
                return None

            with patch("gateway.server.asyncio.sleep", side_effect=_sleep_twice_then_cancel):
                with pytest.raises(asyncio.CancelledError):
                    await retry_coro

        assert any(
            "Recovered 1 unavailable backend(s)" in str(call.args[0])
            for call in logger.info.call_args_list
        )
        assert any(
            "Backend retry error: retry boom" in str(call.args[0])
            for call in logger.warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_lifespan_loops_handle_zero_results_paths(self):
        from gateway import server

        created = []

        def _fake_create_task(coro):
            task = MagicMock()
            task.cancel = MagicMock()
            created.append(coro)
            return task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("gateway.server._build_backends", return_value=[]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", return_value=0
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=False)
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._patch_toolkit_structured_output"
        ), patch(
            "gateway.docker_manager._client", None
        ):
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {}
            mock_mgr.stop_all = AsyncMock()
            mock_mgr.cleanup_stale_sessions.return_value = 0
            mock_mgr.retry_unavailable_backends = AsyncMock(return_value=0)

            with patch("gateway.server._cleanup_terminated_mcp_sessions", return_value=(0, 0)):
                async with server.lifespan(server._starlette):
                    pass

                cleanup_coro = created[0]
                retry_coro = created[1]

                async def _sleep_once_then_cancel(_seconds):
                    if getattr(_sleep_once_then_cancel, "called", False):
                        raise asyncio.CancelledError()
                    _sleep_once_then_cancel.called = True
                    return None

                with patch("gateway.server.asyncio.sleep", side_effect=_sleep_once_then_cancel):
                    with pytest.raises(asyncio.CancelledError):
                        await cleanup_coro

                async def _sleep_once_then_cancel_retry(_seconds):
                    if getattr(_sleep_once_then_cancel_retry, "called", False):
                        raise asyncio.CancelledError()
                    _sleep_once_then_cancel_retry.called = True
                    return None

                with patch("gateway.server.asyncio.sleep", side_effect=_sleep_once_then_cancel_retry):
                    with pytest.raises(asyncio.CancelledError):
                        await retry_coro

    @pytest.mark.asyncio
    async def test_lifespan_ignores_docker_client_close_error(self):
        from gateway import server

        fake_cleanup_task = MagicMock()
        fake_retry_task = MagicMock()
        created = []

        def _fake_create_task(coro):
            created.append(coro)
            coro.close()
            return fake_cleanup_task if len(created) == 1 else fake_retry_task

        fake_session_ctx = MagicMock()
        fake_session_ctx.__aenter__ = AsyncMock(return_value=None)
        fake_session_ctx.__aexit__ = AsyncMock(return_value=False)
        fake_client = SimpleNamespace(close=MagicMock(side_effect=RuntimeError("close failed")))

        with patch("gateway.server._build_backends", return_value=[]), patch(
            "gateway.server._manager"
        ) as mock_mgr, patch(
            "gateway.server._cleanup_orphan_db_containers", return_value=0
        ), patch(
            "gateway.server._restore_databases", new=AsyncMock(return_value=False)
        ), patch(
            "gateway.server.asyncio.create_task", side_effect=_fake_create_task
        ), patch(
            "gateway.server.session_manager.run", return_value=fake_session_ctx
        ), patch(
            "gateway.docker_manager._patch_toolkit_structured_output"
        ), patch(
            "gateway.docker_manager._client", fake_client
        ):
            mock_mgr.start_all = AsyncMock()
            mock_mgr.status.return_value = {}
            mock_mgr.stop_all = AsyncMock()

            async with server.lifespan(server._starlette):
                pass

        fake_client.close.assert_called_once()
        mock_mgr.stop_all.assert_awaited_once()


# ---------------------------------------------------------------------------
# _read_env_file / _write_env_file
# ---------------------------------------------------------------------------


class TestEnvFileFunctions:
    def test_read_env_file_not_found(self, tmp_path, monkeypatch):
        from gateway.server import _read_env_file
        nonexistent = str(tmp_path / "nonexistent.env")
        # Patch all known paths so none can be found
        with patch("builtins.open", side_effect=FileNotFoundError("not found")):
            monkeypatch.setenv("ENV_FILE_PATH", nonexistent)
            result = _read_env_file()
        assert result.startswith("#") or "not found" in result.lower()

    def test_read_env_via_env_path(self, tmp_path, monkeypatch):
        from gateway.server import _read_env_file
        env_file = tmp_path / "custom.env"
        env_file.write_text("KEY=value\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE_PATH", str(env_file))

        # Patch so all standard paths fail but ENV_FILE_PATH path succeeds
        original_open = open

        def selective_open(path, *args, **kwargs):
            if str(path) in ("/data/.env", ".env", "/app/.env"):
                raise FileNotFoundError(f"not found: {path}")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            result = _read_env_file()
        assert "KEY=value" in result

    def test_write_env_file_returns_dict(self, tmp_path):
        from gateway.server import _write_env_file
        target = tmp_path / ".env"
        real_open = open

        def fake_open(path, mode="r", encoding=None):
            if path in ("/data/.env", ".env", "/app/.env"):
                return real_open(target, mode, encoding=encoding)
            return real_open(path, mode, encoding=encoding)

        with patch("builtins.open", side_effect=fake_open):
            result = _write_env_file("PORT=9090\n")

        assert isinstance(result, dict)
        assert "ok" in result
        assert target.read_text(encoding="utf-8") == "PORT=9090\n"

    def test_read_env_file_returns_string(self, tmp_path, monkeypatch):
        from gateway.server import _read_env_file
        env_file = tmp_path / "test.env"
        env_file.write_text("PORT=8080\nLOG_LEVEL=INFO\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE_PATH", str(env_file))

        original_open = open

        def selective_open(path, *args, **kwargs):
            if str(path) in ("/data/.env", ".env", "/app/.env"):
                raise FileNotFoundError(f"not found: {path}")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=selective_open):
            result = _read_env_file()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_read_env_file_returns_fallback_when_env_file_path_unset(self, monkeypatch):
        from gateway.server import _read_env_file

        monkeypatch.delenv("ENV_FILE_PATH", raising=False)
        with patch("builtins.open", side_effect=FileNotFoundError("not found")):
            result = _read_env_file()

        assert result.startswith("# .env file not found")


# ---------------------------------------------------------------------------
# _collect_diagnostics
# ---------------------------------------------------------------------------


class TestCollectDiagnostics:
    def test_collect_diagnostics_structure(self):
        from gateway.server import _collect_diagnostics

        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {}
            mock_mgr.active_db = None
            mock_mgr.session_count = 0
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.list.return_value = []
                with patch("gateway.server._get_container_info", return_value=[]):
                    with patch("gateway.server._get_docker_system_info", return_value={"error": "no docker"}):
                        diag = _collect_diagnostics()

        assert "gateway" in diag
        assert "backends" in diag
        assert "databases" in diag
        assert "optional_services" in diag
        assert "config" in diag

    def test_gateway_version_present(self):
        from gateway.server import _collect_diagnostics

        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {}
            mock_mgr.active_db = None
            mock_mgr.session_count = 0
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.list.return_value = []
                with patch("gateway.server._get_container_info", return_value=[]):
                    with patch("gateway.server._get_docker_system_info", return_value={}):
                        diag = _collect_diagnostics()

        assert "version" in diag["gateway"]

    def test_diagnostics_includes_profiling(self):
        from gateway.server import _collect_diagnostics

        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {}
            mock_mgr.active_db = None
            mock_mgr.session_count = 0
            with patch("gateway.server._registry") as mock_reg:
                mock_reg.list.return_value = []
                with patch("gateway.server._get_container_info", return_value=[]):
                    with patch("gateway.server._get_docker_system_info", return_value={}):
                        diag = _collect_diagnostics()

        assert "profiling" in diag
        assert "cache" in diag
        assert "anonymization" in diag

    def test_collect_diagnostics_includes_reports_summary(self):
        from gateway import server

        with patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_docker_system_info", return_value={}), \
             patch("gateway.server._manager.status", return_value={}), \
             patch("gateway.server._registry.list", return_value=[]), \
             patch("gateway.server._collect_reports_summary", return_value=[{"database": "ERP", "catalog_ready": True}]), \
             patch("gateway.profiler.profiler.get_stats", return_value={}), \
             patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
             patch("gateway.anonymizer.anonymizer.enabled", False):
            diag = server._collect_diagnostics()

        assert diag["reports_summary"] == [{"database": "ERP", "catalog_ready": True}]

    def test_collect_reports_summary_reads_catalog_and_result_files(self, tmp_path):
        from gateway.report_catalog import ReportCatalog
        from gateway.server import _collect_reports_summary

        catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "report-results")
        catalog.replace_analysis(
            "ERP",
            "/projects/ERP",
            {
                "reports": [
                    {
                        "name": "Продажи",
                        "aliases": [{"alias": "Продажи", "confidence": 1.0}],
                        "variants": [{"key": "Основной", "presentation": "Основной"}],
                    },
                    {
                        "name": "Закупки",
                        "aliases": [{"alias": "Закупки", "confidence": 1.0}],
                    },
                    {
                        "name": "Остатки",
                        "aliases": [{"alias": "Остатки", "confidence": 1.0}],
                    },
                ]
            },
        )
        stale_run = catalog.create_run(
            database="ERP",
            report_name="Продажи",
            variant_key="Основной",
            title="Продажи",
            strategy="raw_skd_runner",
            params={},
        )
        catalog.finish_run(
            "ERP",
            stale_run,
            status="error",
            diagnostics={},
            error='Ошибка компоновки макета: Не установлено значение параметра "Организация"',
        )
        run_id = catalog.create_run(
            database="ERP",
            report_name="Продажи",
            variant_key="Основной",
            title="Продажи",
            strategy="raw_skd_runner",
            params={},
        )
        result_ref = str((tmp_path / "report-results" / "ERP" / "done.json.gz").relative_to(tmp_path / "report-results"))
        done_path = tmp_path / "report-results" / result_ref
        done_path.parent.mkdir(parents=True, exist_ok=True)
        done_path.write_bytes(b"gz-placeholder")
        catalog.finish_run(
            "ERP",
            run_id,
            status="done",
            result={"rows": [{"A": 1}]},
            diagnostics={"attempts": []},
        )
        with catalog._connect() as conn:
            conn.execute("UPDATE report_runs SET result_ref = ? WHERE db_slug = ? AND run_id = ?", (result_ref, "ERP", run_id))
        for report_name, status, error, diagnostics in (
            ("Закупки", "error", 'Ошибка компоновки макета: Не установлено значение параметра "Организация"', {}),
            ("Остатки", "error", '{(14, 2)}: Таблица не найдена "ВТКандидаты"', {}),
        ):
            other_run = catalog.create_run(
                database="ERP",
                report_name=report_name,
                variant_key="",
                title=report_name,
                strategy="raw_skd_runner",
                params={},
            )
            catalog.finish_run(
                "ERP",
                other_run,
                status=status,
                diagnostics=diagnostics,
                error=error,
            )

        summary = _collect_reports_summary(catalog)

        assert len(summary) == 1
        item = summary[0]
        assert item["database"] == "ERP"
        assert item["catalog_ready"] is True
        assert item["reports_count"] == 3
        assert item["variants_count"] == 1
        assert item["runs_count"] == 3
        assert item["history_runs_count"] == 4
        assert item["artifacts_count"] == 1
        assert item["status_counts"] == {"done": 1, "needs_input": 1, "unsupported": 1, "error": 0}
        assert item["summary_mode"] == "latest_report_run"
        assert item["top_issues"][0]["label"] in {'Ошибка компоновки макета: Не установлено значение параметра "Организация"', "dynamic_temporary_table"}


class TestContainerInfo:
    def test_get_container_info_skips_non_project_containers(self):
        from gateway.server import _get_container_info

        ignored = MagicMock()
        ignored.name = "postgres"
        ignored.status = "running"
        ignored.id = "pg1"

        client = MagicMock()
        client.containers.list.return_value = [ignored]

        with patch("gateway.docker_manager._docker", return_value=client):
            info = _get_container_info()

        assert info == []

    def test_get_container_info_includes_memory_and_image_size(self):
        from gateway.server import _get_container_info

        container = MagicMock()
        container.name = "mcp-lsp-ERPPur_Local"
        container.status = "running"
        container.id = "abc123"
        container.image.tags = ["mcp-lsp-bridge-bsl:latest"]
        container.image.attrs = {"Size": 2147483648}
        container.attrs = {"Config": {"Image": "mcp-lsp-bridge-bsl:latest"}}

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [container]
        mock_client.api.stats.return_value = {
            "memory_stats": {"usage": 2684354560, "limit": 4294967296}
        }

        with patch("gateway.docker_manager._docker", return_value=mock_client):
            info = _get_container_info()

        assert len(info) == 1
        assert info[0]["name"] == "mcp-lsp-ERPPur_Local"
        assert info[0]["memory_usage_bytes"] == 2684354560
        assert info[0]["memory_limit_bytes"] == 4294967296
        assert info[0]["image_size_bytes"] == 2147483648
        assert info[0]["memory_usage_human"] == "2.50 GB"
        assert info[0]["image_size_human"] == "2.00 GB"

    def test_get_container_info_can_skip_expensive_stats(self):
        from gateway.server import _get_container_info

        container = MagicMock()
        container.name = "onec-mcp-gw"
        container.status = "running"
        container.id = "gw123"
        container.image.tags = ["onec-mcp-universal-gateway:latest"]
        container.image.attrs = {"Size": 2147483648}
        container.attrs = {"Config": {"Image": "onec-mcp-universal-gateway:latest"}}

        mock_client = MagicMock()
        mock_client.containers.list.return_value = [container]

        with patch("gateway.docker_manager._docker", return_value=mock_client):
            info = _get_container_info(include_runtime_stats=False, include_image_size=False)

        assert len(info) == 1
        assert info[0]["memory_usage_bytes"] is None
        assert info[0]["image_size_bytes"] is None
        mock_client.api.stats.assert_not_called()

    def test_get_container_info_skips_non_project_containers(self):
        from gateway.server import _get_container_info

        ignored = SimpleNamespace(name="postgres", status="running", id="pg1", image=None, attrs={})
        client = MagicMock()
        client.containers.list.return_value = [ignored]

        with patch("gateway.docker_manager._docker", return_value=client):
            info = _get_container_info()

        assert info == []

    def test_get_container_info_handles_image_size_read_error(self):
        from gateway.server import _get_container_info

        class ImageWithBrokenAttrs:
            tags = ["onec-mcp-universal-gateway:latest"]

            @property
            def attrs(self):
                raise RuntimeError("attrs failed")

        container = SimpleNamespace(
            name="onec-mcp-gw",
            status="running",
            id="gw123",
            image=ImageWithBrokenAttrs(),
            attrs={"Config": {"Image": "onec-mcp-universal-gateway:latest"}},
        )

        client = MagicMock()
        client.containers.list.return_value = [container]
        client.api.stats.return_value = {"memory_stats": {"usage": 1, "limit": 2}}

        with patch("gateway.docker_manager._docker", return_value=client):
            info = _get_container_info()

        assert info[0]["image_size_bytes"] is None

    def test_get_container_info_handles_missing_image_object(self):
        from gateway.server import _get_container_info

        container = SimpleNamespace(
            name="onec-mcp-gw",
            status="running",
            id="gw123",
            image=None,
            attrs={"Config": {"Image": "dangling:image"}},
        )
        client = MagicMock()
        client.containers.list.return_value = [container]
        client.api.stats.return_value = {"memory_stats": {"usage": 1, "limit": 2}}

        with patch("gateway.docker_manager._docker", return_value=client):
            info = _get_container_info()

        assert info[0]["image"] == ""
        assert info[0]["image_size_bytes"] is None


# ---------------------------------------------------------------------------
# Optional services summary
# ---------------------------------------------------------------------------


class TestOptionalServicesStatus:
    def test_lsp_disabled_in_enabled_backends(self, monkeypatch):
        from gateway.server import _get_optional_services_status, settings

        monkeypatch.setattr(settings, "enabled_backends", "onec-toolkit,platform-context")
        monkeypatch.setattr(settings, "export_host_url", "")
        monkeypatch.setattr(settings, "bsl_graph_url", "http://localhost:8888")
        monkeypatch.setattr(settings, "test_runner_url", "http://localhost:8000/sse")

        with patch("gateway.server._http_service_reachable", return_value=False):
            summary = _get_optional_services_status({}, [], "en")

        lsp = next(s for s in summary if s["name"] == "bsl-lsp-bridge")
        assert lsp["state"] == "warn"
        assert "disabled" in lsp["details"]

    def test_lsp_enabled_but_image_missing(self, monkeypatch):
        from gateway.server import _get_optional_services_status, settings

        monkeypatch.setattr(settings, "enabled_backends", "onec-toolkit,platform-context,bsl-lsp-bridge")
        monkeypatch.setattr(settings, "export_host_url", "")
        monkeypatch.setattr(settings, "bsl_graph_url", "http://localhost:8888")
        monkeypatch.setattr(settings, "test_runner_url", "http://localhost:8000/sse")

        with patch("gateway.server._http_service_reachable", return_value=False), patch(
            "gateway.docker_manager._docker", side_effect=RuntimeError("docker unavailable")
        ):
            summary = _get_optional_services_status({}, [], "en")

        lsp = next(s for s in summary if s["name"] == "bsl-lsp-bridge")
        assert lsp["state"] == "err"
        assert "not found locally" in lsp["details"]

    def test_lsp_image_probe_failure_falls_back_to_not_found_state(self, monkeypatch):
        from gateway.server import _get_optional_services_status, settings

        monkeypatch.setattr(settings, "enabled_backends", "bsl-lsp-bridge")
        monkeypatch.setattr(settings, "export_host_url", "")
        monkeypatch.setattr(settings, "bsl_graph_url", "")
        monkeypatch.setattr(settings, "test_runner_url", "")

        with patch("gateway.server._http_service_reachable", return_value=False), \
             patch("gateway.server._docker_manager.lsp_image_present", side_effect=RuntimeError("boom")):
            summary = _get_optional_services_status({}, [], "en")

        lsp = next(s for s in summary if s["name"] == "bsl-lsp-bridge")
        assert lsp["state"] == "err"
        assert "not found locally" in lsp["details"]

    def test_lsp_running_shows_container_count_and_memory(self, monkeypatch):
        from gateway.server import _get_optional_services_status, settings

        monkeypatch.setattr(settings, "enabled_backends", "onec-toolkit,platform-context,bsl-lsp-bridge")
        monkeypatch.setattr(settings, "export_host_url", "")
        monkeypatch.setattr(settings, "bsl_graph_url", "http://localhost:8888")
        monkeypatch.setattr(settings, "test_runner_url", "http://localhost:8000/sse")

        summary = _get_optional_services_status(
            {"ERPPur_Local/lsp": {"ok": True, "tools": 14}},
            [
                {
                    "name": "mcp-lsp-ERPPur_Local",
                    "running": True,
                    "memory_usage_bytes": 2684354560,
                }
            ],
            "en",
        )

        lsp = next(s for s in summary if s["name"] == "bsl-lsp-bridge")
        assert lsp["state"] == "ok"
        assert "1 container" in lsp["details"]
        assert "2.50 GB" in lsp["details"]

    def test_optional_services_russian_localization(self, monkeypatch):
        from gateway.server import _get_optional_services_status, settings

        monkeypatch.setattr(settings, "enabled_backends", "onec-toolkit,platform-context,bsl-lsp-bridge")
        monkeypatch.setattr(settings, "export_host_url", "")
        monkeypatch.setattr(settings, "bsl_graph_url", "http://localhost:8888")
        monkeypatch.setattr(settings, "test_runner_url", "http://localhost:8000/sse")

        with patch("gateway.server._http_service_reachable", return_value=False):
            summary = _get_optional_services_status(
                {"ERPPur_Local/lsp": {"ok": True, "tools": 14}},
                [
                    {
                        "name": "mcp-lsp-ERPPur_Local",
                        "running": True,
                        "memory_usage_bytes": 2684354560,
                    }
                ],
                "ru",
            )

        lsp = next(s for s in summary if s["name"] == "bsl-lsp-bridge")
        graph = next(s for s in summary if s["name"] == "bsl-graph")
        export = next(s for s in summary if s["name"] == "export-host-service")
        test_runner = next(s for s in summary if s["name"] == "test-runner")

        assert "LSP активен" in lsp["details"]
        assert "опциональный профиль не запущен" in graph["details"]
        assert "не настроен" in export["details"]
        assert "отключён" in test_runner["details"]


class TestServerHelpers:
    def test_audit_action_truncates_long_values(self):
        from gateway import server

        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.method = "POST"
        request.url.path = "/api/action/save-env"

        with patch("gateway.server.logger") as mock_logger:
            server._audit_action(request, "save-env", True, payload="x" * 300, ok_flag=True)

        details = mock_logger.info.call_args.args[-1]
        assert details["payload"].endswith("...")
        assert len(details["payload"]) == 200
        assert details["ok_flag"] is True

    @pytest.mark.asyncio
    async def test_trigger_graph_rebuild_skips_when_url_not_configured(self, monkeypatch):
        from gateway import server

        monkeypatch.setattr(server.settings, "bsl_graph_url", "")
        await server._trigger_graph_rebuild()

    @pytest.mark.asyncio
    async def test_trigger_graph_rebuild_posts_to_backend(self, monkeypatch):
        from gateway import server

        monkeypatch.setattr(server.settings, "bsl_graph_url", "http://localhost:8888")
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=None)

        with patch("gateway.server.httpx.AsyncClient", return_value=client):
            await server._trigger_graph_rebuild()

        client.post.assert_awaited_once_with("http://localhost:8888/api/graph/rebuild", json={})

    def test_http_service_reachable_handles_success_failure_and_exception(self):
        from gateway.server import _http_service_reachable

        ok = MagicMock(status_code=200)
        fatal = MagicMock(status_code=503)

        with patch("gateway.server.httpx.get", side_effect=[Exception("boom"), fatal, ok]) as mock_get:
            assert _http_service_reachable("http://localhost:8082", paths=("/health", "", "/ready")) is True
        assert mock_get.call_count == 3

    def test_http_service_reachable_returns_false_for_empty_base_url(self):
        from gateway.server import _http_service_reachable

        assert _http_service_reachable("") is False

    def test_format_bytes_handles_none_bytes_and_megabytes(self):
        from gateway.server import _format_bytes

        assert _format_bytes(None) == ""
        assert _format_bytes(10) == "10 B"
        assert _format_bytes(1048576) == "1.00 MB"


# ---------------------------------------------------------------------------
# ASGI routing — _App dispatches /mcp to session_manager
# ---------------------------------------------------------------------------


class TestAppRouting:
    def test_non_mcp_path_hits_starlette(self):
        """Requests to /health go through _starlette."""
        from gateway.server import app
        from starlette.testclient import TestClient

        with patch("gateway.server._manager") as mock_mgr:
            mock_mgr.status.return_value = {}
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
        assert resp.status_code in (200, 500)

    def test_unknown_path_returns_404(self):
        from gateway.server import _starlette
        from starlette.testclient import TestClient

        client = TestClient(_starlette, raise_server_exceptions=False)
        resp = client.get("/nonexistent-path-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _host_path_to_container mapping
# ---------------------------------------------------------------------------


class TestHostPathToContainer:
    def test_home_path_maps_to_hostfs(self):
        from gateway.server import _host_path_to_container
        assert _host_path_to_container("/home/user/projects") == "/hostfs-home/user/projects"

    def test_home_path_trailing_slash(self):
        from gateway.server import _host_path_to_container
        assert _host_path_to_container("/home/user/projects/") == "/hostfs-home/user/projects"

    def test_non_home_path_maps_to_workspace(self):
        from gateway.server import _host_path_to_container
        assert _host_path_to_container("/var/data/bsl") == "/workspace"

    def test_windows_path_maps_to_workspace(self):
        from gateway.server import _host_path_to_container
        assert _host_path_to_container("C:\\Users\\user\\bsl") == "/workspace"

    def test_root_path_maps_to_workspace(self):
        from gateway.server import _host_path_to_container
        assert _host_path_to_container("/") == "/workspace"


class TestNormalizeRuntimeProjectPath:
    def test_empty_path_uses_current_workspace_root_plus_slug(self):
        from gateway.server import _normalize_runtime_project_path

        with patch("gateway.server._read_env_value", return_value="/home/as/Z"):
            assert _normalize_runtime_project_path("", "ERP") == "/hostfs-home/as/Z/ERP"

    def test_empty_workspace_root_falls_back_to_workspace(self):
        from gateway.server import _normalize_runtime_project_path

        with patch("gateway.server._managed_workspace_root_container", return_value=""):
            assert _normalize_runtime_project_path("", "ERP") == "/workspace/ERP"

    def test_stale_home_root_falls_back_to_current_workspace_root_plus_slug(self):
        from gateway.server import _normalize_runtime_project_path

        with patch("gateway.server._read_env_value", return_value="/home/as/Z"):
            assert _normalize_runtime_project_path("/home/as", "ERP") == "/hostfs-home/as/Z/ERP"

    def test_keeps_existing_path_inside_current_workspace(self):
        from gateway.server import _normalize_runtime_project_path

        with patch("gateway.server._read_env_value", return_value="/home/as/Z"):
            assert _normalize_runtime_project_path("/hostfs-home/as/Z/ERP", "ERP") == "/hostfs-home/as/Z/ERP"

    def test_managed_root_aliases_expand_to_desired_path(self):
        from gateway.server import _normalize_runtime_project_path

        with patch("gateway.server._read_env_value", return_value="/home/as/Z"):
            assert _normalize_runtime_project_path("/projects", "ERP") == "/hostfs-home/as/Z/ERP"


# ---------------------------------------------------------------------------
# /api/export-bsl workspace check
# ---------------------------------------------------------------------------


class TestExportBslWorkspaceCheck:
    def test_export_rejects_empty_workspace(self, test_client):
        """Export should return 400 when BSL workspace is not configured."""
        with patch("gateway.server._read_env_value", return_value=""), patch("gateway.server.settings") as mock_settings:
            mock_settings.bsl_host_workspace = ""
            mock_settings.port = 8080
            mock_settings.gateway_api_token = ""
            resp = test_client.post(
                "/api/export-bsl",
                json={"connection": "Srvr=srv;Ref=base;", "output_dir": "/workspace/test"},
            )
        assert resp.status_code == 400
        data = resp.json()
        assert "Папка выгрузки BSL не настроена" in data.get("error", "")


# ---------------------------------------------------------------------------
# Slugify and disconnect with Cyrillic names
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_slugify_latin(self):
        from gateway.mcp_server import _slugify
        assert _slugify("ERP_Test") == "ERP_Test"

    def test_slugify_cyrillic(self):
        from gateway.mcp_server import _slugify
        slug = _slugify("Бухгалтерия")
        assert slug.isascii()
        assert len(slug) > 0
        assert "_" not in slug or slug.replace("_", "").isalnum()

    def test_slugify_max_length(self):
        from gateway.mcp_server import _slugify
        long_name = "А" * 100
        slug = _slugify(long_name)
        assert len(slug) <= 63


# ---------------------------------------------------------------------------
# Path traversal protection in browse_api
# ---------------------------------------------------------------------------


class TestBrowseApiSecurity:
    def test_path_traversal_blocked(self, test_client):
        """Path traversal via ../ should be rejected."""
        resp = test_client.get("/api/browse?path=/../../../etc/passwd")
        assert resp.status_code == 400 or "error" in resp.json()

    def test_path_traversal_deep(self, test_client):
        """Deep traversal should also be blocked."""
        resp = test_client.get("/api/browse?path=/home/user/../../../../etc")
        assert resp.status_code == 400 or "error" in resp.json()

    def test_normal_path_accepted(self, test_client):
        """Normal paths should work (may fail filesystem access but not security check)."""
        resp = test_client.get("/api/browse?path=/home")
        # May return 200 with dirs or 500 if /hostfs not mounted — both OK
        assert resp.status_code in (200, 500)


class TestBrowseApiHostRootPrefix:
    """Windows folder browser relies on HOST_ROOT_PREFIX to translate host-side
    paths like C:/Users/Alex/projects into container paths relative to /hostfs
    (which is bind-mounted to the user profile)."""

    def test_prefix_stripped_before_mount_join(self, tmp_path, monkeypatch):
        from starlette.testclient import TestClient

        from gateway import server

        sub = tmp_path / "projects" / "sample"
        sub.mkdir(parents=True)
        (sub / "nested").mkdir()

        monkeypatch.setattr(server, "_HOSTFS", str(tmp_path))
        monkeypatch.setattr(server, "_HOST_ROOT_PREFIX", "C:/Users/Alex")

        client = TestClient(server.app)
        resp = client.get("/api/browse?path=C:/Users/Alex/projects/sample")
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "C:/Users/Alex/projects/sample"
        assert data["parent"] == "C:/Users/Alex/projects"
        assert "nested" in data["dirs"]

    def test_prefix_root_lists_mount(self, tmp_path, monkeypatch):
        from starlette.testclient import TestClient

        from gateway import server

        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()

        monkeypatch.setattr(server, "_HOSTFS", str(tmp_path))
        monkeypatch.setattr(server, "_HOST_ROOT_PREFIX", "C:/Users/Alex")

        client = TestClient(server.app)
        resp = client.get("/api/browse?path=C:/Users/Alex")
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "C:/Users/Alex"
        assert set(data["dirs"]) >= {"a", "b"}

    def test_permission_error_is_returned_as_json(self, tmp_path, monkeypatch):
        from starlette.testclient import TestClient
        from gateway import server

        monkeypatch.setattr(server, "_HOSTFS", str(tmp_path))
        monkeypatch.setattr(server, "_HOST_ROOT_PREFIX", "")

        with patch("gateway.server._browse_via_host_service", new=AsyncMock(return_value=None)), patch(
            "os.path.isdir", return_value=True
        ), patch("os.listdir", side_effect=PermissionError()):
            client = TestClient(server.app)
            resp = client.get("/api/browse?path=/home/as")

        assert resp.status_code == 200
        assert resp.json()["error"] == "Permission denied"


# ---------------------------------------------------------------------------
# MCP tool result helpers
# ---------------------------------------------------------------------------


class TestMcpToolResultHelpers:
    def test_ok_result(self):
        from gateway.mcp_server import _ok
        result = _ok("success message")
        assert result.content[0].text == "success message"
        assert result.isError is not True

    def test_err_result(self):
        from gateway.mcp_server import _err
        result = _err("something failed")
        assert result.content[0].text == "something failed"
        assert result.isError is True

    def test_result_error_prefix(self):
        from gateway.mcp_server import _result
        result = _result("ERROR: bad thing")
        assert result.isError is True

    def test_result_ok_prefix(self):
        from gateway.mcp_server import _result
        result = _result("Export completed successfully")
        assert result.isError is not True


# ---------------------------------------------------------------------------
# Session/container cleanup helpers
# ---------------------------------------------------------------------------


class TestCleanupHelpers:
    def test_cleanup_terminated_mcp_sessions(self, monkeypatch):
        from gateway import server

        term = MagicMock()
        term._terminated = True
        alive = MagicMock()
        alive._terminated = False

        fake_sm = MagicMock()
        fake_sm._server_instances = {"sid-dead": term, "sid-alive": alive}
        monkeypatch.setattr(server, "session_manager", fake_sm)

        fake_mgr = MagicMock()
        fake_mgr.forget_sessions.return_value = 1
        monkeypatch.setattr(server, "_manager", fake_mgr)

        removed_mcp, removed_db = server._cleanup_terminated_mcp_sessions()

        assert removed_mcp == 1
        assert removed_db == 1
        assert "sid-dead" not in fake_sm._server_instances
        assert "sid-alive" in fake_sm._server_instances
        fake_mgr.forget_sessions.assert_called_once_with(["sid-dead"])

    def test_cleanup_terminated_mcp_sessions_no_instances(self, monkeypatch):
        from gateway import server

        fake_sm = MagicMock()
        fake_sm._server_instances = None
        monkeypatch.setattr(server, "session_manager", fake_sm)

        removed_mcp, removed_db = server._cleanup_terminated_mcp_sessions()
        assert (removed_mcp, removed_db) == (0, 0)

    def test_cleanup_orphan_db_containers_uses_saved_slugs(self):
        from gateway import server

        with patch("gateway.server._registry") as mock_registry, \
             patch("gateway.docker_manager.cleanup_orphan_db_containers") as mock_cleanup:
            mock_registry.load_saved_state.return_value = [
                {"name": "ERP", "slug": "erp"},
                {"name": "ZUP"},  # fallback to name
            ]
            mock_cleanup.return_value = 2

            removed = server._cleanup_orphan_db_containers()

        assert removed == 2
        mock_cleanup.assert_called_once()
        keep_slugs = mock_cleanup.call_args.args[0]
        assert keep_slugs == {"erp", "ZUP"}

    def test_purge_db_runtime_state_ignores_missing_connection(self):
        from gateway import server

        db = SimpleNamespace(connection="", project_path="/projects/db1", lsp_container="")
        with patch("gateway.server._export_tasks", {}), \
             patch("gateway.server._export_jobs", {}), \
             patch("gateway.bsl_search.bsl_search.invalidate_paths") as invalidate_paths:
            server._purge_db_runtime_state(db)

        invalidate_paths.assert_called_once()

    def test_purge_db_runtime_state_ignores_none_db(self):
        from gateway import server

        server._purge_db_runtime_state(None)

    def test_purge_db_runtime_state_cancels_jobs_and_invalidates_paths(self):
        from gateway import server
        from gateway import mcp_server

        task = MagicMock()
        task.done.return_value = False
        db = SimpleNamespace(connection="conn", project_path="/projects/db1", lsp_container="mcp-lsp-db1")
        original_export_tasks = dict(server._export_tasks)
        original_export_jobs = dict(server._export_jobs)
        original_mcp_tasks = dict(mcp_server._export_tasks)
        original_mcp_jobs = dict(mcp_server._export_jobs)
        original_mcp_index = dict(mcp_server._index_jobs)
        try:
            server._export_tasks["conn"] = task
            server._export_jobs["conn"] = {"status": "running", "result": ""}
            mcp_server._export_tasks["conn"] = task
            mcp_server._export_jobs["conn"] = {"status": "running", "result": ""}
            mcp_server._index_jobs["conn"] = {"status": "running", "result": ""}
            with patch("gateway.bsl_search.bsl_search.invalidate_paths") as invalidate_paths:
                server._purge_db_runtime_state(db)
            task.cancel.assert_called()
            invalidate_paths.assert_called_once_with("/projects/db1", "mcp-lsp-db1:/projects")
        finally:
            server._export_tasks.clear()
            server._export_tasks.update(original_export_tasks)
            server._export_jobs.clear()
            server._export_jobs.update(original_export_jobs)
            mcp_server._export_tasks.clear()
            mcp_server._export_tasks.update(original_mcp_tasks)
            mcp_server._export_jobs.clear()
            mcp_server._export_jobs.update(original_mcp_jobs)
            mcp_server._index_jobs.clear()
            mcp_server._index_jobs.update(original_mcp_index)


# ---------------------------------------------------------------------------
# Export status/cancel and env helpers
# ---------------------------------------------------------------------------


class TestExportStatusAndCancelApi:
    def test_export_status_get_all_jobs(self, test_client):
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        try:
            gateway_server._export_jobs["conn"] = {"status": "done", "result": "ok"}
            resp = test_client.get("/api/export-status")
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)

        assert resp.status_code == 200
        assert resp.json()["jobs"]["conn"]["status"] == "done"

    def test_export_status_post_merges_index_status(self, test_client):
        from gateway import server as gateway_server
        from gateway import mcp_server

        original_jobs = dict(gateway_server._export_jobs)
        original_index = dict(mcp_server._index_jobs)
        try:
            gateway_server._export_jobs["conn"] = {"status": "done", "result": "ok"}
            mcp_server._index_jobs["conn"] = {"status": "done", "result": "Indexed"}
            resp = test_client.post("/api/export-status", json={"connection": "conn"})
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)
            mcp_server._index_jobs.clear()
            mcp_server._index_jobs.update(original_index)

        assert resp.status_code == 200
        data = resp.json()
        assert data["index_result"] == "Indexed"

    def test_export_status_post_invalid_json_falls_back_to_all_jobs(self, test_client):
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        try:
            gateway_server._export_jobs["conn"] = {"status": "done", "result": "ok"}
            resp = test_client.post(
                "/api/export-status",
                content=b"bad",
                headers={"content-type": "application/json"},
            )
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)

        assert resp.status_code == 200
        assert resp.json()["jobs"]["conn"]["status"] == "done"

    def test_export_status_post_unknown_connection_returns_idle(self, test_client):
        resp = test_client.post("/api/export-status", json={"connection": "missing"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    def test_export_cancel_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/export-cancel",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_export_cancel_requires_connection(self, test_client):
        resp = test_client.post("/api/export-cancel", json={})
        assert resp.status_code == 400

    def test_export_cancel_returns_404_when_job_not_running(self, test_client):
        resp = test_client.post("/api/export-cancel", json={"connection": "conn"})
        assert resp.status_code == 404

    def test_export_cancel_cancels_task_and_notifies_host(self, test_client):
        from gateway import server as gateway_server

        task = MagicMock()
        original_jobs = dict(gateway_server._export_jobs)
        original_tasks = dict(gateway_server._export_tasks)
        try:
            gateway_server._export_jobs["conn"] = {"status": "running", "result": ""}
            gateway_server._export_tasks["conn"] = task
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post = AsyncMock()
            with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
                 patch("gateway.server.httpx.AsyncClient", return_value=client):
                resp = test_client.post("/api/export-cancel", json={"connection": "conn"})
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)
            gateway_server._export_tasks.clear()
            gateway_server._export_tasks.update(original_tasks)

        assert resp.status_code == 200
        task.cancel.assert_called_once()
        client.post.assert_awaited_once_with("http://localhost:8082/cancel", json={"connection": "conn"})

    def test_export_cancel_without_task_or_host_url_still_returns_ok(self, test_client):
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        original_tasks = dict(gateway_server._export_tasks)
        try:
            gateway_server._export_jobs["conn"] = {"status": "running", "result": ""}
            resp = test_client.post("/api/export-cancel", json={"connection": "conn"})
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)
            gateway_server._export_tasks.clear()
            gateway_server._export_tasks.update(original_tasks)

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_export_cancel_logs_host_notify_failure(self, test_client):
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        try:
            gateway_server._export_jobs["conn"] = {"status": "running", "result": ""}
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post = AsyncMock(side_effect=RuntimeError("boom"))
            with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
                 patch("gateway.server.httpx.AsyncClient", return_value=client):
                resp = test_client.post("/api/export-cancel", json={"connection": "conn"})
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)

        assert resp.status_code == 200

    def test_export_cancel_marks_cancelled_job_via_background_task(self, test_client):
        from gateway import server as gateway_server

        original_jobs = dict(gateway_server._export_jobs)
        original_tasks = dict(gateway_server._export_tasks)
        final_status = None
        try:
            with patch("gateway.server.settings") as settings, patch(
                "gateway.server._read_env_value", side_effect=lambda key: "/home/as/Z" if key in ("BSL_HOST_WORKSPACE", "BSL_WORKSPACE") else ""
            ), patch(
                "gateway.server._registry"
            ) as registry, patch(
                "gateway.mcp_server._run_export_bsl", new=AsyncMock(side_effect=asyncio.CancelledError())
            ):
                settings.gateway_api_token = ""
                settings.bsl_host_workspace = "/home/as/Z"
                settings.bsl_workspace = "/workspace"
                settings.port = 8080
                registry.get.return_value = None

                resp = test_client.post("/api/export-bsl", json={"connection": "conn"})

                for _ in range(50):
                    job = gateway_server._export_jobs.get("conn")
                    if job and job["status"] == "cancelled":
                        final_status = job["status"]
                        break
                    time.sleep(0.01)
        finally:
            gateway_server._export_jobs.clear()
            gateway_server._export_jobs.update(original_jobs)
            gateway_server._export_tasks.clear()
            gateway_server._export_tasks.update(original_tasks)

        assert resp.status_code == 200
        assert final_status == "cancelled"


class TestEnvHelpers:
    def test_read_env_file_uses_fallback_path(self, tmp_path, monkeypatch):
        from gateway import server

        env_file = tmp_path / ".env"
        env_file.write_text("PORT=8080\n", encoding="utf-8")
        monkeypatch.setenv("ENV_FILE_PATH", str(env_file))

        real_open = open

        def fake_open(path, mode="r", encoding=None):
            if path in ("/data/.env", ".env", "/app/.env"):
                raise FileNotFoundError
            return real_open(path, mode, encoding=encoding)

        with patch("builtins.open", side_effect=fake_open):
            assert server._read_env_file() == "PORT=8080\n"

    def test_write_env_file_writes_first_available_path(self, monkeypatch, tmp_path):
        from gateway import server

        target = tmp_path / ".env"

        real_open = open

        def fake_open(path, mode="r", encoding=None):
            if path in ("/data/.env", ".env", "/app/.env"):
                return real_open(target, mode, encoding=encoding)
            return real_open(path, mode, encoding=encoding)

        with patch("builtins.open", side_effect=fake_open):
            result = server._write_env_file("PORT=8081\n")

        assert result["ok"] is True
        assert target.read_text(encoding="utf-8") == "PORT=8081\n"

    def test_write_env_file_returns_error_when_all_paths_fail(self):
        from gateway import server

        with patch("builtins.open", side_effect=PermissionError):
            result = server._write_env_file("PORT=8081\n")

        assert result["ok"] is False

    def test_write_env_file_uses_docker_control_when_data_env_exists_but_is_read_only(self, tmp_path):
        from gateway import server

        local_env = tmp_path / ".env"
        local_env.write_text("OLD=1\n", encoding="utf-8")
        real_open = open

        def fake_exists(path):
            return path == "/data/.env"

        def fake_open(path, mode="r", encoding=None):
            if path == "/data/.env":
                raise PermissionError("read only")
            if path in (".env", "/app/.env"):
                return real_open(local_env, mode, encoding=encoding)
            return real_open(path, mode, encoding=encoding)

        with patch("gateway.server.os.path.exists", side_effect=fake_exists), \
             patch("builtins.open", side_effect=fake_open), \
             patch("gateway.server._docker_manager.write_env_file", return_value={"ok": True, "message": "saved via docker-control"}) as write_env:
            result = server._write_env_file("PORT=8081\n")

        assert result["ok"] is True
        assert result["message"] == "saved via docker-control"
        assert local_env.read_text(encoding="utf-8") == "OLD=1\n"
        write_env.assert_called_once_with("PORT=8081\n")

    def test_write_env_file_uses_docker_control_when_data_env_missing(self):
        from gateway import server

        def fake_exists(path):
            return path == "/data/.env"

        def fake_open(path, mode="r", encoding=None):
            if path == "/data/.env":
                raise FileNotFoundError(path)
            raise AssertionError(f"unexpected open: {path}")

        with patch("gateway.server.os.path.exists", side_effect=fake_exists), \
             patch("builtins.open", side_effect=fake_open), \
             patch("gateway.server._docker_manager.write_env_file", return_value={"ok": True, "message": "saved via docker-control"}) as write_env:
            result = server._write_env_file("PORT=8081\n")

        assert result["ok"] is True
        write_env.assert_called_once_with("PORT=8081\n")

    def test_read_env_value_strips_quotes(self):
        from gateway import server

        with patch("gateway.server._read_env_file", return_value="A='1'\nB=\"2\"\nC=3\n"):
            assert server._read_env_value("A") == "1"
            assert server._read_env_value("B") == "2"
            assert server._read_env_value("C") == "3"
            assert server._read_env_value("MISSING") == ""

    def test_read_env_value_skips_comments_and_lines_without_equals(self):
        from gateway import server

        with patch("gateway.server._read_env_file", return_value="# comment\nNOEQUALS\nA=1\n"):
            assert server._read_env_value("A") == "1"

    def test_mask_env_for_ui_hides_docker_control_token(self):
        from gateway import server

        text = server._mask_env_for_ui(
            "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=secret-salt\n"
        )

        assert "PORT=8080" in text
        assert "DOCKER_CONTROL_TOKEN=***hidden***" in text
        assert "ANONYMIZER_SALT=***hidden***" in text

    def test_mask_env_for_ui_preserves_comments_and_invalid_lines(self):
        from gateway import server

        text = server._mask_env_for_ui("# comment\nNOEQUALS\nDOCKER_CONTROL_TOKEN=\nANONYMIZER_SALT=\n")

        assert text == "# comment\nNOEQUALS\nDOCKER_CONTROL_TOKEN=\nANONYMIZER_SALT=\n"

    def test_restore_masked_env_secrets_preserves_existing_token(self):
        from gateway import server

        with patch(
            "gateway.server._read_env_value",
            side_effect=lambda key: {
                "DOCKER_CONTROL_TOKEN": "secret-token",
                "ANONYMIZER_SALT": "secret-salt",
            }.get(key, ""),
        ):
            text = server._restore_masked_env_secrets(
                "PORT=8080\nDOCKER_CONTROL_TOKEN=***hidden***\nANONYMIZER_SALT=***hidden***\n"
            )

        assert text == "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=secret-salt\n"

    def test_restore_masked_env_secrets_appends_existing_token_when_missing(self):
        from gateway import server

        with patch(
            "gateway.server._read_env_value",
            side_effect=lambda key: {
                "DOCKER_CONTROL_TOKEN": "secret-token",
                "ANONYMIZER_SALT": "secret-salt",
            }.get(key, ""),
        ):
            text = server._restore_masked_env_secrets("PORT=8080\n")

        assert text == "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=secret-salt\n"

    def test_restore_masked_env_secrets_keeps_explicit_secret_value(self):
        from gateway import server

        with patch(
            "gateway.server._read_env_value",
            side_effect=lambda key: {
                "DOCKER_CONTROL_TOKEN": "current-secret",
                "ANONYMIZER_SALT": "current-salt",
            }.get(key, ""),
        ):
            text = server._restore_masked_env_secrets(
                "DOCKER_CONTROL_TOKEN=new-secret\nANONYMIZER_SALT=new-salt\n"
            )

        assert text == "DOCKER_CONTROL_TOKEN=new-secret\nANONYMIZER_SALT=new-salt\n"

    def test_restore_masked_env_secrets_preserves_comments_invalid_lines_and_appends_newline(self):
        from gateway import server

        with patch(
            "gateway.server._read_env_value",
            side_effect=lambda key: {
                "DOCKER_CONTROL_TOKEN": "secret-token",
                "ANONYMIZER_SALT": "secret-salt",
            }.get(key, ""),
        ):
            text = server._restore_masked_env_secrets("# comment\nNOEQUALS")

        assert text == "# comment\nNOEQUALS\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=secret-salt\n"

    def test_update_env_value_updates_and_appends(self):
        from gateway import server

        with patch("gateway.server._read_env_file", return_value="A=1\n# comment\n"), \
             patch("gateway.server._write_env_file", return_value={"ok": True}) as write_env:
            server._update_env_value("A", "2")
            server._update_env_value("B", "3")

        written = [call.args[0] for call in write_env.call_args_list]
        assert "A=2\n# comment\n" in written[0]
        assert "B=3\n" in written[1]

    def test_update_env_value_appends_newline_before_new_key(self):
        from gateway import server

        with patch("gateway.server._read_env_file", return_value="A=1"), \
             patch("gateway.server._write_env_file", return_value={"ok": True}) as write_env:
            server._update_env_value("B", "2")

        assert write_env.call_args.args[0] == "A=1\nB=2\n"

    def test_is_managed_project_path(self):
        from gateway import server

        assert server._is_managed_project_path("") is True
        assert server._is_managed_project_path("/projects") is True
        assert server._is_managed_project_path("/workspace/db") is True
        assert server._is_managed_project_path("/hostfs-home/as/Z") is True
        assert server._is_managed_project_path("/tmp/db") is False

    @pytest.mark.asyncio
    async def test_apply_bsl_workspace_runtime_updates_env_and_running_db(self):
        from gateway import server

        db_info = SimpleNamespace(slug="ERP", project_path="/workspace/ERP")
        mock_registry = MagicMock()
        mock_registry.list.return_value = [{"name": "ERP"}]
        mock_registry.get.return_value = db_info
        mock_manager = MagicMock()
        mock_manager.has_db.return_value = True

        with patch("gateway.server._registry", mock_registry), \
             patch("gateway.server._manager", mock_manager), \
             patch("gateway.server._host_path_to_container", side_effect=lambda p: "/hostfs-home/" + p[len('/home/'):] if p.startswith("/home/") else "/workspace"), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.docker_manager.start_lsp", return_value="mcp-lsp-ERP"):
            result = await server._apply_bsl_workspace_runtime("/home/as/Z", "http://localhost:8082")

        assert result["db_reconfigured"] == 1
        mock_registry.update.assert_any_call("ERP", project_path="/hostfs-home/as/Z/ERP")
        mock_registry.update_runtime.assert_called_once_with("ERP", lsp_container="mcp-lsp-ERP" or "")

    @pytest.mark.asyncio
    async def test_apply_bsl_workspace_runtime_collects_errors(self):
        from gateway import server

        db_info = SimpleNamespace(slug="ERP", project_path="/workspace/ERP")
        mock_registry = MagicMock()
        mock_registry.list.return_value = [{"name": "ERP"}]
        mock_registry.get.return_value = db_info
        mock_manager = MagicMock()
        mock_manager.has_db.return_value = True

        with patch("gateway.server._registry", mock_registry), \
             patch("gateway.server._manager", mock_manager), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.docker_manager.start_lsp", side_effect=RuntimeError("boom")):
            result = await server._apply_bsl_workspace_runtime("/tmp/Z", "http://localhost:8082")

        assert result["db_errors"] == 1
        assert "ERP: boom" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_apply_bsl_workspace_runtime_skips_empty_name_missing_db_and_disconnected_db(self):
        from gateway import server

        registry = MagicMock()
        registry.list.return_value = [{"name": ""}, {"name": "MISSING"}, {"name": "IDLE"}]
        idle = SimpleNamespace(slug="IDLE", project_path="/workspace/IDLE")
        registry.get.side_effect = lambda name: None if name == "MISSING" else idle
        manager = MagicMock()
        manager.has_db.return_value = False

        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager):
            result = await server._apply_bsl_workspace_runtime("/tmp/Z", "http://localhost:8082")

        assert result["db_reconfigured"] == 0
        assert result["db_errors"] == 0

    def test_restart_gateway_handles_restart_failure(self):
        from gateway import server

        container = MagicMock()
        container.restart.side_effect = RuntimeError("boom")
        thread_started = []

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                self._target = target

            def start(self):
                thread_started.append(True)
                self._target()

        with patch("threading.Thread", ImmediateThread), \
             patch("time.sleep"), \
             patch("gateway.docker_manager._docker") as docker_client:
            docker_client.return_value.containers.get.return_value = container
            server._restart_gateway()

        assert thread_started == [True]

    def test_get_docker_system_info_handles_df_failure(self):
        from gateway import server

        client = MagicMock()
        client.info.return_value = {
            "ServerVersion": "24.0",
            "OperatingSystem": "Linux",
            "Architecture": "x86_64",
            "NCPU": 8,
            "MemTotal": 8 * 1073741824,
            "ContainersRunning": 2,
            "Containers": 4,
            "Images": 6,
        }
        client.df.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._docker", return_value=client):
            info = server._get_docker_system_info()

        assert info["version"] == "24.0"
        assert info["images_size_gb"] == 0.0

    def test_get_docker_system_info_handles_empty_size_entries(self):
        from gateway import server

        client = MagicMock()
        client.info.return_value = {
            "ServerVersion": "24.0",
            "OperatingSystem": "Linux",
            "Architecture": "x86_64",
            "NCPU": 8,
            "MemTotal": 8 * 1073741824,
            "ContainersRunning": 2,
            "Containers": 4,
            "Images": 6,
        }
        client.df.return_value = {"Images": [{"Size": None}], "Volumes": [{"UsageData": None}]}

        with patch("gateway.docker_manager._docker", return_value=client):
            info = server._get_docker_system_info()

        assert info["images_size_gb"] == 0.0
        assert info["volumes_size_gb"] == 0.0

    def test_get_docker_system_info_returns_error_on_client_failure(self):
        from gateway import server

        with patch("gateway.docker_manager._docker", side_effect=RuntimeError("boom")):
            info = server._get_docker_system_info()

        assert "boom" in info["error"]
        assert "direct fallback failed" in info["error"]

    def test_get_container_info_returns_empty_on_docker_failure(self):
        from gateway import server

        with patch("gateway.docker_manager._docker", side_effect=RuntimeError("boom")):
            assert server._get_container_info() == []

    def test_get_container_info_handles_missing_image_and_stats_errors(self):
        from gateway import server

        class BrokenContainer:
            name = "onec-mcp-gw"
            status = "running"
            id = "cid"
            attrs = {"Config": {"Image": "dangling:image"}}

            @property
            def image(self):
                raise RuntimeError("missing image")

        client = MagicMock()
        client.containers.list.return_value = [BrokenContainer()]
        client.api.stats.side_effect = RuntimeError("stats failed")

        with patch("gateway.docker_manager._docker", return_value=client):
            info = server._get_container_info()

        assert info[0]["image"] == "dangling:image"
        assert info[0]["memory_usage_bytes"] is None

    def test_optional_services_status_covers_ok_and_err_branches(self, monkeypatch):
        from gateway import server

        container_info = [{"name": "onec-bsl-graph", "running": True}]
        backends_status = {
            "db1/lsp": {"ok": True},
            "test-runner": {"ok": True},
        }
        monkeypatch.setattr(server.settings, "enabled_backends", "bsl-lsp-bridge,test-runner")
        monkeypatch.setattr(server.settings, "bsl_graph_url", "http://localhost:8888")
        monkeypatch.setattr(server.settings, "export_host_url", "http://localhost:8082")
        monkeypatch.setattr(server.settings, "test_runner_url", "http://localhost:6789/mcp")

        with patch("gateway.server._http_service_reachable", side_effect=lambda base, paths=("",), timeout=1.5: base != "http://localhost:8082"), \
             patch("gateway.docker_manager._docker") as docker_client:
            docker_client.return_value.images.get.return_value = object()
            summary = server._get_optional_services_status(backends_status, container_info, "en")

        by_name = {item["name"]: item for item in summary}
        assert by_name["bsl-lsp-bridge"]["state"] == "ok"
        assert by_name["bsl-graph"]["state"] == "ok"
        assert by_name["export-host-service"]["state"] == "err"
        assert by_name["test-runner"]["state"] == "ok"

    def test_optional_services_status_test_runner_enabled_but_down(self, monkeypatch):
        from gateway import server

        monkeypatch.setattr(server.settings, "enabled_backends", "test-runner")
        monkeypatch.setattr(server.settings, "export_host_url", "")
        monkeypatch.setattr(server.settings, "test_runner_url", "http://localhost:6789/mcp")

        summary = server._get_optional_services_status({}, [], "ru")
        by_name = {item["name"]: item for item in summary}
        assert by_name["test-runner"]["state"] == "err"
        assert "включён" in by_name["test-runner"]["details"]

    def test_browse_api_permission_denied(self, test_client):
        with patch("gateway.server.settings.export_host_url", ""), \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.server.os.listdir", side_effect=PermissionError):
            resp = test_client.get("/api/browse?path=/home/as")

        assert resp.status_code == 200
        assert resp.json()["error"] == "Permission denied"

    def test_browse_api_prefers_export_host_service_when_configured(self, test_client):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "path": "/home/as/Документы/AI_PROJECTS/onec-mcp-universal/bsl-projects",
            "parent": "/home/as/Документы/AI_PROJECTS/onec-mcp-universal",
            "dirs": ["ERP"],
        }
        client.get = AsyncMock(return_value=response)

        with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client):
            resp = test_client.get("/api/browse?path=/home/as/Документы/AI_PROJECTS/onec-mcp-universal/bsl-projects")

        assert resp.status_code == 200
        assert resp.json()["dirs"] == ["ERP"]
        client.get.assert_awaited_once_with(
            "http://localhost:8082/browse",
            params={"path": "/home/as/Документы/AI_PROJECTS/onec-mcp-universal/bsl-projects"},
        )

    def test_browse_api_falls_back_to_local_fs_when_host_service_unreachable(self, test_client):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.get = AsyncMock(side_effect=RuntimeError("boom"))

        with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client), \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.server.os.listdir", return_value=["ERP"]):
            resp = test_client.get("/api/browse?path=/home/as/Z")

        assert resp.status_code == 200
        assert resp.json()["path"] == "/home/as/Z"
        assert resp.json()["dirs"] == ["ERP"]

    def test_select_directory_api_proxies_to_host_service(self, test_client):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True, "cancelled": False, "path": "/home/as/Z2"}
        client.post = AsyncMock(return_value=response)

        with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client):
            resp = test_client.post("/api/select-directory", json={"currentPath": "/home/as/Z"})

        assert resp.status_code == 200
        assert resp.json()["path"] == "/home/as/Z2"
        client.post.assert_awaited_once_with(
            "http://localhost:8082/select-directory",
            json={"currentPath": "/home/as/Z"},
        )

    def test_select_directory_api_reports_host_service_unavailable(self, test_client):
        with patch("gateway.server.settings.export_host_url", ""):
            resp = test_client.post("/api/select-directory", json={"currentPath": "/home/as/Z"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "EXPORT_HOST_URL" in resp.json()["error"]


class TestAsgiAppRouter:
    @pytest.mark.asyncio
    async def test_app_routes_mcp_requests_to_session_manager(self):
        from gateway import server

        sent = []
        with patch.object(server, "session_manager") as session_manager, \
             patch.object(server, "_starlette") as starlette_app:
            session_manager.handle_request = AsyncMock()
            starlette_app.return_value = None
            await server.app(
                {"type": "http", "path": "/mcp"},
                AsyncMock(),
                lambda message: sent.append(message),
            )

        session_manager.handle_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_app_routes_non_mcp_requests_to_starlette(self):
        from gateway import server

        with patch.object(server, "session_manager") as session_manager, \
             patch.object(server, "_starlette", new=AsyncMock()) as starlette_app:
            await server.app(
                {"type": "http", "path": "/health"},
                AsyncMock(),
                AsyncMock(),
            )

        session_manager.handle_request.assert_not_called()
        starlette_app.assert_awaited_once()


class TestAdditionalServerBranches:
    @pytest.mark.asyncio
    async def test_restore_databases_skips_invalid_entries(self):
        from gateway import server

        registry = MagicMock()
        registry.load_saved_state.return_value = [{"name": "db1"}, {"connection": "Srvr=srv;Ref=db1;"}]
        registry.get_saved_active.return_value = ""

        with patch("gateway.server._registry", registry):
            assert await server._restore_databases() is False

    @pytest.mark.asyncio
    async def test_restore_databases_without_lsp_container_adds_only_toolkit_backend(self):
        from gateway import server

        registry = MagicMock()
        registry.load_saved_state.return_value = [
            {"name": "db1", "slug": "db1", "connection": "Srvr=srv;Ref=db1;", "project_path": "/projects/db1"}
        ]
        registry.get_saved_active.return_value = ""
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.set_default_db.return_value = False

        async def fake_wait_for(awaitable, timeout=None):
            return await awaitable

        loop = MagicMock()
        loop.run_in_executor.side_effect = [asyncio.sleep(0, result=(6100, "onec-toolkit-db1")), asyncio.sleep(0, result="")]

        with patch("gateway.server._registry", registry), \
             patch("gateway.server._manager", manager), \
             patch("gateway.server.asyncio.get_running_loop", return_value=loop), \
             patch("gateway.server.asyncio.wait_for", side_effect=fake_wait_for):
            restored = await server._restore_databases()

        assert restored is True
        args = manager.add_db_backends.await_args.args
        assert args[0] == "db1"
        assert args[2] is None

    def test_audit_action_handles_request_without_client(self):
        from gateway import server

        request = SimpleNamespace(method="POST", url=SimpleNamespace(path="/api/action/save-env"), client=None)
        with patch("gateway.server.logger") as logger:
            server._audit_action(request, "save-env", True, value="x")

        assert logger.info.call_args.args[5] == "-"

    @pytest.mark.asyncio
    async def test_trigger_graph_rebuild_swallow_errors(self):
        from gateway import server

        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        client.post = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("gateway.server.settings.bsl_graph_url", "http://localhost:8888"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client):
            await server._trigger_graph_rebuild()

    def test_register_epf_uses_toolkit_url_when_port_missing(self, test_client):
        db = SimpleNamespace(toolkit_port=0, toolkit_url="http://localhost:6100/mcp")
        with patch("gateway.server._registry") as registry, patch("gateway.server._manager") as manager:
            registry.get.return_value = db
            registry.active_name = ""
            manager.has_db.return_value = True
            resp = test_client.post("/api/register", json={"name": "db1"})

        assert resp.status_code == 200
        assert resp.json()["toolkit_poll_url"] == "http://localhost:6100/1c/poll"

    def test_register_epf_without_ref_uses_workspace_root(self, test_client):
        with patch("gateway.server._registry") as registry, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")) as connect_db:
            registry.get.return_value = None
            registry.active_name = ""
            manager.has_db.return_value = False
            resp = test_client.post("/api/register", json={"name": "db1", "connection": "Srvr=srv;"})

        assert resp.status_code == 200
        assert connect_db.await_args.args[2] == "/hostfs-home/as/Z/db1"

    def test_connect_db_action_returns_backend_error_message(self, test_client):
        with patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ERROR: boom")), \
             patch("gateway.server._audit_action"), \
             patch("gateway.server.settings.gateway_api_token", ""):
            resp = test_client.post(
                "/api/action/connect-db",
                json={"name": "db1", "connection": "Srvr=srv;Ref=db1;", "project_path": "/projects/db1"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert resp.json()["message"] == "ERROR: boom"

    def test_edit_db_action_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/action/edit-db",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_remove_action_logs_cleanup_failure_but_returns_ok(self):
        from gateway import server

        db = SimpleNamespace(slug="db1", connection="Srvr=srv;Ref=db1;", project_path="/projects/db1", lsp_container="")
        request = SimpleNamespace(
            path_params={"action": "remove"},
            query_params={"name": "db1"},
            json=AsyncMock(return_value={}),
            method="POST",
            url=SimpleNamespace(path="/api/action/remove"),
            client=SimpleNamespace(host="127.0.0.1"),
        )
        loop = MagicMock()

        with patch("gateway.server._registry") as registry, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()), \
             patch("gateway.server._audit_action"), \
             patch("gateway.server.asyncio.wait_for", side_effect=RuntimeError("boom")), \
             patch("gateway.server.asyncio.get_running_loop", return_value=loop):
            loop.run_in_executor.return_value = object()
            manager.remove_db_backends = AsyncMock()
            registry.get.return_value = db
            resp = await server.action_api(request)

        assert resp.status_code == 200
        assert json.loads(resp.body)["ok"] is True

    def test_save_bsl_workspace_invalid_json(self, test_client):
        resp = test_client.post(
            "/api/action/save-bsl-workspace",
            content=b"bad",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_save_bsl_workspace_returns_write_error_without_apply(self, test_client):
        with patch("gateway.server._update_env_value", return_value={"ok": False, "error": "cannot write"}), \
             patch("gateway.server._apply_bsl_workspace_runtime", new=AsyncMock()) as apply_runtime:
            resp = test_client.post("/api/action/save-bsl-workspace", json={"value": "/home/as/Z"})

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        apply_runtime.assert_not_called()

    def test_save_env_returns_write_error_without_restart(self, test_client):
        with patch("gateway.server._write_env_file", return_value={"ok": False, "error": "cannot write"}), \
             patch("gateway.server._restart_gateway") as restart_gateway, \
             patch("gateway.server._audit_action"):
            resp = test_client.post(
                "/api/action/save-env",
                json={"content": "PORT=8080\n", "mode": "replace"},
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        restart_gateway.assert_not_called()

    def test_reindex_bsl_returns_not_found_for_missing_database(self, test_client):
        with patch("gateway.server._registry") as registry:
            registry.get.return_value = None
            resp = test_client.post("/api/action/reindex-bsl?name=missing")

        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_reindex_bsl_returns_index_error(self, test_client):
        db = SimpleNamespace(project_path="/projects/db1", lsp_container="")
        with patch("gateway.server._registry") as registry, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.bsl_search.bsl_search.build_index", return_value="ERROR: boom"):
            registry.get.return_value = db
            manager.get_db_backend.return_value = None
            resp = test_client.post("/api/action/reindex-bsl?name=db1")

        assert resp.status_code == 200
        assert resp.json()["ok"] is False

    def test_reindex_bsl_reports_lsp_exception(self, test_client):
        db = SimpleNamespace(project_path="/projects/db1", lsp_container="mcp-lsp-db1")
        lsp = MagicMock()
        lsp.call_tool = AsyncMock(side_effect=RuntimeError("boom"))
        with patch("gateway.server._registry") as registry, \
             patch("gateway.server._manager") as manager, \
             patch("gateway.bsl_search.bsl_search.build_index", return_value="Indexed 3 symbols"):
            registry.get.return_value = db
            manager.get_db_backend.return_value = lsp
            resp = test_client.post("/api/action/reindex-bsl?name=db1")

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "Ошибка LSP-переиндексации" in resp.json()["message"]

    def test_reindex_bsl_without_name_uses_global_handler(self, test_client):
        with patch("gateway.mcp_server._reindex_bsl", new=AsyncMock(return_value="ok")) as reindex_bsl:
            resp = test_client.post("/api/action/reindex-bsl")

        assert resp.status_code == 200
        assert resp.json()["message"] == "ok"
        reindex_bsl.assert_awaited_once_with("")

    def test_http_service_reachable_returns_false_on_client_errors(self):
        from gateway import server

        with patch("gateway.server.httpx.get", side_effect=RuntimeError("boom")):
            assert server._http_service_reachable("http://localhost:8082", paths=("/health",)) is False

    def test_optional_services_status_lsp_running_without_memory_uses_short_details(self, monkeypatch):
        from gateway import server

        monkeypatch.setattr(server.settings, "enabled_backends", "bsl-lsp-bridge")
        with patch("gateway.server._http_service_reachable", return_value=False), \
             patch("gateway.docker_manager._docker") as docker_client:
            docker_client.return_value.images.get.return_value = object()
            summary = server._get_optional_services_status(
                {"db1/lsp": {"ok": True}},
                [{"name": "mcp-lsp-db1", "running": True, "memory_usage_bytes": 0}],
                "ru",
            )

        lsp = {item["name"]: item for item in summary}["bsl-lsp-bridge"]
        assert lsp["state"] == "ok"
        assert "контейнеров" in lsp["details"]

    def test_read_env_file_returns_fallback_when_env_path_missing(self, monkeypatch):
        from gateway import server

        monkeypatch.setenv("ENV_FILE_PATH", "/missing/env")
        real_open = open

        def fake_open(path, mode="r", encoding=None):
            if path in ("/data/.env", ".env", "/app/.env", "/missing/env"):
                raise FileNotFoundError
            return real_open(path, mode, encoding=encoding)

        with patch("builtins.open", side_effect=fake_open):
            text = server._read_env_file()

        assert text.startswith("# .env file not found")

    def test_read_env_file_returns_fallback_when_env_file_path_points_to_missing_file(self, monkeypatch):
        from gateway import server

        monkeypatch.setenv("ENV_FILE_PATH", "/definitely/missing.env")

        def fake_open(path, mode="r", encoding=None):
            raise FileNotFoundError(path)

        with patch("builtins.open", side_effect=fake_open):
            text = server._read_env_file()

        assert text.startswith("# .env file not found")

    @pytest.mark.asyncio
    async def test_apply_bsl_workspace_runtime_uses_workspace_fallback_when_new_value_empty(self):
        from gateway import server

        db_info = SimpleNamespace(slug="ERP", project_path="/workspace/ERP")
        registry = MagicMock()
        registry.list.return_value = [{"name": "ERP"}]
        registry.get.return_value = db_info
        manager = MagicMock()
        manager.has_db.return_value = False

        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager):
            result = await server._apply_bsl_workspace_runtime("", "http://localhost:8082")

        assert result["db_reconfigured"] == 0
        registry.update.assert_not_called()

    def test_collect_diagnostics_handles_container_log_error(self):
        from gateway import server

        container = MagicMock()
        container.name = "onec-mcp-gw"
        container.logs.side_effect = RuntimeError("boom")
        client = MagicMock()
        client.containers.list.return_value = [container]

        with patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_docker_system_info", return_value={}), \
             patch("gateway.server._manager.status", return_value={}), \
             patch("gateway.server._registry.list", return_value=[]), \
             patch("gateway.profiler.profiler.get_stats", return_value={}), \
             patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
             patch("gateway.anonymizer.anonymizer.enabled", False), \
             patch("gateway.docker_manager._docker", return_value=client):
            diag = server._collect_diagnostics()

        assert diag["container_logs"]["onec-mcp-gw"] == "error reading logs"

    def test_collect_diagnostics_skips_non_project_containers(self):
        from gateway import server

        ignored = MagicMock()
        ignored.name = "postgres"
        matched = MagicMock()
        matched.name = "onec-mcp-gw"
        matched.logs.return_value = b"ok"
        client = MagicMock()
        client.containers.list.return_value = [ignored, matched]

        with patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_docker_system_info", return_value={}), \
             patch("gateway.server._manager.status", return_value={}), \
             patch("gateway.server._registry.list", return_value=[]), \
             patch("gateway.profiler.profiler.get_stats", return_value={}), \
             patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
             patch("gateway.anonymizer.anonymizer.enabled", False), \
             patch("gateway.docker_manager._docker", return_value=client):
            diag = server._collect_diagnostics()

        assert "postgres" not in diag["container_logs"]
        assert diag["container_logs"]["onec-mcp-gw"] == "ok"

    def test_collect_diagnostics_handles_outer_docker_exception(self):
        from gateway import server

        with patch("gateway.server._get_container_info", return_value=[]), \
             patch("gateway.server._get_docker_system_info", return_value={}), \
             patch("gateway.server._manager.status", return_value={}), \
             patch("gateway.server._registry.list", return_value=[]), \
             patch("gateway.profiler.profiler.get_stats", return_value={}), \
             patch("gateway.metadata_cache.metadata_cache.stats", return_value={}), \
             patch("gateway.anonymizer.anonymizer.enabled", False), \
             patch("gateway.docker_manager._docker", side_effect=RuntimeError("boom")):
            diag = server._collect_diagnostics()

        assert "boom" in diag["container_logs"]["error"]
        assert "direct fallback failed" in diag["container_logs"]["error"]

    def test_browse_api_uses_workspace_default_when_path_missing(self, test_client):
        with patch("gateway.server.settings.export_host_url", ""), \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.server.os.listdir", return_value=[]):
            resp = test_client.get("/api/browse")

        assert resp.status_code == 200
        assert resp.json()["path"] == "/home/as/Z"

    def test_browse_api_returns_host_service_error_payload_for_non_200(self, test_client):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        response = MagicMock(status_code=503)
        response.json.return_value = {}
        client.get = AsyncMock(return_value=response)

        with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client):
            resp = test_client.get("/api/browse?path=/home/as/Z")

        assert resp.status_code == 200
        assert resp.json()["error"] == "Host browse failed with HTTP 503"

    def test_browse_api_falls_back_to_local_fs_when_host_service_returns_invalid_json(self, test_client):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False
        response = MagicMock(status_code=200)
        response.json.side_effect = ValueError("bad json")
        client.get = AsyncMock(return_value=response)

        with patch("gateway.server.settings.export_host_url", "http://localhost:8082"), \
             patch("gateway.server.httpx.AsyncClient", return_value=client), \
             patch("gateway.server._read_env_value", return_value="/home/as/Z"), \
             patch("gateway.server.os.path.isdir", return_value=True), \
             patch("gateway.server.os.listdir", return_value=[]):
            resp = test_client.get("/api/browse")

        assert resp.status_code == 200
        assert resp.json()["path"] == "/home/as/Z"


class TestRemainingServerCoverage:
    def test_channel_and_toolkit_url_helpers_cover_edge_cases(self):
        from gateway import server

        assert server._normalize_channel_id("") == "default"
        assert server._normalize_channel_id("x" * 65) == "default"
        assert server._normalize_channel_id("bad channel!") == "default"
        assert server._normalize_channel_id("live-Z01_1") == "live-Z01_1"

        assert server._build_db_toolkit_mcp_url(SimpleNamespace(toolkit_port=0, toolkit_url=""), "default") == ""
        assert (
            server._build_db_toolkit_mcp_url(
                SimpleNamespace(toolkit_port=0, toolkit_url="http://localhost:6100/mcp?old=1"),
                "live channel",
            )
            == "http://localhost:6100/mcp?channel=live%20channel"
        )
        assert server._build_db_toolkit_poll_url(SimpleNamespace(toolkit_port=0, toolkit_url="")) == ""

    @pytest.mark.asyncio
    async def test_rebind_db_toolkit_backend_covers_missing_plain_and_async_rebind(self):
        from gateway import server

        manager = MagicMock()
        manager.get_db_backend.return_value = None
        with patch("gateway.server._manager", manager):
            await server._rebind_db_toolkit_backend("missing", "http://localhost:6100/mcp")

        plain_backend = SimpleNamespace(rebind=lambda url: "ok")
        manager.get_db_backend.return_value = plain_backend
        with patch("gateway.server._manager", manager):
            await server._rebind_db_toolkit_backend("db1", "http://localhost:6100/mcp")

        manager.get_db_backend.return_value = SimpleNamespace(rebind="not-callable")
        with patch("gateway.server._manager", manager):
            await server._rebind_db_toolkit_backend("db1", "http://localhost:6100/mcp")

        async_rebind = AsyncMock()
        manager.get_db_backend.return_value = SimpleNamespace(rebind=async_rebind)
        with patch("gateway.server._manager", manager):
            await server._rebind_db_toolkit_backend("db1", "http://localhost:6101/mcp")
        async_rebind.assert_awaited_once_with("http://localhost:6101/mcp")

    @pytest.mark.asyncio
    async def test_recreate_bsl_graph_runtime_disabled_success_and_error(self):
        from gateway import server

        with patch("gateway.server.settings.bsl_graph_url", ""):
            assert await server._recreate_bsl_graph_runtime() == {
                "attempted": False,
                "ok": False,
                "reason": "graph disabled",
            }

        with patch("gateway.server.settings.bsl_graph_url", "http://localhost:8888"), \
             patch("gateway.server._docker_manager.recreate_bsl_graph") as recreate, \
             patch("gateway.server._trigger_graph_rebuild", new=AsyncMock()) as rebuild:
            assert await server._recreate_bsl_graph_runtime() == {"attempted": True, "ok": True}
        recreate.assert_called_once()
        rebuild.assert_awaited_once()

        with patch("gateway.server.settings.bsl_graph_url", "http://localhost:8888"), \
             patch("gateway.server._docker_manager.recreate_bsl_graph", side_effect=RuntimeError("boom")):
            errored = await server._recreate_bsl_graph_runtime()
        assert errored["attempted"] is True
        assert errored["ok"] is False
        assert "boom" in errored["error"]

    def test_export_preview_api_errors_and_success(self, test_client):
        invalid = test_client.post("/api/export-preview", content=b"bad", headers={"content-type": "application/json"})
        missing = test_client.post("/api/export-preview", json={})
        with patch("gateway.server._resolve_export_paths", return_value=("", "", "bad path")):
            resolved_error = test_client.post("/api/export-preview", json={"connection": "Srvr=srv;Ref=Z01;"})
        with patch("gateway.server._resolve_export_paths", return_value=("/workspace/Z01", "/home/as/Z/Z01", None)):
            ok = test_client.post("/api/export-preview", json={"connection": "Srvr=srv;Ref=Z01;"})

        assert invalid.status_code == 400
        assert missing.status_code == 400
        assert resolved_error.status_code == 400
        assert resolved_error.json()["error"] == "bad path"
        assert ok.status_code == 200
        assert ok.json()["output_dir"] == "/workspace/Z01"

    @pytest.mark.asyncio
    async def test_ensure_lsp_started_edge_paths(self, tmp_path):
        from gateway import server

        await server._ensure_lsp_started("Srvr=srv;")

        registry = MagicMock()
        registry.get.return_value = None
        with patch("gateway.server._registry", registry):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        db = SimpleNamespace(project_path="", slug="Z01")
        registry.get.return_value = db
        with patch("gateway.server._registry", registry):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        file_path = tmp_path / "not-dir"
        file_path.write_text("x", encoding="utf-8")
        registry.get.return_value = SimpleNamespace(project_path=str(file_path), slug="Z01")
        with patch("gateway.server._registry", registry):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        missing = tmp_path / "missing"
        registry.get.return_value = SimpleNamespace(project_path=str(missing), slug="Z01")
        with patch("gateway.server._registry", registry):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        broken = tmp_path / "broken"
        broken.mkdir()
        registry.get.return_value = SimpleNamespace(project_path=str(broken), slug="Z01")
        with patch("gateway.server._registry", registry), patch("gateway.server.os.scandir", side_effect=OSError("boom")):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        registry.get.return_value = SimpleNamespace(project_path=str(broken), slug="Z01")
        with patch("gateway.server._registry", registry), patch("gateway.server.os.stat", side_effect=PermissionError("denied")), patch(
            "gateway.server._docker_manager.start_lsp", return_value=""
        ):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        empty = tmp_path / "empty"
        empty.mkdir()
        registry.get.return_value = SimpleNamespace(project_path=str(empty), slug="Z01")
        with patch("gateway.server._registry", registry):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        await server._ensure_lsp_started(None)

    @pytest.mark.asyncio
    async def test_ensure_lsp_started_starts_detaches_and_handles_start_attach_failures(self, tmp_path):
        from gateway import server

        project = tmp_path / "Z01"
        project.mkdir()
        (project / "x.bsl").write_text("Процедура X()\nКонецПроцедуры", encoding="utf-8")
        db = SimpleNamespace(project_path=str(project), slug="Z01")
        registry = MagicMock()
        registry.get.return_value = db
        manager = MagicMock()
        manager.db_has_lsp.return_value = True
        manager.detach_db_lsp = AsyncMock()
        manager.attach_db_lsp = AsyncMock()

        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server._docker_manager.start_lsp", return_value="mcp-lsp-Z01"
        ):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

        registry.update_runtime.assert_called_once_with("Z01", lsp_container="mcp-lsp-Z01")
        manager.detach_db_lsp.assert_awaited_once_with("Z01")
        manager.attach_db_lsp.assert_awaited_once()

        manager.attach_db_lsp.reset_mock()
        manager.db_has_lsp.return_value = False
        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server._docker_manager.start_lsp", side_effect=RuntimeError("start failed")
        ):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")
        manager.attach_db_lsp.assert_not_awaited()

        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server._docker_manager.start_lsp", return_value=""
        ):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")
        manager.attach_db_lsp.assert_not_awaited()

        manager.attach_db_lsp = AsyncMock(side_effect=RuntimeError("attach failed"))
        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server._docker_manager.start_lsp", return_value="mcp-lsp-Z01"
        ):
            await server._ensure_lsp_started("Srvr=srv;Ref=Z01;")

    @pytest.mark.asyncio
    async def test_register_heartbeat_custom_channel_rebinds_toolkit_backend(self, test_client):
        db = SimpleNamespace(toolkit_port=6100, toolkit_url="", project_path="/workspace/Z01")
        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._sync_managed_project_path_if_needed", new=AsyncMock(return_value=False)
        ), patch("gateway.server._rebind_db_toolkit_backend", new=AsyncMock()) as rebind:
            registry.mark_epf_heartbeat.return_value = True
            registry.get.return_value = db
            resp = test_client.post("/api/epf-heartbeat", json={"name": "Z01", "channel": "live"})

        assert resp.status_code == 200
        registry.update_runtime.assert_called_once_with(
            "Z01",
            toolkit_url="http://localhost:6100/mcp?channel=live",
            channel_id="live",
        )
        rebind.assert_awaited_once_with("Z01", "http://localhost:6100/mcp?channel=live")

    @pytest.mark.asyncio
    async def test_register_heartbeat_covers_default_missing_db_and_empty_toolkit_url(self, test_client):
        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._sync_managed_project_path_if_needed", new=AsyncMock()
        ) as sync_path:
            registry.mark_epf_heartbeat.return_value = True
            registry.get.return_value = None
            missing_db = test_client.post("/api/epf-heartbeat", json={"name": "Z01", "channel": "live"})

        assert missing_db.status_code == 200
        sync_path.assert_not_awaited()

        db = SimpleNamespace(toolkit_port=0, toolkit_url="", project_path="/workspace/Z01")
        with patch("gateway.server._registry") as registry, patch(
            "gateway.server._sync_managed_project_path_if_needed", new=AsyncMock(return_value=False)
        ) as sync_path, patch("gateway.server._rebind_db_toolkit_backend", new=AsyncMock()) as rebind:
            registry.mark_epf_heartbeat.return_value = True
            registry.get.return_value = db
            default_channel = test_client.post("/api/epf-heartbeat", json={"name": "Z01", "channel": ""})
            custom_without_url = test_client.post("/api/epf-heartbeat", json={"name": "Z01", "channel": "live"})

        assert default_channel.status_code == 200
        assert custom_without_url.status_code == 200
        assert sync_path.await_count == 2
        rebind.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sync_managed_project_path_no_db_and_triggers_lsp_for_running_db(self):
        from gateway import server

        with patch("gateway.server._registry") as registry:
            registry.get.return_value = None
            assert await server._sync_managed_project_path_if_needed("missing") is False

        db = SimpleNamespace(slug="Z01", project_path="/workspace/Z01", connection="Srvr=srv;Ref=Z01;")
        refreshed = SimpleNamespace(slug="Z01", project_path="/hostfs-home/as/Z/Z01", connection="Srvr=srv;Ref=Z01;")
        registry = MagicMock()
        registry.get.side_effect = [refreshed]
        manager = MagicMock()
        manager.has_db.return_value = True
        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server._normalize_runtime_project_path", return_value="/hostfs-home/as/Z/Z01"
        ), patch("gateway.server._ensure_lsp_started", new=AsyncMock()) as ensure_lsp, patch(
            "gateway.server._trigger_graph_rebuild", new=AsyncMock()
        ) as rebuild:
            assert await server._sync_managed_project_path_if_needed("Z01", db) is True

        registry.update.assert_called_once_with("Z01", project_path="/hostfs-home/as/Z/Z01")
        ensure_lsp.assert_awaited_once_with("Srvr=srv;Ref=Z01;")
        rebuild.assert_awaited_once()

    def test_env_helpers_cover_standard_file_skip_lines_and_not_found_prepare(self, tmp_path, monkeypatch):
        from gateway import server

        env_file = tmp_path / ".env"
        env_file.write_text("A=1\n", encoding="utf-8")
        real_open = open

        def fake_open(path, *args, **kwargs):
            if path == "/data/.env":
                return real_open(env_file, *args, **kwargs)
            raise FileNotFoundError(path)

        with patch("gateway.server.os.environ", {}), patch("builtins.open", side_effect=fake_open):
            assert server._read_env_file() == "A=1\n"

        assert server._iter_env_assignments("# c\nNOEQUALS\nA=1\n") == [("A", "1")]
        with patch("gateway.server._read_env_file", return_value="# .env file not found\n"):
            assert server._prepare_env_content_for_write("B=2", replace=False) == "B=2"
        with patch("gateway.server._read_env_file", return_value="A=1\n"):
            assert server._prepare_env_content_for_write("A=2\n", replace=False) == "A=2\n"

    def test_save_bsl_workspace_message_omits_graph_suffix_when_recreate_not_attempted(self, test_client):
        with patch("gateway.server._update_env_value", return_value={"ok": True, "message": "saved"}), patch(
            "gateway.server._read_env_value", return_value="http://localhost:8082"
        ), patch(
            "gateway.server._apply_bsl_workspace_runtime",
            new=AsyncMock(return_value={"db_reconfigured": 1, "db_errors": 0, "errors": []}),
        ), patch("gateway.server._recreate_bsl_graph_runtime", new=AsyncMock(return_value={"attempted": False, "ok": False})):
            resp = test_client.post("/api/action/save-bsl-workspace", json={"value": "/home/as/Z"})

        assert resp.status_code == 200
        assert "Базы обновлены: 1" in resp.json()["message"]
        assert "Граф" not in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_apply_bsl_workspace_runtime_permission_and_missing_directory_skip(self):
        from gateway import server

        registry = MagicMock()
        registry.list.return_value = [{"name": "PERM"}, {"name": "MISSING"}]
        registry.get.side_effect = lambda name: SimpleNamespace(slug=name, project_path=f"/workspace/{name}")
        manager = MagicMock()
        manager.has_db.return_value = True

        def fake_isdir(path):
            if path.endswith("/PERM"):
                raise PermissionError("denied")
            return False

        with patch("gateway.server._registry", registry), patch("gateway.server._manager", manager), patch(
            "gateway.server.os.path.isdir", side_effect=fake_isdir
        ), patch("gateway.server._docker_manager.start_lsp", return_value="mcp-lsp-PERM") as start_lsp:
            result = await server._apply_bsl_workspace_runtime("/workspace", "http://localhost:8082")

        assert result["db_reconfigured"] == 1
        assert result["db_errors"] == 0
        start_lsp.assert_called_once()

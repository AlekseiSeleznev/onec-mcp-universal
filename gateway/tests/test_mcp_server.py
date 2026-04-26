"""Tests for gateway.mcp_server — tool dispatch, routing, error handling."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import server first so it injects manager/registry into mcp_server
from gateway import server as _server_mod  # noqa: F401 — side-effect: injects into mcp_server
import gateway.mcp_server as _ms_mod

from mcp.types import CallToolResult, TextContent, Tool

from gateway.backends.base import BackendBase
from gateway.backends.manager import BackendManager
from gateway.db_registry import DatabaseRegistry

# ---------------------------------------------------------------------------
# Helpers — FakeBackend
# ---------------------------------------------------------------------------


def _make_tool(name: str) -> Tool:
    return Tool(name=name, description=f"Tool {name}", inputSchema={"type": "object"})


class FakeBackend(BackendBase):
    def __init__(self, name: str, tool_names: list[str]):
        super().__init__(name)
        self.tools = [_make_tool(n) for n in tool_names]

    async def start(self) -> None:
        self.available = True

    async def stop(self) -> None:
        self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return CallToolResult(content=[TextContent(type="text", text=f"{self.name}:{name}")])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_manager():
    return BackendManager()


@pytest.fixture()
def fresh_registry(tmp_path):
    return DatabaseRegistry(state_file=tmp_path / "state.json")


@pytest.fixture(autouse=True)
def patch_mcp_server(fresh_manager, fresh_registry):
    """Patch the module-level manager and registry in mcp_server."""
    import gateway.mcp_server as ms
    original_manager = ms.manager
    original_registry = ms.registry
    original_export_jobs = dict(ms._export_jobs)
    original_index_jobs = dict(ms._index_jobs)
    original_export_tasks = dict(ms._export_tasks)
    ms.manager = fresh_manager
    ms.registry = fresh_registry
    ms._export_jobs.clear()
    ms._index_jobs.clear()
    ms._export_tasks.clear()
    yield ms
    for task in list(ms._export_tasks.values()):
        task.cancel()
    ms.manager = original_manager
    ms.registry = original_registry
    ms._export_jobs.clear()
    ms._export_jobs.update(original_export_jobs)
    ms._index_jobs.clear()
    ms._index_jobs.update(original_index_jobs)
    ms._export_tasks.clear()
    ms._export_tasks.update(original_export_tasks)


@pytest.fixture(autouse=True)
def patch_session_id(patch_mcp_server):
    """Patch _get_session_id to always return None and _get_session_active to use registry."""
    ms = patch_mcp_server
    with patch.object(ms, "_get_session_id", return_value=None):
        with patch.object(ms, "_get_session_active", side_effect=lambda: ms.registry.get_active()):
            yield


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    @pytest.mark.asyncio
    async def test_list_prompts_and_get_prompt_format_known_arguments(self, patch_mcp_server):
        ms = patch_mcp_server

        prompts = await ms.list_prompts()
        result = await ms.get_prompt("describe_object", {"metadata_object": "Справочник.Валюты"})

        assert any(prompt.name == "describe_object" for prompt in prompts)
        assert "Справочник.Валюты" in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_get_prompt_falls_back_to_template_when_argument_missing_and_rejects_unknown(self, patch_mcp_server):
        ms = patch_mcp_server

        result = await ms.get_prompt("describe_object", {})

        assert "{metadata_object}" in result.messages[0].content.text
        with pytest.raises(ValueError, match="Unknown prompt"):
            await ms.get_prompt("missing")


# ---------------------------------------------------------------------------
# list_tools
# ---------------------------------------------------------------------------


class TestListTools:
    @pytest.mark.asyncio
    async def test_handles_uninitialized_manager(self, patch_mcp_server):
        ms = patch_mcp_server
        original_manager = ms.manager
        original_registry = ms.registry
        ms.manager = None
        ms.registry = None
        try:
            tools = await ms.list_tools()
            names = {t.name for t in tools}
            for gw_tool in ms.GW_TOOLS:
                assert gw_tool.name in names
        finally:
            ms.manager = original_manager
            ms.registry = original_registry

    @pytest.mark.asyncio
    async def test_includes_all_gw_tools(self, patch_mcp_server):
        ms = patch_mcp_server
        tools = await ms.list_tools()
        names = {t.name for t in tools}
        for gw_tool in ms.GW_TOOLS:
            assert gw_tool.name in names

    @pytest.mark.asyncio
    async def test_includes_backend_tools(self, patch_mcp_server, fresh_manager):
        ms = patch_mcp_server
        backend = FakeBackend("backend", ["execute_query"])
        await fresh_manager.start_all([backend])
        tools = await ms.list_tools()
        names = {t.name for t in tools}
        assert "execute_query" in names
        assert len(names) == len(tools)

    @pytest.mark.asyncio
    async def test_no_its_search_without_api_key(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "naparnik_api_key", "")
        tools = await ms.list_tools()
        names = {t.name for t in tools}
        assert "its_search" not in names

    @pytest.mark.asyncio
    async def test_its_search_included_with_api_key(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "naparnik_api_key", "test-key")
        tools = await ms.list_tools()
        names = {t.name for t in tools}
        assert "its_search" in names

    @pytest.mark.asyncio
    async def test_gw_tool_names_constant_matches_list(self, patch_mcp_server):
        ms = patch_mcp_server
        assert ms.GW_TOOL_NAMES == {t.name for t in ms.GW_TOOLS}

    @pytest.mark.asyncio
    async def test_deduplicates_static_and_db_tools(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        tk = FakeBackend("tk", ["execute_query", "get_metadata"])
        await fresh_manager.add_db_backends("mydb", tk, None)
        backend = FakeBackend("backend", ["execute_query"])
        await fresh_manager.start_all([backend])

        tools = await ms.list_tools()
        names = [t.name for t in tools]

        assert names.count("execute_query") == 1

    @pytest.mark.asyncio
    async def test_includes_dynamic_lsp_backend_tools(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        tk = FakeBackend("tk", ["execute_query"])
        lsp = FakeBackend("lsp", ["lsp_status", "definition"])
        await fresh_manager.add_db_backends("mydb", tk, lsp)

        tools = await ms.list_tools()
        names = {t.name for t in tools}

        assert "lsp_status" in names
        assert "definition" in names


class TestResourcesAndHelpers:
    @pytest.mark.asyncio
    async def test_list_resources_and_read_resource(self, patch_mcp_server):
        ms = patch_mcp_server

        resources = await ms.list_resources()
        assert len(resources) == 1
        assert str(resources[0].uri) == "file:///syntax_1c.txt"

        body = await ms.read_resource("file:///syntax_1c.txt")
        assert body

    @pytest.mark.asyncio
    async def test_read_unknown_resource_raises(self, patch_mcp_server):
        ms = patch_mcp_server

        with pytest.raises(ValueError, match="Unknown resource"):
            await ms.read_resource("file:///missing.txt")

    def test_search_syntax_reference_requires_keywords(self, patch_mcp_server):
        ms = patch_mcp_server

        payload = json.loads(ms._search_syntax_reference(["", "   "]))
        assert payload["success"] is False

    def test_search_syntax_reference_returns_candidates_without_full_content(self, patch_mcp_server):
        ms = patch_mcp_server

        payload = json.loads(ms._search_syntax_reference(["процедура", "функция"], limit=2))
        assert payload["success"] is True
        assert payload["data"]["candidates"]
        assert payload["data"]["content"] is None or payload["data"]["content"].startswith("## ")

    def test_slugify_handles_empty_and_non_alnum(self, patch_mcp_server):
        ms = patch_mcp_server
        assert ms._slugify("!!!") == "db_"
        assert ms._slugify("__тест") == "test"

    def test_result_helpers(self, patch_mcp_server):
        ms = patch_mcp_server

        assert ms._ok("ok").isError is False
        assert ms._err("bad").isError is True
        assert ms._result("ERROR: boom").isError is True
        assert ms._result("done").isError is False

    def test_get_session_active_falls_back_to_registry_active(self, patch_mcp_server, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        fresh_registry.switch("mydb")

        with patch.object(ms, "_get_session_id", return_value=None):
            assert ms._get_session_active().name == "mydb"

    def test_get_session_id_returns_none_for_missing_request_headers(self, patch_mcp_server):
        ms = patch_mcp_server
        fake_ctx = SimpleNamespace(request=None)
        with patch("mcp.server.lowlevel.server.request_ctx", SimpleNamespace(get=lambda: fake_ctx)):
            assert ms._get_session_id() is None

    def test_get_session_id_handles_attribute_error(self, patch_mcp_server):
        ms = patch_mcp_server

        class _BrokenCtx:
            @property
            def request(self):
                raise AttributeError("boom")

        with patch("mcp.server.lowlevel.server.request_ctx", SimpleNamespace(get=lambda: _BrokenCtx())):
            assert ms._get_session_id() is None

    def test_resolve_export_output_dir_fallbacks(self, patch_mcp_server, fresh_registry, monkeypatch):
        ms = patch_mcp_server
        fresh_registry.register("ERP", "Srvr=srv;Ref=ERP;", "/projects/ERP", slug="erp")
        monkeypatch.setattr(ms.settings, "bsl_host_workspace", "/home/as/Z")
        monkeypatch.setattr(ms.settings, "bsl_workspace", "/workspace")
        assert ms._resolve_export_output_dir("Srvr=srv;Ref=ERP;", "/projects") == "/home/as/Z/erp"

        monkeypatch.setattr(ms.settings, "bsl_host_workspace", "")
        monkeypatch.setattr(ms.settings, "bsl_workspace", "/opt/bsl")
        assert ms._resolve_export_output_dir("Srvr=srv;Ref=ERP;", "/workspace") == "/opt/bsl/erp"
        assert ms._resolve_export_output_dir("Srvr=srv;Ref=ERP;", "/tmp/out") == "/tmp/out"

    def test_resolve_export_output_dir_keeps_placeholder_without_known_roots(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        monkeypatch.setattr(ms.settings, "bsl_host_workspace", "")
        monkeypatch.setattr(ms.settings, "bsl_workspace", "")
        assert ms._resolve_export_output_dir("Srvr=srv;Ref=ERP;", "/projects") == "/projects"

    def test_resolve_export_output_dir_uses_ref_name_when_registry_entry_missing(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        monkeypatch.setattr(ms.settings, "bsl_host_workspace", "/home/as/Z")
        monkeypatch.setattr(ms.settings, "bsl_workspace", "/workspace")
        assert ms._resolve_export_output_dir("Srvr=srv;Ref=ERP;", "/projects") == "/home/as/Z/ERP"

    def test_export_status_payload_shapes(self, patch_mcp_server):
        ms = patch_mcp_server
        ms._export_jobs["conn"] = {"status": "done", "result": "ok"}
        ms._index_jobs["conn"] = {"status": "done", "result": "Indexed"}

        single = ms._export_status_payload("conn")
        all_jobs = ms._export_status_payload()

        assert single["status"] == "done"
        assert all_jobs["jobs"]["conn"]["index_result"] == "Indexed"

    @pytest.mark.asyncio
    async def test_sync_export_status_from_host_updates_jobs(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms.settings, "export_host_url", "http://localhost:8082"), \
             patch.object(ms, "_get_session_active", return_value=None), \
             patch("gateway.mcp_server.build_index_with_fallback", return_value=(True, "Indexed 7 symbols")):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get = AsyncMock(return_value=SimpleNamespace(json=lambda: {"status": "done", "result": "ok"}))
            with patch("gateway.mcp_server.httpx.AsyncClient", return_value=client):
                await ms._sync_export_status_from_host("conn")

        assert ms._export_jobs["conn"]["status"] == "done"
        assert ms._index_jobs["conn"]["result"] == "Indexed 7 symbols"

    @pytest.mark.asyncio
    async def test_sync_export_status_ignores_invalid_status(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms.settings, "export_host_url", "http://localhost:8082"):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get = AsyncMock(return_value=SimpleNamespace(json=lambda: {"status": "idle", "result": ""}))
            with patch("gateway.mcp_server.httpx.AsyncClient", return_value=client):
                await ms._sync_export_status_from_host("conn")

        assert "conn" not in ms._export_jobs

    @pytest.mark.asyncio
    async def test_sync_export_status_ignores_http_errors(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms.settings, "export_host_url", "http://localhost:8082"):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get = AsyncMock(side_effect=RuntimeError("boom"))
            with patch("gateway.mcp_server.httpx.AsyncClient", return_value=client):
                await ms._sync_export_status_from_host("conn")

        assert "conn" not in ms._export_jobs

    @pytest.mark.asyncio
    async def test_sync_export_status_records_index_exception(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms.settings, "export_host_url", "http://localhost:8082"), \
             patch.object(ms, "_get_session_active", return_value=None), \
             patch("gateway.mcp_server.build_index_with_fallback", side_effect=RuntimeError("crash")):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get = AsyncMock(return_value=SimpleNamespace(json=lambda: {"status": "done", "result": "ok"}))
            with patch("gateway.mcp_server.httpx.AsyncClient", return_value=client):
                await ms._sync_export_status_from_host("conn")

        assert ms._index_jobs["conn"]["status"] == "error"
        assert ms._index_jobs["conn"]["result"] == "crash"

    @pytest.mark.asyncio
    async def test_sync_export_status_records_index_error_result(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms.settings, "export_host_url", "http://localhost:8082"), \
             patch.object(ms, "_get_session_active", return_value=None), \
             patch("gateway.mcp_server.build_index_with_fallback", return_value=(False, "ERROR: no symbols")):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get = AsyncMock(return_value=SimpleNamespace(json=lambda: {"status": "done", "result": "ok"}))
            with patch("gateway.mcp_server.httpx.AsyncClient", return_value=client):
                await ms._sync_export_status_from_host("conn")

        assert ms._index_jobs["conn"]["status"] == "error"
        assert ms._index_jobs["conn"]["result"] == "ERROR: no symbols"

    def test_wrapper_helpers_delegate(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._find_1cv8_binaries_impl", return_value={"8.3": Path("/tmp/1cv8")}) as find_impl, \
             patch("gateway.mcp_server._pick_1cv8_impl", return_value=Path("/tmp/1cv8")) as pick_impl:
            assert ms._find_1cv8_binaries() == {"8.3": Path("/tmp/1cv8")}
            assert ms._pick_1cv8("8.3") == Path("/tmp/1cv8")
        find_impl.assert_called_once()
        pick_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_designer_export_wrapper_delegates(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._run_designer_export_impl", new=AsyncMock(return_value=(0, "ok"))) as impl:
            result = await ms._run_designer_export(Path("/tmp/1cv8"), ["/S", "srv\\base"], "/tmp/out", timeout=30)
        assert result == (0, "ok")
        impl.assert_awaited_once()


# ---------------------------------------------------------------------------
# call_tool — gateway tools
# ---------------------------------------------------------------------------


class TestCallToolGatewayTools:

    @pytest.mark.asyncio
    async def test_get_server_status(self, patch_mcp_server, fresh_manager):
        ms = patch_mcp_server
        result = await ms.call_tool("get_server_status", {})
        assert len(result.content) == 1
        parsed = json.loads(result.content[0].text)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_list_databases_empty(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("list_databases", {})
        parsed = json.loads(result.content[0].text)
        assert parsed == []

    @pytest.mark.asyncio
    async def test_list_databases_with_entry(self, patch_mcp_server, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        result = await ms.call_tool("list_databases", {})
        parsed = json.loads(result.content[0].text)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "mydb"

    @pytest.mark.asyncio
    async def test_list_databases_expires_stale_epf(self, patch_mcp_server, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        with patch.object(fresh_registry, "expire_stale_epf", wraps=fresh_registry.expire_stale_epf) as mock_expire:
            await ms.call_tool("list_databases", {})
        from gateway.config import settings as gw_settings
        mock_expire.assert_called_once_with(gw_settings.epf_heartbeat_ttl_seconds)

    @pytest.mark.asyncio
    async def test_list_databases_marks_session_active_db(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
        fresh_registry.register("db2", "Srvr=srv;Ref=db2;", "/projects/db2")
        await fresh_manager.add_db_backends("db1", FakeBackend("tk1", ["execute_query"]), None)
        await fresh_manager.add_db_backends("db2", FakeBackend("tk2", ["execute_query"]), None)
        fresh_manager.switch_db("db2", session_id="sess-1")

        with patch.object(ms, "_get_session_id", return_value="sess-1"):
            result = await ms.call_tool("list_databases", {})

        parsed = json.loads(result.content[0].text)
        active = {row["name"]: row["active"] for row in parsed}
        assert active == {"db1": False, "db2": True}

    @pytest.mark.asyncio
    async def test_switch_database_success(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", "/projects/mydb")
        tk = FakeBackend("tk", ["execute_query"])
        lsp = FakeBackend("lsp", ["symbol_explore"])
        await fresh_manager.add_db_backends("mydb", tk, lsp)

        result = await ms.call_tool("switch_database", {"name": "mydb"})
        assert "mydb" in result.content[0].text
        assert "ERROR" not in result.content[0].text

    @pytest.mark.asyncio
    async def test_switch_database_not_found(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("switch_database", {"name": "no_such_db"})
        assert result.isError is True
        assert "not found" in result.content[0].text

    @pytest.mark.asyncio
    async def test_enable_anonymization(self, patch_mcp_server):
        ms = patch_mcp_server
        from gateway.anonymizer import anonymizer
        anonymizer.disable()
        result = await ms.call_tool("enable_anonymization", {})
        assert result.content[0].text
        assert anonymizer.enabled
        anonymizer.disable()  # restore

    @pytest.mark.asyncio
    async def test_disable_anonymization(self, patch_mcp_server):
        ms = patch_mcp_server
        from gateway.anonymizer import anonymizer
        anonymizer.enable()
        result = await ms.call_tool("disable_anonymization", {})
        assert result.content[0].text
        assert not anonymizer.enabled

    @pytest.mark.asyncio
    async def test_invalidate_metadata_cache(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("invalidate_metadata_cache", {})
        assert result.content[0].text

    @pytest.mark.asyncio
    async def test_query_stats_empty(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("query_stats", {})
        parsed = json.loads(result.content[0].text)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_get_bsl_syntax_help_fallback(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("get_bsl_syntax_help", {"keywords": ["Неопределено"], "limit": 5})
        payload = json.loads(result.content[0].text)
        assert payload["success"] is True
        assert payload["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_export_bsl_wait_requires_connection(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("export_bsl_sources", {"wait": True})
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_export_bsl_wait_returns_error_result(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._run_export_bsl", new=AsyncMock(return_value="ERROR: boom")):
            result = await ms.call_tool(
                "export_bsl_sources",
                {"connection": "Srvr=srv;Ref=ERP;", "wait": True},
            )
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_get_export_status_syncs_specific_connection(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._sync_export_status_from_host", new=AsyncMock()) as sync_status:
            result = await ms.call_tool("get_export_status", {"connection": "conn"})
        sync_status.assert_awaited_once_with("conn")
        payload = json.loads(result.content[0].text)
        assert payload["connection"] == "conn"

    @pytest.mark.asyncio
    async def test_export_bsl_background_requires_connection(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("export_bsl_sources", {})
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_export_bsl_background_rejects_duplicate_job(self, patch_mcp_server):
        ms = patch_mcp_server
        ms._export_jobs["conn"] = {"status": "running", "result": ""}
        result = await ms.call_tool("export_bsl_sources", {"connection": "conn"})
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_connect_database_switches_session_when_session_id_present(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms, "_get_session_id", return_value="sess-1"), \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")), \
             patch.object(ms.manager, "switch_db") as switch_db:
            result = await ms.call_tool(
                "connect_database",
                {"name": "db1", "connection": "Srvr=srv;Ref=db1;", "project_path": "/projects/db1"},
            )
        assert result.isError is False
        switch_db.assert_called_once_with("db1", session_id="sess-1")

    @pytest.mark.asyncio
    async def test_connect_database_without_session_id_does_not_switch_session(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms, "_get_session_id", return_value=None), \
             patch("gateway.mcp_server._connect_database", new=AsyncMock(return_value="ok")), \
             patch.object(ms.manager, "switch_db") as switch_db:
            result = await ms.call_tool(
                "connect_database",
                {"name": "db1", "connection": "Srvr=srv;Ref=db1;", "project_path": "/projects/db1"},
            )
        assert result.isError is False
        switch_db.assert_not_called()


# ---------------------------------------------------------------------------
# call_tool — validate_query (static, no active DB)
# ---------------------------------------------------------------------------


class TestCallToolValidateQuery:

    @pytest.mark.asyncio
    async def test_valid_query_static(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("validate_query", {"query": "ВЫБРАТЬ 1"})
        parsed = json.loads(result.content[0].text)
        assert parsed["valid"] is True
        assert parsed["source"] == "static"

    @pytest.mark.asyncio
    async def test_invalid_query_missing_select(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("validate_query", {"query": "ИЗ Справочник.Номенклатура"})
        parsed = json.loads(result.content[0].text)
        assert parsed["valid"] is False
        assert parsed["errors"]

    @pytest.mark.asyncio
    async def test_empty_query(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("validate_query", {"query": ""})
        parsed = json.loads(result.content[0].text)
        assert parsed["valid"] is False


# ---------------------------------------------------------------------------
# call_tool — bsl_index and bsl_search_tool
# ---------------------------------------------------------------------------


class TestCallToolBslSearch:

    @pytest.mark.asyncio
    async def test_bsl_index_no_active_db(self, patch_mcp_server, tmp_path):
        ms = patch_mcp_server
        result = await ms.call_tool("bsl_index", {"path": str(tmp_path)})
        assert result.content[0].text  # some output expected

    @pytest.mark.asyncio
    async def test_bsl_search_not_indexed(self, patch_mcp_server):
        ms = patch_mcp_server
        from gateway.bsl_search import bsl_search
        # Clear the symbol list to simulate unindexed state
        original_symbols = bsl_search._symbols[:]
        bsl_search._symbols.clear()
        try:
            result = await ms.call_tool("bsl_search_tool", {"query": "ПолучитьСписок"})
            text = result.content[0].text
            # When not indexed, expects a message about running bsl_index
            assert "bsl_index" in text or "Index" in text or "индекс" in text.lower()
        finally:
            bsl_search._symbols.extend(original_symbols)

    @pytest.mark.asyncio
    async def test_bsl_search_no_results(self, patch_mcp_server, tmp_path):
        ms = patch_mcp_server
        from gateway.bsl_search import bsl_search
        bsl_search.build_index(str(tmp_path))
        result = await ms.call_tool("bsl_search_tool", {"query": "НесуществующаяФункцияXYZ"})
        text = result.content[0].text
        assert "No results" in text or "не найдено" in text.lower() or "Run bsl_index" in text

    @pytest.mark.asyncio
    async def test_bsl_search_loads_snapshot_for_active_db(self, patch_mcp_server, fresh_registry, tmp_path):
        ms = patch_mcp_server
        from gateway.bsl_search import bsl_search

        module_dir = tmp_path / "CommonModules" / "ТестМодуль" / "Ext"
        module_dir.mkdir(parents=True)
        (module_dir / "Module.bsl").write_text(
            "Функция ЗаполнитьЗначенияСвойствТест() Экспорт\nКонецФункции\n",
            encoding="utf-8-sig",
        )

        fresh_registry.register("mydb", "Srvr=srv;Ref=base;", str(tmp_path))
        fresh_registry.switch("mydb")
        bsl_search.build_index(str(tmp_path))
        bsl_search._symbols.clear()

        result = await ms.call_tool("bsl_search_tool", {"query": "ЗаполнитьЗначенияСвойствТест", "limit": 1})
        assert "ЗаполнитьЗначенияСвойствТест" in result.content[0].text

    @pytest.mark.asyncio
    async def test_bsl_index_defaults_to_active_project_path_and_uses_active_lsp_container(self, patch_mcp_server):
        ms = patch_mcp_server
        active = SimpleNamespace(project_path="/hostfs-home/as/Z/ERP", lsp_container="mcp-lsp-ERP")

        with patch.object(ms, "_get_session_active", return_value=active), \
             patch("gateway.mcp_server.bsl_search.build_index", return_value="Indexed 3 symbols") as build_index:
            result = await ms.call_tool("bsl_index", {})

        assert result.isError is False
        build_index.assert_called_once_with("/hostfs-home/as/Z/ERP", container="mcp-lsp-ERP")

    @pytest.mark.asyncio
    async def test_bsl_search_returns_results(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch.object(ms, "_ensure_active_bsl_search_index_loaded", return_value=True), \
             patch("gateway.mcp_server.bsl_search.search", return_value=[{"name": "Func"}]):
            result = await ms.call_tool("bsl_search_tool", {"query": "Func"})
        assert "Func" in result.content[0].text

    @pytest.mark.asyncio
    async def test_bsl_search_returns_no_results_when_index_loaded(self, patch_mcp_server):
        ms = patch_mcp_server
        original_symbols = list(ms.bsl_search._symbols)
        ms.bsl_search._symbols = [SimpleNamespace(name="x")]
        try:
            with patch.object(ms, "_ensure_active_bsl_search_index_loaded", return_value=True), \
                 patch("gateway.mcp_server.bsl_search.search", return_value=[]):
                result = await ms.call_tool("bsl_search_tool", {"query": "missing"})
        finally:
            ms.bsl_search._symbols = original_symbols
        assert result.content[0].text == "No results found."

    @pytest.mark.asyncio
    async def test_bsl_search_requires_index_when_empty(self, patch_mcp_server):
        ms = patch_mcp_server
        original_symbols = list(ms.bsl_search._symbols)
        ms.bsl_search._symbols = []
        try:
            with patch.object(ms, "_ensure_active_bsl_search_index_loaded", return_value=False), \
                 patch("gateway.mcp_server.bsl_search.search", return_value=[]):
                result = await ms.call_tool("bsl_search_tool", {"query": "missing"})
        finally:
            ms.bsl_search._symbols = original_symbols
        assert result.isError is True


# ---------------------------------------------------------------------------
# call_tool — proxy to backend (execute_query with profiling)
# ---------------------------------------------------------------------------


class TestCallToolBackendProxy:

    @pytest.mark.asyncio
    async def test_execute_query_proxy_with_profiling(self, patch_mcp_server, fresh_manager):
        ms = patch_mcp_server
        tk = FakeBackend("tk", ["execute_query"])
        lsp = FakeBackend("lsp", ["symbol_explore"])
        await fresh_manager.add_db_backends("db1", tk, lsp)
        fresh_manager.switch_db("db1")

        response_data = json.dumps({"success": True, "data": [{"col": "val"}]})
        tk.call_tool = AsyncMock(return_value=CallToolResult(
            content=[TextContent(type="text", text=response_data)]
        ))

        result = await ms.call_tool("execute_query", {"query": "ВЫБРАТЬ 1"})
        assert len(result.content) == 1
        assert result.content[0].text

    @pytest.mark.asyncio
    async def test_execute_query_fails_fast_when_epf_not_connected(
        self, patch_mcp_server, fresh_manager, fresh_registry
    ):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")

        tk = FakeBackend("tk", ["execute_query"])
        lsp = FakeBackend("lsp", ["symbol_explore"])
        await fresh_manager.add_db_backends("db1", tk, lsp)
        fresh_manager.switch_db("db1")

        tk.call_tool = AsyncMock(return_value=CallToolResult(
            content=[TextContent(type="text", text='{"success": true, "data": []}')]
        ))

        result = await ms.call_tool("execute_query", {"query": "ВЫБРАТЬ 1"})
        assert result.isError is True
        assert "EPF for database 'db1' is not connected" in result.content[0].text
        tk.call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_execute_query_allows_proxy_when_epf_connected(
        self, patch_mcp_server, fresh_manager, fresh_registry
    ):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")
        fresh_registry.mark_epf_connected("db1")

        tk = FakeBackend("tk", ["execute_query"])
        lsp = FakeBackend("lsp", ["symbol_explore"])
        await fresh_manager.add_db_backends("db1", tk, lsp)
        fresh_manager.switch_db("db1")

        tk.call_tool = AsyncMock(return_value=CallToolResult(
            content=[TextContent(type="text", text='{"success": true, "data": []}')]
        ))

        result = await ms.call_tool("execute_query", {"query": "ВЫБРАТЬ 1"})
        assert result.isError is False
        tk.call_tool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_proxy_unknown_tool_raises(self, patch_mcp_server):
        ms = patch_mcp_server
        with pytest.raises(ValueError, match="Unknown tool"):
            await ms.call_tool("totally_unknown_tool", {})

    @pytest.mark.asyncio
    async def test_get_metadata_cached(self, patch_mcp_server):
        ms = patch_mcp_server
        from gateway.metadata_cache import metadata_cache
        metadata_cache.invalidate()

        args = {"type": "catalog", "name": "Номенклатура"}
        metadata_cache.put(args, '{"meta": "data"}')

        result = await ms.call_tool("get_metadata", args)
        assert result.content[0].text == '{"meta": "data"}'

    @pytest.mark.asyncio
    async def test_get_metadata_cache_miss_puts_response(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")
        fresh_registry.mark_epf_connected("db1")
        tk = FakeBackend("tk", ["get_metadata"])
        await fresh_manager.add_db_backends("db1", tk, None)
        fresh_manager.switch_db("db1")
        tk.call_tool = AsyncMock(return_value=CallToolResult(content=[TextContent(type="text", text='{"meta":"fresh"}')]))

        with patch("gateway.mcp_server.metadata_cache.get", return_value=None), \
             patch("gateway.mcp_server.metadata_cache.put") as put_cache:
            result = await ms.call_tool("get_metadata", {"type": "catalog", "name": "Номенклатура"})

        assert result.content[0].text == '{"meta":"fresh"}'
        put_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_anonymization_applied_to_proxy_result(self, patch_mcp_server, fresh_manager):
        ms = patch_mcp_server
        from gateway.anonymizer import anonymizer

        tk = FakeBackend("tk", ["execute_code"])
        lsp = FakeBackend("lsp", ["symbol_explore"])
        await fresh_manager.add_db_backends("db1", tk, lsp)
        fresh_manager.switch_db("db1")

        test_text = '{"success": true, "data": [{"ФИО": "Иванов Иван Иванович", "ИНН": "7707083893"}]}'
        tk.call_tool = AsyncMock(return_value=CallToolResult(
            content=[TextContent(type="text", text=test_text)]
        ))

        was_enabled = anonymizer.enabled
        anonymizer.enable()
        try:
            result = await ms.call_tool("execute_code", {"code": "Сообщить(1)"})
            assert len(result.content) == 1
            text = result.content[0].text
            assert "7707083893" not in text
            assert "Иванов" not in text
        finally:
            if was_enabled:
                anonymizer.enable()
            else:
                anonymizer.disable()

    @pytest.mark.asyncio
    async def test_execute_query_handles_non_json_backend_response(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")
        fresh_registry.mark_epf_connected("db1")
        tk = FakeBackend("tk", ["execute_query"])
        await fresh_manager.add_db_backends("db1", tk, None)
        fresh_manager.switch_db("db1")
        tk.call_tool = AsyncMock(return_value=CallToolResult(content=[TextContent(type="text", text="plain text")]))

        result = await ms.call_tool("execute_query", {"query": "ВЫБРАТЬ 1"})
        assert result.content[0].text

    @pytest.mark.asyncio
    async def test_its_search_dispatches(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._its_search", new=AsyncMock(return_value="ok")) as its_search:
            result = await ms.call_tool("its_search", {"query": "bsp"})
        its_search.assert_awaited_once_with("bsp")
        assert result.isError is False

    @pytest.mark.asyncio
    async def test_anonymization_preserves_non_text_content(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        from mcp.types import EmbeddedResource, TextResourceContents

        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")
        fresh_registry.mark_epf_connected("db1")
        tk = FakeBackend("tk", ["execute_code"])
        await fresh_manager.add_db_backends("db1", tk, None)
        fresh_manager.switch_db("db1")
        custom_content = EmbeddedResource(
            type="resource",
            resource=TextResourceContents(uri="file:///tmp/test.txt", text="payload"),
        )
        tk.call_tool = AsyncMock(return_value=CallToolResult(content=[custom_content]))

        from gateway.anonymizer import anonymizer
        was_enabled = anonymizer.enabled
        anonymizer.enable()
        try:
            result = await ms.call_tool("execute_code", {"code": "x"})
        finally:
            if was_enabled:
                anonymizer.enable()
            else:
                anonymizer.disable()

        assert result.content[0] is custom_content

    @pytest.mark.asyncio
    async def test_proxy_returns_raw_result_when_no_postprocessing_applies(self, patch_mcp_server, fresh_manager, fresh_registry):
        ms = patch_mcp_server
        fresh_registry.register("db1", "Srvr=srv;Ref=base;", "/projects/db1")
        fresh_registry.mark_epf_connected("db1")
        tk = FakeBackend("tk", ["execute_code"])
        await fresh_manager.add_db_backends("db1", tk, None)
        fresh_manager.switch_db("db1")
        raw = CallToolResult(content=[TextContent(type="text", text="ok")])
        tk.call_tool = AsyncMock(return_value=raw)

        from gateway.anonymizer import anonymizer
        was_enabled = anonymizer.enabled
        anonymizer.disable()
        try:
            result = await ms.call_tool("execute_code", {"code": "x"})
        finally:
            if was_enabled:
                anonymizer.enable()

        assert result is raw


# ---------------------------------------------------------------------------
# call_tool — reindex_bsl, graph_stats, graph_search, graph_related, write_bsl
# ---------------------------------------------------------------------------


class TestCallToolExtras:

    @pytest.mark.asyncio
    async def test_reindex_bsl_no_active_db(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("reindex_bsl", {})
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_graph_stats_service_unavailable(self, patch_mcp_server):
        ms = patch_mcp_server
        import httpx

        with patch("gateway.mcp_server._graph_request", new_callable=AsyncMock) as mock_gr:
            mock_gr.return_value = "ERROR: bsl-graph service not available"
            result = await ms.call_tool("graph_stats", {})
            assert result.isError is True

    @pytest.mark.asyncio
    async def test_graph_search_service_unavailable(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch("gateway.mcp_server._graph_request", new_callable=AsyncMock) as mock_gr:
            mock_gr.return_value = "ERROR: bsl-graph service not available"
            result = await ms.call_tool("graph_search", {"query": "Номенклатура"})
            assert result.isError is True

    @pytest.mark.asyncio
    async def test_graph_related_service_unavailable(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch("gateway.mcp_server._graph_request", new_callable=AsyncMock) as mock_gr:
            mock_gr.return_value = "ERROR: bsl-graph not available"
            result = await ms.call_tool("graph_related", {"object_id": "abc123"})
            assert result.isError is True

    @pytest.mark.asyncio
    async def test_graph_tools_success(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch("gateway.mcp_server._graph_request", new=AsyncMock(return_value='{"ok":true}')):
            for name, arguments in (
                ("graph_stats", {}),
                ("graph_search", {"query": "Номенклатура"}),
                ("graph_related", {"object_id": "id-1"}),
            ):
                result = await ms.call_tool(name, arguments)
                assert result.isError is False

    @pytest.mark.asyncio
    async def test_disconnect_database_dispatches(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._disconnect_database", new=AsyncMock(return_value="ok")) as disconnect:
            result = await ms.call_tool("disconnect_database", {"name": "db1"})
        disconnect.assert_awaited_once_with("db1")
        assert result.isError is False

    @pytest.mark.asyncio
    async def test_write_bsl_no_active_db(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms.call_tool("write_bsl", {"file": "test.bsl", "content": "// hello"})
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_write_bsl_path_traversal(self, patch_mcp_server):
        """write_bsl should reject path traversal attempts."""
        ms = patch_mcp_server
        # Simulate active DB
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.lsp_container = "test-lsp"
        with patch("gateway.mcp_server._get_session_active", return_value=mock_db):
            result = await ms.call_tool("write_bsl", {
                "file": "../../etc/passwd",
                "content": "malicious",
            })
        assert result.isError is True
        assert "Invalid file path" in result.content[0].text


# ---------------------------------------------------------------------------
# _validate_query_static — unit tests
# ---------------------------------------------------------------------------


class TestValidateQueryStatic:
    def test_valid_simple_select(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("ВЫБРАТЬ 1 КАК Число")
        assert valid is True
        assert errors == []

    def test_empty_returns_invalid(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("")
        assert valid is False
        assert errors

    def test_whitespace_only_returns_invalid(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("   \n  ")
        assert valid is False

    def test_missing_select_keyword(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("ИЗ Справочник.Номенклатура")
        assert valid is False
        assert any("ВЫБРАТЬ" in e for e in errors)

    def test_unbalanced_open_paren(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("ВЫБРАТЬ * ИЗ Таб ГДЕ (А = 1")
        assert valid is False
        assert errors

    def test_unbalanced_close_paren(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("ВЫБРАТЬ * ИЗ Таб ГДЕ А = 1)")
        assert valid is False

    def test_star_warning(self):
        from gateway.mcp_server import _validate_query_static
        valid, errors, warnings = _validate_query_static("ВЫБРАТЬ * ИЗ Справочник.Номенклатура")
        assert valid is True
        assert warnings

    def test_virtual_table_where_warning(self):
        from gateway.mcp_server import _validate_query_static
        # Pattern: .Остатки) followed by ГДЕ triggers the virtual-table warning
        query = (
            "ВЫБРАТЬ Остатки.Номенклатура "
            "ИЗ РегистрНакопления.ТоварыНаСкладах.Остатки) КАК Остатки "
            "ГДЕ Остатки.Склад = &Склад"
        )
        valid, errors, warnings = _validate_query_static(query)
        assert any("виртуальн" in w.lower() for w in warnings)

    def test_add_limit_zero_handles_queries(self):
        from gateway.mcp_server import _add_limit_zero

        assert _add_limit_zero("ВЫБРАТЬ РАЗЛИЧНЫЕ * ИЗ Таблица").startswith("ВЫБРАТЬ РАЗЛИЧНЫЕ ПЕРВЫЕ 0")
        assert _add_limit_zero("ВЫБРАТЬ ПЕРВЫЕ 10 * ИЗ Таблица").startswith("ВЫБРАТЬ ПЕРВЫЕ 0")
        assert _add_limit_zero("ИЗ Таблица") == "ИЗ Таблица"


class TestWrapperFunctions:
    @pytest.mark.asyncio
    async def test_graph_request_wrapper(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._graph_request_impl", new=AsyncMock(return_value="ok")) as impl, \
             patch.object(ms.settings, "bsl_graph_url", "http://localhost:8888"):
            result = await ms._graph_request("GET", "/api/graph/stats")
        assert result == "ok"
        impl.assert_awaited_once_with("http://localhost:8888", "GET", "/api/graph/stats", body=None, params=None)

    @pytest.mark.asyncio
    async def test_its_search_wrapper(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._its_search_impl", new=AsyncMock(return_value="ok")) as impl, \
             patch.object(ms.settings, "naparnik_api_key", "token"):
            result = await ms._its_search("query")
        assert result == "ok"
        impl.assert_awaited_once_with("query", "token")

    @pytest.mark.asyncio
    async def test_connect_database_wrapper_normalizes_home_path(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._connect_database_impl", new=AsyncMock(return_value="ok")) as impl:
            result = await ms._connect_database("db1", "Srvr=srv;Ref=db1;", "/home/as/Z/db1")
        assert result == "ok"
        assert impl.await_args.kwargs["project_path"] == "/hostfs-home/as/Z/db1"

    @pytest.mark.asyncio
    async def test_disconnect_database_wrapper(self, patch_mcp_server):
        ms = patch_mcp_server
        with patch("gateway.mcp_server._disconnect_database_impl", new=AsyncMock(return_value="ok")) as impl:
            result = await ms._disconnect_database("db1")
        assert result == "ok"
        assert impl.await_count == 1

    def test_disconnected_helper_functions_via_reload(self):
        import importlib
        import gateway.mcp_server as raw_ms
        reloaded = importlib.reload(raw_ms)
        try:
            reloaded.manager = None
            reloaded.registry = None
            assert reloaded._get_session_active() is None

            from mcp.server.lowlevel.server import request_ctx
            token = request_ctx.set(SimpleNamespace(request=SimpleNamespace(headers={"mcp-session-id": "sess-x"})))
            try:
                assert reloaded._get_session_id() == "sess-x"
            finally:
                request_ctx.reset(token)
        finally:
            importlib.reload(raw_ms)


# ---------------------------------------------------------------------------
# _add_limit_zero — unit tests
# ---------------------------------------------------------------------------


class TestAddLimitZero:
    def test_simple_insert(self):
        from gateway.mcp_server import _add_limit_zero
        result = _add_limit_zero("ВЫБРАТЬ Поле ИЗ Таблица")
        assert "ПЕРВЫЕ 0" in result

    def test_replaces_existing_top(self):
        from gateway.mcp_server import _add_limit_zero
        result = _add_limit_zero("ВЫБРАТЬ ПЕРВЫЕ 100 Поле ИЗ Таблица")
        assert "ПЕРВЫЕ 0" in result
        assert "ПЕРВЫЕ 100" not in result

    def test_distinct_preserved(self):
        from gateway.mcp_server import _add_limit_zero
        result = _add_limit_zero("ВЫБРАТЬ РАЗЛИЧНЫЕ ПЕРВЫЕ 50 Поле ИЗ Таблица")
        assert "РАЗЛИЧНЫЕ" in result
        assert "ПЕРВЫЕ 0" in result

    def test_no_select_returns_unchanged(self):
        from gateway.mcp_server import _add_limit_zero
        original = "ИЗ Справочник.Номенклатура"
        result = _add_limit_zero(original)
        assert result == original


# ---------------------------------------------------------------------------
# connect_database — invalid name validation
# ---------------------------------------------------------------------------


class TestConnectDatabase:
    @pytest.mark.asyncio
    async def test_invalid_db_name(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms._connect_database("", "Srvr=srv;", "/projects")
        assert result.startswith("ERROR")

    @pytest.mark.asyncio
    async def test_invalid_db_name_whitespace_only(self, patch_mcp_server):
        ms = patch_mcp_server
        result = await ms._connect_database("   ", "Srvr=srv;", "/projects")
        assert result.startswith("ERROR")

    def test_valid_name_format(self):
        import re
        pattern = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")
        assert pattern.match("ERP")
        assert pattern.match("ZUP_TEST")
        assert pattern.match("buh-main")
        assert not pattern.match("invalid name!")
        assert not pattern.match("-starts-dash")
        assert not pattern.match("")


# ---------------------------------------------------------------------------
# disconnect_database — registry lookup
# ---------------------------------------------------------------------------


class TestDisconnectDatabase:
    @pytest.mark.asyncio
    async def test_disconnect_unknown_db(self, patch_mcp_server):
        ms = patch_mcp_server
        # Mock docker module so docker_manager can be imported
        import sys
        fake_docker = MagicMock()
        with patch.dict(sys.modules, {"docker": fake_docker}):
            result = await ms._disconnect_database("ghost_db")
        assert "ERROR" in result
        assert "ghost_db" in result


# ---------------------------------------------------------------------------
# _graph_request — successful response
# ---------------------------------------------------------------------------


class TestGraphRequest:
    @pytest.mark.asyncio
    async def test_graph_request_success_json(self, patch_mcp_server):
        ms = patch_mcp_server
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"nodes": 42})
        mock_response.text = '{"nodes": 42}'

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await ms._graph_request("GET", "/api/graph/stats")
            parsed = json.loads(result)
            assert parsed["nodes"] == 42

    @pytest.mark.asyncio
    async def test_graph_request_post(self, patch_mcp_server):
        ms = patch_mcp_server
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = MagicMock(return_value={"results": []})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await ms._graph_request("POST", "/api/graph/search", {"query": "test"})
            parsed = json.loads(result)
            assert "results" in parsed

    @pytest.mark.asyncio
    async def test_graph_request_connect_error(self, patch_mcp_server):
        ms = patch_mcp_server
        import httpx

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value = mock_client

            result = await ms._graph_request("GET", "/api/graph/stats")
            assert "ERROR" in result


# ---------------------------------------------------------------------------
# ITS search
# ---------------------------------------------------------------------------


class TestItsSearch:
    @pytest.mark.asyncio
    async def test_its_search_no_api_key(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "naparnik_api_key", "")
        result = await ms._its_search("как настроить БСП?")
        assert "NAPARNIK_API_KEY" in result

    @pytest.mark.asyncio
    async def test_its_search_with_api_key(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "naparnik_api_key", "test-key-123")

        with patch("gateway.tool_handlers.its.NaparnikClient") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.search = AsyncMock(return_value="Результат поиска")
            mock_cls.return_value = mock_instance

            result = await ms._its_search("как создать справочник?")
            assert result == "Результат поиска"
            mock_cls.assert_called_once_with("test-key-123")


# ---------------------------------------------------------------------------
# export_bsl_sources
# ---------------------------------------------------------------------------


class TestExportBsl:
    @pytest.mark.asyncio
    async def test_export_tool_starts_background_job_by_default(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch.object(ms, "_run_export_bsl", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = "Выгрузка завершена: 10 BSL файлов."
            result = await ms.call_tool(
                "export_bsl_sources",
                {"connection": "Srvr=srv;Ref=base;", "output_dir": "/home/as/Z/base"},
            )
            await asyncio.sleep(0)

        assert result.isError is False
        assert "background" in result.content[0].text
        mock_export.assert_awaited_once_with("Srvr=srv;Ref=base;", "/home/as/Z/base")
        status = json.loads((await ms.call_tool("get_export_status", {"connection": "Srvr=srv;Ref=base;"})).content[0].text)
        assert status["status"] == "done"

    @pytest.mark.asyncio
    async def test_export_tool_wait_mode_runs_inline(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch.object(ms, "_run_export_bsl", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = "Выгрузка завершена: 10 BSL файлов."
            result = await ms.call_tool(
                "export_bsl_sources",
                {"connection": "Srvr=srv;Ref=base;", "output_dir": "/home/as/Z/base", "wait": True},
            )

        assert result.isError is False
        assert "Выгрузка завершена" in result.content[0].text
        mock_export.assert_awaited_once_with("Srvr=srv;Ref=base;", "/home/as/Z/base")

    @pytest.mark.asyncio
    async def test_get_export_status_returns_all_jobs(self, patch_mcp_server):
        ms = patch_mcp_server
        ms._export_jobs["conn-1"] = {"status": "running", "result": ""}
        ms._index_jobs["conn-1"] = {"status": "done", "result": "100 символов"}

        result = await ms.call_tool("get_export_status", {})
        payload = json.loads(result.content[0].text)

        assert payload["jobs"]["conn-1"]["status"] == "running"
        assert payload["jobs"]["conn-1"]["index_status"] == "done"

    @pytest.mark.asyncio
    async def test_get_export_status_syncs_running_job_from_host(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config

        monkeypatch.setattr(config.settings, "export_host_url", "http://host:8082")
        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"status": "running", "result": ""})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await ms.call_tool("get_export_status", {"connection": "Srvr=srv;Ref=base;"})

        payload = json.loads(result.content[0].text)
        assert payload["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_export_status_syncs_done_job_and_indexes_without_placeholder(
        self, patch_mcp_server, monkeypatch, fresh_registry
    ):
        ms = patch_mcp_server
        from gateway import config

        fresh_registry.register("base", "Srvr=srv;Ref=base;", "/workspace/base")
        fresh_registry.switch("base")
        monkeypatch.setattr(config.settings, "export_host_url", "http://host:8082")
        monkeypatch.setattr(config.settings, "bsl_host_workspace", "/home/as/Z")

        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 3 BSL files in /home/as/Z/base"}
        )

        with patch("httpx.AsyncClient") as mock_client_cls, patch.object(
            ms, "_get_session_active", return_value=SimpleNamespace(lsp_container="mcp-lsp-base")
        ), patch.object(
            ms.bsl_search,
            "build_index",
            side_effect=lambda path, container="": "Indexed 55 symbols"
            if path == "/hostfs-home/as/Z/base"
            else "ERROR: stale mount",
        ):
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await ms.call_tool("get_export_status", {"connection": "Srvr=srv;Ref=base;"})

        payload = json.loads(result.content[0].text)
        assert payload["status"] == "done"
        assert payload["index_status"] == "done"
        assert payload["index_result"] == "55 символов"

    @pytest.mark.asyncio
    async def test_export_tool_resolves_default_projects_to_host_workspace(
        self, patch_mcp_server, fresh_registry, monkeypatch
    ):
        ms = patch_mcp_server
        from gateway import config

        fresh_registry.register("base", "Srvr=srv;Ref=base;", "/projects/base")
        monkeypatch.setattr(config.settings, "bsl_host_workspace", "/home/test/bsl")
        monkeypatch.setattr(config.settings, "bsl_workspace", "/workspace")

        with patch.object(ms, "_run_export_bsl", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = "Export OK"
            result = await ms.call_tool(
                "export_bsl_sources",
                {"connection": "Srvr=srv;Ref=base;", "output_dir": "/projects", "wait": True},
            )

        assert result.isError is False
        mock_export.assert_awaited_once_with("Srvr=srv;Ref=base;", "/home/test/bsl/base")

    @pytest.mark.asyncio
    async def test_export_tool_keeps_explicit_host_path(self, patch_mcp_server):
        ms = patch_mcp_server

        with patch.object(ms, "_run_export_bsl", new_callable=AsyncMock) as mock_export:
            mock_export.return_value = "Export OK"
            await ms.call_tool(
                "export_bsl_sources",
                {"connection": "Srvr=srv;Ref=base;", "output_dir": "/home/as/Z/custom", "wait": True},
            )

        mock_export.assert_awaited_once_with("Srvr=srv;Ref=base;", "/home/as/Z/custom")

    @pytest.mark.asyncio
    async def test_export_via_host_url(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "export_host_url", "http://host:8082")
        monkeypatch.setattr(config.settings, "bsl_workspace", "/projects")
        monkeypatch.setattr(config.settings, "bsl_host_workspace", "")

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"result": "Export OK"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = await ms._run_export_bsl("Srvr=srv;Ref=base;", "/workspace/test")
            assert "Export OK" in result

    @pytest.mark.asyncio
    async def test_run_export_bsl_refresh_lsp_helper_skips_empty_slug_and_analyzes_success(self, patch_mcp_server):
        ms = patch_mcp_server

        async def fake_impl(**kwargs):
            await kwargs["refresh_lsp_fn"]("", "/workspace/Z01")
            return "Export OK"

        with patch.object(ms, "_run_export_bsl_impl", new=AsyncMock(side_effect=fake_impl)) as impl, patch.object(
            ms, "_auto_analyze_reports_for_db", new=AsyncMock()
        ) as analyze, patch("gateway.docker_manager.start_lsp") as start_lsp:
            result = await ms._run_export_bsl("Srvr=srv;Ref=Z01;", "/workspace/Z01")

        assert result == "Export OK"
        assert impl.await_count == 1
        start_lsp.assert_not_called()
        analyze.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_export_bsl_refresh_lsp_helper_restarts_lsp_for_slug(self, patch_mcp_server):
        ms = patch_mcp_server

        async def fake_impl(**kwargs):
            await kwargs["refresh_lsp_fn"]("Z01", "/workspace/Z01")
            return "ERROR: export failed"

        with patch.object(ms, "_run_export_bsl_impl", new=AsyncMock(side_effect=fake_impl)), patch(
            "gateway.docker_manager.start_lsp", return_value="mcp-lsp-Z01"
        ) as start_lsp, patch.object(ms, "_auto_analyze_reports_for_db", new=AsyncMock()) as analyze:
            result = await ms._run_export_bsl("Srvr=srv;Ref=Z01;", "/workspace/Z01")

        assert result == "ERROR: export failed"
        start_lsp.assert_called_once_with("Z01", "/workspace/Z01")
        analyze.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_export_no_1cv8_no_host(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "export_host_url", "")
        monkeypatch.setattr(config.settings, "allow_container_designer_export", False)

        result = await ms._run_export_bsl("Srvr=srv;Ref=base;", "/workspace/test")
        assert "ERROR" in result
        assert "ALLOW_CONTAINER_DESIGNER_EXPORT" in result

    @pytest.mark.asyncio
    async def test_export_no_1cv8_no_host_opt_in_container_export(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "export_host_url", "")
        monkeypatch.setattr(config.settings, "allow_container_designer_export", True)
        # Mock _find_1cv8_binaries to return empty dict (no binaries)
        monkeypatch.setattr(ms, "_find_1cv8_binaries", lambda: {})

        result = await ms._run_export_bsl("Srvr=srv;Ref=base;", "/workspace/test")
        assert "No 1cv8" in result

    @pytest.mark.asyncio
    async def test_export_via_host_url_error(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "export_host_url", "http://host:8082")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
            mock_client_cls.return_value = mock_client

            result = await ms._run_export_bsl("Srvr=srv;Ref=base;", "/workspace/test")
            assert "ERROR" in result

    @pytest.mark.asyncio
    async def test_export_no_workspace_configured(self, patch_mcp_server, monkeypatch):
        ms = patch_mcp_server
        from gateway import config
        monkeypatch.setattr(config.settings, "export_host_url", "")
        result = await ms._run_export_bsl("Srvr=srv;Ref=base;", "/projects")
        assert "ERROR" in result
        assert "dashboard" in result

"""Low-level tests for gateway.mcp_server helpers without file-local autouse patches."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gateway.mcp_server as ms
from gateway.backends.manager import BackendManager
from gateway.db_registry import DatabaseRegistry


@pytest.fixture()
def fresh_state(tmp_path):
    original_manager = ms.manager
    original_registry = ms.registry
    original_export_jobs = dict(ms._export_jobs)
    original_export_tasks = dict(ms._export_tasks)
    original_index_jobs = dict(ms._index_jobs)

    manager = BackendManager()
    registry = DatabaseRegistry(state_file=tmp_path / "db_state.json")
    ms.manager = manager
    ms.registry = registry
    ms._export_jobs.clear()
    ms._export_tasks.clear()
    ms._index_jobs.clear()
    try:
        yield manager, registry
    finally:
        for task in list(ms._export_tasks.values()):
            task.cancel()
        ms.manager = original_manager
        ms.registry = original_registry
        ms._export_jobs.clear()
        ms._export_jobs.update(original_export_jobs)
        ms._export_tasks.clear()
        ms._export_tasks.update(original_export_tasks)
        ms._index_jobs.clear()
        ms._index_jobs.update(original_index_jobs)


def test_get_session_active_returns_session_db(fresh_state):
    manager, registry = fresh_state
    registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
    manager._db_backends["db1"] = {}
    manager.switch_db("db1", session_id="sess-1")

    with patch.object(ms, "_get_session_id", return_value="sess-1"):
        active = ms._get_session_active()

    assert active.name == "db1"


def test_get_session_active_returns_none_when_registry_lookup_misses(fresh_state):
    manager, _registry = fresh_state
    manager._db_backends["db1"] = {}
    manager.switch_db("db1", session_id="sess-1")

    with patch.object(ms, "_get_session_id", return_value="sess-1"):
        assert ms._get_session_active() is None


def test_get_session_active_falls_back_to_registry_active_in_real_helper(fresh_state):
    manager, registry = fresh_state
    registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
    registry.switch("db1")

    with patch.object(ms, "_get_session_id", return_value="sess-1"):
        assert manager.get_active_db("sess-1") is None
        active = ms._get_session_active()

    assert active.name == "db1"


def test_get_connection_active_prefers_ref_lookup(fresh_state):
    _manager, registry = fresh_state
    registry.register("Z01", "Srvr=srv;Ref=Z01;", "/projects/Z01")

    active = ms._get_connection_active("Srvr=srv;Ref=Z01;Usr=u;")

    assert active.name == "Z01"


def test_get_connection_active_falls_back_to_registry_active(fresh_state):
    _manager, registry = fresh_state
    registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
    registry.switch("db1")

    active = ms._get_connection_active("Srvr=srv;")

    assert active.name == "db1"


def test_get_connection_active_falls_back_when_ref_lookup_misses(fresh_state):
    _manager, registry = fresh_state
    registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
    registry.switch("db1")

    active = ms._get_connection_active("Srvr=srv;Ref=missing;")

    assert active.name == "db1"


def test_get_connection_active_returns_none_without_registry():
    original_registry = ms.registry
    ms.registry = None
    try:
        assert ms._get_connection_active("Srvr=srv;Ref=db1;") is None
    finally:
        ms.registry = original_registry


def test_get_session_id_reads_header_and_handles_lookup_error():
    request_ctx = SimpleNamespace(get=lambda: SimpleNamespace(request=SimpleNamespace(headers={"mcp-session-id": "sess-x"})))
    with patch("mcp.server.lowlevel.server.request_ctx", request_ctx):
        assert ms._get_session_id() == "sess-x"

    failing_ctx = SimpleNamespace(get=lambda: (_ for _ in ()).throw(LookupError()))
    with patch("mcp.server.lowlevel.server.request_ctx", failing_ctx):
        assert ms._get_session_id() is None


def test_get_session_id_returns_none_when_request_missing():
    request_ctx = SimpleNamespace(get=lambda: SimpleNamespace(request=None))
    with patch("mcp.server.lowlevel.server.request_ctx", request_ctx):
        assert ms._get_session_id() is None


def test_resolve_export_output_dir_without_ref_uses_host_root(fresh_state):
    _manager, _registry = fresh_state
    with patch.object(ms.settings, "bsl_host_workspace", "/home/as/Z"), \
         patch.object(ms.settings, "bsl_workspace", "/workspace"):
        assert ms._resolve_export_output_dir("Srvr=srv;", "/projects") == "/home/as/Z"


def test_ensure_active_bsl_search_index_loaded_returns_indexed_without_project(fresh_state):
    _manager, _registry = fresh_state
    original_symbols = list(ms.bsl_search._symbols)
    ms.bsl_search._symbols = [SimpleNamespace(name="Symbol")]
    try:
        with patch.object(ms, "_get_session_active", return_value=SimpleNamespace(project_path="", lsp_container="")):
            assert ms._ensure_active_bsl_search_index_loaded() is True
    finally:
        ms.bsl_search._symbols = original_symbols


def test_search_syntax_reference_omits_content_for_ambiguous_matches():
    syntax_text = "# Alpha\nalpha\n# Beta\nbeta\n"
    with patch.object(ms, "_SYNTAX_RESOURCE_PATH", SimpleNamespace(read_text=lambda encoding="utf-8": syntax_text)):
        result = json.loads(ms._search_syntax_reference(["alpha", "beta"]))

    assert result["success"] is True
    assert result["data"]["total"] == 2
    assert result["data"]["content"] is None


def test_search_syntax_reference_keeps_empty_sections_out_of_candidates():
    syntax_text = "# Empty\n# Filled\nkeyword here\n"
    with patch.object(ms, "_SYNTAX_RESOURCE_PATH", SimpleNamespace(read_text=lambda encoding="utf-8": syntax_text)):
        result = json.loads(ms._search_syntax_reference(["keyword"]))

    assert result["data"]["total"] == 1
    assert result["data"]["candidates"][0]["title"] == "Filled"


@pytest.mark.asyncio
async def test_sync_export_status_records_index_error_result(fresh_state):
    _manager, _registry = fresh_state
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


@pytest.mark.asyncio
async def test_export_background_task_records_exception(fresh_state):
    _manager, _registry = fresh_state
    with patch("gateway.mcp_server._run_export_bsl", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await ms.call_tool("export_bsl_sources", {"connection": "conn", "output_dir": "/tmp/out"})
        assert result.isError is False
        task = ms._export_tasks["conn"]
        await task

    assert ms._export_jobs["conn"]["status"] == "error"
    assert ms._export_jobs["conn"]["result"] == "boom"


@pytest.mark.asyncio
async def test_export_background_task_records_cancelled_status(fresh_state):
    _manager, _registry = fresh_state

    async def slow_export(_connection: str, _output_dir: str) -> str:
        await asyncio.sleep(60)
        return "done"

    with patch("gateway.mcp_server._run_export_bsl", new=slow_export):
        result = await ms.call_tool("export_bsl_sources", {"connection": "conn", "output_dir": "/tmp/out"})
        assert result.isError is False
        task = ms._export_tasks["conn"]
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert ms._export_jobs["conn"]["status"] == "cancelled"

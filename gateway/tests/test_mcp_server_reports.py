from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway import server as _server_mod  # noqa: F401
import gateway.mcp_server as _ms
from gateway.db_registry import DatabaseRegistry


@pytest.fixture()
def isolated_registry(tmp_path):
    original = _ms.registry
    registry = DatabaseRegistry(state_file=tmp_path / "state.json")
    _ms.registry = registry
    try:
        yield registry
    finally:
        _ms.registry = original


@pytest.mark.asyncio
async def test_report_tools_are_registered_in_mcp_tool_list():
    tools = await _ms.list_tools()
    names = {tool.name for tool in tools}

    assert {
        "analyze_reports",
        "enrich_report_docs",
        "find_reports",
        "list_reports",
        "describe_report",
        "run_report",
        "get_report_result",
        "explain_report_strategy",
    }.issubset(names)


@pytest.mark.asyncio
async def test_mcp_call_tool_delegates_report_tool_and_preserves_error_shape():
    with patch("gateway.mcp_server.try_handle_report_tool", new=AsyncMock(return_value='{"ok":false,"error_code":"report_not_found"}')):
        result = await _ms.call_tool("find_reports", {"database": "Z01", "query": "Расчетка"})

    payload = json.loads(result.content[0].text)
    assert result.isError is False
    assert payload["error_code"] == "report_not_found"


@pytest.mark.asyncio
async def test_run_export_bsl_refreshes_report_catalog_after_success(tmp_path, isolated_registry):
    isolated_registry.register("Z01", "Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"), slug="Z01")

    with patch("gateway.mcp_server._run_export_bsl_impl", new=AsyncMock(return_value="Выгрузка завершена")) as export_impl, \
         patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock(return_value={"ok": True, "reports": 1})) as rebuild:
        result = await _ms._run_export_bsl("Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"))

    assert result == "Выгрузка завершена"
    export_impl.assert_awaited_once()
    rebuild.assert_awaited_once()
    assert rebuild.await_args.args[0] == "Z01"


@pytest.mark.asyncio
async def test_connect_database_refreshes_report_catalog_after_success(tmp_path, isolated_registry):
    project = tmp_path / "Z01"

    async def fake_connect_database_impl(**kwargs):
        kwargs["registry"].register(
            kwargs["name"],
            kwargs["connection"],
            kwargs["project_path"],
            slug=kwargs["name"],
        )
        return "Database 'Z01' connected successfully."

    with patch("gateway.mcp_server._connect_database_impl", new=AsyncMock(side_effect=fake_connect_database_impl)) as connect_impl, \
         patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock(return_value={"ok": True, "reports": 1})) as rebuild:
        result = await _ms._connect_database("Z01", "Srvr=localhost;Ref=Z01;", str(project))

    assert result == "Database 'Z01' connected successfully."
    connect_impl.assert_awaited_once()
    rebuild.assert_awaited_once()
    assert rebuild.await_args.args[0] == "Z01"


@pytest.mark.asyncio
async def test_connect_database_skips_report_catalog_after_error(tmp_path):
    with patch("gateway.mcp_server._connect_database_impl", new=AsyncMock(return_value="ERROR: failed")), \
         patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock()) as rebuild:
        result = await _ms._connect_database("Z01", "Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"))

    assert result == "ERROR: failed"
    rebuild.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_export_bsl_skips_report_catalog_after_export_error(tmp_path, isolated_registry):
    isolated_registry.register("Z01", "Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"), slug="Z01")

    with patch("gateway.mcp_server._run_export_bsl_impl", new=AsyncMock(return_value="ERROR: failed")), \
         patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock()) as rebuild:
        result = await _ms._run_export_bsl("Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"))

    assert result == "ERROR: failed"
    rebuild.assert_not_awaited()


@pytest.mark.asyncio
async def test_reindex_bsl_refreshes_report_catalog_after_success(tmp_path, isolated_registry):
    isolated_registry.register("Z01", "Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"), slug="Z01")
    isolated_registry.switch("Z01")

    with patch("gateway.mcp_server._reindex_bsl_impl", new=AsyncMock(return_value="Indexed 1 symbols")) as reindex_impl, \
         patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock(return_value={"ok": True, "reports": 1})) as rebuild:
        result = await _ms._reindex_bsl("")

    assert result == "Indexed 1 symbols"
    reindex_impl.assert_awaited_once()
    rebuild.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_analyze_reports_is_best_effort(tmp_path):
    db = SimpleNamespace(name="Z01", project_path=str(tmp_path / "Z01"))

    with patch("gateway.mcp_server.rebuild_report_catalog_for_db_info", new=AsyncMock(side_effect=RuntimeError("boom"))) as rebuild:
        await _ms._auto_analyze_reports_for_db(db, "test")

    rebuild.assert_awaited_once()

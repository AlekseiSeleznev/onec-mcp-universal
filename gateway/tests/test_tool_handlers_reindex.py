"""Tests for gateway.tool_handlers.reindex."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.reindex import reindex_bsl


class TestReindexBslHandler:
    @pytest.mark.asyncio
    async def test_no_active_db(self):
        result = await reindex_bsl(
            path="",
            get_active=lambda: None,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            build_search_index=lambda path, container: "Indexed 1 symbols",
        )
        assert "ERROR: No active database" in result

    @pytest.mark.asyncio
    async def test_lsp_tool_unavailable(self):
        active = SimpleNamespace(name="ERP", project_path="/workspace/ERP", lsp_container="")
        result = await reindex_bsl(
            path="",
            get_active=lambda: active,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            build_search_index=lambda path, container: f"Indexed 1 symbols in {path}",
        )
        assert "Indexed 1 symbols in /workspace/ERP" in result
        assert "full-text index rebuilt only" in result

    @pytest.mark.asyncio
    async def test_success_with_custom_path(self):
        active = SimpleNamespace(name="ERP", project_path="/workspace/ERP", lsp_container="")
        call_tool = AsyncMock(
            return_value=SimpleNamespace(content=[SimpleNamespace(text="ok")])
        )

        result = await reindex_bsl(
            path=" /workspace/ERP ",
            get_active=lambda: active,
            has_tool=lambda name: name == "did_change_watched_files",
            call_tool=call_tool,
            build_search_index=lambda path, container: f"Indexed 5 symbols in {path}",
        )

        assert "Indexed 5 symbols in /workspace/ERP" in result
        assert "Re-indexing triggered for 'ERP' at /workspace/ERP." in result
        assert "ok" in result
        call_tool.assert_awaited_once_with(
            "did_change_watched_files",
            {"language": "bsl", "changes_json": "[]"},
        )

    @pytest.mark.asyncio
    async def test_call_tool_exception(self):
        active = SimpleNamespace(name="ERP", project_path="/workspace/ERP", lsp_container="")
        call_tool = AsyncMock(side_effect=RuntimeError("boom"))

        result = await reindex_bsl(
            path="",
            get_active=lambda: active,
            has_tool=lambda name: name == "did_change_watched_files",
            call_tool=call_tool,
            build_search_index=lambda path, container: f"Indexed 2 symbols in {path}",
        )

        assert "Indexed 2 symbols in /workspace/ERP" in result
        assert "ERROR triggering LSP re-index: boom" in result

    @pytest.mark.asyncio
    async def test_search_index_error_is_returned_immediately(self):
        active = SimpleNamespace(name="ERP", project_path="/workspace/ERP", lsp_container="lsp")

        result = await reindex_bsl(
            path="",
            get_active=lambda: active,
            has_tool=lambda _: True,
            call_tool=AsyncMock(),
            build_search_index=lambda path, container: "ERROR: no symbols",
        )

        assert result == "ERROR: no symbols"

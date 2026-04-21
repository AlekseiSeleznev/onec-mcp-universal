"""Tests for gateway.tool_handlers.write_bsl."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.write_bsl import write_bsl


class TestWriteBslHandler:
    @pytest.mark.asyncio
    async def test_no_active_db(self):
        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="",
            get_active=lambda: None,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            write_via_runtime=None,
        )
        assert "ERROR: No active database" in result

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self):
        active = SimpleNamespace(lsp_container="lsp-test", project_path="/tmp/project")
        result = await write_bsl(
            file="../../etc/passwd",
            content="malicious",
            get_active=lambda: active,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            write_via_runtime=None,
        )
        assert "ERROR: Invalid file path" in result

    @pytest.mark.asyncio
    async def test_mkdir_error_propagates(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))

        with patch("pathlib.Path.mkdir", side_effect=OSError("mkdir failed")):
            result = await write_bsl(
                file="CommonModules/Test/Ext/Module.bsl",
                content="x",
                get_active=lambda: active,
                has_tool=lambda _: False,
                call_tool=AsyncMock(),
                write_via_runtime=None,
            )

        assert result == "ERROR writing file: mkdir failed"

    @pytest.mark.asyncio
    async def test_no_lsp_container(self):
        active = SimpleNamespace(lsp_container="", project_path="/tmp/project")
        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="x",
            get_active=lambda: active,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            write_via_runtime=None,
        )
        assert "ERROR: No LSP container" in result

    @pytest.mark.asyncio
    async def test_no_project_path(self):
        active = SimpleNamespace(lsp_container="lsp-test", project_path="")
        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="x",
            get_active=lambda: active,
            has_tool=lambda _: False,
            call_tool=AsyncMock(),
            write_via_runtime=None,
        )

        assert result == "ERROR: No project path for active database."

    @pytest.mark.asyncio
    async def test_write_error_propagates(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))

        with patch("pathlib.Path.write_text", side_effect=OSError("tee failed")):
            result = await write_bsl(
                file="CommonModules/Test/Ext/Module.bsl",
                content="x",
                get_active=lambda: active,
                has_tool=lambda _: False,
                call_tool=AsyncMock(),
                write_via_runtime=None,
            )

        assert "ERROR writing file: tee failed" in result

    @pytest.mark.asyncio
    async def test_success_triggers_reindex_when_tool_available(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))
        call_tool = AsyncMock()

        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="// hello",
            get_active=lambda: active,
            has_tool=lambda name: name == "did_change_watched_files",
            call_tool=call_tool,
            write_via_runtime=None,
        )

        assert "Written" in result
        assert str(tmp_path / "CommonModules" / "Test" / "Ext" / "Module.bsl") in result
        assert (tmp_path / "CommonModules" / "Test" / "Ext" / "Module.bsl").read_text(encoding="utf-8-sig") == "// hello"
        call_tool.assert_awaited_once_with(
            "did_change_watched_files",
            {"language": "bsl", "changes_json": "[]"},
        )

    @pytest.mark.asyncio
    async def test_success_ignores_reindex_error(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))
        call_tool = AsyncMock(side_effect=RuntimeError("boom"))

        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="// hello",
            get_active=lambda: active,
            has_tool=lambda name: name == "did_change_watched_files",
            call_tool=call_tool,
            write_via_runtime=None,
        )

        assert "Written" in result

    @pytest.mark.asyncio
    async def test_success_without_reindex_tool_still_writes_file(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))
        call_tool = AsyncMock()

        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="// hello",
            get_active=lambda: active,
            has_tool=lambda name: False,
            call_tool=call_tool,
            write_via_runtime=None,
        )

        assert "Written" in result
        call_tool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generic_exception_is_returned(self, tmp_path):
        active = SimpleNamespace(lsp_container="lsp-test", project_path=str(tmp_path))

        with patch("pathlib.Path.write_text", side_effect=RuntimeError("spawn failed")):
            result = await write_bsl(
                file="CommonModules/Test/Ext/Module.bsl",
                content="x",
                get_active=lambda: active,
                has_tool=lambda _: False,
                call_tool=AsyncMock(),
                write_via_runtime=None,
            )

        assert result == "ERROR writing file: spawn failed"

    @pytest.mark.asyncio
    async def test_managed_workspace_uses_runtime_writer(self):
        active = SimpleNamespace(lsp_container="mcp-lsp-z01", project_path="/hostfs-home/as/Z/Z01")
        call_tool = AsyncMock()
        runtime_writer = Mock(return_value="/projects/CommonModules/Test/Ext/Module.bsl")

        result = await write_bsl(
            file="CommonModules/Test/Ext/Module.bsl",
            content="// hello",
            get_active=lambda: active,
            has_tool=lambda name: name == "did_change_watched_files",
            call_tool=call_tool,
            write_via_runtime=runtime_writer,
        )

        assert "Written" in result
        runtime_writer.assert_called_once_with("mcp-lsp-z01", "CommonModules/Test/Ext/Module.bsl", "// hello")
        call_tool.assert_awaited_once_with(
            "did_change_watched_files",
            {"language": "bsl", "changes_json": "[]"},
        )

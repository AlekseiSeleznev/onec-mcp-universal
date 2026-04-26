"""Tests for the docker-control-backed LSP backend."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import CallToolResult, TextContent, Tool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.backends.docker_control_lsp_backend import (
    DockerControlLspBackend,
    _apply_rename_preview_to_text,
    _parse_rename_preview,
)


class _Response:
    def __init__(self, payload: dict, exc: Exception | None = None):
        self._payload = payload
        self._exc = exc

    def raise_for_status(self):
        if self._exc is not None:
            raise self._exc

    def json(self):
        return self._payload


class _AsyncClientContext:
    def __init__(self, response: _Response | None = None, exc: Exception | None = None):
        self._response = response
        self._exc = exc
        self.calls: list[tuple[str, dict, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, json: dict, headers: dict | None = None):
        self.calls.append((url, json, headers or {}))
        if self._exc is not None:
            raise self._exc
        return self._response


def _result(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _tool_payload(name: str) -> dict:
    return {"name": name, "description": name, "inputSchema": {"type": "object"}}


RENAME_PREVIEW = (
    "File: RenameProbe_Z01.bsl (2 edits)\n"
    "   URI: file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl\n"
    "   1. Line 5 (chars 12-31): Replace with \"ЛокПереим\"\n"
    "   2. Line 4 (chars 4-23): Replace with \"ЛокПереим\"\n"
    "Files to be modified: 1\n"
    "Total edits: 2\n\n"
    "To apply these changes, use: rename with apply='true'"
)


@pytest.mark.asyncio
async def test_start_populates_tools_and_marks_backend_available():
    client = _AsyncClientContext(_Response({"ok": True, "tools": [_tool_payload("symbol_explore")]}))

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client), \
         patch("gateway.backends.docker_control_lsp_backend.settings") as settings:
        settings.docker_control_url = "http://docker-control"
        settings.docker_control_token = "secret-token"
        backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
        await backend.start()

    assert backend.available is True
    assert [tool.name for tool in backend.tools] == ["symbol_explore"]
    assert client.calls == [
        (
            "http://docker-control/api/lsp-proxy/start",
            {"slug": "erp"},
            {"Authorization": "Bearer secret-token"},
        ),
    ]


@pytest.mark.asyncio
async def test_start_raises_when_sidecar_reports_error():
    client = _AsyncClientContext(_Response({"ok": False, "error": "boom"}))

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client):
        backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
        with pytest.raises(RuntimeError, match="boom"):
            await backend.start()


@pytest.mark.asyncio
async def test_stop_swallows_sidecar_errors_and_clears_state():
    client = _AsyncClientContext(exc=RuntimeError("sidecar unavailable"))
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend.available = True
    backend.tools = []

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client):
        await backend.stop()

    assert backend.available is False
    assert backend.tools == []


@pytest.mark.asyncio
async def test_call_tool_connects_when_backend_not_available():
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend.available = False
    backend._start_locked = AsyncMock(side_effect=lambda: setattr(backend, "available", True))
    backend._call_tool_once = AsyncMock(return_value=_result("ok"))

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    backend._start_locked.assert_awaited_once()
    backend._call_tool_once.assert_awaited_once_with("symbol_explore", {"query": "x"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_call_tool_reconnects_after_failed_call():
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend.available = True
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(side_effect=[RuntimeError("broken"), _result("recovered")])

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    assert backend._call_tool_once.await_count == 2
    backend._start_locked.assert_awaited_once()
    assert result.content[0].text == "recovered"


@pytest.mark.asyncio
async def test_call_tool_symbol_explore_uses_local_fallback_after_timeout():
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control", project_path="/tmp/erp")
    backend.available = True
    backend._call_tool_once = AsyncMock(side_effect=asyncio.TimeoutError())
    backend._symbol_search_index.ensure_loaded = Mock(return_value=True)
    backend._symbol_search_index.search = Mock(
        return_value=[
            {
                "name": "НоменклатураНайти",
                "kind": "Функция",
                "params": "",
                "export": True,
                "module": "ОбщийМодуль.Поиск",
                "file": "CommonModules/Поиск/Ext/Module.bsl",
                "line": 12,
                "comment": "",
                "score": 100,
            }
        ]
    )

    result = await backend.call_tool("symbol_explore", {"query": "Номенклатура", "limit": 3})

    backend._call_tool_once.assert_awaited_once_with("symbol_explore", {"query": "Номенклатура", "limit": 3})
    backend._symbol_search_index.ensure_loaded.assert_called()
    backend._symbol_search_index.search.assert_called_once_with("Номенклатура", limit=3, export_only=False)
    assert "НоменклатураНайти" in result.content[0].text
    assert result.isError is False


@pytest.mark.asyncio
async def test_symbol_explore_fallback_tries_container_snapshot_after_host_roots(monkeypatch):
    monkeypatch.setattr("gateway.backends.docker_control_lsp_backend.settings.bsl_workspace", "/workspace")
    monkeypatch.setattr("gateway.backends.docker_control_lsp_backend.settings.bsl_host_workspace", "/home/as/Z")
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control", project_path="/tmp/erp")
    ensure_loaded = Mock(side_effect=[False, False, False, True])
    backend._symbol_search_index.ensure_loaded = ensure_loaded
    backend._symbol_search_index.search = Mock(return_value=[])

    result = backend._symbol_explore_fallback({"query": "Номенклатура"})

    assert result.content[0].text == "[]"
    attempted_roots = [call.args[0] for call in ensure_loaded.call_args_list]
    assert attempted_roots == ["/tmp/erp", "/workspace/erp", "/hostfs-home/as/Z/erp", "mcp-lsp-erp:/projects"]


@pytest.mark.asyncio
async def test_call_tool_once_successfully_builds_mcp_result():
    payload = {
        "ok": True,
        "result": {
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
        },
    }
    client = _AsyncClientContext(_Response(payload))

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client), \
         patch("gateway.backends.docker_control_lsp_backend.settings") as settings:
        settings.docker_control_url = "http://docker-control"
        settings.docker_control_token = "secret-token"
        backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
        result = await backend._call_tool_once("symbol_explore", {"query": "x"})

    assert result.content[0].text == "ok"
    assert client.calls == [
        (
            "http://docker-control/api/lsp-proxy/call",
            {"slug": "erp", "name": "symbol_explore", "arguments": {"query": "x"}},
            {"Authorization": "Bearer secret-token"},
        ),
    ]


@pytest.mark.asyncio
async def test_call_tool_once_raises_when_sidecar_returns_error_payload():
    client = _AsyncClientContext(_Response({"ok": False, "error": "call failed"}))

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client):
        backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
        with pytest.raises(RuntimeError, match="call failed"):
            await backend._call_tool_once("symbol_explore", {"query": "x"})


def test_parse_rename_preview_extracts_uri_and_edits():
    files = _parse_rename_preview(RENAME_PREVIEW)

    assert len(files) == 1
    assert files[0].uri == "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl"
    assert len(files[0].edits) == 2
    assert files[0].edits[0].line == 5
    assert files[0].edits[0].start_char == 12
    assert files[0].edits[0].end_char == 31
    assert files[0].edits[0].replacement == "ЛокПереим"


def test_parse_rename_preview_flushes_multiple_files_and_ignores_empty_file_block():
    preview = (
        "File: First.bsl (1 edits)\n"
        "   URI: file:///projects/First.bsl\n"
        "   1. Line 1 (chars 0-3): Replace with \"Один\"\n"
        "File: Empty.bsl (0 edits)\n"
        "File: Second.bsl (1 edits)\n"
        "   URI: file:///projects/Second.bsl\n"
        "   1. Line 2 (chars 4-8): Replace with \"Два\"\n"
    )

    files = _parse_rename_preview(preview)

    assert [file.uri for file in files] == ["file:///projects/First.bsl", "file:///projects/Second.bsl"]
    assert files[0].edits[0].replacement == "Один"
    assert _parse_rename_preview("File: Empty.bsl (0 edits)") == []


def test_apply_rename_preview_to_text_applies_overlapping_identifier_replacements():
    original = (
        "Перем ГлобальнаяПеременная;\n"
        "\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n"
    )
    parsed = _parse_rename_preview(RENAME_PREVIEW)

    updated = _apply_rename_preview_to_text(original, parsed[0].edits)

    assert "ЛокПереим = 1;" in updated
    assert "Возврат ЛокПереим;" in updated
    assert "ЛокПереим�" not in updated
    assert "ВозвЛокПереим" not in updated


def test_apply_rename_preview_to_text_rejects_out_of_bounds_and_invalid_ranges():
    with pytest.raises(ValueError, match="outside file"):
        _apply_rename_preview_to_text("one\n", (_parse_rename_preview(
            'File: A.bsl\n   URI: file:///projects/A.bsl\n   1. Line 2 (chars 0-1): Replace with "x"\n'
        )[0].edits[0],))

    with pytest.raises(ValueError, match="range is invalid"):
        _apply_rename_preview_to_text("one\n", (_parse_rename_preview(
            'File: A.bsl\n   URI: file:///projects/A.bsl\n   1. Line 1 (chars 2-99): Replace with "x"\n'
        )[0].edits[0],))


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_uses_preview_and_local_write(tmp_path):
    project_path = tmp_path / "erp"
    project_path.mkdir()
    target = project_path / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir()
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )

    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control", project_path=str(project_path))
    backend.available = True
    backend.tools = [Tool(**_tool_payload("did_change_watched_files"))]
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(
        side_effect=[
            CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]),
            CallToolResult(content=[TextContent(type="text", text="ok")]),
        ]
    )

    result = await backend.call_tool(
        "rename",
        {
            "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
            "line": 3,
            "character": 4,
            "new_name": "ЛокПереим",
            "apply": "true",
        },
    )

    updated = target.read_text(encoding="utf-8-sig")
    assert "ЛокПереим = 1;" in updated
    assert "Возврат ЛокПереим;" in updated
    assert "RENAME APPLIED" in result.content[0].text
    assert backend._call_tool_once.await_args_list[0].args == (
        "rename",
        {
            "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
            "line": 3,
            "character": 4,
            "new_name": "ЛокПереим",
            "apply": "false",
        },
    )
    assert backend._call_tool_once.await_args_list[1].args == (
        "did_change_watched_files",
        {"language": "bsl", "changes_json": "[]"},
    )


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_without_watcher_tool_skips_notification(tmp_path):
    project_path = tmp_path / "erp"
    target = project_path / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control", project_path=str(project_path))
    backend.available = True
    backend.tools = []
    backend._call_tool_once = AsyncMock(return_value=CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]))

    result = await backend.call_tool("rename", {"apply": "true"})

    assert "RENAME APPLIED" in result.content[0].text
    assert backend._call_tool_once.await_count == 1


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_falls_back_to_workspace_slug(tmp_path):
    workspace_root = tmp_path / "workspace"
    project_path = tmp_path / "hostfs-home" / "as" / "Z" / "erp"
    target = workspace_root / "erp" / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )

    backend = DockerControlLspBackend(
        "ERP/lsp",
        "erp",
        control_url="http://docker-control",
        project_path=str(project_path),
    )
    backend.available = True
    backend.tools = [Tool(**_tool_payload("did_change_watched_files"))]
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(
        side_effect=[
            CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]),
            CallToolResult(content=[TextContent(type="text", text="ok")]),
        ]
    )

    with patch("gateway.backends.docker_control_lsp_backend.settings") as mock_settings:
        mock_settings.docker_control_url = "http://docker-control"
        mock_settings.docker_control_token = ""
        mock_settings.bsl_workspace = str(workspace_root)
        await backend.call_tool(
            "rename",
            {
                "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
                "line": 3,
                "character": 4,
                "new_name": "ЛокПереим",
                "apply": "true",
            },
        )

    updated = target.read_text(encoding="utf-8-sig")
    assert "ЛокПереим = 1;" in updated
    assert "Возврат ЛокПереим;" in updated


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_skips_inaccessible_hostfs_candidate(tmp_path):
    workspace_root = tmp_path / "workspace"
    hostfs_root = tmp_path / "hostfs-home" / "as" / "Z" / "erp"
    target = workspace_root / "erp" / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir(parents=True)
    hostfs_root.mkdir(parents=True)
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )

    backend = DockerControlLspBackend(
        "ERP/lsp",
        "erp",
        control_url="http://docker-control",
        project_path=str(hostfs_root),
    )
    backend.available = True
    backend.tools = [Tool(**_tool_payload("did_change_watched_files"))]
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(
        side_effect=[
            CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]),
            CallToolResult(content=[TextContent(type="text", text="ok")]),
        ]
    )

    original_exists = Path.exists

    def _patched_exists(self):
        if self == hostfs_root:
            raise PermissionError("hostfs denied")
        return original_exists(self)

    with patch("gateway.backends.docker_control_lsp_backend.settings") as mock_settings, \
         patch("gateway.backends.docker_control_lsp_backend.Path.exists", new=_patched_exists):
        mock_settings.docker_control_url = "http://docker-control"
        mock_settings.docker_control_token = ""
        mock_settings.bsl_workspace = str(workspace_root)
        await backend.call_tool(
            "rename",
            {
                "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
                "line": 3,
                "character": 4,
                "new_name": "ЛокПереим",
                "apply": "true",
            },
        )

    updated = target.read_text(encoding="utf-8-sig")
    assert "ЛокПереим = 1;" in updated
    assert "Возврат ЛокПереим;" in updated


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_prefers_existing_hostfs_target_over_stale_workspace_root(tmp_path):
    workspace_root = tmp_path / "workspace"
    stale_root = workspace_root / "Z01"
    hostfs_root = tmp_path / "hostfs-home" / "as" / "Z"
    target = hostfs_root / "Z01" / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"

    stale_root.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )

    backend = DockerControlLspBackend(
        "Z01/lsp",
        "Z01",
        control_url="http://docker-control",
        project_path=str(stale_root),
    )
    backend.available = True
    backend.tools = [Tool(**_tool_payload("did_change_watched_files"))]
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(
        side_effect=[
            CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]),
            CallToolResult(content=[TextContent(type="text", text="ok")]),
        ]
    )

    with patch("gateway.backends.docker_control_lsp_backend.settings") as mock_settings:
        mock_settings.docker_control_url = "http://docker-control"
        mock_settings.docker_control_token = ""
        mock_settings.bsl_workspace = str(workspace_root)
        mock_settings.bsl_host_workspace = str(hostfs_root)
        result = await backend.call_tool(
            "rename",
            {
                "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
                "line": 3,
                "character": 4,
                "new_name": "ЛокПереим",
                "apply": "true",
            },
        )

    updated = target.read_text(encoding="utf-8-sig")
    assert "ЛокПереим = 1;" in updated
    assert "Возврат ЛокПереим;" in updated
    assert "RENAME APPLIED" in result.content[0].text


def test_project_root_candidates_translate_home_host_workspace_to_hostfs_path():
    backend = DockerControlLspBackend(
        "Z01/lsp",
        "Z01",
        control_url="http://docker-control",
        project_path="/workspace/Z01",
    )

    with patch("gateway.backends.docker_control_lsp_backend.settings") as mock_settings:
        mock_settings.bsl_workspace = "/workspace"
        mock_settings.bsl_host_workspace = "/home/as/Z"

        candidates = backend._project_root_candidates()

    assert Path("/hostfs-home/as/Z/Z01") in candidates


def test_project_root_candidates_and_symbol_roots_skip_duplicate_hostfs_candidate(tmp_path):
    workspace_root = tmp_path / "hostfs-home" / "as" / "Z"
    backend = DockerControlLspBackend("Z01/lsp", "Z01", control_url="http://docker-control")

    with patch("gateway.backends.docker_control_lsp_backend.settings") as mock_settings:
        mock_settings.bsl_workspace = str(workspace_root)
        mock_settings.bsl_host_workspace = str(workspace_root)
        candidates = backend._project_root_candidates()
        roots = backend._symbol_search_roots()

    assert candidates.count(workspace_root / "Z01") == 1
    assert roots.count(str(workspace_root / "Z01")) == 1

    backend._project_root_candidates = Mock(return_value=[workspace_root / "Z01", workspace_root / "Z01"])
    assert backend._symbol_search_roots().count(str(workspace_root / "Z01")) == 1


@pytest.mark.asyncio
async def test_call_tool_rename_apply_true_uses_sidecar_write_on_permission_error(tmp_path):
    project_path = tmp_path / "erp"
    project_path.mkdir()
    target = project_path / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir()
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )

    backend = DockerControlLspBackend(
        "ERP/lsp",
        "erp",
        control_url="http://docker-control",
        project_path=str(project_path),
    )
    backend.available = True
    backend.tools = [Tool(**_tool_payload("did_change_watched_files"))]
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(
        side_effect=[
            CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)]),
            CallToolResult(content=[TextContent(type="text", text="ok")]),
        ]
    )
    client = _AsyncClientContext(_Response({"ok": True, "path": "/projects/__codex_live_smoke__/RenameProbe_Z01.bsl"}))
    original_write_text = Path.write_text

    def _patched_write_text(self, *args, **kwargs):
        if self == target:
            raise PermissionError("readonly")
        return original_write_text(self, *args, **kwargs)

    with patch("gateway.backends.docker_control_lsp_backend.Path.write_text", new=_patched_write_text), \
         patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client):
        await backend.call_tool(
            "rename",
            {
                "uri": "file:///projects/__codex_live_smoke__/RenameProbe_Z01.bsl",
                "line": 3,
                "character": 4,
                "new_name": "ЛокПереим",
                "apply": "true",
            },
        )

    assert len(client.calls) == 1
    url, payload, headers = client.calls[0]
    assert url == "http://docker-control/api/lsp/write-file"
    assert payload == {
        "container_name": "mcp-lsp-erp",
        "relative_path": "__codex_live_smoke__/RenameProbe_Z01.bsl",
        "content": "Перем ГлобальнаяПеременная;\n\nФункция ТестоваяФункция() Экспорт\n    ЛокПереим = 1;\n    Возврат ЛокПереим;\nКонецФункции\n",
    }
    assert isinstance(headers, dict)


@pytest.mark.asyncio
async def test_call_tool_non_special_tool_returns_once_and_reconnects_generic_failure():
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend.available = True
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(return_value=_result("ok"))

    result = await backend.call_tool("hover", {"uri": "file:///projects/A.bsl"})

    assert result.content[0].text == "ok"
    backend._call_tool_once.assert_awaited_once_with("hover", {"uri": "file:///projects/A.bsl"})

    backend._call_tool_once = AsyncMock(side_effect=[RuntimeError("broken"), _result("recovered")])
    recovered = await backend.call_tool("hover", {"uri": "file:///projects/A.bsl"})

    assert recovered.content[0].text == "recovered"
    assert backend._start_locked.await_count == 1


@pytest.mark.asyncio
async def test_call_tool_reconnects_rename_apply_after_failure(tmp_path):
    project_path = tmp_path / "erp"
    target = project_path / "__codex_live_smoke__" / "RenameProbe_Z01.bsl"
    target.parent.mkdir(parents=True)
    target.write_text(
        "Перем ГлобальнаяПеременная;\n\n"
        "Функция ТестоваяФункция() Экспорт\n"
        "    ЛокальнаяПеременная = 1;\n"
        "    Возврат ЛокальнаяПеременная;\n"
        "КонецФункции\n",
        encoding="utf-8-sig",
    )
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control", project_path=str(project_path))
    backend.available = True
    backend.tools = []
    backend._start_locked = AsyncMock()
    backend._call_tool_once = AsyncMock(side_effect=[RuntimeError("stale"), CallToolResult(content=[TextContent(type="text", text=RENAME_PREVIEW)])])

    result = await backend.call_tool("rename", {"apply": "true"})

    assert "RENAME APPLIED" in result.content[0].text
    backend._start_locked.assert_awaited_once()


def test_project_roots_headers_symbol_fallback_and_uri_validation_edges(tmp_path, monkeypatch):
    monkeypatch.setattr("gateway.backends.docker_control_lsp_backend.settings.bsl_workspace", str(tmp_path / "workspace"))
    monkeypatch.setattr("gateway.backends.docker_control_lsp_backend.settings.bsl_host_workspace", "")
    monkeypatch.setattr("gateway.backends.docker_control_lsp_backend.settings.docker_control_token", "")
    backend = DockerControlLspBackend(
        "ERP/lsp",
        "erp",
        control_url="http://docker-control",
        project_path=f"mcp-lsp-erp:/projects",
    )
    backend._symbol_search_index.ensure_loaded = Mock(return_value=True)
    backend._symbol_search_index.search = Mock(return_value=[])

    assert backend._headers() == {}
    assert backend._symbol_search_roots().count("mcp-lsp-erp:/projects") == 1
    backend._symbol_explore_fallback({"query": "x", "limit": "bad", "export_only": "yes"})
    backend._symbol_search_index.search.assert_called_once_with("x", limit=20, export_only=True)

    empty_slug_backend = DockerControlLspBackend("ERP/lsp", "", control_url="http://docker-control")
    assert empty_slug_backend._project_root_candidates() == []
    with pytest.raises(RuntimeError, match="outside /projects"):
        backend._project_file_from_uri("file:///tmp/A.bsl")
    with pytest.raises(RuntimeError, match="Unsafe rename URI"):
        backend._project_file_from_uri("file:///projects/../A.bsl")
    with pytest.raises(RuntimeError, match="not configured"):
        empty_slug_backend._project_file_from_uri("file:///projects/A.bsl")
    with pytest.raises(RuntimeError, match="outside /projects"):
        backend._relative_project_path_from_uri("file:///tmp/A.bsl")
    with pytest.raises(RuntimeError, match="Unsafe rename URI"):
        backend._relative_project_path_from_uri("file:///projects/../A.bsl")


def test_project_file_from_uri_uses_existing_root_or_first_probeable_candidate(tmp_path):
    existing_root = tmp_path / "existing"
    existing_root.mkdir()
    missing_root = tmp_path / "missing"
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend._project_root_candidates = Mock(return_value=[missing_root, existing_root])

    assert backend._project_file_from_uri("file:///projects/A.bsl") == existing_root / "A.bsl"

    backend._project_root_candidates = Mock(return_value=[missing_root])
    assert backend._project_file_from_uri("file:///projects/A.bsl") == missing_root / "A.bsl"


@pytest.mark.asyncio
async def test_write_project_file_via_runtime_raises_sidecar_error():
    client = _AsyncClientContext(_Response({"ok": False, "error": "write denied"}))
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")

    with patch("gateway.backends.docker_control_lsp_backend.httpx.AsyncClient", return_value=client):
        with pytest.raises(RuntimeError, match="write denied"):
            await backend._write_project_file_via_runtime("A.bsl", "content")


@pytest.mark.asyncio
async def test_rename_apply_rejects_preview_without_editable_files():
    backend = DockerControlLspBackend("ERP/lsp", "erp", control_url="http://docker-control")
    backend._call_tool_once = AsyncMock(return_value=CallToolResult(content=[TextContent(type="text", text="No edits")]))

    with pytest.raises(RuntimeError, match="did not include editable"):
        await backend._call_rename_with_local_apply({"apply": "true"})

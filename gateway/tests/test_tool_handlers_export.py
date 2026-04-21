"""Tests for gateway.tool_handlers.export."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.export import (
    _extract_bsl_file_count,
    _existing_bsl_file_count,
    _finalize_index_result,
    _reuse_existing_export_tree,
    build_index_with_fallback,
    find_1cv8_binaries,
    pick_1cv8,
    run_export_bsl,
    run_designer_export,
    _container_fallback_index_path,
    _gateway_visible_host_path,
    _summarize_index_result,
)


class Test1Cv8Discovery:
    def test_find_1cv8_binaries_returns_empty_for_missing_dir(self, tmp_path):
        found = find_1cv8_binaries(base_dir=tmp_path / "missing")
        assert found == {}

    def test_find_1cv8_binaries_ignores_non_directory_entries(self, tmp_path):
        (tmp_path / "README.txt").write_text("x", encoding="utf-8")
        assert find_1cv8_binaries(base_dir=tmp_path) == {}

    def test_find_1cv8_binaries_scans_versions(self, tmp_path):
        ver_a = tmp_path / "8.3.27.2074"
        ver_b = tmp_path / "8.3.25.1000"
        ver_bad = tmp_path / "8.3.20.0"
        ver_a.mkdir()
        ver_b.mkdir()
        ver_bad.mkdir()
        (ver_a / "1cv8").write_text("", encoding="utf-8")
        (ver_b / "1cv8").write_text("", encoding="utf-8")

        found = find_1cv8_binaries(base_dir=tmp_path)

        assert set(found.keys()) == {"8.3.27.2074", "8.3.25.1000"}
        assert found["8.3.27.2074"] == ver_a / "1cv8"

    def test_pick_1cv8_prefers_requested_version(self):
        versions = {
            "8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
            "8.3.25.1000": Path("/opt/1cv8/x86_64/8.3.25.1000/1cv8"),
        }

        picked = pick_1cv8(
            "8.3.25.1000",
            find_binaries=lambda: versions,
        )

        assert picked == versions["8.3.25.1000"]

    def test_pick_1cv8_uses_latest_when_preferred_missing(self):
        versions = {
            "8.3.25.1000": Path("/opt/1cv8/x86_64/8.3.25.1000/1cv8"),
            "8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
        }

        picked = pick_1cv8(
            "8.3.24.1",
            find_binaries=lambda: versions,
        )

        assert picked == versions["8.3.27.2074"]

    def test_pick_1cv8_returns_none_when_nothing_installed(self):
        assert pick_1cv8(find_binaries=lambda: {}) is None


def _settings(**overrides):
    base = {
        "bsl_export_timeout": 600,
        "bsl_workspace": "/projects",
        "bsl_host_workspace": "",
        "export_host_url": "",
        "allow_container_designer_export": False,
        "port": 8000,
        "platform_path": "/opt/1cv8/x86_64/8.3.27.2074",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _deps():
    manager = MagicMock()
    manager.has_tool = MagicMock(return_value=False)
    manager.call_tool = AsyncMock()
    return {
        "manager": manager,
        "index_jobs": {},
        "get_session_active": lambda: None,
        "get_connection_active": lambda _connection: None,
        "build_index": lambda *_args, **_kwargs: "0 symbols",
        "find_binaries": lambda: {"8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")},
        "pick_binary": lambda _ver: Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
        "run_designer_export_fn": AsyncMock(return_value=(0, "")),
        "logger": MagicMock(),
    }


class TestRunExportBsl:
    def test_gateway_visible_host_path_maps_home_root(self):
        assert _gateway_visible_host_path("/home") == "/hostfs-home"
        assert _gateway_visible_host_path("/home/as/Z") == "/hostfs-home/as/Z"
        assert _gateway_visible_host_path("/tmp/Z") == "/tmp/Z"

    def test_container_fallback_index_path_uses_projects_for_gateway_mounts(self):
        assert _container_fallback_index_path("/hostfs-home/as/Z/Z01") == "/projects"
        assert _container_fallback_index_path("/workspace/Z01") == "/projects"
        assert _container_fallback_index_path("/projects/Z01") == "/projects"
        assert _container_fallback_index_path("/home/as/Z/Z01") == "/home/as/Z/Z01"

    def test_summarize_index_result_parses_known_formats(self):
        assert _summarize_index_result("Indexed 42 symbols from 3 BSL files") == "42 символов"
        assert _summarize_index_result("Проиндексировано 15") == "15 символов"
        assert _summarize_index_result("19 символов") == "19 символов"
        assert _summarize_index_result("ERROR: broken") is None

    def test_summarize_index_result_returns_raw_text_when_no_known_counter(self):
        assert _summarize_index_result("\ufeffCompleted without counters ") == "Completed without counters"

    def test_extract_bsl_file_count_parses_export_messages(self):
        assert _extract_bsl_file_count("Export completed: 11622 BSL files in /home/as/Z/Z01") == 11622
        assert _extract_bsl_file_count("Выгрузка завершена") is None

    def test_build_index_with_fallback_returns_last_error_when_all_attempts_fail(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return f"ERROR: missing symbols in {container or path}"

        ok, result = build_index_with_fallback(
            "/workspace/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is False
        assert result == "ERROR: missing symbols in mcp-lsp-z01"
        assert calls == [
            ("/workspace/Z01", ""),
            ("/projects", "mcp-lsp-z01"),
        ]

    def test_build_index_with_fallback_skips_duplicate_attempts(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "ERROR: none"

        ok, result = build_index_with_fallback("/hostfs-home/as/Z/Z01", build_index=_build_index, active_db=None)
        assert ok is False
        assert calls == [("/hostfs-home/as/Z/Z01", "")]

    def test_build_index_with_fallback_skips_placeholder_gateway_path_attempt(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "ERROR: none"

        ok, result = build_index_with_fallback(
            "/projects",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is False
        assert result == "ERROR: none"
        assert calls == [("/projects", "mcp-lsp-z01")]

    def test_build_index_with_fallback_prefers_gateway_visible_host_path(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01":
                return "Indexed 77 symbols"
            return "ERROR: no files"

        ok, result = build_index_with_fallback(
            "/home/as/Z/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is True
        assert result == "77 символов"
        assert calls[0] == ("/hostfs-home/as/Z/Z01", "")

    def test_build_index_with_fallback_prefers_existing_hostfs_path_before_container(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01" and not container:
                return "Indexed 91 symbols"
            return "ERROR: stale /projects mount"

        ok, result = build_index_with_fallback(
            "/hostfs-home/as/Z/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is True
        assert result == "91 символов"
        assert calls[0] == ("/hostfs-home/as/Z/Z01", "")

    def test_build_index_with_fallback_tries_container_after_zero_symbol_host_result(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01" and not container:
                return "Indexed 0 symbols from 11622 BSL files"
            if container == "mcp-lsp-z01":
                return "Indexed 220968 symbols from 11622 BSL files"
            return "ERROR: unexpected"

        ok, result = build_index_with_fallback(
            "/hostfs-home/as/Z/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is True
        assert result == "220968 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/projects", "mcp-lsp-z01"),
        ]

    def test_build_index_with_fallback_returns_zero_when_all_attempts_are_zero(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "Indexed 0 symbols from 11622 BSL files"

        ok, result = build_index_with_fallback(
            "/hostfs-home/as/Z/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is True
        assert result == "0 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/projects", "mcp-lsp-z01"),
        ]

    def test_build_index_with_fallback_continues_to_container_after_local_permission_error(self):
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01" and not container:
                raise PermissionError("[Errno 13] Permission denied: '/hostfs-home/as/Z/Z01'")
            if container == "mcp-lsp-z01":
                return "Indexed 101 symbols"
            return "ERROR: stale /workspace mount"

        ok, result = build_index_with_fallback(
            "/hostfs-home/as/Z/Z01",
            build_index=_build_index,
            active_db=SimpleNamespace(lsp_container="mcp-lsp-z01"),
        )

        assert ok is True
        assert result == "101 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/projects", "mcp-lsp-z01"),
        ]

    @pytest.mark.asyncio
    async def test_finalize_index_result_retries_large_zero_symbol_export(self):
        logger = MagicMock()
        calls = []
        results = iter(["Indexed 0 symbols from 11622 BSL files", "Indexed 220968 symbols from 11622 BSL files"])

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return next(results)

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/hostfs-home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=11622,
                retry_delays=(0.1,),
            )

        assert ok is True
        assert result == "220968 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
        ]
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_finalize_index_result_retries_large_tiny_nonzero_export(self):
        logger = MagicMock()
        calls = []
        results = iter(["Indexed 2 symbols from 11622 BSL files", "Indexed 220968 symbols from 11622 BSL files"])

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return next(results)

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/hostfs-home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=11622,
                retry_delays=(0.1,),
            )

        assert ok is True
        assert result == "220968 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
        ]
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_finalize_index_result_keeps_small_zero_symbol_export_without_retry(self):
        logger = MagicMock()
        calls = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "Indexed 0 symbols from 3 BSL files"

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=3,
                retry_delays=(0.1,),
            )

        assert ok is True
        assert result == "0 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", ""),
        ]
        sleep_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finalize_index_result_keeps_small_nonzero_export_without_retry(self):
        logger = MagicMock()
        calls = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "Indexed 2 symbols from 3 BSL files"

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=3,
                retry_delays=(0.1,),
            )

        assert ok is True
        assert result == "2 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
        ]
        sleep_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finalize_index_result_returns_retry_error_after_zero_symbol_first_pass(self):
        logger = MagicMock()
        calls = []
        results = iter([
            "Indexed 0 symbols from 11622 BSL files",
            "ERROR: stale index",
        ])

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return next(results)

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/hostfs-home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=11622,
                retry_delays=(0.1,),
            )

        assert ok is False
        assert result == "ERROR: stale index"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
        ]
        sleep_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_finalize_index_result_returns_error_after_all_retries_stay_tiny_nonzero(self):
        logger = MagicMock()
        calls = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "Indexed 2 symbols from 11622 BSL files"

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=11622,
                retry_delays=(0.1, 0.2),
            )

        assert ok is False
        assert "still returns an implausibly small symbol count" in result
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
        ]
        assert sleep_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_finalize_index_result_returns_error_after_all_retries_stay_zero(self):
        logger = MagicMock()
        calls = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return "Indexed 0 symbols from 11622 BSL files"

        with patch("gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()) as sleep_mock:
            ok, result = await _finalize_index_result(
                output_dir="/home/as/Z/Z01",
                build_index=_build_index,
                active_db=None,
                logger=logger,
                expected_file_count=11622,
                retry_delays=(0.1, 0.2),
            )

        assert ok is False
        assert "still returns 0 symbols" in result
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", ""),
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", ""),
        ]
        assert sleep_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_unconfigured_output_dir_returns_dashboard_error(self):
        result = await run_export_bsl(
            connection="Srvr=srv;Ref=base;",
            output_dir="/projects",
            settings=_settings(export_host_url=""),
            **_deps(),
        )
        assert "ERROR: Папка выгрузки BSL не настроена." in result
        assert "dashboard#settings" in result

    @pytest.mark.asyncio
    async def test_host_service_busy_returns_conflict_error(self):
        response = MagicMock()
        response.status_code = 409
        response.json = MagicMock(return_value={})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls:
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert "уже выполняет другую выгрузку" in result

    @pytest.mark.asyncio
    async def test_host_service_error_bubbles_with_url(self):
        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls:
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(side_effect=Exception("connection refused"))
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert result.startswith("ERROR calling export host service at http://host:8082/export-bsl:")

    @pytest.mark.asyncio
    async def test_host_service_keeps_non_workspace_output_dir_without_remap(self):
        response = MagicMock()
        response.status_code = 200
        response.json = MagicMock(return_value={"ok": True})
        status_response = MagicMock()
        status_response.json = MagicMock(return_value={"status": "done", "result": "ok"})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.build_index_with_fallback",
            return_value=(True, "17 символов"),
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/tmp/custom/base",
                settings=_settings(
                    export_host_url="http://host:8082",
                    bsl_workspace="/workspace",
                    bsl_host_workspace="/home/as/Z",
                ),
                **_deps(),
            )

        assert "Выгрузка завершена:" in result
        assert "Индекс: 17 символов." in result
        assert client.post.await_args.kwargs["json"]["output_dir"] == "/tmp/custom/base"

    @pytest.mark.asyncio
    async def test_host_service_returns_explicit_export_error_payload(self):
        response = MagicMock()
        response.status_code = 200
        response.json = MagicMock(return_value={"ok": False, "result": "boom"})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls:
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert result == "Export failed: boom"

    @pytest.mark.asyncio
    async def test_hostfs_home_output_dir_is_mapped_to_host_path_for_service(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 3 BSL files in /home/as/Z/ERP"}
        )

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/hostfs-home/as/Z/ERP",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        sent = client.post.await_args.kwargs["json"]
        assert sent["output_dir"] == "/home/as/Z/ERP"
        assert result.startswith("Выгрузка завершена: 3 BSL файлов.")

    @pytest.mark.asyncio
    async def test_container_workspace_output_dir_is_mapped_to_host_workspace_for_service(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(return_value={"status": "error", "result": "boom"})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/ERP",
                settings=_settings(export_host_url="http://host:8082", bsl_workspace="/workspace", bsl_host_workspace="/home/as/Z"),
                **_deps(),
            )

        sent = client.post.await_args.kwargs["json"]
        assert sent["output_dir"] == "/home/as/Z/ERP"

    @pytest.mark.asyncio
    async def test_hostfs_home_root_output_dir_maps_to_home(self):
        result = await run_export_bsl(
            connection="Srvr=srv;Ref=base;",
            output_dir="/hostfs-home",
            settings=_settings(export_host_url="http://host:8082"),
            **_deps(),
        )

        assert result.startswith("ERROR: Папка выгрузки BSL не настроена.")

    @pytest.mark.asyncio
    async def test_host_service_done_uses_hostfs_fallback_for_index(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 3 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()
        deps["get_session_active"] = lambda: SimpleNamespace(lsp_container="mcp-lsp-z01")
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01":
                return "Indexed 88 symbols"
            return "ERROR: stale /workspace mount"

        deps["build_index"] = _build_index

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert "Индекс: 88 символов." in result
        assert calls == [("/hostfs-home/as/Z/Z01", "")]

    @pytest.mark.asyncio
    async def test_host_service_done_uses_connection_db_when_session_active_missing(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 3 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()
        deps["get_connection_active"] = lambda _connection: SimpleNamespace(lsp_container="mcp-lsp-z01")
        calls: list[tuple[str, str]] = []

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            if path == "/hostfs-home/as/Z/Z01":
                raise PermissionError("[Errno 13] Permission denied: '/hostfs-home/as/Z/Z01'")
            if container == "mcp-lsp-z01":
                return "Indexed 88 symbols"
            return "ERROR: unexpected"

        deps["build_index"] = _build_index

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert "Индекс: 88 символов." in result
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", "mcp-lsp-z01"),
        ]

    @pytest.mark.asyncio
    async def test_host_service_done_retries_zero_symbol_large_export(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 11622 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()
        calls: list[tuple[str, str]] = []
        results = iter(["Indexed 0 symbols from 11622 BSL files", "Indexed 220968 symbols from 11622 BSL files"])

        def _build_index(path: str, container: str = "") -> str:
            calls.append((path, container))
            return next(results)

        deps["build_index"] = _build_index

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert result == "Выгрузка завершена: 11622 BSL файлов. Индекс: 220968 символов."
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["status"] == "done"
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["result"] == "220968 символов"
        assert calls == [
            ("/hostfs-home/as/Z/Z01", ""),
            ("/home/as/Z/Z01", ""),
        ]

    @pytest.mark.asyncio
    async def test_host_service_auth_error_reuses_cached_index_when_tree_missing(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "error", "result": "Export failed (rc=1): The infobase user is not authenticated"}
        )

        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 220968 symbols from cached snapshot"

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ), patch(
            "gateway.tool_handlers.export._existing_bsl_file_count", return_value=0
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert "Свежая выгрузка недоступна" in result
        assert "ПользовательBSL/ПарольBSL" in result
        assert "сохранённый BSL индекс" in result
        assert "220968 символов" in result
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_host_service_license_error_reuses_cached_index_when_tree_missing(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "error", "result": "Export failed (rc=1): License not found. Software protection key or acquired software license not found!"}
        )

        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 220968 symbols from cached snapshot"

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ), patch(
            "gateway.tool_handlers.export._existing_bsl_file_count", return_value=0
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert "Свежая выгрузка недоступна" in result
        assert "не найдена лицензия 1С" in result
        assert "сохранённый BSL индекс" in result
        assert "220968 символов" in result
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_local_export_uses_no_connection_resolver_when_not_provided(self, tmp_path):
        deps = _deps()
        deps["get_connection_active"] = None
        deps["get_session_active"] = lambda: SimpleNamespace(lsp_container="mcp-lsp-z01")
        deps["build_index"] = lambda path, container="": "Indexed 12 symbols" if container == "mcp-lsp-z01" else "ERROR: miss"
        output_dir = tmp_path / "base"

        result = await run_export_bsl(
            connection="Srvr=srv;Ref=base;",
            output_dir=str(output_dir),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Индекс: 12 символов." in result

    @pytest.mark.asyncio
    async def test_host_service_done_without_index_summary_sets_error_state(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 4 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "ERROR: No BSL symbols found"

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert result == "Выгрузка завершена: 4 BSL файлов."
        assert deps["index_jobs"]["Srvr=srv;Ref=base;"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_host_service_done_with_index_exception_sets_error_state(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 5 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()
        deps["build_index"] = MagicMock(side_effect=RuntimeError("index crash"))

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert result == "Выгрузка завершена: 5 BSL файлов."
        assert deps["index_jobs"]["Srvr=srv;Ref=base;"]["status"] == "error"
        assert deps["index_jobs"]["Srvr=srv;Ref=base;"]["result"] == "ERROR: index crash"

    @pytest.mark.asyncio
    async def test_host_service_done_handles_build_index_fallback_exception(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={"status": "done", "result": "Export completed: 5 BSL files in /home/as/Z/Z01"}
        )

        deps = _deps()

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ), patch(
            "gateway.tool_handlers.export.build_index_with_fallback",
            side_effect=RuntimeError("fallback crash"),
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/home/as/Z/Z01",
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert result == "Выгрузка завершена: 5 BSL файлов."
        assert deps["index_jobs"]["Srvr=srv;Ref=base;"]["status"] == "error"
        assert deps["index_jobs"]["Srvr=srv;Ref=base;"]["result"] == "fallback crash"

    @pytest.mark.asyncio
    async def test_host_service_status_error_bubbles_result(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(return_value={"status": "error", "result": "fatal"})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert result == "Export failed: fatal"

    @pytest.mark.asyncio
    async def test_host_service_auth_error_reuses_existing_bsl_tree(self, tmp_path):
        existing_root = tmp_path / "Z01"
        module_path = existing_root / "CommonModules" / "Demo" / "Ext" / "Module.bsl"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("Процедура Тест() Экспорт\nКонецПроцедуры\n", encoding="utf-8-sig")

        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={
                "status": "error",
                "result": "Export failed (rc=1):\nThe infobase user is not authenticated",
            }
        )

        deps = _deps()
        deps["build_index"] = lambda path, container="": "Indexed 12 symbols from 1 BSL files in /hostfs-home/as/Z/Z01"

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir=str(existing_root),
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert result == "Выгрузка завершена: 1 BSL файлов. Индекс: 12 символов."
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["status"] == "done"
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["result"] == "12 символов"

    @pytest.mark.asyncio
    async def test_host_service_auth_error_without_existing_tree_returns_bsl_credentials_hint(self, tmp_path):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(
            return_value={
                "status": "error",
                "result": "Export failed (rc=1):\nThe infobase user is not authenticated",
            }
        )

        deps = _deps()

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=Z01;",
                output_dir=str(tmp_path / "missing"),
                settings=_settings(export_host_url="http://host:8082"),
                **deps,
            )

        assert "The infobase user is not authenticated" in result
        assert "ПользовательBSL" in result
        assert "ПарольBSL" in result

    @pytest.mark.asyncio
    async def test_local_export_auth_error_with_existing_tree_reuses_index(self, tmp_path):
        existing_root = tmp_path / "Z01"
        module_path = existing_root / "CommonModules" / "Demo" / "Ext" / "Module.bsl"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("Процедура Тест() Экспорт\nКонецПроцедуры\n", encoding="utf-8-sig")

        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(1, "The infobase user is not authenticated"))
        deps["build_index"] = lambda path, container="": "Indexed 7 symbols from 1 BSL files in /tmp"

        result = await run_export_bsl(
            connection="Srvr=srv;Ref=Z01;",
            output_dir=str(existing_root),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: 1 BSL файлов. Индекс: 7 символов."

    @pytest.mark.asyncio
    async def test_local_export_auth_error_reuses_existing_tree_with_active_session_db(self, tmp_path):
        existing_root = tmp_path / "Z01"
        module_path = existing_root / "CommonModules" / "Demo" / "Ext" / "Module.bsl"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("Процедура Тест() Экспорт\nКонецПроцедуры\n", encoding="utf-8-sig")

        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(1, "The infobase user is not authenticated"))
        deps["build_index"] = lambda path, container="": "Indexed 7 symbols from 1 BSL files in /tmp"
        deps["get_session_active"] = lambda: SimpleNamespace(lsp_container="mcp-lsp-Z01")
        deps["get_connection_active"] = MagicMock(side_effect=AssertionError("should not fallback to connection resolver"))

        result = await run_export_bsl(
            connection="Srvr=srv;Ref=Z01;",
            output_dir=str(existing_root),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: 1 BSL файлов. Индекс: 7 символов."
        assert deps["index_jobs"]["Srvr=srv;Ref=Z01;"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_local_export_auth_error_without_existing_tree_returns_bsl_credentials_hint(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(1, "The infobase user is not authenticated"))

        result = await run_export_bsl(
            connection="Srvr=srv;Ref=Z01;",
            output_dir=str(tmp_path / "missing"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "ПользовательBSL" in result
        assert "ПарольBSL" in result

    def test_existing_bsl_file_count_returns_zero_on_rglob_error(self, tmp_path):
        root = tmp_path / "Z01"
        root.mkdir(parents=True)

        with patch.object(Path, "rglob", side_effect=RuntimeError("boom")):
            assert _existing_bsl_file_count(str(root)) == 0

    @pytest.mark.asyncio
    async def test_reuse_existing_export_tree_returns_index_error(self, tmp_path):
        root = tmp_path / "Z01"
        module_path = root / "CommonModules" / "Demo" / "Ext" / "Module.bsl"
        module_path.parent.mkdir(parents=True, exist_ok=True)
        module_path.write_text("Процедура Тест() Экспорт\nКонецПроцедуры\n", encoding="utf-8-sig")

        index_jobs = {}
        result = await _reuse_existing_export_tree(
            connection="Srvr=srv;Ref=Z01;",
            output_dir=str(root),
            build_index=lambda *_args, **_kwargs: "ERROR: no symbols",
            active_db=None,
            index_jobs=index_jobs,
            logger=MagicMock(),
        )

        assert result == "ERROR: no symbols"
        assert index_jobs["Srvr=srv;Ref=Z01;"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_reuse_existing_export_tree_uses_explicit_existing_file_count(self, tmp_path):
        root = tmp_path / "Z01"
        root.mkdir(parents=True, exist_ok=True)

        index_jobs = {}
        result = await _reuse_existing_export_tree(
            connection="Srvr=srv;Ref=Z01;",
            output_dir=str(root),
            build_index=lambda *_args, **_kwargs: "Indexed 7 symbols from 1 BSL files in /tmp",
            active_db=None,
            index_jobs=index_jobs,
            logger=MagicMock(),
            existing_file_count=5,
        )

        assert result == "Выгрузка завершена: 5 BSL файлов. Индекс: 7 символов."
        assert index_jobs["Srvr=srv;Ref=Z01;"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_host_service_timeout_after_polling_loop(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        status_response = MagicMock()
        status_response.json = MagicMock(return_value={"status": "running", "result": ""})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(return_value=status_response)
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert result == "Export timed out after 2 hours"

    @pytest.mark.asyncio
    async def test_host_service_poll_errors_are_ignored_until_timeout(self):
        start_response = MagicMock()
        start_response.status_code = 200
        start_response.json = MagicMock(return_value={"ok": True})

        with patch("gateway.tool_handlers.export.httpx.AsyncClient") as client_cls, patch(
            "gateway.tool_handlers.export.asyncio.sleep", new=AsyncMock()
        ):
            client = MagicMock()
            client.__aenter__ = AsyncMock(return_value=client)
            client.__aexit__ = AsyncMock(return_value=False)
            client.post = AsyncMock(return_value=start_response)
            client.get = AsyncMock(side_effect=RuntimeError("boom"))
            client_cls.return_value = client

            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="http://host:8082"),
                **_deps(),
            )

        assert result == "Export timed out after 2 hours"

    @pytest.mark.asyncio
    async def test_container_export_disabled(self):
        result = await run_export_bsl(
            connection="Srvr=srv;Ref=base;",
            output_dir="/workspace/test",
            settings=_settings(export_host_url="", allow_container_designer_export=False),
            **_deps(),
        )
        assert "ALLOW_CONTAINER_DESIGNER_EXPORT=true" in result

    @pytest.mark.asyncio
    async def test_no_1cv8_binaries(self):
        deps = _deps()
        deps["find_binaries"] = lambda: {}
        fake_version_dir = MagicMock()
        fake_version_dir.is_dir.return_value = True
        fake_version_dir.name = "8.3.27.2074"

        with patch("gateway.tool_handlers.export.Path.exists", return_value=True), \
             patch("gateway.tool_handlers.export.Path.iterdir", return_value=[fake_version_dir]):
            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="", allow_container_designer_export=True),
                **deps,
            )
        assert "No 1cv8 thick client binary found" in result
        assert "Installed versions: 8.3.27.2074" in result

    @pytest.mark.asyncio
    async def test_no_1cv8_binaries_reports_missing_directory(self):
        deps = _deps()
        deps["find_binaries"] = lambda: {}

        with patch("gateway.tool_handlers.export.Path.exists", return_value=False):
            result = await run_export_bsl(
                connection="Srvr=srv;Ref=base;",
                output_dir="/workspace/test",
                settings=_settings(export_host_url="", allow_container_designer_export=True),
                **deps,
            )

        assert "(directory not found)" in result

    @pytest.mark.asyncio
    async def test_invalid_connection_string_returns_parse_error(self, tmp_path):
        result = await run_export_bsl(
            connection="Usr=test;Pwd=secret;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **_deps(),
        )

        assert result.startswith("ERROR: Cannot parse connection string:")

    @pytest.mark.asyncio
    async def test_file_connection_includes_credentials(self, tmp_path):
        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 2 symbols"

        result = await run_export_bsl(
            connection=f"File={tmp_path / 'ib'};Usr=test;Pwd=secret;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Индекс: 2 символов." in result
        conn_args = deps["run_designer_export_fn"].await_args.args[1]
        assert ["/F", str(tmp_path / "ib")] == conn_args[:2]
        assert "/N" in conn_args and "/P" in conn_args

    @pytest.mark.asyncio
    async def test_local_export_uses_longer_timeout_for_remote_server(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(0, ""))
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 7 symbols"

        result = await run_export_bsl(
            connection="Srvr=remote-srv;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов. Индекс: 7 символов."
        assert deps["run_designer_export_fn"].await_args.args[3] == 10800

    @pytest.mark.asyncio
    async def test_local_export_success_with_log_still_returns_normalized_summary(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(0, "designer log"))
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 2 symbols"

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов. Индекс: 2 символов."

    @pytest.mark.asyncio
    async def test_local_export_notifies_lsp_when_watcher_tool_present(self, tmp_path):
        deps = _deps()
        deps["manager"].has_tool.return_value = True
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 11 symbols"

        out_dir = tmp_path / "export"
        (out_dir / "CommonModules").mkdir(parents=True)
        (out_dir / "CommonModules" / "TestModule.bsl").write_text("Procedure Test() EndProcedure", encoding="utf-8")

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(out_dir),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов. Индекс: 11 символов."
        deps["manager"].call_tool.assert_awaited_once_with(
            "did_change_watched_files",
            {"language": "bsl", "changes_json": "[]"},
        )

    @pytest.mark.asyncio
    async def test_local_export_handles_index_exception(self, tmp_path):
        deps = _deps()
        deps["build_index"] = MagicMock(side_effect=RuntimeError("broken index"))

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов."
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["status"] == "error"
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["result"] == "ERROR: broken index"

    @pytest.mark.asyncio
    async def test_local_export_handles_build_index_fallback_exception(self, tmp_path):
        deps = _deps()

        with patch(
            "gateway.tool_handlers.export.build_index_with_fallback",
            side_effect=RuntimeError("fallback boom"),
        ):
            result = await run_export_bsl(
                connection="Srvr=localhost;Ref=base;",
                output_dir=str(tmp_path / "export"),
                settings=_settings(export_host_url="", allow_container_designer_export=True),
                **deps,
            )

        assert result == "Выгрузка завершена: ? BSL файлов."
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["status"] == "error"
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["result"] == "fallback boom"

    @pytest.mark.asyncio
    async def test_local_export_sets_index_error_when_build_index_returns_error(self, tmp_path):
        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "ERROR: no symbols"

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов."
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["status"] == "error"

    @pytest.mark.asyncio
    async def test_local_export_ignores_cleanup_errors(self, tmp_path):
        deps = _deps()
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 1 symbols"

        out_dir = tmp_path / "export"
        out_dir.mkdir()
        (out_dir / "old.txt").write_text("x", encoding="utf-8")

        with patch("pathlib.Path.unlink", side_effect=OSError("boom")):
            result = await run_export_bsl(
                connection="Srvr=localhost;Ref=base;",
                output_dir=str(out_dir),
                settings=_settings(export_host_url="", allow_container_designer_export=True),
                **deps,
            )

        assert "Индекс: 1 символов." in result

    @pytest.mark.asyncio
    async def test_local_export_ignores_lsp_notify_failure(self, tmp_path):
        deps = _deps()
        deps["manager"].has_tool.return_value = True
        deps["manager"].call_tool = AsyncMock(side_effect=RuntimeError("boom"))
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 1 symbols"

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Индекс: 1 символов." in result

    @pytest.mark.asyncio
    async def test_local_export_retries_with_matching_server_version(self, tmp_path):
        deps = _deps()
        deps["find_binaries"] = lambda: {
            "8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
            "8.3.28.1000": Path("/opt/1cv8/x86_64/8.3.28.1000/1cv8"),
        }
        deps["pick_binary"] = lambda _ver: Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")
        deps["run_designer_export_fn"] = AsyncMock(
            side_effect=[
                (1, "Version mismatch (8.3.27.2074 - 8.3.28.1000)"),
                (0, ""),
            ]
        )
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 12 symbols"

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Выгрузка завершена: ? BSL файлов. Индекс: 12 символов."
        assert deps["run_designer_export_fn"].await_count == 2
        assert str(deps["run_designer_export_fn"].await_args_list[1].args[0]).endswith("8.3.28.1000/1cv8")

    @pytest.mark.asyncio
    async def test_local_export_reports_missing_matching_platform(self, tmp_path):
        deps = _deps()
        deps["find_binaries"] = lambda: {"8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")}
        deps["pick_binary"] = lambda _ver: Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")
        deps["run_designer_export_fn"] = AsyncMock(
            return_value=(1, "Version mismatch (8.3.27.2074 - 8.3.29.1)")
        )

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Server version: 8.3.29.1" in result
        assert "Installed 1cv8 versions: 8.3.27.2074" in result

    @pytest.mark.asyncio
    async def test_local_export_version_mismatch_without_alternate_binary_falls_to_generic_error(self, tmp_path):
        deps = _deps()
        deps["find_binaries"] = lambda: {"8.3.27.2074": Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")}
        deps["pick_binary"] = lambda _ver: Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8")
        deps["run_designer_export_fn"] = AsyncMock(
            return_value=(1, "Version mismatch (8.3.27.2074 - 8.3.27.2074)")
        )

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result.startswith("Export failed (rc=1):")

    @pytest.mark.asyncio
    async def test_local_export_reports_license_error(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(1, "License not found"))

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "лицензия 1С не найдена" in result

    @pytest.mark.asyncio
    async def test_local_export_license_error_reuses_cached_index_when_available(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(1, "License not found"))
        deps["build_index"] = lambda *_args, **_kwargs: "Indexed 220968 symbols from cached snapshot"
        deps["get_session_active"] = lambda: SimpleNamespace(lsp_container="mcp-lsp-z01")

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Свежая выгрузка недоступна" in result
        assert "сохранённый BSL индекс" in result
        assert "220968 символов" in result
        assert deps["index_jobs"]["Srvr=localhost;Ref=base;"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_local_export_reports_segfault(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(139, "segfault"))

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert "Segmentation fault" in result
        assert "8.3.27.2074" in result

    @pytest.mark.asyncio
    async def test_local_export_reports_generic_failure(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(return_value=(5, "boom"))

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "Export failed (rc=5):\nboom"

    @pytest.mark.asyncio
    async def test_local_export_handles_timeout(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(side_effect=TimeoutError())

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True, bsl_export_timeout=900),
            **deps,
        )

        assert result == "ERROR: 1cv8 DESIGNER timed out after 15 minutes"

    @pytest.mark.asyncio
    async def test_local_export_handles_unexpected_exception(self, tmp_path):
        deps = _deps()
        deps["run_designer_export_fn"] = AsyncMock(side_effect=RuntimeError("unexpected"))

        result = await run_export_bsl(
            connection="Srvr=localhost;Ref=base;",
            output_dir=str(tmp_path / "export"),
            settings=_settings(export_host_url="", allow_container_designer_export=True),
            **deps,
        )

        assert result == "ERROR: unexpected"


class TestRunDesignerExport:
    @pytest.mark.asyncio
    async def test_run_designer_export_executes_and_reads_log(self, tmp_path):
        log_path = tmp_path / "out.log"

        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0

        def fake_mkstemp(suffix=".log"):
            log_path.write_text("done", encoding="utf-8")
            return (123, str(log_path))

        async def fake_wait_for(awaitable, timeout):
            return await awaitable

        with patch("gateway.tool_handlers.export.tempfile.mkstemp", side_effect=fake_mkstemp), \
             patch("gateway.tool_handlers.export.os.close"), \
             patch("gateway.tool_handlers.export.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as create_proc, \
             patch("gateway.tool_handlers.export.asyncio.wait_for", new=AsyncMock(side_effect=fake_wait_for)), \
             patch("gateway.tool_handlers.export.os.unlink"):
            rc, log_output = await run_designer_export(
                Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
                ["/S", "srv\\base"],
                "/tmp/out",
                timeout=30,
                default_timeout=60,
                logger=MagicMock(),
            )

        assert rc == 0
        assert log_output == "done"
        assert create_proc.await_count == 1

    @pytest.mark.asyncio
    async def test_run_designer_export_ignores_log_read_and_unlink_failures(self, tmp_path):
        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 5

        async def fake_wait_for(awaitable, timeout):
            return await awaitable

        with patch("gateway.tool_handlers.export.tempfile.mkstemp", return_value=(123, str(tmp_path / "out.log"))), \
             patch("gateway.tool_handlers.export.os.close"), \
             patch("gateway.tool_handlers.export.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)), \
             patch("gateway.tool_handlers.export.asyncio.wait_for", new=AsyncMock(side_effect=fake_wait_for)), \
             patch("builtins.open", side_effect=OSError("boom")), \
             patch("gateway.tool_handlers.export.os.unlink", side_effect=OSError("boom")):
            rc, log_output = await run_designer_export(
                Path("/opt/1cv8/x86_64/8.3.27.2074/1cv8"),
                ["/S", "srv\\base"],
                "/tmp/out",
                timeout=None,
                default_timeout=60,
                logger=MagicMock(),
            )

        assert rc == 5
        assert log_output == ""

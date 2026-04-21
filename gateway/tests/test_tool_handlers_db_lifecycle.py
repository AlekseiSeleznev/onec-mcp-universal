"""Tests for gateway.tool_handlers.db_lifecycle."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.db_lifecycle import connect_database, disconnect_database


_DB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")


class TestConnectDatabaseHandler:
    @pytest.mark.asyncio
    async def test_empty_name_returns_error(self):
        result = await connect_database(
            name="",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/projects/ERP",
            registry=MagicMock(),
            manager=MagicMock(),
            db_name_re=_DB_NAME_RE,
            slugify=lambda s: s,
            start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
            start_lsp=lambda *_: "mcp-lsp-ERP",
            http_backend_factory=lambda *_: object(),
            stdio_backend_factory=lambda *_: object(),
        )
        assert result == "ERROR: Database name cannot be empty."

    @pytest.mark.asyncio
    async def test_invalid_slug_returns_error(self):
        result = await connect_database(
            name="!!!",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/projects/ERP",
            registry=MagicMock(),
            manager=MagicMock(),
            db_name_re=_DB_NAME_RE,
            slugify=lambda _: "",
            start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
            start_lsp=lambda *_: "mcp-lsp-ERP",
            http_backend_factory=lambda *_: object(),
            stdio_backend_factory=lambda *_: object(),
        )
        assert result.startswith("ERROR: Invalid database name '!!!'")

    @pytest.mark.asyncio
    async def test_success_connects_and_switches(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        # Pretend project_path exists as a non-empty directory so LSP starts.
        import stat as _stat
        fake_stat = SimpleNamespace(st_mode=_stat.S_IFDIR | 0o755)
        fake_scandir = MagicMock()
        fake_scandir.__enter__ = MagicMock(return_value=iter([MagicMock()]))
        fake_scandir.__exit__ = MagicMock(return_value=False)

        with patch("gateway.tool_handlers.db_lifecycle.os.stat", return_value=fake_stat), \
             patch("gateway.tool_handlers.db_lifecycle.os.scandir", return_value=fake_scandir):
            result = await connect_database(
                name="ERP",
                connection="Srvr=srv;Ref=ERP;",
                project_path="/projects/ERP",
                registry=registry,
                manager=manager,
                db_name_re=_DB_NAME_RE,
                slugify=lambda s: s.lower(),
                start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
                start_lsp=lambda *_: "mcp-lsp-ERP",
                http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
                stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
            )

        assert "Database 'ERP' connected successfully." in result
        assert db_info.toolkit_url == "http://localhost:6101/mcp"
        assert db_info.lsp_container == "mcp-lsp-ERP"
        manager.add_db_backends.assert_awaited_once()
        args = manager.add_db_backends.await_args.args
        lsp_backend = args[2]
        assert lsp_backend == (
            "stdio",
            "mcp-lsp-ERP",
            "docker",
            ["exec", "-i", "mcp-lsp-ERP", "sh", "-lc", "cd /projects && exec mcp-lsp-bridge"],
        )
        manager.switch_db.assert_called_once_with("ERP")
        registry.switch.assert_called_once_with("ERP")

    @pytest.mark.asyncio
    async def test_rolls_back_registry_on_start_failure(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.remove = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()

        def _fail_start(_):
            raise RuntimeError("toolkit unavailable")

        result = await connect_database(
            name="ERP",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/projects/ERP",
            registry=registry,
            manager=manager,
            db_name_re=_DB_NAME_RE,
            slugify=lambda s: s.lower(),
            start_toolkit=_fail_start,
            start_lsp=lambda *_: "mcp-lsp-ERP",
            http_backend_factory=lambda *_: object(),
            stdio_backend_factory=lambda *_: object(),
        )

        assert "ERROR connecting database 'ERP': toolkit unavailable" in result
        registry.remove.assert_called_once_with("ERP")
        manager.add_db_backends.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_without_lsp_container_adds_only_toolkit_backend(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        result = await connect_database(
            name="ERP",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/projects/ERP",
            registry=registry,
            manager=manager,
            db_name_re=_DB_NAME_RE,
            slugify=lambda s: s.lower(),
            start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
            start_lsp=lambda *_: "",
            http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
            stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
        )

        assert "Database 'ERP' connected successfully." in result
        assert manager.add_db_backends.await_args.args[2] is None

    @pytest.mark.asyncio
    async def test_explicit_lsp_backend_factory_overrides_stdio_alias(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        import stat as _stat
        fake_stat = SimpleNamespace(st_mode=_stat.S_IFDIR | 0o755)
        fake_scandir = MagicMock()
        fake_scandir.__enter__ = MagicMock(return_value=iter([MagicMock()]))
        fake_scandir.__exit__ = MagicMock(return_value=False)

        with patch("gateway.tool_handlers.db_lifecycle.os.stat", return_value=fake_stat), \
             patch("gateway.tool_handlers.db_lifecycle.os.scandir", return_value=fake_scandir):
            result = await connect_database(
                name="ERP",
                connection="Srvr=srv;Ref=ERP;",
                project_path="/projects/ERP",
                registry=registry,
                manager=manager,
                db_name_re=_DB_NAME_RE,
                slugify=lambda s: s.lower(),
                start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
                start_lsp=lambda *_: "mcp-lsp-ERP",
                http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
                lsp_backend_factory=lambda name, slug, project_path: ("lsp", name, slug, project_path),
                stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
            )

        assert "Database 'ERP' connected successfully." in result
        assert manager.add_db_backends.await_args.args[2] == ("lsp", "mcp-lsp-ERP", "ERP", "/projects/ERP")

    @pytest.mark.asyncio
    async def test_hostfs_home_path_starts_lsp_even_when_gateway_cannot_stat_it(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        with patch("gateway.tool_handlers.db_lifecycle.os.stat", side_effect=FileNotFoundError):
            result = await connect_database(
                name="ERP",
                connection="Srvr=srv;Ref=ERP;",
                project_path="/hostfs-home/as/Z/ERP",
                registry=registry,
                manager=manager,
                db_name_re=_DB_NAME_RE,
                slugify=lambda s: s.lower(),
                start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
                start_lsp=lambda *_: "mcp-lsp-ERP",
                http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
                stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
            )

        assert "Database 'ERP' connected successfully." in result
        assert manager.add_db_backends.await_args.args[2] == (
            "stdio",
            "mcp-lsp-ERP",
            "docker",
            ["exec", "-i", "mcp-lsp-ERP", "sh", "-lc", "cd /projects && exec mcp-lsp-bridge"],
        )

    @pytest.mark.asyncio
    async def test_explicit_lsp_backend_factory_receives_project_path(self):
        db_info = SimpleNamespace(toolkit_port=0, toolkit_url="", lsp_container="", slug="ERP")
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        import stat as _stat
        fake_stat = SimpleNamespace(st_mode=_stat.S_IFDIR | 0o755)
        fake_scandir = MagicMock()
        fake_scandir.__enter__ = MagicMock(return_value=iter([MagicMock()]))
        fake_scandir.__exit__ = MagicMock(return_value=False)

        with patch("gateway.tool_handlers.db_lifecycle.os.stat", return_value=fake_stat), \
             patch("gateway.tool_handlers.db_lifecycle.os.scandir", return_value=fake_scandir):
            await connect_database(
                name="ERP",
                connection="Srvr=srv;Ref=ERP;",
                project_path="/workspace/ERP",
                registry=registry,
                manager=manager,
                db_name_re=_DB_NAME_RE,
                slugify=lambda s: s.lower(),
                start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
                start_lsp=lambda *_: "mcp-lsp-ERP",
                http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
                lsp_backend_factory=lambda name, slug, project_path: ("lsp", name, slug, project_path),
                stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
            )

        assert manager.add_db_backends.await_args.args[2] == ("lsp", "mcp-lsp-ERP", "ERP", "/workspace/ERP")

    @pytest.mark.asyncio
    async def test_reuses_live_channel_and_arms_unregister_grace_for_connected_epf(self):
        db_info = SimpleNamespace(
            toolkit_port=0,
            toolkit_url="",
            lsp_container="",
            slug="ERP",
            channel_id="live-z01",
            connected=True,
        )
        registry = MagicMock()
        registry.register.return_value = db_info
        registry.switch = MagicMock(return_value=True)
        registry.arm_unregister_grace = MagicMock(return_value=True)
        manager = MagicMock()
        manager.add_db_backends = AsyncMock()
        manager.switch_db = MagicMock(return_value=True)

        result = await connect_database(
            name="ERP",
            connection="Srvr=srv;Ref=ERP;",
            project_path="/projects/ERP",
            registry=registry,
            manager=manager,
            db_name_re=_DB_NAME_RE,
            slugify=lambda s: s.lower(),
            start_toolkit=lambda _: (6101, "onec-toolkit-ERP"),
            start_lsp=lambda *_: "",
            http_backend_factory=lambda name, url, transport: ("http", name, url, transport),
            stdio_backend_factory=lambda name, cmd, args: ("stdio", name, cmd, args),
        )

        assert "Database 'ERP' connected successfully." in result
        assert db_info.toolkit_url == "http://localhost:6101/mcp?channel=live-z01"
        assert manager.add_db_backends.await_args.args[1] == (
            "http",
            "onec-toolkit-ERP",
            "http://localhost:6101/mcp?channel=live-z01",
            "streamable",
        )
        registry.arm_unregister_grace.assert_called_once_with("ERP", 15.0)


class TestDisconnectDatabaseHandler:
    @pytest.mark.asyncio
    async def test_unknown_db_returns_error(self):
        registry = MagicMock()
        registry.get.return_value = None
        manager = MagicMock()
        manager.remove_db_backends = AsyncMock()

        result = await disconnect_database(
            name="ghost",
            registry=registry,
            manager=manager,
            stop_db_containers=lambda _: None,
        )

        assert result == "ERROR: Database 'ghost' not found."

    @pytest.mark.asyncio
    async def test_success_disconnects_everything(self):
        registry = MagicMock()
        registry.get.return_value = SimpleNamespace(slug="ERP")
        registry.mark_epf_disconnected = MagicMock(return_value=True)
        manager = MagicMock()
        manager.remove_db_backends = AsyncMock()

        stopped: list[str] = []

        def _stop(slug: str):
            stopped.append(slug)

        result = await disconnect_database(
            name="ERP",
            registry=registry,
            manager=manager,
            stop_db_containers=_stop,
            mark_epf_disconnected=registry.mark_epf_disconnected,
        )

        assert result == "Database 'ERP' disconnected, runtime stopped but registry entry kept."
        assert stopped == ["ERP"]
        manager.remove_db_backends.assert_awaited_once_with("ERP")
        registry.mark_epf_disconnected.assert_called_once_with("ERP")

    @pytest.mark.asyncio
    async def test_stop_error_propagates(self):
        registry = MagicMock()
        registry.get.return_value = SimpleNamespace(slug="ERP")
        manager = MagicMock()
        manager.remove_db_backends = AsyncMock()

        def _stop(_slug: str):
            raise RuntimeError("docker failed")

        result = await disconnect_database(
            name="ERP",
            registry=registry,
            manager=manager,
            stop_db_containers=_stop,
        )

        assert result == "ERROR disconnecting database 'ERP': docker failed"
        manager.remove_db_backends.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_reports_sidecar_config_error_when_runtime_stop_cannot_fallback(self):
        import gateway.docker_manager as docker_manager

        registry = MagicMock()
        registry.get.return_value = SimpleNamespace(slug="ERP")
        manager = MagicMock()
        manager.remove_db_backends = AsyncMock()

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch(
            "gateway.docker_manager._stop_db_containers_direct",
            side_effect=RuntimeError("docker SDK is not available"),
        ):
            result = await disconnect_database(
                name="ERP",
                registry=registry,
                manager=manager,
                stop_db_containers=docker_manager.stop_db_containers,
            )

        assert result == "ERROR disconnecting database 'ERP': DOCKER_CONTROL_TOKEN is not configured."
        manager.remove_db_backends.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_skips_epf_marker_when_callback_missing(self):
        registry = MagicMock()
        registry.get.return_value = SimpleNamespace(slug="ERP")
        manager = MagicMock()
        manager.remove_db_backends = AsyncMock()

        result = await disconnect_database(
            name="ERP",
            registry=registry,
            manager=manager,
            stop_db_containers=lambda _: None,
            mark_epf_disconnected=None,
        )

        assert result == "Database 'ERP' disconnected, runtime stopped but registry entry kept."
        manager.remove_db_backends.assert_awaited_once_with("ERP")

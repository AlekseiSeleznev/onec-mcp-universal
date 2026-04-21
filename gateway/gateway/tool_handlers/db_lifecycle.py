"""Handlers for database connect/disconnect lifecycle tools."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from typing import Protocol
from urllib.parse import urlencode


class DbInfoLike(Protocol):
    """Minimal registry DB-info shape used by connect_database."""

    toolkit_port: int
    toolkit_url: str
    lsp_container: str
    slug: str


class RegistryLike(Protocol):
    """Registry methods used by db lifecycle handlers."""

    def register(self, name: str, connection: str, project_path: str, slug: str = "") -> DbInfoLike: ...
    def remove(self, name: str) -> bool: ...
    def switch(self, name: str) -> bool: ...
    def get(self, name: str): ...
    def arm_unregister_grace(self, name: str, seconds: float) -> bool: ...


class ManagerLike(Protocol):
    """Manager methods used by db lifecycle handlers."""

    async def add_db_backends(self, db_name: str, toolkit, lsp=None) -> None: ...
    async def remove_db_backends(self, db_name: str) -> None: ...
    def switch_db(self, db_name: str, session_id: str | None = None) -> bool: ...


def _project_path_needs_hostfs_probe_fallback(project_path: str) -> bool:
    normalized = (project_path or "").strip()
    return normalized.startswith("/hostfs-home/") or normalized.startswith("/hostfs/")


async def connect_database(
    name: str,
    connection: str,
    project_path: str,
    registry: RegistryLike,
    manager: ManagerLike,
    db_name_re: re.Pattern[str],
    slugify: Callable[[str], str],
    start_toolkit: Callable[[str], tuple[int, str]],
    start_lsp: Callable[[str, str], str | None],
    http_backend_factory: Callable[[str, str, str], object],
    lsp_backend_factory: Callable[[str, str, str], object] | None = None,
    stdio_backend_factory: Callable[[str, str, list[str]], object] | None = None,
) -> str:
    """Connect DB: start containers, wire MCP backends, and activate DB in registry/manager."""
    if not name or not name.strip():
        return "ERROR: Database name cannot be empty."

    slug = name if db_name_re.match(name) else slugify(name)
    if not slug or not db_name_re.match(slug):
        return (
            f"ERROR: Invalid database name '{name}'. Must contain at least one alphanumeric character."
        )

    try:
        db_info = registry.register(name, connection, project_path, slug=slug)

        loop = asyncio.get_running_loop()
        try:
            toolkit_port, _toolkit_container = await asyncio.wait_for(
                loop.run_in_executor(None, start_toolkit, slug),
                timeout=120,
            )
            # Registration and BSL export are separate flows:
            # start LSP only when sources already exist in the workspace path.
            # If not, LSP is started later by the export handler after DumpConfigToFiles completes.
            # Decide whether to start LSP now or defer until the first export.
            # Gateway may run as non-root (uid 10001) and lack traverse rights
            # on user home dirs; in that case we delegate the decision to
            # docker-control (runs as root) which will validate the path and
            # skip LSP if it's empty.
            has_sources = True
            try:
                import stat as _stat_mod
                st_result = os.stat(project_path)
                if _stat_mod.S_ISDIR(st_result.st_mode):
                    with os.scandir(project_path) as it:
                        has_sources = any(True for _ in it)
                else:
                    has_sources = False
            except PermissionError:
                # Defer to docker-control which can read the path as root.
                has_sources = True
            except FileNotFoundError:
                has_sources = _project_path_needs_hostfs_probe_fallback(project_path)
            except OSError:
                has_sources = False
            if has_sources:
                lsp_container = await asyncio.wait_for(
                    loop.run_in_executor(None, start_lsp, slug, project_path),
                    timeout=60,
                )
            else:
                lsp_container = None
        except Exception:
            registry.remove(name)
            raise

        toolkit_internal_url = f"http://localhost:{toolkit_port}/mcp"
        channel_id = (getattr(db_info, "channel_id", "") or "default").strip() or "default"
        if channel_id != "default":
            toolkit_internal_url = f"{toolkit_internal_url}?{urlencode({'channel': channel_id})}"
        db_info.toolkit_port = toolkit_port
        db_info.toolkit_url = toolkit_internal_url
        db_info.lsp_container = lsp_container or ""
        if getattr(db_info, "connected", False) and hasattr(registry, "arm_unregister_grace"):
            registry.arm_unregister_grace(name, 15.0)

        toolkit_backend = http_backend_factory(
            f"onec-toolkit-{slug}",
            toolkit_internal_url,
            "streamable",
        )
        backend_factory = lsp_backend_factory
        if backend_factory is None and stdio_backend_factory is not None:
            backend_factory = lambda backend_name, backend_slug, _project_path: stdio_backend_factory(
                backend_name,
                "docker",
                ["exec", "-i", f"mcp-lsp-{backend_slug}", "sh", "-lc", "cd /projects && exec mcp-lsp-bridge"],
            )
        lsp_backend = None
        if lsp_container and backend_factory is not None:
            lsp_backend = backend_factory(
                f"mcp-lsp-{slug}",
                slug,
                project_path,
            )

        await manager.add_db_backends(name, toolkit_backend, lsp_backend)
        manager.switch_db(name)
        registry.switch(name)

        return (
            f"Database '{name}' connected successfully.\n"
            f"  onec-toolkit: {db_info.toolkit_url}\n"
            f"  LSP container: {lsp_container}\n"
            f"  BSL workspace: {project_path}\n\n"
            f"Next steps:\n"
            f"1. In the 1C EPF, set database name to '{name}' and press 'Подключить к прокси'\n"
            f"2. Press 'Выгрузить BSL' to export sources to {project_path}\n"
            f"3. BSL navigation will be available after indexing completes"
        )
    except Exception as exc:
        return f"ERROR connecting database '{name}': {exc}"


async def disconnect_database(
    name: str,
    registry: RegistryLike,
    manager: ManagerLike,
    stop_db_containers: Callable[[str], None],
    mark_epf_disconnected: Callable[[str], bool] | None = None,
) -> str:
    """Soft-disconnect DB: stop containers and backends, keep registry entry intact."""
    db = registry.get(name)
    if not db:
        return f"ERROR: Database '{name}' not found."

    slug = db.slug or name
    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, stop_db_containers, slug),
            timeout=30,
        )
        await manager.remove_db_backends(name)
        if mark_epf_disconnected is not None:
            mark_epf_disconnected(name)
        return f"Database '{name}' disconnected, runtime stopped but registry entry kept."
    except Exception as exc:
        return f"ERROR disconnecting database '{name}': {exc}"

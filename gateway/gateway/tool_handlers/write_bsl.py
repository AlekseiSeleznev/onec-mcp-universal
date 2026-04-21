"""Handler for write_bsl MCP tool."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol


class ActiveDbRef(Protocol):
    """Minimal shape of active DB object used by write_bsl."""

    lsp_container: str
    project_path: str


async def write_bsl(
    file: str,
    content: str,
    get_active: Callable[[], ActiveDbRef | None],
    has_tool: Callable[[str], bool],
    call_tool: Callable[[str, dict], Awaitable[object]],
    write_via_runtime: Callable[[str, str, str], str] | None = None,
) -> str:
    """Write BSL file to the active DB workspace and trigger reindex when possible."""
    active = get_active()
    if not active:
        return "ERROR: No active database. Connect a database first."

    container = active.lsp_container
    if not container:
        return "ERROR: No LSP container for active database."

    safe_file = os.path.normpath(file.lstrip("/"))
    if safe_file.startswith(".."):
        return "ERROR: Invalid file path — must be relative within the project."

    project_path = (getattr(active, "project_path", "") or "").strip()
    if not project_path:
        return "ERROR: No project path for active database."

    file_path = str(Path(project_path) / safe_file)
    try:
        runtime_managed_path = project_path.startswith(("/hostfs-home/", "/workspace/", "/projects"))
        if runtime_managed_path and write_via_runtime is not None:
            write_via_runtime(container, safe_file, content)
        else:
            path_obj = Path(file_path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(content, encoding="utf-8-sig")

        if has_tool("did_change_watched_files"):
            try:
                await call_tool("did_change_watched_files", {"language": "bsl", "changes_json": "[]"})
            except Exception:
                pass

        return f"Written {len(content)} chars to {file_path}."
    except Exception as exc:
        return f"ERROR writing file: {exc}"

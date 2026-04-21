"""Handler for reindex_bsl MCP tool."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol


class ActiveDbRef(Protocol):
    """Minimal shape of active DB object used by reindex_bsl."""

    name: str
    project_path: str
    lsp_container: str


async def reindex_bsl(
    path: str,
    get_active: Callable[[], ActiveDbRef | None],
    has_tool: Callable[[str], bool],
    call_tool: Callable[[str, dict], Awaitable[object]],
    build_search_index: Callable[[str, str], str],
) -> str:
    """Rebuild full-text BSL index and trigger LSP reindex when available."""
    active = get_active()
    if not active:
        return "ERROR: No active database. Connect a database first."

    reindex_path = path.strip() if path else getattr(active, "project_path", "").strip() or "/projects"
    search_result = build_search_index(reindex_path, getattr(active, "lsp_container", ""))
    if search_result.startswith("ERROR"):
        return search_result

    lsp_message = "LSP backend not available — full-text index rebuilt only."
    if not has_tool("did_change_watched_files"):
        return f"{search_result}\n{lsp_message}"
    try:
        result = await call_tool("did_change_watched_files", {"language": "bsl", "changes_json": "[]"})
        response_text = result.content[0].text if result.content else ""
        return f"{search_result}\nRe-indexing triggered for '{active.name}' at {reindex_path}.\n{response_text}"
    except Exception as exc:
        return f"{search_result}\nERROR triggering LSP re-index: {exc}"

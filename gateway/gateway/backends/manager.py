import asyncio
import logging

from mcp.types import CallToolResult, Tool

from .base import BackendBase

logger = logging.getLogger(__name__)

# Tool names that belong to database-specific backends
TOOLKIT_TOOL_NAMES = {
    "execute_query", "execute_code", "get_metadata", "get_event_log",
    "get_object_by_link", "get_link_of_object", "find_references_to_object",
    "get_access_rights",
}
LSP_TOOL_NAMES = {
    "symbol_explore", "definition", "hover", "call_hierarchy", "call_graph",
    "document_diagnostics", "project_analysis", "code_actions", "rename",
    "prepare_rename", "get_range_content", "selection_range",
    "did_change_watched_files", "lsp_status",
}


class BackendManager:
    def __init__(self) -> None:
        self._backends: list[BackendBase] = []
        self._tool_map: dict[str, BackendBase] = {}

        # Per-database backends: {db_name: {"toolkit": backend, "lsp": backend}}
        self._db_backends: dict[str, dict[str, BackendBase]] = {}
        self._active_db: str | None = None

    async def start_all(self, backends: list[BackendBase]) -> None:
        async def _safe_start(b: BackendBase) -> None:
            try:
                await b.start()
                for tool in b.tools:
                    self._tool_map[tool.name] = b
                self._backends.append(b)
            except Exception as exc:
                logger.error(f"[{b.name}] failed to start: {exc}")

        await asyncio.gather(*[_safe_start(b) for b in backends])

    async def stop_all(self) -> None:
        async def _safe_stop(b: BackendBase) -> None:
            try:
                await b.stop()
            except Exception as exc:
                logger.warning(f"[{b.name}] error during stop: {exc}")

        all_backends = list(self._backends)
        for db_backends in self._db_backends.values():
            all_backends.extend(db_backends.values())
        await asyncio.gather(*[_safe_stop(b) for b in all_backends])

    async def add_db_backends(
        self, db_name: str, toolkit: BackendBase, lsp: BackendBase
    ) -> None:
        """Start and register per-database toolkit + LSP backends."""
        async def _safe_start(b: BackendBase) -> None:
            try:
                await b.start()
                logger.info(f"[{b.name}] started with {len(b.tools)} tools")
            except Exception as exc:
                logger.error(f"[{b.name}] failed to start: {exc}")

        await asyncio.gather(_safe_start(toolkit), _safe_start(lsp))
        self._db_backends[db_name] = {"toolkit": toolkit, "lsp": lsp}

        # If no active db yet — set this one
        if self._active_db is None:
            self._active_db = db_name
            self._update_db_tool_map(db_name)

    async def remove_db_backends(self, db_name: str) -> None:
        if db_name not in self._db_backends:
            return
        db = self._db_backends.pop(db_name)
        for b in db.values():
            try:
                await b.stop()
            except Exception:
                pass
        if self._active_db == db_name:
            self._active_db = next(iter(self._db_backends), None)
            if self._active_db:
                self._update_db_tool_map(self._active_db)

    def switch_db(self, db_name: str) -> bool:
        if db_name not in self._db_backends:
            return False
        self._active_db = db_name
        self._update_db_tool_map(db_name)
        logger.info(f"Active database switched to: {db_name}")
        return True

    def _update_db_tool_map(self, db_name: str) -> None:
        db = self._db_backends.get(db_name, {})
        toolkit = db.get("toolkit")
        lsp = db.get("lsp")
        if toolkit:
            for name in TOOLKIT_TOOL_NAMES:
                self._tool_map[name] = toolkit
        if lsp:
            for name in LSP_TOOL_NAMES:
                self._tool_map[name] = lsp

    def get_all_tools(self) -> list[Tool]:
        tools = [t for b in self._backends for t in b.tools if b.available]
        if self._active_db and self._active_db in self._db_backends:
            for b in self._db_backends[self._active_db].values():
                if b.available:
                    tools.extend(b.tools)
        return tools

    def has_tool(self, name: str) -> bool:
        return name in self._tool_map

    def get_backend_for_tool(self, name: str) -> BackendBase | None:
        return self._tool_map.get(name)

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        backend = self._tool_map.get(name)
        if backend is None:
            raise ValueError(f"Unknown tool: {name!r}")
        return await backend.call_tool(name, arguments)

    def status(self) -> dict:
        result = {
            b.name: {"ok": b.available, "tools": len(b.tools)}
            for b in self._backends
        }
        for db_name, db in self._db_backends.items():
            for role, b in db.items():
                result[f"{db_name}/{role}"] = {
                    "ok": b.available,
                    "tools": len(b.tools),
                    "active": db_name == self._active_db,
                }
        return result

    @property
    def active_db(self) -> str | None:
        return self._active_db

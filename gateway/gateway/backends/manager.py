import asyncio
import logging
import time

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
DB_TOOL_NAMES = TOOLKIT_TOOL_NAMES | LSP_TOOL_NAMES

_SESSION_CLEANUP_INTERVAL = 3600  # cleanup stale sessions every hour
_SESSION_MAX_AGE = 28800  # 8 hours idle timeout


class BackendManager:
    def __init__(self) -> None:
        self._backends: list[BackendBase] = []
        self._tool_map: dict[str, BackendBase] = {}

        # Per-database backends: {db_name: {"toolkit": backend, "lsp": backend}}
        self._db_backends: dict[str, dict[str, BackendBase]] = {}
        self._default_db: str | None = None  # global default for new sessions

        # Per-session active DB: {session_id: (db_name, last_access_time)}
        self._session_db: dict[str, tuple[str, float]] = {}

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

        # If no default db yet — set this one
        if self._default_db is None:
            self._default_db = db_name

    async def remove_db_backends(self, db_name: str) -> None:
        if db_name not in self._db_backends:
            return
        db = self._db_backends.pop(db_name)
        for b in db.values():
            try:
                await b.stop()
            except Exception:
                pass
        # Clean session references to this DB
        stale = [sid for sid, (dn, _) in self._session_db.items() if dn == db_name]
        for sid in stale:
            del self._session_db[sid]
        if self._default_db == db_name:
            self._default_db = next(iter(self._db_backends), None)

    def switch_db(self, db_name: str, session_id: str | None = None) -> bool:
        """Switch active DB. If session_id given, only for that session."""
        if db_name not in self._db_backends:
            return False
        if session_id:
            self._session_db[session_id] = (db_name, time.monotonic())
            logger.info(f"Session {session_id[:8]}... switched to: {db_name}")
        else:
            self._default_db = db_name
            logger.info(f"Default database switched to: {db_name}")
        return True

    def set_default_db(self, db_name: str) -> bool:
        """Set global default DB (for new sessions and dashboard)."""
        if db_name not in self._db_backends:
            return False
        self._default_db = db_name
        return True

    def get_active_db(self, session_id: str | None = None) -> str | None:
        """Get active DB for a session, falling back to default."""
        if session_id and session_id in self._session_db:
            db_name, _ = self._session_db[session_id]
            self._session_db[session_id] = (db_name, time.monotonic())
            if db_name in self._db_backends:
                return db_name
        return self._default_db

    def get_all_tools(self) -> list[Tool]:
        """Return tools from static backends + one set of DB tools (from any connected DB)."""
        tools = [t for b in self._backends for t in b.tools if b.available]
        # Add DB-specific tools from any connected DB (schemas are identical across DBs)
        if self._db_backends:
            sample_db = next(iter(self._db_backends.values()))
            for b in sample_db.values():
                if b.available:
                    tools.extend(b.tools)
        return tools

    def has_tool(self, name: str) -> bool:
        if name in self._tool_map:
            return True
        return name in DB_TOOL_NAMES and bool(self._db_backends)

    def get_backend_for_tool(self, name: str, session_id: str | None = None) -> BackendBase | None:
        """Get backend for a tool, routing DB tools to the session's active DB."""
        if name in DB_TOOL_NAMES:
            db_name = self.get_active_db(session_id)
            if db_name and db_name in self._db_backends:
                db = self._db_backends[db_name]
                if name in TOOLKIT_TOOL_NAMES:
                    return db.get("toolkit")
                if name in LSP_TOOL_NAMES:
                    return db.get("lsp")
        return self._tool_map.get(name)

    async def call_tool(self, name: str, arguments: dict, session_id: str | None = None) -> CallToolResult:
        backend = self.get_backend_for_tool(name, session_id)
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
                    "default": db_name == self._default_db,
                }
        return result

    def cleanup_stale_sessions(self) -> int:
        """Remove sessions idle for more than _SESSION_MAX_AGE."""
        now = time.monotonic()
        stale = [sid for sid, (_, ts) in self._session_db.items()
                 if now - ts > _SESSION_MAX_AGE]
        for sid in stale:
            del self._session_db[sid]
        return len(stale)

    @property
    def active_db(self) -> str | None:
        return self._default_db

    @property
    def session_count(self) -> int:
        return len(self._session_db)

import asyncio
import logging
import time

from mcp.types import CallToolResult, Tool

from .base import BackendBase

logger = logging.getLogger(__name__)

# Legacy tool-name groups kept for tests/docs only.
# Runtime routing below is dynamic and reads actual tool lists from connected DB backends.
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
            except Exception as exc:
                logger.error(f"[{b.name}] failed to start: {exc}")

        for backend in backends:
            if backend not in self._backends:
                self._backends.append(backend)
        await asyncio.gather(*[_safe_start(b) for b in backends])

    async def retry_unavailable_backends(self) -> int:
        """Retry static backends that were configured but failed to start earlier."""
        recovered = 0
        for backend in self._backends:
            if backend.available:
                continue
            try:
                await backend.start()
                for tool in backend.tools:
                    self._tool_map[tool.name] = backend
                recovered += 1
                logger.info(f"[{backend.name}] recovered with {len(backend.tools)} tools")
            except Exception as exc:
                logger.debug(f"[{backend.name}] retry failed: {exc}")
        return recovered

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
        self, db_name: str, toolkit: BackendBase, lsp: BackendBase | None = None
    ) -> None:
        """Start and register per-database toolkit + LSP backends."""
        async def _safe_start(b: BackendBase) -> None:
            try:
                await b.start()
                logger.info(f"[{b.name}] started with {len(b.tools)} tools")
            except Exception as exc:
                logger.error(f"[{b.name}] failed to start: {exc}")

        starters = [_safe_start(toolkit)]
        if lsp is not None:
            starters.append(_safe_start(lsp))
        await asyncio.gather(*starters)
        entry: dict[str, BackendBase] = {"toolkit": toolkit}
        if lsp is not None:
            entry["lsp"] = lsp
        self._db_backends[db_name] = entry

        # If no default db yet — set this one
        if self._default_db is None:
            self._default_db = db_name

    def db_has_lsp(self, db_name: str) -> bool:
        return "lsp" in self._db_backends.get(db_name, {})

    async def detach_db_lsp(self, db_name: str) -> None:
        """Stop and remove LSP backend for a DB (used before re-attaching a fresh LSP)."""
        db = self._db_backends.get(db_name)
        if not db or "lsp" not in db:
            return
        lsp = db.pop("lsp")
        try:
            await lsp.stop()
        except Exception as exc:
            logger.warning(f"[{lsp.name}] stop during detach failed: {exc}")

    async def attach_db_lsp(self, db_name: str, lsp: BackendBase) -> None:
        """Attach LSP backend to an already-registered DB (used after deferred BSL export)."""
        if db_name not in self._db_backends:
            raise RuntimeError(f"DB {db_name!r} is not registered")
        try:
            await lsp.start()
            logger.info(f"[{lsp.name}] started with {len(lsp.tools)} tools")
        except Exception as exc:
            logger.error(f"[{lsp.name}] failed to start: {exc}")
        self._db_backends[db_name]["lsp"] = lsp

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
        """Return tools from static backends + all available DB backends."""
        tools = [t for b in self._backends for t in b.tools if b.available]
        for db_backends in self._db_backends.values():
            for b in db_backends.values():
                if b.available:
                    tools.extend(b.tools)
        return tools

    def has_db(self, name: str) -> bool:
        """Return True if the database has active backends in the manager."""
        return name in self._db_backends

    def get_db_backend(self, db_name: str, role: str) -> BackendBase | None:
        """Return a DB backend by role (e.g. toolkit/lsp) without exposing internals."""
        db = self._db_backends.get(db_name)
        if not db:
            return None
        return db.get(role)

    def has_tool(self, name: str) -> bool:
        if name in self._tool_map:
            return True
        return self._has_db_tool(name)

    def get_backend_for_tool(self, name: str, session_id: str | None = None) -> BackendBase | None:
        """Get backend for a tool, routing DB tools to the session's active DB."""
        db_name = self.get_active_db(session_id)
        if db_name and db_name in self._db_backends:
            backend = self._find_db_backend_for_tool(self._db_backends[db_name], name)
            if backend is not None:
                return backend
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
        self.forget_sessions(stale)
        return len(stale)

    def forget_sessions(self, session_ids: list[str]) -> int:
        """Remove specific session IDs from per-session DB routing state."""
        removed = 0
        for sid in session_ids:
            if sid in self._session_db:
                del self._session_db[sid]
                removed += 1
        return removed

    def _has_db_tool(self, name: str) -> bool:
        for db in self._db_backends.values():
            if self._find_db_backend_for_tool(db, name) is not None:
                return True
        return False

    @staticmethod
    def _find_db_backend_for_tool(
        db_backends: dict[str, BackendBase], name: str
    ) -> BackendBase | None:
        # Stable role order first, then any extra roles if introduced later.
        for role in ("toolkit", "lsp"):
            backend = db_backends.get(role)
            if not backend:
                continue
            if any(t.name == name for t in backend.tools):
                return backend
            if not backend.available:
                legacy_names = TOOLKIT_TOOL_NAMES if role == "toolkit" else LSP_TOOL_NAMES
                if name in legacy_names:
                    return backend
        for role, backend in db_backends.items():
            if role in {"toolkit", "lsp"}:
                continue
            if backend and any(t.name == name for t in backend.tools):
                return backend
        return None

    @property
    def active_db(self) -> str | None:
        return self._default_db

    @property
    def session_count(self) -> int:
        return len(self._session_db)

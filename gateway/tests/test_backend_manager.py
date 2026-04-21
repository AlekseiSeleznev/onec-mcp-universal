"""Tests for BackendManager."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.backends.base import BackendBase
from gateway.backends.manager import BackendManager, LSP_TOOL_NAMES, TOOLKIT_TOOL_NAMES
from mcp.types import CallToolResult, TextContent, Tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool(name: str) -> Tool:
    return Tool(name=name, description=f"Test tool {name}", inputSchema={"type": "object"})


class FakeBackend(BackendBase):
    """In-memory backend for testing."""

    def __init__(self, name: str, tool_names: list[str]):
        super().__init__(name)
        self.tools = [_make_tool(n) for n in tool_names]
        self._started = False

    async def start(self) -> None:
        self._started = True
        self.available = True

    async def stop(self) -> None:
        self._started = False
        self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return CallToolResult(content=[TextContent(type="text", text=f"{self.name}:{name}")])


class FailingBackend(BackendBase):
    """Backend that fails on start."""

    def __init__(self, name: str):
        super().__init__(name)

    async def start(self) -> None:
        raise ConnectionError("Cannot connect")

    async def stop(self) -> None:
        pass

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        raise RuntimeError("Not connected")


class StopFailingBackend(FakeBackend):
    async def stop(self) -> None:
        raise RuntimeError("stop failed")


class RetryFailingBackend(FakeBackend):
    async def start(self) -> None:
        raise RuntimeError("still down")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    return BackendManager()


@pytest.mark.asyncio
async def test_start_all_registers_tools(mgr):
    b1 = FakeBackend("b1", ["tool_a", "tool_b"])
    b2 = FakeBackend("b2", ["tool_c"])
    await mgr.start_all([b1, b2])

    assert mgr.has_tool("tool_a")
    assert mgr.has_tool("tool_b")
    assert mgr.has_tool("tool_c")
    assert not mgr.has_tool("tool_x")


@pytest.mark.asyncio
async def test_start_all_handles_failure(mgr):
    good = FakeBackend("good", ["tool_ok"])
    bad = FailingBackend("bad")
    await mgr.start_all([good, bad])

    assert mgr.has_tool("tool_ok")
    assert good.available
    assert not bad.available
    assert "bad" in mgr.status()


@pytest.mark.asyncio
async def test_start_all_does_not_duplicate_backend_entries(mgr):
    backend = FakeBackend("b1", ["tool_a"])
    await mgr.start_all([backend])
    await mgr.start_all([backend])

    assert mgr._backends == [backend]


@pytest.mark.asyncio
async def test_call_tool_routes_correctly(mgr):
    b1 = FakeBackend("b1", ["query"])
    b2 = FakeBackend("b2", ["navigate"])
    await mgr.start_all([b1, b2])

    result = await mgr.call_tool("query", {})
    assert result.content[0].text == "b1:query"

    result = await mgr.call_tool("navigate", {})
    assert result.content[0].text == "b2:navigate"


@pytest.mark.asyncio
async def test_call_tool_unknown_raises(mgr):
    await mgr.start_all([])
    with pytest.raises(ValueError, match="Unknown tool"):
        await mgr.call_tool("nonexistent", {})


@pytest.mark.asyncio
async def test_add_db_backends(mgr):
    toolkit = FakeBackend("tk-db1", list(TOOLKIT_TOOL_NAMES)[:3])
    lsp = FakeBackend("lsp-db1", list(LSP_TOOL_NAMES)[:3])
    await mgr.add_db_backends("db1", toolkit, lsp)

    # First DB becomes active automatically
    assert mgr.active_db == "db1"
    assert toolkit.available
    assert lsp.available


@pytest.mark.asyncio
async def test_switch_db(mgr):
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    # db1 is active (first added)
    result = await mgr.call_tool("execute_query", {})
    assert result.content[0].text == "tk-1:execute_query"

    # Switch to db2
    assert mgr.switch_db("db2")
    result = await mgr.call_tool("execute_query", {})
    assert result.content[0].text == "tk-2:execute_query"


@pytest.mark.asyncio
async def test_switch_db_nonexistent(mgr):
    assert not mgr.switch_db("no_such_db")


@pytest.mark.asyncio
async def test_remove_db_backends(mgr):
    tk = FakeBackend("tk-rm", ["execute_query"])
    lsp = FakeBackend("lsp-rm", ["symbol_explore"])
    await mgr.add_db_backends("rmdb", tk, lsp)

    assert mgr.active_db == "rmdb"
    await mgr.remove_db_backends("rmdb")
    assert mgr.active_db is None
    assert not tk.available


@pytest.mark.asyncio
async def test_remove_switches_to_next(mgr):
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    await mgr.remove_db_backends("db1")
    assert mgr.active_db == "db2"


@pytest.mark.asyncio
async def test_get_all_tools(mgr):
    static = FakeBackend("static", ["health"])
    await mgr.start_all([static])

    tk = FakeBackend("tk", ["execute_query"])
    lsp = FakeBackend("lsp", ["symbol_explore"])
    await mgr.add_db_backends("mydb", tk, lsp)

    all_tools = mgr.get_all_tools()
    names = {t.name for t in all_tools}
    assert "health" in names
    assert "execute_query" in names
    assert "symbol_explore" in names


@pytest.mark.asyncio
async def test_get_all_tools_aggregates_available_db_tools_across_databases(mgr):
    tk1 = FakeBackend("tk1", ["execute_query"])
    lsp1 = FakeBackend("lsp1", ["symbol_explore"])
    tk2 = FakeBackend("tk2", ["execute_query"])
    lsp2 = FakeBackend("lsp2", ["definition"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    lsp1.available = False  # first DB LSP unavailable must not hide second DB LSP tools

    all_tools = mgr.get_all_tools()
    names = {t.name for t in all_tools}

    assert "execute_query" in names
    assert "definition" in names


@pytest.mark.asyncio
async def test_dynamic_db_tool_detection_without_constant_update(mgr):
    """DB tool routing must work for new tool names without editing constants."""
    toolkit = FakeBackend("tk-dyn", ["brand_new_db_tool"])
    await mgr.add_db_backends("dyn-db", toolkit, None)

    assert mgr.has_tool("brand_new_db_tool")
    result = await mgr.call_tool("brand_new_db_tool", {})
    assert result.content[0].text == "tk-dyn:brand_new_db_tool"


@pytest.mark.asyncio
async def test_db_tool_routing_overrides_static_backend(mgr):
    """If both static and DB backends expose a tool, DB routing wins for active DB."""
    static = FakeBackend("static", ["execute_query"])
    await mgr.start_all([static])

    toolkit = FakeBackend("tk-db", ["execute_query"])
    await mgr.add_db_backends("db1", toolkit, None)

    result = await mgr.call_tool("execute_query", {})
    assert result.content[0].text == "tk-db:execute_query"


@pytest.mark.asyncio
async def test_status(mgr):
    static = FakeBackend("static", ["t1"])
    await mgr.start_all([static])

    tk = FakeBackend("tk-s", ["execute_query"])
    lsp = FakeBackend("lsp-s", ["symbol_explore"])
    await mgr.add_db_backends("sdb", tk, lsp)

    status = mgr.status()
    assert status["static"]["ok"] is True
    assert status["sdb/toolkit"]["ok"] is True
    assert status["sdb/lsp"]["default"] is True


@pytest.mark.asyncio
async def test_stop_all(mgr):
    b = FakeBackend("b", ["t"])
    await mgr.start_all([b])

    tk = FakeBackend("tk-stop", ["execute_query"])
    lsp = FakeBackend("lsp-stop", ["symbol_explore"])
    await mgr.add_db_backends("stopdb", tk, lsp)

    await mgr.stop_all()
    assert not b.available
    assert not tk.available
    assert not lsp.available


@pytest.mark.asyncio
async def test_retry_unavailable_backends_recovers_tools(mgr):
    class FlakyBackend(FakeBackend):
        def __init__(self, name: str, tool_names: list[str]):
            super().__init__(name, tool_names)
            self._attempts = 0

        async def start(self) -> None:
            self._attempts += 1
            if self._attempts == 1:
                raise ConnectionError("not ready yet")
            await super().start()

    flaky = FlakyBackend("flaky", ["tool_after_retry"])
    await mgr.start_all([flaky])

    assert not mgr.has_tool("tool_after_retry")
    recovered = await mgr.retry_unavailable_backends()

    assert recovered == 1
    assert mgr.has_tool("tool_after_retry")
    assert mgr.status()["flaky"]["ok"] is True


@pytest.mark.asyncio
async def test_retry_unavailable_backends_skips_available_entries(mgr):
    backend = FakeBackend("ready", ["tool_ready"])
    await mgr.start_all([backend])

    recovered = await mgr.retry_unavailable_backends()

    assert recovered == 0


@pytest.mark.asyncio
async def test_retry_unavailable_backends_keeps_zero_when_retry_fails(mgr):
    backend = RetryFailingBackend("down", ["tool_down"])
    mgr._backends.append(backend)

    recovered = await mgr.retry_unavailable_backends()

    assert recovered == 0


@pytest.mark.asyncio
async def test_stop_all_swallows_backend_stop_errors(mgr):
    static = StopFailingBackend("bad-stop", ["tool"])
    await mgr.start_all([static])

    await mgr.stop_all()


@pytest.mark.asyncio
async def test_remove_db_backends_ignores_stop_errors_and_missing_db(mgr):
    toolkit = StopFailingBackend("tk-bad-stop", ["execute_query"])
    await mgr.add_db_backends("db1", toolkit, None)
    await mgr.remove_db_backends("db1")
    await mgr.remove_db_backends("db1")


@pytest.mark.asyncio
async def test_set_default_db_returns_true_for_existing_database(mgr):
    toolkit = FakeBackend("tk-default", ["execute_query"])
    await mgr.add_db_backends("db1", toolkit, None)

    assert mgr.set_default_db("db1") is True
    assert mgr.active_db == "db1"


@pytest.mark.asyncio
async def test_set_default_db_returns_false_for_missing_database(mgr):
    assert mgr.set_default_db("missing") is False


@pytest.mark.asyncio
async def test_add_db_backends_keeps_entry_even_if_lsp_start_fails(mgr):
    toolkit = FakeBackend("tk-ok", ["execute_query"])
    lsp = FailingBackend("lsp-bad")

    await mgr.add_db_backends("db1", toolkit, lsp)

    assert mgr.has_db("db1") is True
    assert mgr.get_db_backend("db1", "lsp") is lsp


@pytest.mark.asyncio
async def test_find_db_backend_for_tool_supports_extra_roles(mgr):
    toolkit = FakeBackend("tk-main", ["execute_query"])
    extra = FakeBackend("graph-role", ["graph_search"])
    await mgr.add_db_backends("db1", toolkit, None)
    mgr._db_backends["db1"]["graph"] = extra

    assert mgr.get_backend_for_tool("graph_search") is extra


@pytest.mark.asyncio
async def test_find_db_backend_for_tool_returns_none_for_extra_role_without_tool(mgr):
    toolkit = FakeBackend("tk-main", ["execute_query"])
    extra = FakeBackend("graph-role", ["graph_search"])
    await mgr.add_db_backends("db1", toolkit, None)
    mgr._db_backends["db1"]["graph"] = extra

    assert mgr.get_backend_for_tool("missing_tool") is None


@pytest.mark.asyncio
async def test_has_tool_uses_legacy_names_for_unavailable_db_backend(mgr):
    toolkit = FakeBackend("tk-main", [])
    await mgr.add_db_backends("db1", toolkit, None)
    toolkit.available = False

    assert mgr.has_tool("execute_query") is True


def test_get_active_db_drops_to_default_when_session_points_to_removed_db(mgr):
    mgr._default_db = "db1"
    mgr._session_db["sess-1"] = ("missing-db", 1.0)

    assert mgr.get_active_db("sess-1") == "db1"


@pytest.mark.asyncio
async def test_has_tool_checks_multiple_databases_until_match(mgr):
    await mgr.add_db_backends("db1", FakeBackend("tk1", ["execute_code"]), None)
    await mgr.add_db_backends("db2", FakeBackend("tk2", ["execute_query"]), None)

    assert mgr.has_tool("execute_query") is True


@pytest.mark.asyncio
async def test_find_db_backend_for_tool_skips_unavailable_legacy_miss_and_checks_extra_role(mgr):
    toolkit = FakeBackend("tk-main", [])
    await mgr.add_db_backends("db1", toolkit, None)
    toolkit.available = False
    mgr._db_backends["db1"]["graph"] = FakeBackend("graph-role", ["graph_search"])

    assert mgr.get_backend_for_tool("graph_search") is mgr._db_backends["db1"]["graph"]


# ---------------------------------------------------------------------------
# Per-session routing tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_switch_db_with_session_id(mgr):
    """Different sessions can have different active DBs."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    # Session A switches to db2, session B stays on default (db1)
    assert mgr.switch_db("db2", session_id="session-a")

    result_a = await mgr.call_tool("execute_query", {}, session_id="session-a")
    assert result_a.content[0].text == "tk-2:execute_query"

    result_b = await mgr.call_tool("execute_query", {}, session_id="session-b")
    assert result_b.content[0].text == "tk-1:execute_query"


@pytest.mark.asyncio
async def test_switch_db_session_does_not_affect_global(mgr):
    """Switching DB for a session does not change the global default."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db2", session_id="session-x")
    assert mgr.active_db == "db1"  # global default unchanged


@pytest.mark.asyncio
async def test_switch_db_session_nonexistent_db(mgr):
    """switch_db returns False for a non-existent DB even with session_id."""
    tk = FakeBackend("tk", ["execute_query"])
    lsp = FakeBackend("lsp", ["symbol_explore"])
    await mgr.add_db_backends("db1", tk, lsp)

    assert not mgr.switch_db("no_such_db", session_id="session-z")


@pytest.mark.asyncio
async def test_get_active_db_with_session(mgr):
    """get_active_db returns the session-specific DB when set."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db2", session_id="sess-1")

    assert mgr.get_active_db(session_id="sess-1") == "db2"
    assert mgr.get_active_db(session_id="sess-1") == "db2"  # still db2 after re-read


@pytest.mark.asyncio
async def test_get_active_db_fallback_to_global(mgr):
    """get_active_db falls back to global default for unknown sessions."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    # Session has no DB set - should fall back to global default
    assert mgr.get_active_db(session_id="unknown-session") == "db1"

    # No session at all - should return global default
    assert mgr.get_active_db() == "db1"


@pytest.mark.asyncio
async def test_get_active_db_no_session_id(mgr):
    """get_active_db(None) returns the global default."""
    tk = FakeBackend("tk", ["execute_query"])
    lsp = FakeBackend("lsp", ["symbol_explore"])
    await mgr.add_db_backends("db1", tk, lsp)

    assert mgr.get_active_db(session_id=None) == "db1"


@pytest.mark.asyncio
async def test_get_active_db_session_removed_db_falls_back(mgr):
    """If a session's DB was removed, get_active_db falls back to default."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db2", session_id="sess-orphan")
    assert mgr.get_active_db(session_id="sess-orphan") == "db2"

    # Remove db2 - session reference is cleaned up by remove_db_backends
    await mgr.remove_db_backends("db2")
    assert mgr.get_active_db(session_id="sess-orphan") == "db1"


@pytest.mark.asyncio
async def test_multiple_sessions_independent(mgr):
    """Three sessions each pointing to different DBs route independently."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])
    tk3 = FakeBackend("tk-3", ["execute_query"])
    lsp3 = FakeBackend("lsp-3", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)
    await mgr.add_db_backends("db3", tk3, lsp3)

    mgr.switch_db("db1", session_id="alice")
    mgr.switch_db("db2", session_id="bob")
    mgr.switch_db("db3", session_id="carol")

    r1 = await mgr.call_tool("execute_query", {}, session_id="alice")
    r2 = await mgr.call_tool("execute_query", {}, session_id="bob")
    r3 = await mgr.call_tool("execute_query", {}, session_id="carol")

    assert r1.content[0].text == "tk-1:execute_query"
    assert r2.content[0].text == "tk-2:execute_query"
    assert r3.content[0].text == "tk-3:execute_query"


@pytest.mark.asyncio
async def test_session_lsp_routing(mgr):
    """Per-session routing works for LSP tools as well as toolkit tools."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db2", session_id="sess-lsp")

    result = await mgr.call_tool("symbol_explore", {}, session_id="sess-lsp")
    assert result.content[0].text == "lsp-2:symbol_explore"


# ---------------------------------------------------------------------------
# cleanup_stale_sessions tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_stale_sessions(mgr, monkeypatch):
    """cleanup_stale_sessions removes sessions older than _SESSION_MAX_AGE."""
    import gateway.backends.manager as manager_mod

    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    await mgr.add_db_backends("db1", tk1, lsp1)

    # Inject sessions with timestamps in the past
    now = 100000.0
    mgr._session_db["fresh"] = ("db1", now - 100)         # 100s ago - fresh
    mgr._session_db["stale1"] = ("db1", now - 30000)      # > 8h ago - stale
    mgr._session_db["stale2"] = ("db1", now - 50000)      # > 8h ago - stale

    monkeypatch.setattr("time.monotonic", lambda: now)

    removed = mgr.cleanup_stale_sessions()

    assert removed == 2
    assert "fresh" in mgr._session_db
    assert "stale1" not in mgr._session_db
    assert "stale2" not in mgr._session_db


@pytest.mark.asyncio
async def test_cleanup_stale_sessions_none_stale(mgr, monkeypatch):
    """cleanup_stale_sessions returns 0 when no sessions are stale."""
    tk = FakeBackend("tk", ["execute_query"])
    lsp = FakeBackend("lsp", ["symbol_explore"])
    await mgr.add_db_backends("db1", tk, lsp)

    now = 100000.0
    mgr._session_db["s1"] = ("db1", now - 10)
    mgr._session_db["s2"] = ("db1", now - 20)

    monkeypatch.setattr("time.monotonic", lambda: now)

    removed = mgr.cleanup_stale_sessions()

    assert removed == 0
    assert len(mgr._session_db) == 2


@pytest.mark.asyncio
async def test_cleanup_stale_sessions_empty(mgr):
    """cleanup_stale_sessions on empty session_db returns 0."""
    removed = mgr.cleanup_stale_sessions()
    assert removed == 0


# ---------------------------------------------------------------------------
# session_count property tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_count_zero(mgr):
    """session_count is 0 when no sessions exist."""
    assert mgr.session_count == 0


@pytest.mark.asyncio
async def test_session_count_tracks_sessions(mgr):
    """session_count reflects the number of active sessions."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    assert mgr.session_count == 0

    mgr.switch_db("db1", session_id="s1")
    assert mgr.session_count == 1

    mgr.switch_db("db2", session_id="s2")
    assert mgr.session_count == 2

    mgr.switch_db("db1", session_id="s3")
    assert mgr.session_count == 3


@pytest.mark.asyncio
async def test_session_count_no_duplicates(mgr):
    """Switching the same session again does not increase session_count."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db1", session_id="s1")
    mgr.switch_db("db2", session_id="s1")  # same session, different DB
    assert mgr.session_count == 1


@pytest.mark.asyncio
async def test_session_count_decreases_after_cleanup(mgr, monkeypatch):
    """session_count decreases after stale sessions are cleaned up."""
    tk = FakeBackend("tk", ["execute_query"])
    lsp = FakeBackend("lsp", ["symbol_explore"])
    await mgr.add_db_backends("db1", tk, lsp)

    now = 100000.0
    mgr._session_db["active"] = ("db1", now - 100)
    mgr._session_db["stale"] = ("db1", now - 50000)

    assert mgr.session_count == 2

    monkeypatch.setattr("time.monotonic", lambda: now)
    mgr.cleanup_stale_sessions()

    assert mgr.session_count == 1


@pytest.mark.asyncio
async def test_forget_sessions_removes_known_ids(mgr):
    tk = FakeBackend("tk", ["execute_query"])
    await mgr.add_db_backends("db1", tk, None)

    mgr.switch_db("db1", session_id="s1")
    mgr.switch_db("db1", session_id="s2")
    removed = mgr.forget_sessions(["s1", "missing"])

    assert removed == 1
    assert mgr.session_count == 1


@pytest.mark.asyncio
async def test_session_count_decreases_after_remove_db(mgr):
    """session_count decreases when a DB is removed (orphan sessions cleaned)."""
    tk1 = FakeBackend("tk-1", ["execute_query"])
    lsp1 = FakeBackend("lsp-1", ["symbol_explore"])
    tk2 = FakeBackend("tk-2", ["execute_query"])
    lsp2 = FakeBackend("lsp-2", ["symbol_explore"])

    await mgr.add_db_backends("db1", tk1, lsp1)
    await mgr.add_db_backends("db2", tk2, lsp2)

    mgr.switch_db("db1", session_id="s1")
    mgr.switch_db("db2", session_id="s2")
    mgr.switch_db("db2", session_id="s3")
    assert mgr.session_count == 3

    await mgr.remove_db_backends("db2")
    assert mgr.session_count == 1  # only s1 remains


@pytest.mark.asyncio
async def test_add_db_backends_without_lsp(mgr):
    """Adding DB backends with lsp=None should work (toolkit only)."""
    toolkit = FakeBackend("tk-nolsp", list(TOOLKIT_TOOL_NAMES)[:3])
    await mgr.add_db_backends("db_nolsp", toolkit, None)

    assert mgr.active_db == "db_nolsp"
    assert toolkit.available
    assert mgr.has_db("db_nolsp")


@pytest.mark.asyncio
async def test_add_db_backends_without_lsp_no_lsp_routing(mgr):
    """When LSP is None, LSP tools should not route to that DB."""
    toolkit = FakeBackend("tk-nolsp2", ["execute_query"])
    await mgr.add_db_backends("db_nolsp2", toolkit, None)

    result = await mgr.call_tool("execute_query", {})
    assert result.content[0].text == "tk-nolsp2:execute_query"

    backend = mgr.get_backend_for_tool("symbol_explore")
    assert backend is None


@pytest.mark.asyncio
async def test_lsp_tool_routes_to_unavailable_backend_for_reconnect(mgr):
    toolkit = FakeBackend("tk-reconnect", ["execute_query"])
    lsp = FakeBackend("lsp-reconnect", ["symbol_explore"])
    await mgr.add_db_backends("db_reconnect", toolkit, lsp)

    lsp.available = False

    backend = mgr.get_backend_for_tool("symbol_explore")
    assert backend is lsp


@pytest.mark.asyncio
async def test_get_db_backend_by_role(mgr):
    toolkit = FakeBackend("tk-role", ["execute_query"])
    lsp = FakeBackend("lsp-role", ["symbol_explore"])
    await mgr.add_db_backends("db_role", toolkit, lsp)

    assert mgr.get_db_backend("db_role", "toolkit") is toolkit
    assert mgr.get_db_backend("db_role", "lsp") is lsp


@pytest.mark.asyncio
async def test_get_db_backend_missing_returns_none(mgr):
    toolkit = FakeBackend("tk-role-miss", ["execute_query"])
    await mgr.add_db_backends("db_role_miss", toolkit, None)

    assert mgr.get_db_backend("db_role_miss", "lsp") is None
    assert mgr.get_db_backend("ghost", "toolkit") is None

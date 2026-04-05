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
async def test_status(mgr):
    static = FakeBackend("static", ["t1"])
    await mgr.start_all([static])

    tk = FakeBackend("tk-s", ["execute_query"])
    lsp = FakeBackend("lsp-s", ["symbol_explore"])
    await mgr.add_db_backends("sdb", tk, lsp)

    status = mgr.status()
    assert status["static"]["ok"] is True
    assert status["sdb/toolkit"]["ok"] is True
    assert status["sdb/lsp"]["active"] is True


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

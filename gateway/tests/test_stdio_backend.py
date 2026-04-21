from unittest.mock import AsyncMock

import pytest
from mcp.types import CallToolResult, TextContent

from gateway.backends.stdio_backend import StdioBackend


@pytest.mark.asyncio
async def test_call_tool_reconnects_stale_session_before_user_call():
    backend = StdioBackend("lsp-test", "docker", ["exec", "fake"])
    stale_session = AsyncMock()
    stale_session.list_tools.side_effect = RuntimeError("broken pipe")
    stale_session.call_tool = AsyncMock()
    backend._session = stale_session

    fresh_session = AsyncMock()
    fresh_session.list_tools = AsyncMock()
    fresh_session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    async def fake_connect():
        backend._session = fresh_session
        backend.tools = []
        backend.available = True

    backend._connect = fake_connect

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    stale_session.call_tool.assert_not_called()
    fresh_session.call_tool.assert_awaited_once_with("symbol_explore", {"query": "x"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_call_tool_connects_when_session_missing():
    backend = StdioBackend("lsp-test", "docker", ["exec", "fake"])

    fresh_session = AsyncMock()
    fresh_session.list_tools = AsyncMock()
    fresh_session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    async def fake_connect():
        backend._session = fresh_session
        backend.tools = []
        backend.available = True

    backend._connect = fake_connect

    result = await backend.call_tool("lsp_status", {})

    fresh_session.call_tool.assert_awaited_once_with("lsp_status", {})
    assert result.content[0].text == "ok"

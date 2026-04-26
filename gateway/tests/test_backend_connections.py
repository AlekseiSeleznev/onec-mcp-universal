"""Connection lifecycle tests for HTTP and stdio backends."""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.types import CallToolResult, TextContent, Tool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.backends.http_backend import HttpBackend
from gateway.backends.stdio_backend import StdioBackend


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _tool(name: str) -> Tool:
    return Tool(name=name, description=name, inputSchema={"type": "object"})


@asynccontextmanager
async def _http_stream_ctx():
    yield object(), object(), object()


@asynccontextmanager
async def _sse_stream_ctx():
    yield object(), object()


@asynccontextmanager
async def _stdio_ctx(_params):
    yield object(), object()


@pytest.mark.asyncio
async def test_http_backend_start_and_stop_streamable():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("ping")]))

    with patch("gateway.backends.http_backend.streamablehttp_client", side_effect=lambda *_: _http_stream_ctx()), \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(session)):
        backend = HttpBackend("http-test", "http://localhost:8080/mcp", "streamable")
        await backend.start()

        assert backend.available is True
        assert [tool.name for tool in backend.tools] == ["ping"]

        await backend.stop()

    assert backend.available is False
    assert backend._session is None


@pytest.mark.asyncio
async def test_http_backend_start_uses_sse_transport():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("pong")]))

    with patch("gateway.backends.http_backend.sse_client", side_effect=lambda *_: _sse_stream_ctx()) as sse_client, \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(session)):
        backend = HttpBackend("http-test", "http://localhost:8080/sse", "sse")
        await backend.start()

    sse_client.assert_called_once_with("http://localhost:8080/sse")
    assert backend.available is True
    assert [tool.name for tool in backend.tools] == ["pong"]


@pytest.mark.asyncio
async def test_http_backend_stateless_uses_fresh_session_per_call():
    probe = MagicMock()
    probe.initialize = AsyncMock()
    probe.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("info")]))

    call_a = MagicMock()
    call_a.initialize = AsyncMock()
    call_a.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="search ok")])
    )

    call_b = MagicMock()
    call_b.initialize = AsyncMock()
    call_b.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="info ok")])
    )

    sessions = iter([probe, call_a, call_b])

    with patch("gateway.backends.http_backend.sse_client", side_effect=lambda *_: _sse_stream_ctx()) as sse_client, \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(next(sessions))):
        backend = HttpBackend("http-test", "http://localhost:8080/sse", "sse", stateless=True)
        await backend.start()
        first = await backend.call_tool("search", {"query": "Строка", "type": "type", "limit": 5})
        second = await backend.call_tool("info", {"name": "Строка", "type": "type"})

    assert backend.available is True
    assert backend._session is None
    assert [tool.name for tool in backend.tools] == ["info"]
    assert first.content[0].text == "search ok"
    assert second.content[0].text == "info ok"
    assert sse_client.call_count == 3
    probe.list_tools.assert_awaited_once()
    call_a.call_tool.assert_awaited_once_with("search", {"query": "Строка", "type": "type", "limit": 5})
    call_b.call_tool.assert_awaited_once_with("info", {"name": "Строка", "type": "type"})


@pytest.mark.asyncio
async def test_http_backend_stateless_streamable_uses_open_session_streamable_branch():
    probe = MagicMock()
    probe.initialize = AsyncMock()
    probe.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("info")]))

    with patch("gateway.backends.http_backend.streamablehttp_client", side_effect=lambda *_: _http_stream_ctx()) as streamable_client, \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(probe)):
        backend = HttpBackend("http-test", "http://localhost:8080/mcp", "streamable", stateless=True)
        await backend.start()

    streamable_client.assert_called_once_with("http://localhost:8080/mcp")
    assert backend.available is True
    assert backend._session is None


@pytest.mark.asyncio
async def test_http_backend_stateless_applies_call_timeout():
    probe = MagicMock()
    probe.initialize = AsyncMock()
    probe.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("info")]))

    slow = MagicMock()
    slow.initialize = AsyncMock()
    slow.call_tool = AsyncMock()

    fresh = MagicMock()
    fresh.initialize = AsyncMock()
    fresh.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    sessions = iter([probe, slow, probe, fresh])

    backend = HttpBackend("http-test", "http://localhost:8080/sse", "sse", call_timeout=5, stateless=True)

    wait_for_calls = {"count": 0}

    async def fake_wait_for(awaitable, timeout):
        wait_for_calls["count"] += 1
        if wait_for_calls["count"] == 1:
            awaitable.close()
            raise TimeoutError
        return await awaitable

    with patch("gateway.backends.http_backend.sse_client", side_effect=lambda *_: _sse_stream_ctx()), \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(next(sessions))), \
         patch("gateway.backends.http_backend.asyncio.wait_for", side_effect=fake_wait_for):
        await backend.start()
        result = await backend.call_tool("info", {"name": "Строка", "type": "type"})

    assert wait_for_calls["count"] == 2
    slow.call_tool.assert_called_once_with("info", {"name": "Строка", "type": "type"})
    fresh.call_tool.assert_awaited_once_with("info", {"name": "Строка", "type": "type"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_http_backend_reconnects_after_failed_call():
    stale = MagicMock()
    stale.call_tool = AsyncMock(side_effect=RuntimeError("broken"))

    fresh = MagicMock()
    fresh.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._session = stale
    backend.available = True
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", fresh))

    result = await backend.call_tool("ping", {})

    stale.call_tool.assert_awaited_once_with("ping", {})
    backend._connect.assert_awaited_once()
    fresh.call_tool.assert_awaited_once_with("ping", {})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_http_backend_call_tool_once_raises_when_session_not_initialized():
    backend = HttpBackend("http-test", "http://localhost:8080/mcp")

    with pytest.raises(RuntimeError, match="not initialized"):
        await backend._call_tool_once("ping", {})


@pytest.mark.asyncio
async def test_http_backend_cancel_pending_calls_cancels_and_awaits_tasks():
    backend = HttpBackend("http-test", "http://localhost:8080/mcp")

    async def _sleep_forever():
        await asyncio.sleep(3600)

    task = asyncio.create_task(_sleep_forever())
    backend._pending_calls.add(task)

    await backend._cancel_pending_calls()

    assert backend._pending_calls == set()
    assert task.cancelled()


@pytest.mark.asyncio
async def test_http_backend_reconnects_after_timed_out_call():
    stale = MagicMock()
    stale.call_tool = AsyncMock()

    fresh = MagicMock()
    fresh.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = HttpBackend("http-test", "http://localhost:8080/sse", "sse", call_timeout=5)
    backend._session = stale
    backend.available = True
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", fresh))

    wait_for_calls = {"count": 0}

    async def fake_wait_for(awaitable, timeout):
        wait_for_calls["count"] += 1
        if wait_for_calls["count"] == 1:
            awaitable.close()
            raise TimeoutError
        return await awaitable

    with patch("gateway.backends.http_backend.asyncio.wait_for", side_effect=fake_wait_for):
        result = await backend.call_tool("info", {"name": "Массив", "type": "type"})

    assert wait_for_calls["count"] == 2
    stale.call_tool.assert_called_once_with("info", {"name": "Массив", "type": "type"})
    backend._connect.assert_awaited_once()
    fresh.call_tool.assert_awaited_once_with("info", {"name": "Массив", "type": "type"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_http_backend_call_tool_connects_when_session_missing():
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", session))

    result = await backend.call_tool("ping", {})

    backend._connect.assert_awaited_once()
    session.call_tool.assert_awaited_once_with("ping", {})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_http_backend_call_tool_connects_when_backend_marked_unavailable():
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._session = MagicMock()
    backend.available = False
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", session))

    result = await backend.call_tool("ping", {})

    backend._connect.assert_awaited_once()
    session.call_tool.assert_awaited_once_with("ping", {})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_http_backend_rebind_updates_url_and_reconnects():
    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._connect = AsyncMock()

    await backend.rebind("http://localhost:8080/mcp?channel=z01")

    assert backend._url == "http://localhost:8080/mcp?channel=z01"
    backend._connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_http_backend_connect_closes_previous_exit_stack_even_on_close_error():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("ping")]))

    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._exit_stack = MagicMock(aclose=AsyncMock(side_effect=RuntimeError("close failed")))

    with patch("gateway.backends.http_backend.streamablehttp_client", side_effect=lambda *_: _http_stream_ctx()), \
         patch("gateway.backends.http_backend.ClientSession", side_effect=lambda *_: _SessionContext(session)):
        await backend._connect_locked()

    assert backend.available is True
    assert [tool.name for tool in backend.tools] == ["ping"]


@pytest.mark.asyncio
async def test_http_backend_stop_swallows_close_errors():
    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    backend._exit_stack = MagicMock(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    backend._session = MagicMock()
    backend.available = True

    await backend.stop()

    assert backend._session is None
    assert backend.available is False


@pytest.mark.asyncio
async def test_http_backend_stop_without_exit_stack_is_noop():
    backend = HttpBackend("http-test", "http://localhost:8080/mcp")
    await backend.stop()
    assert backend._session is None
    assert backend.available is False


@pytest.mark.asyncio
async def test_stdio_backend_start_and_stop():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("symbol_explore")]))

    with patch("gateway.backends.stdio_backend.stdio_client", side_effect=_stdio_ctx), \
         patch("gateway.backends.stdio_backend.ClientSession", side_effect=lambda *_: _SessionContext(session)):
        backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
        await backend.start()

        assert backend.available is True
        assert [tool.name for tool in backend.tools] == ["symbol_explore"]

        await backend.stop()

    assert backend.available is False
    assert backend._session is None


@pytest.mark.asyncio
async def test_stdio_backend_reconnects_after_failed_call():
    stale = MagicMock()
    stale.call_tool = AsyncMock(side_effect=RuntimeError("broken"))

    fresh = MagicMock()
    fresh.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    backend._session = stale
    backend.available = True
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", fresh))

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    stale.call_tool.assert_awaited_once_with("symbol_explore", {"query": "x"})
    backend._connect.assert_awaited_once()
    fresh.call_tool.assert_awaited_once_with("symbol_explore", {"query": "x"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_stdio_backend_stop_without_exit_stack_is_noop():
    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    await backend.stop()
    assert backend._session is None
    assert backend.available is False


@pytest.mark.asyncio
async def test_stdio_backend_call_tool_connects_when_session_missing():
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", session))

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    backend._connect.assert_awaited_once()
    session.call_tool.assert_awaited_once_with("symbol_explore", {"query": "x"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_stdio_backend_call_tool_connects_when_backend_marked_unavailable():
    session = MagicMock()
    session.call_tool = AsyncMock(
        return_value=CallToolResult(content=[TextContent(type="text", text="ok")])
    )

    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    backend._session = MagicMock()
    backend.available = False
    backend._connect = AsyncMock(side_effect=lambda: setattr(backend, "_session", session))

    result = await backend.call_tool("symbol_explore", {"query": "x"})

    backend._connect.assert_awaited_once()
    session.call_tool.assert_awaited_once_with("symbol_explore", {"query": "x"})
    assert result.content[0].text == "ok"


@pytest.mark.asyncio
async def test_stdio_backend_connect_closes_previous_exit_stack_even_on_close_error():
    session = MagicMock()
    session.initialize = AsyncMock()
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[_tool("symbol_explore")]))

    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    backend._exit_stack = MagicMock(aclose=AsyncMock(side_effect=RuntimeError("close failed")))

    with patch("gateway.backends.stdio_backend.stdio_client", side_effect=_stdio_ctx), \
         patch("gateway.backends.stdio_backend.ClientSession", side_effect=lambda *_: _SessionContext(session)):
        await backend._connect_locked()

    assert backend.available is True
    assert [tool.name for tool in backend.tools] == ["symbol_explore"]


@pytest.mark.asyncio
async def test_stdio_backend_stop_swallows_close_errors():
    backend = StdioBackend("stdio-test", "docker", ["exec", "container", "cmd"])
    backend._exit_stack = MagicMock(aclose=AsyncMock(side_effect=RuntimeError("close failed")))
    backend._session = MagicMock()
    backend.available = True

    await backend.stop()

    assert backend._session is None
    assert backend.available is False

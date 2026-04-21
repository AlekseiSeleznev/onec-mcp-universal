import asyncio
import logging
from contextlib import AsyncExitStack
from contextlib import suppress

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from .base import BackendBase

logger = logging.getLogger(__name__)


class HttpBackend(BackendBase):
    """MCP backend connected via HTTP (Streamable HTTP or legacy SSE)."""

    def __init__(
        self,
        name: str,
        url: str,
        transport: str = "streamable",
        call_timeout: float | None = None,
        stateless: bool = False,
    ):
        super().__init__(name)
        self._url = url
        self._transport = transport  # "streamable" or "sse"
        self._call_timeout = call_timeout
        self._stateless = stateless
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._pending_calls: set[asyncio.Task] = set()

    async def rebind(self, url: str) -> None:
        async with self._lock:
            self._url = url
            await self._connect()

    async def _connect(self) -> None:
        await self._connect_locked()

    async def _open_session(self) -> tuple[AsyncExitStack, ClientSession]:
        stack = AsyncExitStack()
        if self._transport == "sse":
            read, write = await stack.enter_async_context(sse_client(self._url))
        else:
            read, write, _ = await stack.enter_async_context(streamablehttp_client(self._url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return stack, session

    async def _connect_locked(self) -> None:
        await self._cancel_pending_calls()
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
        if self._stateless:
            self._exit_stack = None
            self._session = None
            stack, session = await self._open_session()
            try:
                result = await session.list_tools()
            finally:
                await stack.aclose()
            self.tools = result.tools
            self.available = True
            return
        self._exit_stack = AsyncExitStack()
        if self._transport == "sse":
            read, write = await self._exit_stack.enter_async_context(sse_client(self._url))
        else:
            read, write, _ = await self._exit_stack.enter_async_context(streamablehttp_client(self._url))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        result = await self._session.list_tools()
        self.tools = result.tools
        self.available = True

    async def start(self) -> None:
        async with self._lock:
            await self._connect()
        logger.info(f"[{self.name}] connected ({len(self.tools)} tools) via {self._transport}")

    async def stop(self) -> None:
        async with self._lock:
            await self._cancel_pending_calls()
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except Exception:
                    pass
            self._exit_stack = None
            self._session = None
            self.available = False

    async def _cancel_pending_calls(self) -> None:
        if not self._pending_calls:
            return
        pending = list(self._pending_calls)
        self._pending_calls.clear()
        for task in pending:
            task.cancel()
        for task in pending:
            with suppress(asyncio.CancelledError, Exception):
                await task

    async def _call_tool_once(self, name: str, arguments: dict) -> CallToolResult:
        if self._stateless:
            stack, session = await self._open_session()
            task: asyncio.Task | None = None
            try:
                if self._call_timeout is None:
                    return await session.call_tool(name, arguments)
                task = asyncio.create_task(session.call_tool(name, arguments))
                self._pending_calls.add(task)
                return await asyncio.wait_for(asyncio.shield(task), timeout=self._call_timeout)
            finally:
                if task is not None:
                    self._pending_calls.discard(task)
                await stack.aclose()
        if self._session is None:
            raise RuntimeError("Backend session is not initialized")
        if self._call_timeout is None:
            return await self._session.call_tool(name, arguments)
        task = asyncio.create_task(self._session.call_tool(name, arguments))
        self._pending_calls.add(task)
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self._call_timeout)
        finally:
            self._pending_calls.discard(task)

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        async with self._lock:
            if (self._stateless and not self.available) or (
                not self._stateless and (self._session is None or not self.available)
            ):
                await self._connect()
            try:
                return await self._call_tool_once(name, arguments)
            except Exception as exc:
                logger.warning(f"[{self.name}] call_tool failed ({exc}), reconnecting...")
                await self._connect()
                logger.info(f"[{self.name}] reconnected ({len(self.tools)} tools)")
                return await self._call_tool_once(name, arguments)

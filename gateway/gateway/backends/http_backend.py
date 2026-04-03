import logging
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult

from .base import BackendBase

logger = logging.getLogger(__name__)


class HttpBackend(BackendBase):
    """MCP backend connected via HTTP (Streamable HTTP or legacy SSE)."""

    def __init__(self, name: str, url: str, transport: str = "streamable"):
        super().__init__(name)
        self._url = url
        self._transport = transport  # "streamable" or "sse"
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def start(self) -> None:
        self._exit_stack = AsyncExitStack()
        if self._transport == "sse":
            read, write = await self._exit_stack.enter_async_context(
                sse_client(self._url)
            )
        else:
            read, write, _ = await self._exit_stack.enter_async_context(
                streamablehttp_client(self._url)
            )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        result = await self._session.list_tools()
        self.tools = result.tools
        self.available = True
        logger.info(f"[{self.name}] connected ({len(self.tools)} tools) via {self._transport}")

    async def stop(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return await self._session.call_tool(name, arguments)

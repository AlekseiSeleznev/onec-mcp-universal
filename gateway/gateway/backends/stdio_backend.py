import logging
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

from .base import BackendBase

logger = logging.getLogger(__name__)


class StdioBackend(BackendBase):
    """MCP backend connected via stdio (e.g. docker exec into running container)."""

    def __init__(self, name: str, command: str, args: list[str]):
        super().__init__(name)
        self._command = command
        self._args = args
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def start(self) -> None:
        params = StdioServerParameters(command=self._command, args=self._args)
        self._exit_stack = AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        result = await self._session.list_tools()
        self.tools = result.tools
        self.available = True
        logger.info(f"[{self.name}] connected ({len(self.tools)} tools) via stdio")

    async def stop(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        return await self._session.call_tool(name, arguments)

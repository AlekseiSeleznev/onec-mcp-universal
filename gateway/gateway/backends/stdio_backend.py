import logging
from contextlib import AsyncExitStack

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

from .base import BackendBase

logger = logging.getLogger(__name__)


class StdioBackend(BackendBase):
    """MCP backend connected via stdio (e.g. docker exec into running container).

    Supports auto-reconnect: if call_tool fails due to a broken pipe
    or other transport error, the connection is re-established and the
    call is retried once.
    """

    def __init__(self, name: str, command: str, args: list[str]):
        super().__init__(name)
        self._command = command
        self._args = args
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def _connect(self) -> None:
        await self._connect_locked()

    async def _connect_locked(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
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

    async def start(self) -> None:
        async with self._lock:
            await self._connect()
        logger.info(f"[{self.name}] connected ({len(self.tools)} tools) via stdio")

    async def stop(self) -> None:
        async with self._lock:
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except Exception:
                    pass
            self._exit_stack = None
            self._session = None
            self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        async with self._lock:
            if self._session is None or not self.available:
                await self._connect()
            try:
                return await self._session.call_tool(name, arguments)
            except Exception as exc:
                logger.warning(f"[{self.name}] call_tool failed ({exc}), reconnecting...")
                await self._connect()
                logger.info(f"[{self.name}] reconnected ({len(self.tools)} tools)")
                return await self._session.call_tool(name, arguments)

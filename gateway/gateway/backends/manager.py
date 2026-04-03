import asyncio
import logging

from mcp.types import CallToolResult, Tool

from .base import BackendBase

logger = logging.getLogger(__name__)


class BackendManager:
    def __init__(self) -> None:
        self._backends: list[BackendBase] = []
        self._tool_map: dict[str, BackendBase] = {}

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

        await asyncio.gather(*[_safe_stop(b) for b in self._backends])

    def get_all_tools(self) -> list[Tool]:
        return [t for b in self._backends for t in b.tools if b.available]

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        backend = self._tool_map.get(name)
        if backend is None:
            raise ValueError(f"Unknown tool: {name!r}")
        return await backend.call_tool(name, arguments)

    def status(self) -> dict:
        return {
            b.name: {"ok": b.available, "tools": len(b.tools)}
            for b in self._backends
        }

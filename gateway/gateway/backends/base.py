from abc import ABC, abstractmethod

from mcp.types import CallToolResult, Tool


class BackendBase(ABC):
    def __init__(self, name: str):
        self.name = name
        self.tools: list[Tool] = []
        self.available: bool = False

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict) -> CallToolResult: ...

"""
Registry of connected 1C databases.
Each database has its own onec-toolkit and LSP container.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class DatabaseInfo:
    name: str
    connection: str          # "Srvr=as-hp;Ref=Z01;"
    project_path: str        # host path to BSL workspace
    toolkit_port: int = 0    # dynamic port for onec-toolkit
    lsp_container: str = ""  # docker container name for LSP
    toolkit_url: str = ""    # http://localhost:{port}/mcp
    connected: bool = False  # EPF has registered and is polling


class DatabaseRegistry:
    def __init__(self):
        self._databases: dict[str, DatabaseInfo] = {}
        self._active: Optional[str] = None
        self._lock = asyncio.Lock()

    def register(self, name: str, connection: str, project_path: str) -> DatabaseInfo:
        """Add or update a database entry (called when connect_database tool is used)."""
        if name not in self._databases:
            self._databases[name] = DatabaseInfo(
                name=name,
                connection=connection,
                project_path=project_path,
            )
        else:
            db = self._databases[name]
            db.connection = connection
            db.project_path = project_path
        if self._active is None:
            self._active = name
        log.info(f"Database registered: {name} → {project_path}")
        return self._databases[name]

    def mark_epf_connected(self, name: str):
        """Called when EPF sends /api/register — the 1C client is ready."""
        if name in self._databases:
            self._databases[name].connected = True
            log.info(f"EPF connected for database: {name}")

    def get(self, name: str) -> Optional[DatabaseInfo]:
        return self._databases.get(name)

    def get_active(self) -> Optional[DatabaseInfo]:
        if self._active and self._active in self._databases:
            return self._databases[self._active]
        return None

    def switch(self, name: str) -> bool:
        if name not in self._databases:
            return False
        self._active = name
        log.info(f"Active database switched to: {name}")
        return True

    def list(self) -> list[dict]:
        return [
            {
                "name": db.name,
                "connection": db.connection,
                "project_path": db.project_path,
                "toolkit_url": db.toolkit_url,
                "lsp_container": db.lsp_container,
                "epf_connected": db.connected,
                "active": db.name == self._active,
            }
            for db in self._databases.values()
        ]

    def remove(self, name: str) -> bool:
        if name not in self._databases:
            return False
        del self._databases[name]
        if self._active == name:
            self._active = next(iter(self._databases), None)
        return True

    @property
    def active_name(self) -> Optional[str]:
        return self._active


# Singleton — injected into server.py
registry = DatabaseRegistry()

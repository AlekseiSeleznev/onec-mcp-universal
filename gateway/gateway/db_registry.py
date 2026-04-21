"""
Registry of connected 1C databases.
Each database has its own onec-toolkit and LSP container.
Persists state to JSON for auto-reconnect on gateway restart.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

def _default_state_file() -> Path:
    """Pick a writable state file path (Docker container → /data, host → ~/.config/)."""
    docker_path = Path("/data/db_state.json")
    if docker_path.parent.exists():
        return docker_path
    # Fallback for non-Docker environments (dev, host-mode)
    import os
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "onec-gateway"
    return config_dir / "db_state.json"

_STATE_FILE = _default_state_file()


@dataclass
class DatabaseInfo:
    name: str
    connection: str          # "Srvr=as-hp;Ref=Z01;"
    project_path: str        # host path to BSL workspace
    slug: str = ""           # Docker-safe identifier derived from name
    toolkit_port: int = 0    # dynamic port for onec-toolkit
    lsp_container: str = ""  # docker container name for LSP
    toolkit_url: str = ""    # http://localhost:{port}/mcp
    connected: bool = False  # EPF has registered and is polling
    epf_last_seen: float = 0.0  # unix timestamp of last EPF register/heartbeat
    channel_id: str = "default"  # live EPF channel currently bound to toolkit MCP URL
    ignore_unregister_until: float = 0.0  # ignore stale unregister events until this timestamp


class DatabaseRegistry:
    def __init__(self, state_file: Path | None = None):
        self._databases: dict[str, DatabaseInfo] = {}
        self._active: Optional[str] = None
        self._lock = threading.Lock()
        self._state_file = state_file or _STATE_FILE

    def register(self, name: str, connection: str, project_path: str, slug: str = "") -> DatabaseInfo:
        """Add or update a database entry (called when connect_database tool is used)."""
        with self._lock:
            if name not in self._databases:
                self._databases[name] = DatabaseInfo(
                    name=name,
                    connection=connection,
                    project_path=project_path,
                    slug=slug or name,
                )
            else:
                db = self._databases[name]
                db.connection = connection
                db.project_path = project_path
                if slug:
                    db.slug = slug
            if self._active is None:
                self._active = name
            log.info(f"Database registered: {name} → {project_path}")
            self._save_state()
            return self._databases[name]

    def mark_epf_connected(self, name: str):
        """Called when EPF sends /api/register — the 1C client is ready."""
        with self._lock:
            if name in self._databases:
                self._databases[name].connected = True
                self._databases[name].epf_last_seen = time.time()
                self._databases[name].ignore_unregister_until = 0.0
                log.info(f"EPF connected for database: {name}")

    def mark_epf_heartbeat(self, name: str) -> bool:
        """Refresh EPF liveness timestamp for a database."""
        with self._lock:
            db = self._databases.get(name)
            if db is None:
                return False
            db.connected = True
            db.epf_last_seen = time.time()
            return True

    def arm_unregister_grace(self, name: str, seconds: float) -> bool:
        """Ignore stale EPF unregister events for a short period after reconnect."""
        with self._lock:
            db = self._databases.get(name)
            if db is None:
                return False
            db.ignore_unregister_until = max(db.ignore_unregister_until, time.time() + max(seconds, 0.0))
            return True

    def mark_epf_disconnected(self, name: str, *, force: bool = False) -> bool:
        """Mark EPF as disconnected for a database."""
        with self._lock:
            db = self._databases.get(name)
            if db is None:
                return False
            now = time.time()
            if not force and db.ignore_unregister_until > now:
                log.info(
                    "Ignoring stale EPF unregister for database: %s (grace %.1fs left)",
                    name,
                    db.ignore_unregister_until - now,
                )
                return True
            db.connected = False
            db.epf_last_seen = 0.0
            db.ignore_unregister_until = 0.0
            log.info(f"EPF disconnected for database: {name}")
            return True

    def expire_stale_epf(self, max_age_seconds: int, now: float | None = None) -> int:
        """Mark EPF as disconnected when heartbeat is older than max_age_seconds."""
        if max_age_seconds <= 0:
            return 0
        ts_now = time.time() if now is None else now
        expired = 0
        with self._lock:
            for db in self._databases.values():
                if not db.connected:
                    continue
                if db.epf_last_seen <= 0.0 or (ts_now - db.epf_last_seen) > max_age_seconds:
                    db.connected = False
                    db.epf_last_seen = 0.0
                    expired += 1
        return expired

    def update_runtime(
        self,
        name: str,
        *,
        toolkit_port: int | None = None,
        toolkit_url: str | None = None,
        lsp_container: str | None = None,
        channel_id: str | None = None,
        connected: bool | None = None,
    ) -> bool:
        """Update non-persistent runtime fields for a database atomically."""
        with self._lock:
            db = self._databases.get(name)
            if db is None:
                return False
            if toolkit_port is not None:
                db.toolkit_port = toolkit_port
            if toolkit_url is not None:
                db.toolkit_url = toolkit_url
            if lsp_container is not None:
                db.lsp_container = lsp_container
            if channel_id is not None:
                db.channel_id = channel_id
            if connected is not None:
                db.connected = connected
                db.epf_last_seen = time.time() if connected else 0.0
            return True

    def update(self, name: str, connection: str | None = None, project_path: str | None = None) -> bool:
        """Update database connection/project_path atomically and persist state."""
        with self._lock:
            db = self._databases.get(name)
            if db is None:
                return False
            if connection:
                db.connection = connection
            if project_path:
                db.project_path = project_path
            self._save_state()
            return True

    def get(self, name: str) -> Optional[DatabaseInfo]:
        with self._lock:
            return self._databases.get(name)

    def get_active(self) -> Optional[DatabaseInfo]:
        with self._lock:
            if self._active and self._active in self._databases:
                return self._databases[self._active]
            return None

    def switch(self, name: str) -> bool:
        with self._lock:
            if name not in self._databases:
                return False
            self._active = name
            log.info(f"Active database switched to: {name}")
            self._save_state()
            return True

    def list(self) -> list[dict]:
        with self._lock:
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
        with self._lock:
            if name not in self._databases:
                return False
            del self._databases[name]
            if self._active == name:
                self._active = next(iter(self._databases), None)
            self._save_state()
            return True

    @property
    def active_name(self) -> Optional[str]:
        with self._lock:
            return self._active

    # --- Persistence ---

    def _save_state(self) -> None:
        """Persist database configs to JSON for auto-reconnect on restart."""
        state = {
            "active": self._active,
            "databases": [
                {
                    "name": db.name,
                    "slug": db.slug,
                    "connection": db.connection,
                    "project_path": db.project_path,
                }
                for db in self._databases.values()
            ],
        }
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(state, ensure_ascii=False, indent=2)
            tmp = self._state_file.with_suffix(self._state_file.suffix + ".tmp")
            tmp.write_text(payload, encoding="utf-8")
            tmp.replace(self._state_file)
        except Exception as exc:
            log.warning(f"Failed to save DB state: {exc}")

    def load_saved_state(self) -> list[dict]:
        """Load saved database configs. Returns list of {name, connection, project_path}."""
        if not self._state_file.exists():
            return []
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            saved_active = data.get("active")
            databases = data.get("databases", [])
            log.info(f"Loaded saved state: {len(databases)} database(s), active={saved_active}")
            return databases
        except Exception as exc:
            log.warning(f"Failed to load DB state: {exc}")
            return []

    def get_saved_active(self) -> Optional[str]:
        """Get the active database name from saved state."""
        if not self._state_file.exists():
            return None
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return data.get("active")
        except Exception:
            return None


# Singleton — injected into server.py
registry = DatabaseRegistry()

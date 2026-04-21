"""Compatibility wrapper around StreamableHTTPSessionManager internals.

The underlying MCP library does not expose a public API for enumerating
terminated transports, so this adapter keeps the private-field dependency
localized in one place.
"""

from __future__ import annotations


def _instances_map(session_manager) -> dict | None:
    instances = getattr(session_manager, "_server_instances", None)
    return instances if isinstance(instances, dict) else None


def terminated_session_ids(session_manager) -> list[str]:
    """Return IDs of transports marked as terminated by the MCP manager."""
    instances = _instances_map(session_manager)
    if not instances:
        return []
    return [
        sid
        for sid, transport in instances.items()
        if getattr(transport, "_terminated", False)
    ]


def drop_sessions(session_manager, session_ids: list[str]) -> int:
    """Remove session IDs from the manager's internal transport map."""
    instances = _instances_map(session_manager)
    if not instances:
        return 0
    removed = 0
    for sid in session_ids:
        if sid in instances:
            instances.pop(sid, None)
            removed += 1
    return removed


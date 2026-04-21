"""Tests for gateway.session_cleanup compatibility adapter."""

from __future__ import annotations

from gateway.session_cleanup import drop_sessions, terminated_session_ids


class _Transport:
    def __init__(self, terminated: bool):
        self._terminated = terminated


class _SessionManager:
    def __init__(self, instances):
        self._server_instances = instances


def test_terminated_session_ids_reads_private_map_safely():
    sm = _SessionManager(
        {
            "dead-1": _Transport(True),
            "alive": _Transport(False),
            "dead-2": _Transport(True),
        }
    )
    assert sorted(terminated_session_ids(sm)) == ["dead-1", "dead-2"]


def test_terminated_session_ids_handles_missing_map():
    sm = _SessionManager(None)
    assert terminated_session_ids(sm) == []


def test_drop_sessions_removes_only_existing_entries():
    sm = _SessionManager(
        {
            "dead-1": _Transport(True),
            "alive": _Transport(False),
        }
    )
    removed = drop_sessions(sm, ["dead-1", "ghost"])
    assert removed == 1
    assert "dead-1" not in sm._server_instances
    assert "alive" in sm._server_instances


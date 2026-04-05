"""Tests for DatabaseRegistry persistence."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.db_registry import DatabaseRegistry


@pytest.fixture
def registry(tmp_path):
    state_file = tmp_path / "db_state.json"
    return DatabaseRegistry(state_file=state_file)


def test_register_and_list(registry):
    registry.register("db1", "Srvr=srv;Ref=db1;", "/projects/db1")
    dbs = registry.list()
    assert len(dbs) == 1
    assert dbs[0]["name"] == "db1"
    assert dbs[0]["active"] is True


def test_switch(registry):
    registry.register("db1", "conn1", "/p1")
    registry.register("db2", "conn2", "/p2")
    assert registry.active_name == "db1"

    registry.switch("db2")
    assert registry.active_name == "db2"


def test_switch_nonexistent(registry):
    assert not registry.switch("nope")


def test_remove(registry):
    registry.register("db1", "conn1", "/p1")
    assert registry.remove("db1")
    assert registry.list() == []
    assert registry.active_name is None


def test_remove_switches_active(registry):
    registry.register("db1", "conn1", "/p1")
    registry.register("db2", "conn2", "/p2")
    registry.switch("db1")
    registry.remove("db1")
    assert registry.active_name == "db2"


def test_persistence_save_and_load(registry):
    registry.register("erp", "Srvr=srv;Ref=erp;", "/z/erp")
    registry.register("zup", "Srvr=srv;Ref=zup;", "/z/zup")
    registry.switch("zup")

    # Create new registry from same file
    registry2 = DatabaseRegistry(state_file=registry._state_file)
    saved = registry2.load_saved_state()
    assert len(saved) == 2
    names = {d["name"] for d in saved}
    assert names == {"erp", "zup"}
    assert registry2.get_saved_active() == "zup"


def test_persistence_empty_file(tmp_path):
    state_file = tmp_path / "empty.json"
    reg = DatabaseRegistry(state_file=state_file)
    assert reg.load_saved_state() == []
    assert reg.get_saved_active() is None


def test_persistence_corrupt_file(tmp_path):
    state_file = tmp_path / "corrupt.json"
    state_file.write_text("not json at all", encoding="utf-8")
    reg = DatabaseRegistry(state_file=state_file)
    assert reg.load_saved_state() == []


def test_mark_epf_connected(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    db = registry.get("db1")
    assert db.connected is True


def test_get_active(registry):
    assert registry.get_active() is None
    registry.register("db1", "conn1", "/p1")
    assert registry.get_active().name == "db1"

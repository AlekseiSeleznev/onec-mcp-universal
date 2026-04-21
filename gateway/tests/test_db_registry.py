"""Tests for DatabaseRegistry persistence."""

import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.db_registry import DatabaseRegistry, _default_state_file


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


def test_default_state_file_prefers_data_mount(monkeypatch):
    monkeypatch.setattr(Path, "exists", lambda self: str(self) == "/data", raising=False)
    assert _default_state_file() == Path("/data/db_state.json")


def test_default_state_file_uses_xdg_config_when_data_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "exists", lambda self: False, raising=False)
    expected = tmp_path / "xdg" / "onec-gateway" / "db_state.json"
    assert _default_state_file() == expected


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


def test_remove_non_active_database_keeps_current_active(registry):
    registry.register("db1", "conn1", "/p1")
    registry.register("db2", "conn2", "/p2")
    registry.switch("db1")
    registry.remove("db2")
    assert registry.active_name == "db1"


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


def test_persistence_uses_atomic_replace(registry):
    registry.register("erp", "Srvr=srv;Ref=erp;", "/z/erp")
    state_file = registry._state_file
    tmp_file = state_file.with_suffix(state_file.suffix + ".tmp")

    assert state_file.exists()
    assert not tmp_file.exists()


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


def test_get_saved_active_returns_none_for_corrupt_file(tmp_path):
    state_file = tmp_path / "corrupt.json"
    state_file.write_text("not json at all", encoding="utf-8")
    reg = DatabaseRegistry(state_file=state_file)
    assert reg.get_saved_active() is None


def test_mark_epf_connected(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    db = registry.get("db1")
    assert db.connected is True


def test_mark_epf_connected_missing_database_is_noop(registry):
    registry.mark_epf_connected("ghost")
    assert registry.list() == []


def test_mark_epf_disconnected(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    assert registry.mark_epf_disconnected("db1") is True
    db = registry.get("db1")
    assert db.connected is False


def test_mark_epf_disconnected_not_found(registry):
    assert registry.mark_epf_disconnected("ghost") is False


def test_mark_epf_disconnected_ignores_stale_unregister_during_grace(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    assert registry.arm_unregister_grace("db1", 15) is True
    assert registry.mark_epf_disconnected("db1") is True
    db = registry.get("db1")
    assert db.connected is True


def test_mark_epf_disconnected_force_overrides_grace(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    assert registry.arm_unregister_grace("db1", 15) is True
    assert registry.mark_epf_disconnected("db1", force=True) is True
    db = registry.get("db1")
    assert db.connected is False


def test_mark_epf_heartbeat(registry):
    registry.register("db1", "conn1", "/p1")
    assert registry.mark_epf_heartbeat("db1") is True
    db = registry.get("db1")
    assert db.connected is True
    assert db.epf_last_seen > 0


def test_arm_unregister_grace_missing_database_returns_false(registry):
    assert registry.arm_unregister_grace("ghost", 10) is False


def test_mark_epf_heartbeat_unknown_database_returns_false(registry):
    assert registry.mark_epf_heartbeat("ghost") is False


def test_expire_stale_epf(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    db = registry.get("db1")
    db.epf_last_seen = 100.0

    expired = registry.expire_stale_epf(30, now=200.0)

    assert expired == 1
    assert registry.get("db1").connected is False


def test_expire_stale_epf_skips_fresh(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    db = registry.get("db1")
    db.epf_last_seen = 180.0

    expired = registry.expire_stale_epf(30, now=200.0)

    assert expired == 0
    assert registry.get("db1").connected is True


def test_expire_stale_epf_disabled_when_max_age_non_positive(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    assert registry.expire_stale_epf(0, now=200.0) == 0
    assert registry.get("db1").connected is True


def test_get_active(registry):
    assert registry.get_active() is None
    registry.register("db1", "conn1", "/p1")
    assert registry.get_active().name == "db1"


def test_get_active_returns_none_when_active_name_points_to_missing_db(registry):
    registry.register("db1", "conn1", "/p1")
    registry._active = "ghost"
    assert registry.get_active() is None


def test_mark_epf_connected_thread_safe(registry):
    registry.register("db1", "conn1", "/p1")
    errors: list[Exception] = []

    def worker():
        try:
            registry.mark_epf_connected("db1")
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert registry.get("db1").connected is True


def test_update_db_fields(registry):
    registry.register("db1", "conn1", "/p1")

    assert registry.update("db1", connection="conn2", project_path="/p2")
    db = registry.get("db1")
    assert db.connection == "conn2"
    assert db.project_path == "/p2"


def test_update_db_fields_keeps_existing_values_when_arguments_empty(registry):
    registry.register("db1", "conn1", "/p1")

    assert registry.update("db1", connection="", project_path="") is True
    db = registry.get("db1")
    assert db.connection == "conn1"
    assert db.project_path == "/p1"


def test_register_existing_database_preserves_slug_when_new_slug_empty(registry):
    registry.register("db1", "conn1", "/p1", slug="slug-1")
    registry.register("db1", "conn2", "/p2", slug="")
    db = registry.get("db1")
    assert db.connection == "conn2"
    assert db.project_path == "/p2"
    assert db.slug == "slug-1"


def test_register_existing_database_updates_slug_when_new_slug_provided(registry):
    registry.register("db1", "conn1", "/p1", slug="slug-1")
    registry.register("db1", "conn2", "/p2", slug="slug-2")
    assert registry.get("db1").slug == "slug-2"


def test_update_db_not_found(registry):
    assert registry.update("ghost", connection="conn2", project_path="/p2") is False


def test_remove_missing_database_returns_false(registry):
    assert registry.remove("ghost") is False


def test_update_db_thread_safe(registry):
    registry.register("db1", "conn1", "/p1")
    errors: list[Exception] = []

    def worker(idx: int):
        try:
            registry.update("db1", connection=f"conn-{idx}", project_path=f"/p/{idx}")
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    db = registry.get("db1")
    assert db.connection.startswith("conn-")
    assert db.project_path.startswith("/p/")


def test_update_runtime_fields(registry):
    registry.register("db1", "conn1", "/p1")

    assert registry.update_runtime(
        "db1",
        toolkit_port=6101,
        toolkit_url="http://localhost:6101/mcp",
        lsp_container="mcp-lsp-db1",
        channel_id="z01-live",
        connected=True,
    )
    db = registry.get("db1")
    assert db.toolkit_port == 6101
    assert db.toolkit_url == "http://localhost:6101/mcp"
    assert db.lsp_container == "mcp-lsp-db1"
    assert db.channel_id == "z01-live"
    assert db.connected is True


def test_update_runtime_can_update_fields_independently(registry):
    registry.register("db1", "conn1", "/p1")
    assert registry.update_runtime("db1", toolkit_port=6101, lsp_container="mcp-lsp-db1")
    db = registry.get("db1")
    assert db.toolkit_port == 6101
    assert db.lsp_container == "mcp-lsp-db1"
    assert db.toolkit_url == ""


def test_update_runtime_can_reset_connected_state(registry):
    registry.register("db1", "conn1", "/p1")
    registry.mark_epf_connected("db1")
    assert registry.update_runtime("db1", connected=False) is True
    db = registry.get("db1")
    assert db.connected is False
    assert db.epf_last_seen == 0.0


def test_remove_unknown_database_returns_false(registry):
    assert registry.remove("ghost") is False


def test_save_state_failures_are_swallowed(registry, monkeypatch):
    class _BrokenTmp:
        def write_text(self, *_args, **_kwargs):
            raise OSError("disk full")

        def replace(self, *_args, **_kwargs):
            raise AssertionError("replace should not be reached")

    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(Path, "with_suffix", lambda self, suffix: _BrokenTmp(), raising=False)

    registry.register("db1", "conn1", "/p1")


def test_update_runtime_not_found(registry):
    assert registry.update_runtime("ghost", connected=False) is False

"""Tests for BSL search index."""

import sys
import time
import threading
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.bsl_search import BslSearchIndex


def _create_bsl_tree(tmp_path: Path) -> None:
    """Create a minimal BSL file structure for testing."""
    module_dir = tmp_path / "CommonModules" / "ОбщегоНазначения" / "Ext"
    module_dir.mkdir(parents=True)
    (module_dir / "Module.bsl").write_text(
        '// Получает значения реквизитов объекта\n'
        '// Параметры:\n'
        '//   Ссылка - ЛюбаяСсылка\n'
        'Функция ЗначенияРеквизитовОбъекта(Ссылка, Реквизиты) Экспорт\n'
        '    Возврат Неопределено;\n'
        'КонецФункции\n'
        '\n'
        'Процедура СообщитьПользователю(Текст, Объект) Экспорт\n'
        'КонецПроцедуры\n'
        '\n'
        'Функция ВнутренняяФункция()\n'
        '    Возврат 1;\n'
        'КонецФункции\n',
        encoding="utf-8-sig",
    )

    doc_dir = tmp_path / "Documents" / "Реализация" / "Ext"
    doc_dir.mkdir(parents=True)
    (doc_dir / "ObjectModule.bsl").write_text(
        'Процедура ПередЗаписью(Отказ) Экспорт\n'
        'КонецПроцедуры\n',
        encoding="utf-8-sig",
    )


def test_build_index(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    result = idx.build_index(str(tmp_path))
    assert "4" in result  # 4 symbols
    assert idx.indexed
    assert idx.symbol_count == 4


def test_build_index_returns_permission_error_when_bsl_files_unreadable(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()

    with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
        result = idx.build_index(str(tmp_path))

    assert result == (
        f"ERROR: Permission denied reading 2 BSL files in {tmp_path}. "
        "Verify export file permissions for the gateway user."
    )
    assert idx.indexed is False


def test_search_by_name(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ЗначенияРеквизитовОбъекта")
    assert len(results) >= 1
    assert results[0]["name"] == "ЗначенияРеквизитовОбъекта"
    assert results[0]["export"] is True


def test_search_by_module(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ОбщегоНазначения")
    assert len(results) >= 2  # Functions from that module


def test_search_export_only(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("Функция", export_only=True)
    # ВнутренняяФункция is NOT exported
    names = [r["name"] for r in results]
    assert "ВнутренняяФункция" not in names


def test_search_no_results(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("НесуществующаяФункция")
    assert results == []


def test_search_empty_index():
    idx = BslSearchIndex()
    assert idx.search("anything") == []


def test_module_name_derivation(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    results = idx.search("ПередЗаписью")
    assert len(results) >= 1
    assert "Документ.Реализация" in results[0]["module"]


def test_index_snapshot_can_be_loaded_by_path(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    idx2 = BslSearchIndex()
    assert idx2.ensure_loaded(str(tmp_path)) is True
    assert idx2.indexed
    assert idx2.symbol_count == 4


def test_ensure_loaded_rebuilds_when_snapshot_missing(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    snapshot = idx._snapshot_path(str(tmp_path))
    if snapshot.exists():
        snapshot.unlink()

    assert idx.ensure_loaded(str(tmp_path)) is True
    assert idx.indexed
    assert idx.symbol_count == 4


def test_build_index_uses_projects_root_for_container_paths():
    idx = BslSearchIndex()

    captured = {}

    def fake_build(container: str, bsl_root: str = "/projects"):
        captured["container"] = container
        captured["bsl_root"] = bsl_root
        return "ok"

    idx._build_index_docker = fake_build  # type: ignore[method-assign]

    result = idx.build_index("/hostfs-home/as/Z/ERPPur_Local", container="mcp-lsp-ERPPur_Local")

    assert result == "ok"
    assert captured == {
        "container": "mcp-lsp-ERPPur_Local",
        "bsl_root": "/projects",
    }


def test_default_cache_dir_falls_back_to_xdg_cache(monkeypatch, tmp_path):
    from gateway.bsl_search import _default_cache_dir

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with patch("gateway.bsl_search.Path.exists", return_value=False):
        result = _default_cache_dir()

    assert result == tmp_path / "onec-gateway" / "bsl-search-cache"


def test_default_cache_dir_prefers_data_volume(monkeypatch):
    from gateway.bsl_search import _default_cache_dir

    with patch("gateway.bsl_search.Path.exists", return_value=True):
        assert _default_cache_dir() == Path("/data/bsl-search-cache")


def test_load_index_returns_false_when_snapshot_missing(tmp_path):
    idx = BslSearchIndex()
    assert idx.load_index(str(tmp_path)) is False


def test_load_index_handles_corrupt_snapshot(tmp_path):
    idx = BslSearchIndex()
    snapshot = idx._snapshot_path(str(tmp_path))
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("not-json", encoding="utf-8")

    assert idx.load_index(str(tmp_path)) is False


def test_save_snapshot_handles_write_failure(tmp_path):
    idx = BslSearchIndex()
    idx._symbols = []

    with patch.object(Path, "write_text", side_effect=OSError("boom")):
        idx._save_snapshot(str(tmp_path))


def test_ensure_loaded_returns_cached_result_without_reload(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    with patch.object(idx, "load_index", side_effect=AssertionError("should not load")):
        assert idx.ensure_loaded(str(tmp_path)) is True


def test_ensure_loaded_returns_false_for_missing_root(tmp_path):
    idx = BslSearchIndex()
    missing = tmp_path / "missing"
    assert idx.ensure_loaded(str(missing)) is False


def test_ensure_loaded_uses_compatible_snapshot_for_same_db_basename(tmp_path):
    old_root = tmp_path / "legacy-root" / "Z01"
    old_root.mkdir(parents=True)
    _create_bsl_tree(old_root)

    writer = BslSearchIndex()
    assert writer.build_index(str(old_root)).startswith("Indexed")

    idx = BslSearchIndex()
    idx._cache_dir = writer._cache_dir

    new_root = tmp_path / "new-root" / "Z01"
    assert new_root.exists() is False

    assert idx.ensure_loaded(str(new_root)) is True
    assert idx.symbol_count > 0


def test_load_compatible_snapshot_returns_false_when_cache_dir_missing(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "missing-cache"
    assert idx._load_compatible_snapshot(str(tmp_path / "Z01")) is False


def test_load_compatible_snapshot_returns_false_when_requested_name_is_empty(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "cache"
    idx._cache_dir.mkdir(parents=True)
    assert idx._load_compatible_snapshot("") is False


def test_load_compatible_snapshot_ignores_stat_error_and_loads_snapshot(tmp_path):
    old_root = tmp_path / "legacy-root" / "Z01"
    old_root.mkdir(parents=True)
    _create_bsl_tree(old_root)

    writer = BslSearchIndex()
    assert writer.build_index(str(old_root)).startswith("Indexed")

    idx = BslSearchIndex()
    idx._cache_dir = writer._cache_dir

    original_stat = Path.stat

    def _stat(self, *args, **kwargs):
        if self.suffix == ".json" and self.name != idx._cache_dir.name:
            raise OSError("boom")
        return original_stat(self, *args, **kwargs)

    with patch.object(Path, "stat", _stat):
        assert idx._load_compatible_snapshot(str(tmp_path / "new-root" / "Z01")) is True


def test_load_compatible_snapshot_skips_corrupt_candidate(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "cache"
    idx._cache_dir.mkdir(parents=True)
    (idx._cache_dir / "bad.json").write_text('{"indexed_path": "/x/Z01", "symbols": [', encoding="utf-8")
    assert idx._load_compatible_snapshot(str(tmp_path / "new-root" / "Z01")) is False


def test_load_compatible_snapshot_logs_and_skips_invalid_symbol_payload(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "cache"
    idx._cache_dir.mkdir(parents=True)
    (idx._cache_dir / "bad.json").write_text(
        '{"indexed_path": "/x/Z01", "symbols": [{"name": "broken"}]}',
        encoding="utf-8",
    )

    assert idx._load_compatible_snapshot(str(tmp_path / "new-root" / "Z01")) is False


def test_ensure_loaded_uses_container_projects_snapshot_for_same_db(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "cache"
    idx._cache_dir.mkdir(parents=True)

    snapshot_root = "mcp-lsp-Z01:/projects"
    snapshot = idx._snapshot_path(snapshot_root)
    snapshot.write_text(
        '{"indexed_path": "mcp-lsp-Z01:/projects", "symbols": ['
        '{"name": "Тест", "kind": "Функция", "params": "", "export": true, '
        '"file": "CommonModules/Test/Ext/Module.bsl", "module": "ОбщийМодуль.Тест", '
        '"line": 1, "comment": ""}'
        ']}',
        encoding="utf-8",
    )

    requested_root = "mcp-lsp-Z01:/hostfs-home/as/Z/Z01"

    assert idx.ensure_loaded(requested_root) is True
    assert idx.symbol_count == 1
    assert idx.indexed_path == snapshot_root


def test_ensure_loaded_builds_from_existing_root_when_snapshot_missing(tmp_path):
    root = tmp_path / "Z01"
    _create_bsl_tree(root)
    idx = BslSearchIndex()
    assert idx.ensure_loaded(str(root)) is True
    assert idx.symbol_count > 0


def test_ensure_loaded_returns_true_when_build_index_succeeds_for_existing_root(tmp_path):
    root = tmp_path / "Z01"
    root.mkdir(parents=True)
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "empty-cache"

    with patch.object(idx, "load_index", return_value=False), patch.object(
        idx, "_load_compatible_snapshot", return_value=False
    ), patch.object(idx, "build_index", return_value="Indexed 1 symbols from 1 BSL files"):
        assert idx.ensure_loaded(str(root)) is True


def test_clear_resets_loaded_index(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))
    idx.clear()

    assert idx.indexed is False
    assert idx.symbol_count == 0
    assert idx.indexed_path == ""


def test_invalidate_paths_clears_loaded_index_and_snapshot(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))
    snapshot = idx._snapshot_path(str(tmp_path))
    assert snapshot.exists()

    assert idx.invalidate_paths(str(tmp_path)) is True
    assert idx.indexed is False
    assert snapshot.exists() is False


def test_invalidate_paths_returns_false_for_empty_input():
    idx = BslSearchIndex()
    assert idx.invalidate_paths("", "   ") is False


def test_invalidate_paths_logs_unlink_failure(tmp_path):
    idx = BslSearchIndex()
    snapshot = idx._snapshot_path(str(tmp_path))
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text("{}", encoding="utf-8")

    with patch.object(Path, "unlink", side_effect=OSError("boom")):
        assert idx.invalidate_paths(str(tmp_path)) is False


def test_invalidate_paths_ignores_missing_snapshot_file(tmp_path):
    idx = BslSearchIndex()
    assert idx.invalidate_paths(str(tmp_path)) is False


def test_invalidate_paths_handles_file_not_found_during_unlink(tmp_path):
    idx = BslSearchIndex()

    with patch.object(Path, "unlink", side_effect=FileNotFoundError):
        assert idx.invalidate_paths(str(tmp_path / "missing")) is False


def test_container_bsl_root_translation():
    idx = BslSearchIndex()

    assert idx._container_bsl_root("") == "/projects"
    assert idx._container_bsl_root("/projects") == "/projects"
    assert idx._container_bsl_root("/projects/Test") == "/projects/Test"
    assert idx._container_bsl_root("/hostfs-home/as/Z/ERP") == "/projects"


def test_gateway_visible_root_defaults_to_workspace():
    idx = BslSearchIndex()

    assert idx._gateway_visible_root("") == "/workspace"


def test_gateway_visible_root_translates_projects_paths():
    idx = BslSearchIndex()

    assert idx._gateway_visible_root("/projects") == "/workspace"
    assert idx._gateway_visible_root("/projects/ERP") == "/workspace/ERP"


def test_gateway_visible_root_handles_windows_style_container_prefix():
    idx = BslSearchIndex()

    assert idx._gateway_visible_root("C:/projects/ERP") == "/workspace/ERP"


def test_gateway_visible_root_keeps_drive_prefix_without_suffix():
    idx = BslSearchIndex()

    assert idx._gateway_visible_root("C:") == "C:"


def test_build_index_reports_missing_directory(tmp_path):
    idx = BslSearchIndex()
    missing = tmp_path / "missing"
    result = idx.build_index(str(missing))
    assert result == f"ERROR: Directory {missing} does not exist."


def test_build_index_reports_no_bsl_files(tmp_path):
    idx = BslSearchIndex()
    result = idx.build_index(str(tmp_path))
    assert result == f"ERROR: No BSL files found in {tmp_path}."


def test_build_index_uses_compatible_snapshot_when_directory_is_empty(tmp_path):
    old_root = tmp_path / "legacy-root" / "Z01"
    old_root.mkdir(parents=True)
    _create_bsl_tree(old_root)

    writer = BslSearchIndex()
    assert writer.build_index(str(old_root)).startswith("Indexed")

    idx = BslSearchIndex()
    idx._cache_dir = writer._cache_dir

    empty_root = tmp_path / "new-root" / "Z01"
    empty_root.mkdir(parents=True)

    result = idx.build_index(str(empty_root))

    assert result.startswith("Indexed ")
    assert "cached snapshot" in result


def test_build_index_uses_compatible_snapshot_when_rglob_permission_denied(tmp_path):
    old_root = tmp_path / "legacy-root" / "Z01"
    old_root.mkdir(parents=True)
    _create_bsl_tree(old_root)

    writer = BslSearchIndex()
    assert writer.build_index(str(old_root)).startswith("Indexed")

    idx = BslSearchIndex()
    idx._cache_dir = writer._cache_dir

    locked_root = tmp_path / "locked-root" / "Z01"
    locked_root.mkdir(parents=True)

    with patch.object(Path, "rglob", side_effect=PermissionError("denied")):
        result = idx.build_index(str(locked_root))

    assert result.startswith("Indexed ")
    assert "cached snapshot" in result


def test_build_index_uses_compatible_snapshot_when_root_exists_check_is_denied(tmp_path):
    old_root = tmp_path / "legacy-root" / "Z01"
    old_root.mkdir(parents=True)
    _create_bsl_tree(old_root)

    writer = BslSearchIndex()
    assert writer.build_index(str(old_root)).startswith("Indexed")

    idx = BslSearchIndex()
    idx._cache_dir = writer._cache_dir

    original_exists = Path.exists

    def _exists(self):
        if str(self).endswith("/blocked-root/Z01"):
            raise PermissionError("denied")
        return original_exists(self)

    with patch.object(Path, "exists", _exists):
        result = idx.build_index(str(tmp_path / "blocked-root" / "Z01"))

    assert result.startswith("Indexed ")
    assert "cached snapshot" in result


def test_build_index_reports_permission_denied_when_exists_check_blocked_without_snapshot(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "empty-cache"
    original_exists = Path.exists

    def _exists(self):
        if str(self).endswith("/blocked-root/Z01"):
            raise PermissionError("denied")
        return original_exists(self)

    with patch.object(Path, "exists", _exists):
        result = idx.build_index(str(tmp_path / "blocked-root" / "Z01"))

    assert "ERROR: Permission denied accessing" in result


def test_build_index_reports_permission_denied_when_rglob_blocked_without_snapshot(tmp_path):
    idx = BslSearchIndex()
    idx._cache_dir = tmp_path / "empty-cache"
    root = tmp_path / "Z01"
    root.mkdir(parents=True)

    with patch.object(Path, "rglob", side_effect=PermissionError("denied")):
        result = idx.build_index(str(root))

    assert "ERROR: Permission denied listing BSL files" in result


def test_build_index_docker_timeout():
    idx = BslSearchIndex()

    with patch.object(BslSearchIndex, "_build_index_via_docker_control", return_value=None), \
         patch("gateway.bsl_search.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=120)):
        result = idx._build_index_docker("container")

    assert result == "ERROR: grep timed out after 120s."


def test_build_index_docker_uses_docker_control_when_configured(monkeypatch):
    idx = BslSearchIndex()
    monkeypatch.setenv("DOCKER_CONTROL_URL", "http://docker-control:8091")
    monkeypatch.setenv("DOCKER_CONTROL_TOKEN", "secret")
    resp = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "ok": True,
                "output": "/projects/CommonModules/Test/Ext/Module.bsl:4:Функция Good(Парам) Экспорт\n",
            }
        ),
    )

    with patch("gateway.bsl_search.httpx.post", return_value=resp) as post_mock, patch(
        "gateway.bsl_search.subprocess.run"
    ) as run_mock:
        result = idx._build_index_docker("container", "/projects")

    assert "Indexed 1 symbols" in result
    assert idx.symbol_count == 1
    assert idx.search("Good")[0]["export"] is True
    run_mock.assert_not_called()
    headers = post_mock.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret"


def test_build_index_docker_returns_docker_control_error(monkeypatch):
    idx = BslSearchIndex()
    monkeypatch.setenv("DOCKER_CONTROL_URL", "http://docker-control:8091")
    resp = MagicMock(status_code=503, json=MagicMock(return_value={"ok": False, "error": "sidecar down"}))

    with patch("gateway.bsl_search.httpx.post", return_value=resp), patch(
        "gateway.bsl_search.subprocess.run"
    ) as run_mock:
        result = idx._build_index_docker("container", "/projects")

    assert result == "ERROR: sidecar down"
    run_mock.assert_not_called()


def test_build_index_docker_handles_non_json_docker_control_error(monkeypatch):
    idx = BslSearchIndex()
    monkeypatch.setenv("DOCKER_CONTROL_URL", "http://docker-control:8091")
    resp = MagicMock(status_code=502)
    resp.json.side_effect = ValueError("not json")

    with patch("gateway.bsl_search.httpx.post", return_value=resp), patch(
        "gateway.bsl_search.subprocess.run"
    ) as run_mock:
        result = idx._build_index_docker("container", "/projects")

    assert result == "ERROR: docker-control returned HTTP 502"
    run_mock.assert_not_called()


def test_build_index_docker_falls_back_to_subprocess_when_docker_control_unreachable(monkeypatch):
    idx = BslSearchIndex()
    monkeypatch.setenv("DOCKER_CONTROL_URL", "http://docker-control:8091")
    proc = MagicMock(
        stdout="/projects/CommonModules/Test/Ext/Module.bsl:4:Функция Good(Парам) Экспорт\n",
        returncode=0,
    )

    with patch("gateway.bsl_search.httpx.post", side_effect=RuntimeError("boom")), patch(
        "gateway.bsl_search.subprocess.run", return_value=proc
    ):
        result = idx._build_index_docker("container", "/projects")

    assert "Indexed 1 symbols" in result


def test_build_index_docker_generic_error():
    idx = BslSearchIndex()

    with patch.object(BslSearchIndex, "_build_index_via_docker_control", return_value=None), \
         patch("gateway.bsl_search.subprocess.run", side_effect=RuntimeError("boom")):
        result = idx._build_index_docker("container")

    assert result == "ERROR: boom"


def test_build_index_docker_reports_no_symbols():
    idx = BslSearchIndex()
    proc = MagicMock(stdout="", returncode=0)

    with patch.object(BslSearchIndex, "_build_index_via_docker_control", return_value=None), \
         patch("gateway.bsl_search.subprocess.run", return_value=proc):
        result = idx._build_index_docker("container", "/projects")

    assert result == "ERROR: No BSL symbols found in container:/projects."


def test_build_index_docker_ignores_invalid_lines_and_parses_valid_symbol():
    idx = BslSearchIndex()
    proc = MagicMock(
        stdout=(
            "broken-line\n"
            "/projects/CommonModules/Test/Ext/Module.bsl:notint:Функция Bad()\n"
            "/projects/CommonModules/Test/Ext/Module.bsl:4:Функция Good(Парам) Экспорт\n"
        ),
        returncode=0,
    )

    with patch.object(BslSearchIndex, "_build_index_via_docker_control", return_value=None), \
         patch("gateway.bsl_search.subprocess.run", return_value=proc):
        result = idx._build_index_docker("container", "/projects")

    assert "Indexed 1 symbols" in result
    assert idx.symbol_count == 1
    assert idx.search("Good")[0]["export"] is True


def test_build_index_docker_skips_non_matching_declarations():
    idx = BslSearchIndex()
    proc = MagicMock(
        stdout="/projects/CommonModules/Test/Ext/Module.bsl:4:Перем Something\n",
        returncode=0,
    )

    with patch.object(BslSearchIndex, "_build_index_via_docker_control", return_value=None), \
         patch("gateway.bsl_search.subprocess.run", return_value=proc):
        result = idx._build_index_docker("container", "/projects")

    assert result == "Indexed 0 symbols from 0 BSL files in container:/projects."


def test_build_index_serializes_concurrent_runs_on_shared_index(tmp_path):
    root_a = tmp_path / "Z01"
    root_b = tmp_path / "Z02"
    for root, count in ((root_a, 2), (root_b, 1)):
        for idx_file in range(count):
            module_dir = root / "CommonModules" / f"Модуль{idx_file}" / "Ext"
            module_dir.mkdir(parents=True, exist_ok=True)
            (module_dir / "Module.bsl").write_text(
                f"Функция Тест{idx_file}() Экспорт\nКонецФункции\n",
                encoding="utf-8-sig",
            )

    idx = BslSearchIndex()

    original_index_file = idx._index_file

    def slow_index_file(filepath, root, symbols=None):
        original_index_file(filepath, root, symbols)
        time.sleep(0.05)

    idx._index_file = slow_index_file  # type: ignore[method-assign]

    results = {}

    def run(name, root):
        results[name] = idx.build_index(str(root))

    thread_a = threading.Thread(target=run, args=("A", root_a))
    thread_b = threading.Thread(target=run, args=("B", root_b))

    thread_a.start()
    time.sleep(0.02)
    thread_b.start()
    thread_a.join()
    thread_b.join()

    assert results["A"].startswith(f"Indexed 2 symbols from 2 BSL files in {root_a}")
    assert results["B"].startswith(f"Indexed 1 symbols from 1 BSL files in {root_b}")


def test_derive_module_name_for_constant():
    idx = BslSearchIndex()
    assert idx._derive_module_name(("Constants", "Имя", "Ext", "ManagerModule.bsl")) == "Константа.Имя"


def test_derive_module_name_falls_back_to_folder_path():
    idx = BslSearchIndex()
    assert idx._derive_module_name(("SomeFolder", "Inner", "Module.bsl")) == "SomeFolder.Inner"


def test_derive_module_name_empty_parts():
    idx = BslSearchIndex()
    assert idx._derive_module_name(tuple()) == ""


def test_search_matches_comment_and_multiword(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    comment_results = idx.search("значения реквизитов")
    multiword_results = idx.search("общего значения")

    assert comment_results
    assert multiword_results


def test_search_exact_startswith_contains_and_module_scoring(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()
    idx.build_index(str(tmp_path))

    exact = idx.search("ЗначенияРеквизитовОбъекта")
    startswith = idx.search("Значения")
    contains = idx.search("Реквизитов")
    module_match = idx.search("Документ.Реализация")

    assert exact[0]["name"] == "ЗначенияРеквизитовОбъекта"
    assert startswith[0]["name"] == "ЗначенияРеквизитовОбъекта"
    assert contains[0]["name"] == "ЗначенияРеквизитовОбъекта"
    assert module_match[0]["module"] == "Документ.Реализация"


def test_index_file_ignores_read_errors(tmp_path):
    idx = BslSearchIndex()
    root = tmp_path
    broken = tmp_path / "broken.bsl"
    broken.write_text("", encoding="utf-8")

    with patch.object(Path, "read_text", side_effect=OSError("boom")):
        idx._index_file(broken, root)

    assert idx.symbol_count == 0


def test_build_index_ignores_file_level_exceptions(tmp_path):
    _create_bsl_tree(tmp_path)
    idx = BslSearchIndex()

    with patch.object(idx, "_index_file", side_effect=[RuntimeError("boom"), None]):
        result = idx.build_index(str(tmp_path))

    assert "Indexed 0 symbols from 2 BSL files" in result

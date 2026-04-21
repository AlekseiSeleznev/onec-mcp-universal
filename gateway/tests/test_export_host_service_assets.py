from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_export_host_service():
    script = _repo_root() / "tools/export-host-service.py"
    spec = importlib.util.spec_from_file_location("export_host_service", script)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_current_workspace_normalizes_relative_env_path(tmp_path):
    module = _load_export_host_service()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".env").write_text("BSL_WORKSPACE=relative-bsl\n", encoding="utf-8")

    module.WORKSPACE_OVERRIDE = ""
    module.WORKSPACE = ""
    module._repo_root = lambda: repo_root

    assert module.current_workspace() == str((repo_root / "relative-bsl").resolve())


def test_browse_directories_lists_host_subdirectories(tmp_path):
    module = _load_export_host_service()
    root = tmp_path / "bsl-root"
    (root / "ERP").mkdir(parents=True)
    (root / "ERP2").mkdir()
    (root / ".hidden").mkdir()

    data = module.browse_directories(str(root))

    assert data["path"] == str(root.resolve())
    assert data["parent"] == str(root.parent.resolve())
    assert data["dirs"] == ["ERP", "ERP2"]


def test_sample_bsl_symbol_hits_detects_procedure_declarations(tmp_path):
    module = _load_export_host_service()
    root = tmp_path / "bsl-root"
    (root / "Catalogs" / "Items").mkdir(parents=True)
    (root / "Catalogs" / "Items" / "Module.bsl").write_text(
        "Процедура Тест() Экспорт\nКонецПроцедуры\n",
        encoding="utf-8",
    )
    (root / "Catalogs" / "Items" / "Empty.bsl").write_text("// comment only\n", encoding="utf-8")

    sampled, hits = module._sample_bsl_symbol_hits(str(root), sample_limit=10)

    assert sampled == 2
    assert hits == 1


def test_wait_for_export_stabilization_retries_until_symbols_appear(tmp_path):
    module = _load_export_host_service()
    calls = []

    def _fake_hits(_output_dir: str, *, sample_limit: int = 32):
        calls.append(sample_limit)
        if len(calls) < 3:
            return 5, 0
        return 5, 2

    module._sample_bsl_symbol_hits = _fake_hits
    sleeps = []
    module.time.sleep = lambda seconds: sleeps.append(seconds)

    module._wait_for_export_stabilization(
        str(tmp_path),
        bsl_count=1000,
        attempts=5,
        delay_seconds=0.5,
    )

    assert len(calls) == 3
    assert sleeps == [0.5, 0.5]


def test_wait_for_export_stabilization_skips_small_exports(tmp_path):
    module = _load_export_host_service()
    called = False

    def _fake_hits(_output_dir: str, *, sample_limit: int = 32):
        nonlocal called
        called = True
        return 1, 0

    module._sample_bsl_symbol_hits = _fake_hits
    module._wait_for_export_stabilization(str(tmp_path), bsl_count=3)

    assert called is False


def test_ensure_gateway_readable_adds_other_read_and_execute_bits(tmp_path):
    module = _load_export_host_service()
    root = tmp_path / "bsl-root"
    nested = root / "Catalogs" / "Items"
    nested.mkdir(parents=True)
    source = nested / "Module.bsl"
    source.write_text("Процедура Тест() Экспорт\nКонецПроцедуры\n", encoding="utf-8")

    root.chmod(0o770)
    nested.chmod(0o770)
    source.chmod(0o660)

    module._ensure_gateway_readable(str(root))

    assert oct(root.stat().st_mode & 0o777) == "0o775"
    assert oct(nested.stat().st_mode & 0o777) == "0o775"
    assert oct(source.stat().st_mode & 0o777) == "0o664"


def test_run_export_preserves_existing_tree_when_designer_fails(tmp_path):
    module = _load_export_host_service()
    output_dir = tmp_path / "Z01"
    output_dir.mkdir()
    sentinel = output_dir / "keep.txt"
    sentinel.write_text("preserve-me", encoding="utf-8")

    class _FailingProc:
        returncode = 1
        stderr = "designer failed"

        def communicate(self, timeout=None):
            return "", ""

    module._resolve_v8_binary = lambda: "/fake/1cv8"
    with patch.object(module.subprocess, "Popen", side_effect=lambda *args, **kwargs: _FailingProc()):
        ok, result = module.run_export("Srvr=localhost;Ref=Z01;", str(output_dir))

    assert ok is False
    assert "Export failed" in result
    assert sentinel.read_text(encoding="utf-8") == "preserve-me"


def test_run_export_replaces_existing_tree_only_after_success(tmp_path):
    module = _load_export_host_service()
    output_dir = tmp_path / "Z01"
    old_dir = output_dir / "old"
    old_dir.mkdir(parents=True)
    (old_dir / "legacy.txt").write_text("old", encoding="utf-8")

    class _SuccessfulProc(SimpleNamespace):
        def communicate(self, timeout=None):
            export_dir = Path(self.cmd[self.cmd.index("/DumpConfigToFiles") + 1])
            target = export_dir / "Catalogs" / "Items"
            target.mkdir(parents=True, exist_ok=True)
            (target / "Module.bsl").write_text(
                "Процедура Тест() Экспорт\nКонецПроцедуры\n",
                encoding="utf-8",
            )
            return "", ""

    def _fake_popen(cmd, **kwargs):
        return _SuccessfulProc(cmd=cmd, returncode=0, stderr="")

    module._resolve_v8_binary = lambda: "/fake/1cv8"
    module._ensure_gateway_readable = lambda *_args, **_kwargs: None
    module._wait_for_export_stabilization = lambda *_args, **_kwargs: None
    with patch.object(module.subprocess, "Popen", side_effect=_fake_popen):
        ok, result = module.run_export("Srvr=localhost;Ref=Z01;", str(output_dir))

    assert ok is True
    assert "Export completed" in result
    assert (output_dir / "Catalogs" / "Items" / "Module.bsl").is_file()
    assert not (output_dir / "old" / "legacy.txt").exists()

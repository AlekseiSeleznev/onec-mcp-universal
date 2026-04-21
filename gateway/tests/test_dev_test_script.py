from pathlib import Path
import os


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_gateway_test_script_exists_and_executable():
    root = _repo_root()
    script = root / "gateway" / "scripts" / "test.sh"
    assert script.is_file(), "gateway/scripts/test.sh must exist"
    assert os.access(script, os.X_OK), "gateway/scripts/test.sh must be executable"


def test_gateway_test_script_has_pytest_asyncio_preflight():
    root = _repo_root()
    script = root / "gateway" / "scripts" / "test.sh"
    text = script.read_text(encoding="utf-8")

    assert "import pytest_asyncio" in text
    assert "requirements-dev.txt" in text
    assert "python3 -m venv ../.venv" in text
    assert "../.venv/bin/pip install -r requirements-dev.txt" in text
    assert "python3 -m pytest tests" in text
    assert "--cov=gateway" in text
    assert "--cov-branch" in text
    assert "--cov-fail-under=94" in text

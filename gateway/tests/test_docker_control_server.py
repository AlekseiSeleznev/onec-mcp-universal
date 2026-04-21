"""Tests for docker-control auth and input validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient


def _load_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "docker-control" / "server.py"
    spec = importlib.util.spec_from_file_location("docker_control_server", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


docker_control_server = _load_module()


def test_health_is_public_without_auth():
    client = TestClient(docker_control_server.app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_repairs_missing_secret_keys_from_environment(tmp_path, monkeypatch):
    client = TestClient(docker_control_server.app)
    target = tmp_path / ".env"
    target.write_text("PORT=9090\n", encoding="utf-8")
    real_open = open

    def fake_open(path, mode="r", encoding=None):
        if path in docker_control_server.ENV_FILE_PATHS:
            return real_open(target, mode, encoding=encoding)
        return real_open(path, mode, encoding=encoding)

    monkeypatch.setenv("DOCKER_CONTROL_TOKEN", "secret-token")
    monkeypatch.setenv("ANONYMIZER_SALT", "secret-salt")
    with patch("builtins.open", side_effect=fake_open):
        response = client.get("/health")

    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == (
        "PORT=9090\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=secret-salt\n"
    )


def test_protected_api_requires_bearer_token():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"):
        response = client.get("/api/docker/system")

    assert response.status_code == 401
    assert response.json()["ok"] is False


def test_protected_api_rejects_wrong_bearer_token():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"):
        response = client.get(
            "/api/docker/system",
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert response.status_code == 401
    assert response.json()["ok"] is False


def test_protected_api_accepts_correct_bearer_token():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch.object(docker_control_server, "get_docker_system_info", return_value={"version": "1"}):
        response = client.get(
            "/api/docker/system",
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": {"version": "1"}}


def test_validate_mount_path_accepts_absolute_path_inside_workspace():
    with patch.object(docker_control_server, "_workspace_root", return_value="/tmp/workspace"):
        normalized = docker_control_server._validate_mount_path("/tmp/workspace/erp")

    assert normalized == "/tmp/workspace/erp"


def test_validate_mount_path_rejects_relative_path():
    with patch.object(docker_control_server, "_workspace_root", return_value="/tmp/workspace"):
        try:
            docker_control_server._validate_mount_path("tmp/workspace/erp")
        except ValueError as exc:
            assert "absolute" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("ValueError was not raised")


def test_validate_mount_path_rejects_forbidden_characters():
    with patch.object(docker_control_server, "_workspace_root", return_value="/tmp/workspace"):
        try:
            docker_control_server._validate_mount_path("/tmp/workspace/erp;rm -rf /")
        except ValueError as exc:
            assert "forbidden characters" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("ValueError was not raised")


def test_validate_mount_path_rejects_outside_workspace():
    with patch.object(docker_control_server, "_workspace_root", return_value="/tmp/workspace"):
        try:
            docker_control_server._validate_mount_path("/tmp/other/erp")
        except ValueError as exc:
            assert "configured BSL workspace" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("ValueError was not raised")


def test_validate_mount_path_accepts_explicit_absolute_path_when_workspace_root_missing():
    with patch.object(docker_control_server, "_workspace_root", return_value=""):
        normalized = docker_control_server._validate_mount_path("/tmp/workspace/erp")

    assert normalized == "/tmp/workspace/erp"


def test_lsp_start_api_returns_400_for_invalid_mount_path():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch.object(docker_control_server, "_workspace_root", return_value="/tmp/workspace"):
        response = client.post(
            "/api/lsp/start",
            json={"slug": "erp", "mount_path": "relative/path"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_validate_env_content_accepts_comments_blank_lines_and_key_value():
    error = docker_control_server._validate_env_content(
        "# comment\n\nPORT=8080\nDOCKER_CONTROL_TOKEN=secret\nKEY=\n"
    )

    assert error is None


def test_validate_env_content_rejects_invalid_line():
    error = docker_control_server._validate_env_content("PORT=8080\nNOT VALID\n")

    assert "line 2" in error


def test_write_env_api_accepts_valid_env_content(tmp_path):
    client = TestClient(docker_control_server.app)
    target = tmp_path / ".env"
    real_open = open

    def fake_open(path, mode="r", encoding=None):
        if path in docker_control_server.ENV_FILE_PATHS:
            return real_open(target, mode, encoding=encoding)
        return real_open(path, mode, encoding=encoding)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch("builtins.open", side_effect=fake_open):
        response = client.post(
            "/api/env/write",
            json={"content": "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\n"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\n"


def test_write_env_api_rejects_sparse_patch_without_replace_mode(tmp_path):
    client = TestClient(docker_control_server.app)
    target = tmp_path / ".env"
    target.write_text(
        "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=abc\n",
        encoding="utf-8",
    )
    real_open = open

    def fake_open(path, mode="r", encoding=None):
        if path in docker_control_server.ENV_FILE_PATHS:
            return real_open(target, mode, encoding=encoding)
        return real_open(path, mode, encoding=encoding)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch("builtins.open", side_effect=fake_open):
        response = client.post(
            "/api/env/write",
            json={"content": "PORT=9090\n"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "partial env update rejected; submit the full .env content"
    assert target.read_text(encoding="utf-8") == (
        "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=abc\n"
    )


def test_write_env_api_replace_mode_allows_full_replace(tmp_path):
    client = TestClient(docker_control_server.app)
    target = tmp_path / ".env"
    target.write_text(
        "PORT=8080\nDOCKER_CONTROL_TOKEN=secret-token\nANONYMIZER_SALT=abc\n",
        encoding="utf-8",
    )
    real_open = open

    def fake_open(path, mode="r", encoding=None):
        if path in docker_control_server.ENV_FILE_PATHS:
            return real_open(target, mode, encoding=encoding)
        return real_open(path, mode, encoding=encoding)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch("builtins.open", side_effect=fake_open):
        response = client.post(
            "/api/env/write",
            json={"content": "PORT=9090\n", "mode": "replace"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert target.read_text(encoding="utf-8") == "PORT=9090\n"


def test_write_env_api_rejects_invalid_env_content():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"):
        response = client.post(
            "/api/env/write",
            json={"content": "PORT=8080\nNOT VALID\n"},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_recreate_bsl_graph_api_calls_helper():
    client = TestClient(docker_control_server.app)

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch.object(docker_control_server, "recreate_bsl_graph") as recreate:
        response = client.post(
            "/api/services/bsl-graph/recreate",
            json={},
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    recreate.assert_called_once_with()


def test_start_lsp_recreates_existing_container_when_projects_mount_is_empty():
    container = MagicMock()
    container.attrs = {
        "Mounts": [
            {"Destination": "/projects", "Source": "/home/as/Z/Z01"},
        ]
    }
    docker_client = MagicMock()

    with patch.object(docker_control_server, "_validate_mount_path", return_value="/home/as/Z/Z01"), \
         patch.object(docker_control_server, "_container_running", return_value=container), \
         patch.object(docker_control_server, "_container_dir_has_entries", return_value=False), \
         patch.object(docker_control_server, "_close_lsp_proxy") as close_proxy, \
         patch.object(docker_control_server, "_docker", return_value=docker_client), \
         patch.object(docker_control_server.os, "makedirs"), \
         patch.object(docker_control_server.time, "sleep"):
        docker_client.images.get.return_value = object()

        result = docker_control_server.start_lsp("Z01", "/home/as/Z/Z01", "768m", "256m")

    assert result == "mcp-lsp-Z01"
    container.remove.assert_called_once_with(force=True)
    docker_client.containers.run.assert_called_once()
    close_proxy.assert_called_once_with("Z01")


def test_validate_container_relative_path_rejects_absolute_path():
    try:
        docker_control_server._validate_container_relative_path("/projects/Module.bsl")
    except ValueError as exc:
        assert "relative" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("ValueError was not raised")


def test_lsp_write_file_api_writes_archive_into_projects():
    client = TestClient(docker_control_server.app)
    container = MagicMock()
    container.exec_run.side_effect = [
        MagicMock(exit_code=1, output=b""),
        MagicMock(exit_code=0, output=b""),
        MagicMock(exit_code=0, output=b"1000:1000"),
        MagicMock(exit_code=0, output=b""),
    ]
    container.put_archive.return_value = True
    docker_client = MagicMock()
    docker_client.containers.get.return_value = container

    with patch.object(docker_control_server, "_docker_control_token", return_value="secret-token"), \
         patch.object(docker_control_server, "_docker", return_value=docker_client):
        response = client.post(
            "/api/lsp/write-file",
            json={
                "container_name": "mcp-lsp-Z01",
                "relative_path": "CommonModules/Test/Ext/Module.bsl",
                "content": "Процедура Тест() Экспорт\nКонецПроцедуры\n",
            },
            headers={"Authorization": "Bearer secret-token"},
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["path"] == "/projects/CommonModules/Test/Ext/Module.bsl"
    assert container.exec_run.call_args_list[0].args[0] == ["test", "-d", "/projects/CommonModules/Test/Ext"]
    assert container.exec_run.call_args_list[1].args[0] == ["mkdir", "-p", "/projects/CommonModules/Test/Ext"]
    assert container.exec_run.call_args_list[2].args[0] == ["stat", "-c", "%u:%g", "/projects"]
    assert container.exec_run.call_args_list[3].args[0] == ["chown", "-R", "1000:1000", "/projects/CommonModules/Test/Ext"]
    put_args = container.put_archive.call_args.args
    assert put_args[0] == "/projects/CommonModules/Test/Ext"
    assert isinstance(put_args[1], bytes)

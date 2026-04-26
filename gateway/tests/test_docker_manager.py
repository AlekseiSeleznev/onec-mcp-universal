"""Tests for docker_manager — container lifecycle, port allocation."""

import builtins
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import docker
import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def disable_live_docker_control(request):
    if request.node.get_closest_marker("allow_docker_control"):
        yield
        return

    with patch(
        "gateway.docker_manager._request_json",
        side_effect=RuntimeError("docker-control disabled in direct unit test"),
    ):
        yield


class TestFindFreePort:
    def test_returns_port_in_range(self):
        from gateway.docker_manager import _find_free_port
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = []
            port = _find_free_port(6100)
        assert 6100 <= port < 7000

    def test_skips_docker_bound_ports(self):
        from gateway.docker_manager import _find_free_port
        mock_container = MagicMock()
        mock_container.ports = {"6003/tcp": [{"HostPort": "6100"}]}
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [mock_container]
            port = _find_free_port(6100)
        assert port != 6100

    def test_raises_on_exhaustion(self):
        from gateway.docker_manager import _find_free_port
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = []
            with patch("socket.socket") as mock_sock:
                mock_sock.return_value.__enter__ = MagicMock(return_value=mock_sock.return_value)
                mock_sock.return_value.__exit__ = MagicMock(return_value=False)
                mock_sock.return_value.connect_ex.return_value = 0  # All ports in use
                with pytest.raises(RuntimeError, match="No free ports"):
                    _find_free_port(6100)

    def test_ignores_docker_list_failure(self):
        from gateway.docker_manager import _find_free_port

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.side_effect = RuntimeError("boom")
            port = _find_free_port(6100)

        assert 6100 <= port < 7000

    def test_ignores_bad_docker_port_bindings(self):
        from gateway.docker_manager import _find_free_port

        mock_container = MagicMock()
        mock_container.ports = {"6003/tcp": [{"HostPort": "bad"}, {}]}

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [mock_container]
            port = _find_free_port(6100)

        assert 6100 <= port < 7000

    def test_ignores_empty_docker_port_bindings(self):
        from gateway.docker_manager import _find_free_port

        mock_container = MagicMock()
        mock_container.ports = {"6003/tcp": []}

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [mock_container]
            port = _find_free_port(6100)

        assert 6100 <= port < 7000

    def test_skips_host_network_port_from_container_environment(self):
        from gateway.docker_manager import _find_free_port

        mock_container = MagicMock()
        mock_container.ports = {}
        mock_container.attrs = {"Config": {"Env": ["PORT=6100"]}}

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [mock_container]
            port = _find_free_port(6100)

        assert port != 6100


class TestHelperEnvReaders:
    def test_control_url_defaults_and_trims_trailing_slash(self):
        from gateway.docker_manager import _control_url

        with patch("gateway.docker_manager._setting", return_value="http://docker-control:8091/"):
            assert _control_url() == "http://docker-control:8091"

    def test_setting_falls_back_when_settings_attr_raises(self, monkeypatch):
        from gateway.docker_manager import _setting

        class BrokenSettings:
            def __getattr__(self, _name):
                raise RuntimeError("boom")

        monkeypatch.setenv("BROKEN_ENV", "from-env")
        with patch("gateway.docker_manager._settings_obj", return_value=BrokenSettings()):
            assert _setting("missing", "BROKEN_ENV", "default") == "from-env"

    def test_setting_falls_back_when_settings_value_is_empty(self, monkeypatch):
        from gateway.docker_manager import _setting

        settings = SimpleNamespace(missing="")
        monkeypatch.setenv("EMPTY_ENV", "from-env")

        with patch("gateway.docker_manager._settings_obj", return_value=settings):
            assert _setting("missing", "EMPTY_ENV", "default") == "from-env"

    def test_bsl_workspace_host_prefers_settings(self):
        from gateway.docker_manager import _bsl_workspace_host

        with patch("gateway.config.settings") as settings:
            settings.bsl_host_workspace = "/home/as/Z"
            assert _bsl_workspace_host() == "/home/as/Z"

    def test_hostfs_home_host_prefers_env(self, monkeypatch):
        from gateway.docker_manager import _hostfs_home_host

        monkeypatch.setenv("HOSTFS_HOME", "/mnt/home")
        assert _hostfs_home_host() == "/mnt/home"

    def test_host_root_prefix_defaults_to_empty(self, monkeypatch):
        from gateway.docker_manager import _host_root_prefix

        monkeypatch.delenv("HOST_ROOT_PREFIX", raising=False)
        assert _host_root_prefix() == ""

    def test_java_heap_readers_use_settings(self):
        from gateway.docker_manager import _lsp_java_xmx, _lsp_java_xms

        with patch("gateway.config.settings") as settings:
            settings.mcp_lsp_bsl_java_xmx = "3g"
            settings.mcp_lsp_bsl_java_xms = "1g"
            assert _lsp_java_xmx() == "3g"
            assert _lsp_java_xms() == "1g"

    def test_env_readers_fall_back_when_config_import_fails(self, monkeypatch):
        from gateway.docker_manager import (
            _bsl_workspace_host,
            _host_root_prefix,
            _hostfs_home_host,
            _lsp_java_xms,
            _lsp_java_xmx,
        )

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in {"gateway.config", "config"}:
                raise ImportError("boom")
            return real_import(name, *args, **kwargs)

        monkeypatch.setenv("BSL_WORKSPACE_HOST", "/tmp/ws")
        monkeypatch.setenv("HOSTFS_HOME", "/tmp/home")
        monkeypatch.setenv("HOST_ROOT_PREFIX", "/tmp/root")
        monkeypatch.setenv("MCP_LSP_BSL_JAVA_XMX", "7g")
        monkeypatch.setenv("MCP_LSP_BSL_JAVA_XMS", "3g")

        with patch("builtins.__import__", side_effect=fake_import):
            assert _bsl_workspace_host() == "/tmp/ws"
            assert _hostfs_home_host() == "/tmp/home"
            assert _host_root_prefix() == "/tmp/root"
            assert _lsp_java_xmx() == "7g"
            assert _lsp_java_xms() == "3g"

    def test_bool_value_handles_bool_and_truthy_string(self):
        from gateway.docker_manager import _bool_value

        assert _bool_value(True) is True
        assert _bool_value("yes") is True


class TestDockerClientCache:
    def test_docker_client_cached(self):
        import gateway.docker_manager as mod

        mod._client = None
        client = object()
        with patch("gateway.docker_manager.docker.from_env", return_value=client) as from_env:
            assert mod._docker() is client
            assert mod._docker() is client

        from_env.assert_called_once()
        mod._client = None

    def test_docker_raises_when_sdk_missing(self, monkeypatch):
        import gateway.docker_manager as mod

        monkeypatch.setattr(mod, "_client", None)
        monkeypatch.setattr(mod, "docker", None)

        with pytest.raises(RuntimeError, match="docker SDK is not available"):
            mod._docker()


@pytest.mark.allow_docker_control
class TestDockerControlHttpHelpers:
    def test_request_json_success(self):
        from gateway.docker_manager import _request_json

        response = MagicMock()
        response.json.return_value = {"ok": True, "value": 1}

        with patch("gateway.docker_manager._control_url", return_value="http://docker-control"), \
             patch("gateway.docker_manager._control_headers", return_value={"Authorization": "Bearer secret"}), \
             patch("gateway.docker_manager.httpx.request", return_value=response) as request:
            payload = _request_json("POST", "/api/ping", json={"x": 1}, timeout=9)

        assert payload == {"ok": True, "value": 1}
        request.assert_called_once_with(
            "POST",
            "http://docker-control/api/ping",
            json={"x": 1},
            timeout=9,
            headers={"Authorization": "Bearer secret"},
        )
        response.raise_for_status.assert_called_once()

    def test_control_headers_return_empty_when_token_is_missing(self):
        from gateway.docker_manager import _control_headers

        with patch("gateway.docker_manager._control_token", return_value=""):
            assert _control_headers() == {}

    def test_control_headers_include_bearer_token(self):
        from gateway.docker_manager import _control_headers

        with patch("gateway.docker_manager._control_token", return_value="secret-token"):
            assert _control_headers() == {"Authorization": "Bearer secret-token"}

    def test_request_json_raises_when_sidecar_returns_error_payload(self):
        from gateway.docker_manager import _request_json

        response = MagicMock()
        response.json.return_value = {"ok": False, "error": "boom"}

        with patch("gateway.docker_manager._control_url", return_value="http://docker-control"), \
             patch("gateway.docker_manager.httpx.request", return_value=response):
            with pytest.raises(RuntimeError, match="boom"):
                _request_json("POST", "/api/ping")

    def test_request_json_surfaces_http_error_payload_message(self):
        from gateway.docker_manager import _request_json

        response = MagicMock()
        response.status_code = 503
        response.json.return_value = {"ok": False, "error": "DOCKER_CONTROL_TOKEN is not configured."}
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 error",
            request=MagicMock(),
            response=response,
        )

        with patch("gateway.docker_manager._control_url", return_value="http://docker-control"), \
             patch("gateway.docker_manager.httpx.request", return_value=response):
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                _request_json("POST", "/api/ping")

    def test_request_json_uses_plain_text_when_error_json_is_unavailable(self):
        from gateway.docker_manager import _request_json

        response = MagicMock()
        response.status_code = 503
        response.json.side_effect = ValueError("not json")
        response.text = "plain sidecar error"
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 error",
            request=MagicMock(),
            response=response,
        )

        with patch("gateway.docker_manager._control_url", return_value="http://docker-control"), \
             patch("gateway.docker_manager.httpx.request", return_value=response):
            with pytest.raises(RuntimeError, match="plain sidecar error"):
                _request_json("POST", "/api/ping")

    def test_request_json_falls_back_to_default_http_error_message(self):
        from gateway.docker_manager import _request_json

        response = MagicMock()
        response.status_code = 503
        response.json.side_effect = ValueError("not json")
        response.text = ""
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503 error",
            request=MagicMock(),
            response=response,
        )

        with patch("gateway.docker_manager._control_url", return_value="http://docker-control"), \
             patch("gateway.docker_manager.httpx.request", return_value=response):
            with pytest.raises(RuntimeError, match="docker-control HTTP 503 for /api/ping"):
                _request_json("POST", "/api/ping")

    def test_can_fallback_to_direct_docker_returns_false_for_unknown_exception(self):
        from gateway.docker_manager import _can_fallback_to_direct_docker

        assert _can_fallback_to_direct_docker(ValueError("boom")) is False

    def test_patch_toolkit_structured_output_prefers_sidecar(self):
        from gateway.docker_manager import patch_toolkit_structured_output

        with patch("gateway.docker_manager._request_json", return_value={"ok": True}) as request_json, \
             patch("gateway.docker_manager._patch_toolkit_structured_output") as fallback:
            patch_toolkit_structured_output("onec-toolkit-ERP")

        request_json.assert_called_once()
        fallback.assert_not_called()

    def test_patch_toolkit_structured_output_falls_back_to_direct_patch(self):
        from gateway.docker_manager import patch_toolkit_structured_output

        with patch("gateway.docker_manager._request_json", side_effect=httpx.ConnectError("boom")), \
             patch("gateway.docker_manager._patch_toolkit_structured_output") as fallback:
            patch_toolkit_structured_output("onec-toolkit-ERP")

        fallback.assert_called_once_with("onec-toolkit-ERP")

    def test_patch_toolkit_structured_output_surfaces_sidecar_runtime_error_without_direct_fallback(self):
        from gateway.docker_manager import patch_toolkit_structured_output

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch("gateway.docker_manager._patch_toolkit_structured_output") as fallback:
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                patch_toolkit_structured_output("onec-toolkit-ERP")

        fallback.assert_not_called()

    def test_start_toolkit_prefers_sidecar_when_available(self):
        from gateway.docker_manager import start_toolkit

        with patch("gateway.docker_manager._request_json", return_value={"port": "6110", "container_name": "onec-toolkit-erp"}), \
             patch("gateway.docker_manager._toolkit_allow_dangerous_with_approval", return_value=False):
            assert start_toolkit("erp") == (6110, "onec-toolkit-erp")

    def test_start_toolkit_falls_back_only_when_sidecar_is_unreachable(self):
        from gateway.docker_manager import start_toolkit

        with patch("gateway.docker_manager._request_json", side_effect=httpx.ConnectError("boom")), \
             patch("gateway.docker_manager._start_toolkit_direct", return_value=(6111, "onec-toolkit-erp")) as fallback:
            assert start_toolkit("erp") == (6111, "onec-toolkit-erp")

        fallback.assert_called_once_with("erp")

    def test_start_toolkit_surfaces_sidecar_runtime_error_without_direct_fallback(self):
        from gateway.docker_manager import start_toolkit

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch("gateway.docker_manager._start_toolkit_direct") as fallback:
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                start_toolkit("erp")

        fallback.assert_not_called()

    def test_start_lsp_prefers_sidecar_when_available(self):
        from gateway.docker_manager import start_lsp

        with patch("gateway.docker_manager._request_json", return_value={"container_name": "mcp-lsp-erp"}), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/tmp/ws"), \
             patch("gateway.docker_manager.os.makedirs") as makedirs:
            assert start_lsp("erp", "/workspace/erp") == "mcp-lsp-erp"
        makedirs.assert_not_called()

    def test_start_lsp_surfaces_sidecar_runtime_error_without_direct_fallback(self):
        from gateway.docker_manager import start_lsp

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("BSL workspace root is not configured"),
        ), patch("gateway.docker_manager._start_lsp_direct") as fallback:
            with pytest.raises(RuntimeError, match="BSL workspace root is not configured"):
                start_lsp("erp", "/workspace/erp")

        fallback.assert_not_called()

    def test_stop_db_containers_surfaces_sidecar_runtime_error_without_direct_fallback(self):
        from gateway.docker_manager import stop_db_containers

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch("gateway.docker_manager._stop_db_containers_direct") as fallback:
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                stop_db_containers("erp")

        fallback.assert_not_called()

    def test_stop_db_containers_raises_combined_error_when_direct_fallback_fails(self):
        from gateway.docker_manager import stop_db_containers

        with patch("gateway.docker_manager._request_json", side_effect=httpx.ConnectError("sidecar down")), \
             patch("gateway.docker_manager._stop_db_containers_direct", side_effect=RuntimeError("docker SDK is not available")):
            with pytest.raises(
                RuntimeError,
                match="sidecar down.*direct fallback failed: docker SDK is not available",
            ):
                stop_db_containers("erp")

    def test_cleanup_orphan_db_containers_prefers_sidecar(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        with patch("gateway.docker_manager._request_json", return_value={"removed": 2}):
            assert cleanup_orphan_db_containers({"erp"}) == 2

    def test_cleanup_orphan_db_containers_surfaces_sidecar_runtime_error_without_direct_fallback(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch("gateway.docker_manager._cleanup_orphan_db_containers_direct") as fallback:
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                cleanup_orphan_db_containers({"erp"})

        fallback.assert_not_called()

    def test_cleanup_orphan_db_containers_raises_combined_error_when_direct_fallback_fails(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        with patch("gateway.docker_manager._request_json", side_effect=httpx.ConnectError("sidecar down")), \
             patch("gateway.docker_manager._cleanup_orphan_db_containers_direct", side_effect=RuntimeError("docker down")):
            with pytest.raises(RuntimeError, match="sidecar down.*direct fallback failed: docker down"):
                cleanup_orphan_db_containers({"erp"})

    def test_get_container_info_direct_handles_missing_attrs_fallback(self):
        from gateway.docker_manager import _get_container_info_direct

        class BrokenContainer:
            name = "onec-mcp-gw"
            status = "running"
            id = "abc123"

            @property
            def image(self):
                raise RuntimeError("broken image")

            @property
            def attrs(self):
                raise RuntimeError("broken attrs")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [BrokenContainer()]
            result = _get_container_info_direct(include_runtime_stats=False, include_image_size=False)

        assert result[0]["image"] == ""
        assert result[0]["image_size_bytes"] is None

    def test_lsp_image_present_prefers_sidecar_when_available(self):
        from gateway.docker_manager import lsp_image_present

        with patch("gateway.docker_manager._request_json", return_value={"present": 1}):
            assert lsp_image_present() is True

    @pytest.mark.parametrize(
        ("func_name", "kwargs", "direct_target"),
        [
            ("get_docker_system_info", {}, "gateway.docker_manager._get_docker_system_info_direct"),
            (
                "get_container_info",
                {"include_runtime_stats": False, "include_image_size": False},
                "gateway.docker_manager._get_container_info_direct",
            ),
            ("get_container_logs", {"tail": 5}, "gateway.docker_manager._get_container_logs_direct"),
            ("restart_container", {"name": "onec-mcp-gw"}, "gateway.docker_manager._restart_container_direct"),
            (
                "write_lsp_file",
                {"container_name": "mcp-lsp-Z01", "relative_path": "CommonModules/Test/Ext/Module.bsl", "content": "x"},
                "gateway.docker_manager._write_lsp_file_direct",
            ),
            ("lsp_image_present", {}, "gateway.docker_manager._lsp_image_present_direct"),
        ],
    )
    def test_other_wrappers_surface_sidecar_runtime_error_without_direct_fallback(
        self,
        func_name,
        kwargs,
        direct_target,
    ):
        import gateway.docker_manager as mod

        func = getattr(mod, func_name)

        with patch(
            "gateway.docker_manager._request_json",
            side_effect=RuntimeError("DOCKER_CONTROL_TOKEN is not configured."),
        ), patch(direct_target) as fallback:
            with pytest.raises(RuntimeError, match="DOCKER_CONTROL_TOKEN is not configured"):
                func(**kwargs)

        fallback.assert_not_called()

    def test_write_lsp_file_prefers_sidecar_when_available(self):
        from gateway.docker_manager import write_lsp_file

        with patch("gateway.docker_manager._request_json", return_value={"path": "/projects/CommonModules/Test/Ext/Module.bsl"}):
            result = write_lsp_file("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

        assert result == "/projects/CommonModules/Test/Ext/Module.bsl"

    def test_recreate_bsl_graph_prefers_sidecar_when_available(self):
        from gateway.docker_manager import recreate_bsl_graph

        with patch("gateway.docker_manager._request_json", return_value={"ok": True}) as request_json:
            recreate_bsl_graph()

        request_json.assert_called_once_with(
            "POST",
            "/api/services/bsl-graph/recreate",
            json={},
            timeout=60,
        )

    def test_recreate_bsl_graph_direct_recreates_container_with_current_workspace_mounts(self):
        from gateway.docker_manager import _recreate_bsl_graph_direct

        container = MagicMock()
        container.attrs = {
            "Config": {
                "Env": ["EXISTING=1", "BROKEN"],
                "Image": "old-image",
                "Labels": {"app": "graph"},
                "Cmd": ["python", "-m", "bsl_graph_lite"],
            },
            "HostConfig": {
                "PortBindings": {
                    "8888/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8888"}],
                    "9999/tcp": [{}],
                    "7777/tcp": [],
                },
                "NetworkMode": "bridge",
                "RestartPolicy": {"Name": "unless-stopped"},
            },
            "Mounts": [
                {"Destination": "", "Source": "/ignored"},
                {"Destination": "/workspace", "Source": "/old-workspace", "RW": False},
                {"Destination": "/hostfs-home", "Source": "/old-home", "RW": True},
                {"Destination": "/data", "Name": "graph-data", "RW": True},
                {"Destination": "/ignored", "Source": "/ignored", "RW": True},
            ],
        }
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client), patch(
            "gateway.docker_manager._bsl_workspace_host", return_value="/home/as/Z"
        ), patch("gateway.docker_manager._hostfs_home_host", return_value=""):
            _recreate_bsl_graph_direct()

        container.remove.assert_called_once_with(force=True)
        docker_client.containers.run.assert_called_once()
        kwargs = docker_client.containers.run.call_args.kwargs
        assert docker_client.containers.run.call_args.args[0] == "old-image"
        assert kwargs["environment"]["GRAPH_WORKSPACE"] == "/workspace"
        assert kwargs["environment"]["EXISTING"] == "1"
        assert kwargs["volumes"]["/home/as/Z"] == {"bind": "/workspace", "mode": "ro"}
        assert kwargs["volumes"]["/home"] == {"bind": "/hostfs-home", "mode": "rw"}
        assert kwargs["volumes"]["graph-data"] == {"bind": "/data", "mode": "rw"}
        assert kwargs["ports"] == {"8888/tcp": ("127.0.0.1", 8888)}
        assert kwargs["network"] == "bridge"
        assert kwargs["command"] == ["python", "-m", "bsl_graph_lite"]

    def test_recreate_bsl_graph_direct_requires_workspace_and_reports_remove_errors(self):
        from gateway.docker_manager import _recreate_bsl_graph_direct

        container = MagicMock()
        container.attrs = {"Config": {}, "HostConfig": {}, "Mounts": []}
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client), patch(
            "gateway.docker_manager._bsl_workspace_host", return_value=""
        ):
            with pytest.raises(RuntimeError, match="not configured"):
                _recreate_bsl_graph_direct()

        container.remove.side_effect = RuntimeError("remove failed")
        with patch("gateway.docker_manager._docker", return_value=docker_client), patch(
            "gateway.docker_manager._bsl_workspace_host", return_value="/home/as/Z"
        ), patch("gateway.docker_manager._hostfs_home_host", return_value="/home"):
            with pytest.raises(RuntimeError, match="Cannot remove existing"):
                _recreate_bsl_graph_direct()

    def test_write_lsp_file_direct_puts_archive_and_chowns_new_directory(self):
        from gateway.docker_manager import _write_lsp_file_direct

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

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            result = _write_lsp_file_direct(
                "mcp-lsp-Z01",
                "CommonModules/Test/Ext/Module.bsl",
                "Процедура Тест() Экспорт\nКонецПроцедуры\n",
            )

        assert result == "/projects/CommonModules/Test/Ext/Module.bsl"
        assert container.exec_run.call_args_list[0].args[0] == ["test", "-d", "/projects/CommonModules/Test/Ext"]
        assert container.exec_run.call_args_list[1].args[0] == ["mkdir", "-p", "/projects/CommonModules/Test/Ext"]
        assert container.exec_run.call_args_list[2].args[0] == ["stat", "-c", "%u:%g", "/projects"]
        assert container.exec_run.call_args_list[3].args[0] == ["chown", "-R", "1000:1000", "/projects/CommonModules/Test/Ext"]
        put_args = container.put_archive.call_args.args
        assert put_args[0] == "/projects/CommonModules/Test/Ext"
        assert isinstance(put_args[1], bytes)

    def test_write_lsp_file_direct_raises_when_mkdir_fails(self):
        from gateway.docker_manager import _write_lsp_file_direct

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=1, output=b"mkdir boom"),
        ]
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            with pytest.raises(RuntimeError, match="mkdir boom"):
                _write_lsp_file_direct("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

    def test_write_lsp_file_direct_raises_when_put_archive_fails(self):
        from gateway.docker_manager import _write_lsp_file_direct

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=0, output=b""),
        ]
        container.put_archive.return_value = False
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            with pytest.raises(RuntimeError, match="put_archive returned false"):
                _write_lsp_file_direct("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

    def test_write_lsp_file_direct_chowns_single_file_when_directory_exists(self):
        from gateway.docker_manager import _write_lsp_file_direct

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=0, output=b"1000:1000"),
            MagicMock(exit_code=0, output=b""),
        ]
        container.put_archive.return_value = True
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            result = _write_lsp_file_direct("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

        assert result == "/projects/CommonModules/Test/Ext/Module.bsl"
        assert container.exec_run.call_args_list[3].args[0] == [
            "chown",
            "1000:1000",
            "/projects/CommonModules/Test/Ext/Module.bsl",
        ]

    def test_write_lsp_file_direct_skips_chown_when_owner_lookup_fails(self):
        from gateway.docker_manager import _write_lsp_file_direct

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=1, output=b""),
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=1, output=b""),
        ]
        container.put_archive.return_value = True
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            result = _write_lsp_file_direct("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

        assert result == "/projects/CommonModules/Test/Ext/Module.bsl"
        assert len(container.exec_run.call_args_list) == 3

    def test_write_lsp_file_direct_skips_chown_when_owner_is_empty(self):
        from gateway.docker_manager import _write_lsp_file_direct

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=1, output=b""),
            MagicMock(exit_code=0, output=b""),
            MagicMock(exit_code=0, output=b""),
        ]
        container.put_archive.return_value = True
        docker_client = MagicMock()
        docker_client.containers.get.return_value = container

        with patch("gateway.docker_manager._docker", return_value=docker_client):
            result = _write_lsp_file_direct("mcp-lsp-Z01", "CommonModules/Test/Ext/Module.bsl", "x")

        assert result == "/projects/CommonModules/Test/Ext/Module.bsl"
        assert len(container.exec_run.call_args_list) == 3

    def test_write_lsp_file_direct_rejects_path_traversal(self):
        from gateway.docker_manager import _write_lsp_file_direct

        with patch("gateway.docker_manager._docker") as mock_docker:
            with pytest.raises(RuntimeError, match="relative_path must stay inside /projects"):
                _write_lsp_file_direct("mcp-lsp-Z01", "../etc/passwd", "x")

        mock_docker.assert_called_once()


class TestContainerRunning:
    def test_returns_container_when_running(self):
        from gateway.docker_manager import _container_running
        mock_container = MagicMock()
        mock_container.status = "running"
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.return_value = mock_container
            result = _container_running("test-container")
        assert result == mock_container

    def test_returns_none_when_not_found(self):
        import docker
        from gateway.docker_manager import _container_running
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            result = _container_running("no-such-container")
        assert result is None

    def test_returns_none_when_stopped(self):
        from gateway.docker_manager import _container_running
        mock_container = MagicMock()
        mock_container.status = "exited"
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.return_value = mock_container
            result = _container_running("stopped-container")
        assert result is None


class TestGetContainerPort:
    def test_extracts_port_from_env(self):
        from gateway.docker_manager import _get_container_port
        mock_container = MagicMock()
        mock_container.attrs = {"Config": {"Env": ["PORT=6150", "OTHER=abc"]}}
        port = _get_container_port(mock_container, "PORT")
        assert port == 6150

    def test_returns_none_for_missing_env(self):
        from gateway.docker_manager import _get_container_port
        mock_container = MagicMock()
        mock_container.attrs = {"Config": {"Env": ["OTHER=abc"]}}
        port = _get_container_port(mock_container, "PORT")
        assert port is None

    def test_returns_none_for_invalid_value(self):
        from gateway.docker_manager import _get_container_port
        mock_container = MagicMock()
        mock_container.attrs = {"Config": {"Env": ["PORT=not_a_number"]}}
        port = _get_container_port(mock_container, "PORT")
        assert port is None

    def test_returns_none_when_container_env_missing(self):
        from gateway.docker_manager import _get_container_port

        mock_container = MagicMock()
        mock_container.attrs = {"Config": {}}

        assert _get_container_port(mock_container, "PORT") is None


class TestStopDbContainers:
    def test_stops_and_removes_both_containers(self):
        import docker
        from gateway.docker_manager import stop_db_containers
        mock_tk = MagicMock()
        mock_lsp = MagicMock()

        def get_container(name):
            if "toolkit" in name:
                return mock_tk
            if "lsp" in name:
                return mock_lsp
            raise docker.errors.NotFound("not found")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get = get_container
            stop_db_containers("testdb")

        mock_tk.stop.assert_called_once()
        mock_tk.remove.assert_called_once()
        mock_lsp.stop.assert_called_once()
        mock_lsp.remove.assert_called_once()

    def test_handles_not_found_gracefully(self):
        import docker
        from gateway.docker_manager import stop_db_containers
        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("nope")
            # Should not raise
            stop_db_containers("nonexistent")

    def test_logs_generic_stop_error(self):
        from gateway.docker_manager import stop_db_containers

        broken = MagicMock()
        broken.stop.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.return_value = broken
            stop_db_containers("db1")


class TestCleanupOrphanDbContainers:
    def test_removes_only_orphan_per_db_containers(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        keep_toolkit = MagicMock()
        keep_toolkit.name = "onec-toolkit-keep"

        orphan_toolkit = MagicMock()
        orphan_toolkit.name = "onec-toolkit-orphan"

        orphan_lsp = MagicMock()
        orphan_lsp.name = "mcp-lsp-orphan"

        static_container = MagicMock()
        static_container.name = "onec-mcp-gw"

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [
                keep_toolkit,
                orphan_toolkit,
                orphan_lsp,
                static_container,
            ]
            removed = cleanup_orphan_db_containers({"keep"})

        assert removed == 2
        orphan_toolkit.remove.assert_called_once_with(force=True)
        orphan_lsp.remove.assert_called_once_with(force=True)
        keep_toolkit.remove.assert_not_called()
        static_container.remove.assert_not_called()

    def test_handles_container_list_failure(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.side_effect = RuntimeError("boom")
            assert cleanup_orphan_db_containers({"keep"}) == 0

    def test_ignores_notfound_during_orphan_remove(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        orphan = MagicMock()
        orphan.name = "onec-toolkit-orphan"
        orphan.remove.side_effect = docker.errors.NotFound("gone")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [orphan]
            assert cleanup_orphan_db_containers(set()) == 0

    def test_logs_generic_remove_error_and_continues(self):
        from gateway.docker_manager import cleanup_orphan_db_containers

        orphan = MagicMock()
        orphan.name = "mcp-lsp-orphan"
        orphan.remove.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.list.return_value = [orphan]
            assert cleanup_orphan_db_containers(set()) == 0


class TestResolveLspMountPath:
    def test_workspace_path_maps_to_host_workspace(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._bsl_workspace_host", return_value="/home/as/Z"):
            assert _resolve_lsp_mount_path("/workspace/ERPPur_Local") == "/home/as/Z/ERPPur_Local"

    def test_hostfs_home_path_maps_to_real_home(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._hostfs_home_host", return_value="/home"):
            assert _resolve_lsp_mount_path("/hostfs-home/as/Z/ERPPur_Local") == "/home/as/Z/ERPPur_Local"

    def test_hostfs_home_root_maps_to_real_home_root(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._hostfs_home_host", return_value="/home"):
            assert _resolve_lsp_mount_path("/hostfs-home") == "/home"

    def test_workspace_root_maps_to_host_workspace(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._bsl_workspace_host", return_value="/home/as/Z"):
            assert _resolve_lsp_mount_path("/workspace") == "/home/as/Z"

    def test_hostfs_root_path_maps_with_prefix(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._host_root_prefix", return_value="/mnt/wsl"):
            assert _resolve_lsp_mount_path("/hostfs/tmp/project") == "/mnt/wsl/tmp/project"

    def test_hostfs_root_maps_to_prefix_root(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        with patch("gateway.docker_manager._host_root_prefix", return_value="/mnt/wsl"):
            assert _resolve_lsp_mount_path("/hostfs") == "/mnt/wsl"

    def test_other_path_is_returned_as_is(self):
        from gateway.docker_manager import _resolve_lsp_mount_path

        assert _resolve_lsp_mount_path("/tmp/project") == "/tmp/project"


class TestLspContainerRefresh:
    def test_start_lsp_skips_when_image_missing(self):
        from gateway.docker_manager import start_lsp

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/tmp/erp"):
            mock_docker.return_value.images.get.side_effect = docker.errors.ImageNotFound("missing")
            assert start_lsp("ERP", "/hostfs-home/as/Z/ERP") is None

    def test_lsp_mount_source_changed_detects_mismatch(self):
        from gateway.docker_manager import _lsp_mount_source_changed

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/tmp/old-project"},
            ]
        }

        assert _lsp_mount_source_changed(container, "/home/as/Z/ERPPur_Local") is True

    def test_lsp_mount_source_changed_accepts_expected_source(self):
        from gateway.docker_manager import _lsp_mount_source_changed

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/home/as/Z/ERPPur_Local"},
            ]
        }

        assert _lsp_mount_source_changed(container, "/home/as/Z/ERPPur_Local") is False

    def test_lsp_mount_source_changed_without_projects_mount(self):
        from gateway.docker_manager import _lsp_mount_source_changed

        container = MagicMock()
        container.attrs = {"Mounts": [{"Destination": "/other", "Source": "/tmp/x"}]}

        assert _lsp_mount_source_changed(container, "/home/as/Z/ERPPur_Local") is True

    def test_start_lsp_recreates_existing_container_when_projects_mount_is_empty(self):
        from gateway.docker_manager import start_lsp

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/home/as/Z/ERPPur_Local"},
            ]
        }

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager._container_dir_has_entries", return_value=False), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        container.remove.assert_called_once_with(force=True)
        mock_docker.return_value.containers.run.assert_called_once()

    def test_start_lsp_returns_existing_container_without_changes(self):
        from gateway.docker_manager import start_lsp

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/home/as/Z/ERPPur_Local"},
            ]
        }

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager._container_dir_has_entries", return_value=True), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        container.restart.assert_not_called()
        mock_docker.return_value.containers.run.assert_not_called()

    def test_start_lsp_recreates_container_when_mount_changed(self):
        from gateway.docker_manager import start_lsp

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/tmp/old"},
            ]
        }

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        container.remove.assert_called_once_with(force=True)
        mock_docker.return_value.containers.run.assert_called_once()

    def test_start_lsp_logs_recreate_failure_but_returns_existing(self):
        from gateway.docker_manager import start_lsp

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/tmp/old"},
            ]
        }
        container.remove.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()
            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        mock_docker.return_value.containers.run.assert_not_called()

    def test_start_lsp_logs_recreate_failure_and_keeps_container(self):
        from gateway.docker_manager import start_lsp

        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {"Destination": "/projects", "Source": "/home/as/Z/ERPPur_Local"},
            ]
        }
        container.remove.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager._container_dir_has_entries", return_value=False), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        mock_docker.return_value.containers.run.assert_not_called()

    def test_patch_toolkit_structured_output_stops_after_healthy_restart(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        container = MagicMock()
        container.exec_run.side_effect = [
            SimpleNamespace(exit_code=0, output=b"0"),
            SimpleNamespace(exit_code=0, output=b""),
        ]
        container.attrs = {"State": {"Health": {"Status": "healthy"}}}

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.containers.get.return_value = container
            _patch_toolkit_structured_output("onec-mcp-toolkit")

        container.restart.assert_called_once_with(timeout=5)

    def test_patch_toolkit_structured_output_skips_when_already_patched(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        container = MagicMock()
        container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b"1")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.return_value = container
            _patch_toolkit_structured_output("onec-mcp-toolkit")

        container.restart.assert_not_called()

    def test_patch_toolkit_structured_output_waits_full_loop_when_never_healthy(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        container = MagicMock()
        container.exec_run.side_effect = [
            SimpleNamespace(exit_code=0, output=b"0"),
            SimpleNamespace(exit_code=0, output=b""),
        ]
        container.attrs = {"State": {"Health": {"Status": "starting"}}}

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.containers.get.return_value = container
            _patch_toolkit_structured_output("onec-mcp-toolkit")

        assert container.reload.call_count == 20

    def test_start_lsp_removes_stopped_container_before_run(self):
        from gateway.docker_manager import start_lsp

        stopped = MagicMock()

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()
            mock_docker.return_value.containers.get.return_value = stopped

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        stopped.remove.assert_called_once_with(force=True)

    def test_start_lsp_passes_java_heap_env_to_new_container(self):
        from gateway.docker_manager import start_lsp

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager.os.makedirs"), \
             patch("gateway.docker_manager._resolve_lsp_mount_path", return_value="/home/as/Z/ERPPur_Local"), \
             patch("gateway.docker_manager._lsp_java_xmx", return_value="2g"), \
             patch("gateway.docker_manager._lsp_java_xms", return_value="512m"), \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.images.get.return_value = object()
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")

            result = start_lsp("ERPPur_Local", "/hostfs-home/as/Z/ERPPur_Local")

        assert result == "mcp-lsp-ERPPur_Local"
        mock_docker.return_value.containers.run.assert_called_once_with(
            "mcp-lsp-bridge-bsl:latest",
            name="mcp-lsp-ERPPur_Local",
            volumes={"/home/as/Z/ERPPur_Local": {"bind": "/projects", "mode": "rw"}},
            environment={
                "MCP_LSP_BSL_JAVA_XMX": "2g",
                "MCP_LSP_BSL_JAVA_XMS": "512m",
            },
            detach=True,
            restart_policy={"Name": "unless-stopped"},
        )

    def test_host_dir_has_entries_handles_oserror(self):
        from gateway.docker_manager import _host_dir_has_entries

        with patch("gateway.docker_manager.os.scandir", side_effect=OSError("boom")):
            assert _host_dir_has_entries("/tmp/missing") is False

    def test_container_dir_has_entries_success_and_failure(self):
        from gateway.docker_manager import _container_dir_has_entries

        ok = MagicMock(returncode=0, stdout="file\n")
        fail = MagicMock(returncode=1, stdout="")

        with patch("gateway.docker_manager.subprocess.run", return_value=ok):
            assert _container_dir_has_entries("container", "/projects") is True

        with patch("gateway.docker_manager.subprocess.run", return_value=fail):
            assert _container_dir_has_entries("container", "/projects") is False

        with patch("gateway.docker_manager.subprocess.run", side_effect=RuntimeError("boom")):
            assert _container_dir_has_entries("container", "/projects") is False

    def test_host_dir_has_entries_true_for_non_empty_dir(self, tmp_path):
        from gateway.docker_manager import _host_dir_has_entries

        (tmp_path / "child").mkdir()
        assert _host_dir_has_entries(str(tmp_path)) is True


class TestToolkitLifecycle:
    def test_start_toolkit_returns_existing_running_container(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.status = "running"
        container.attrs = {"Config": {"Env": ["PORT=6123"]}}

        with patch("gateway.docker_manager._container_running", return_value=container), \
             patch("gateway.docker_manager._patch_toolkit_structured_output") as patch_toolkit:
            port, name = start_toolkit("ERP")

        assert (port, name) == (6123, "onec-toolkit-ERP")
        patch_toolkit.assert_called_once_with("onec-toolkit-ERP")

    def test_start_toolkit_starts_new_linux_container(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "healthy"}}}

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6124), \
             patch("gateway.docker_manager._patch_toolkit_structured_output"), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Linux"):
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value.containers.run.return_value = container
            port, name = start_toolkit("ERP")

        assert (port, name) == (6124, "onec-toolkit-ERP")
        mock_docker.return_value.containers.run.assert_called_once()
        kwargs = mock_docker.return_value.containers.run.call_args.kwargs
        assert kwargs["network_mode"] == "host"

    def test_start_toolkit_starts_new_non_linux_container(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "healthy"}}}

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6125), \
             patch("gateway.docker_manager._patch_toolkit_structured_output"), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Windows"):
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value.containers.run.return_value = container
            start_toolkit("ERP")

        kwargs = mock_docker.return_value.containers.run.call_args.kwargs
        assert kwargs["ports"] == {"6125/tcp": 6125}

    def test_start_toolkit_raises_on_unhealthy_container(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "unhealthy"}}}

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6126), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Linux"):
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value.containers.run.return_value = container
            with pytest.raises(RuntimeError, match="unhealthy"):
                start_toolkit("ERP")

    def test_patch_toolkit_skips_when_already_patched(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        container = MagicMock()
        container.exec_run.return_value = MagicMock(exit_code=0, output=b"1\n")

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.return_value = container
            _patch_toolkit_structured_output("onec-toolkit-ERP")

        container.restart.assert_not_called()

    def test_patch_toolkit_applies_patch_and_restarts(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        container = MagicMock()
        container.exec_run.side_effect = [
            MagicMock(exit_code=0, output=b"0\n"),
            MagicMock(exit_code=0, output=b""),
        ]
        container.attrs = {"State": {"Health": {"Status": "starting"}}}

        def _reload():
            container.attrs["State"]["Health"]["Status"] = "healthy"

        container.reload.side_effect = _reload

        with patch("gateway.docker_manager._docker") as mock_docker, \
             patch("gateway.docker_manager.time.sleep"):
            mock_docker.return_value.containers.get.return_value = container
            _patch_toolkit_structured_output("onec-toolkit-ERP")

        container.restart.assert_called_once_with(timeout=5)
        assert container.exec_run.call_count == 2

    def test_patch_toolkit_logs_failure(self):
        from gateway.docker_manager import _patch_toolkit_structured_output

        with patch("gateway.docker_manager._docker") as mock_docker:
            mock_docker.return_value.containers.get.side_effect = RuntimeError("boom")
            _patch_toolkit_structured_output("onec-toolkit-ERP")

    def test_start_toolkit_removes_stopped_container_before_run(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "healthy"}}}
        stopped = MagicMock()

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6127), \
             patch("gateway.docker_manager._patch_toolkit_structured_output"), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Linux"):
            mock_docker.return_value.containers.get.return_value = stopped
            mock_docker.return_value.containers.run.return_value = container
            start_toolkit("ERP")

        stopped.remove.assert_called_once_with(force=True)

    def test_start_toolkit_logs_timeout_and_continues(self):
        from gateway.docker_manager import start_toolkit

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "starting"}}}

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6128), \
             patch("gateway.docker_manager._patch_toolkit_structured_output"), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Linux"):
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value.containers.run.return_value = container
            port, name = start_toolkit("ERP")

        assert (port, name) == (6128, "onec-toolkit-ERP")

    def test_start_toolkit_returns_when_reload_fails_during_health_wait(self):
        from gateway.docker_manager import _start_toolkit_direct

        container = MagicMock()
        container.attrs = {"State": {"Health": {"Status": "starting"}}}
        container.reload.side_effect = RuntimeError("boom")

        with patch("gateway.docker_manager._container_running", return_value=None), \
             patch("gateway.docker_manager._find_free_port", return_value=6129), \
             patch("gateway.docker_manager._patch_toolkit_structured_output"), \
             patch("gateway.docker_manager.time.sleep"), \
             patch("gateway.docker_manager._docker") as mock_docker, \
             patch("platform.system", return_value="Linux"):
            mock_docker.return_value.containers.get.side_effect = docker.errors.NotFound("not found")
            mock_docker.return_value.containers.run.return_value = container
            port, name = _start_toolkit_direct("ERP")

        assert (port, name) == (6129, "onec-toolkit-ERP")

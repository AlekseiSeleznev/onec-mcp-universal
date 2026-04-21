"""Tests for gateway.config Settings."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.config import Settings

# Environment variables set by docker-compose that interfere with default-value tests.
_DOCKER_ENV_VARS = [
    "PORT", "LOG_LEVEL", "LOG_JSON", "ONEC_TOOLKIT_URL", "PLATFORM_CONTEXT_URL",
    "ENABLED_BACKENDS", "PLATFORM_PATH",
    "IBCMD_PATH", "NAPARNIK_API_KEY", "METADATA_CACHE_TTL",
    "BSL_WORKSPACE_HOST", "BSL_HOST_WORKSPACE", "BSL_WORKSPACE",
    "EXPORT_HOST_URL", "ALLOW_CONTAINER_DESIGNER_EXPORT",
    "BSL_LSP_COMMAND", "TEST_RUNNER_URL", "BSL_GRAPH_URL",
    "GATEWAY_API_TOKEN", "DOCKER_CONTROL_TOKEN", "ANONYMIZER_SALT",
    "MCP_LSP_BSL_JAVA_XMX", "MCP_LSP_BSL_JAVA_XMS",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Remove docker-compose injected env vars so defaults are tested accurately."""
    for var in _DOCKER_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


def test_default_port(clean_env):
    s = Settings(_env_file=None)
    assert s.port == 8080


def test_default_log_level(clean_env):
    s = Settings(_env_file=None)
    assert s.log_level == "INFO"


def test_default_log_json(clean_env):
    s = Settings(_env_file=None)
    assert s.log_json is False


def test_default_onec_toolkit_url(clean_env):
    s = Settings(_env_file=None)
    assert s.onec_toolkit_url == "http://onec-toolkit:6003/mcp"


def test_default_platform_context_url(clean_env):
    s = Settings(_env_file=None)
    assert s.platform_context_url == "http://platform-context:8080/sse"


def test_default_bsl_lsp_command(clean_env):
    s = Settings(_env_file=None)
    assert s.bsl_lsp_command == ""


def test_default_mcp_lsp_bsl_java_xmx(clean_env):
    s = Settings(_env_file=None)
    assert s.mcp_lsp_bsl_java_xmx == "6g"


def test_default_mcp_lsp_bsl_java_xms(clean_env):
    s = Settings(_env_file=None)
    assert s.mcp_lsp_bsl_java_xms == "2g"


def test_default_ibcmd_path(clean_env):
    s = Settings(_env_file=None)
    assert s.ibcmd_path == "/opt/1cv8/x86_64/8.3.27.2074/ibcmd"


def test_default_export_host_url(clean_env):
    s = Settings(_env_file=None)
    assert s.export_host_url == ""


def test_default_docker_control_token(clean_env):
    s = Settings(_env_file=None)
    assert s.docker_control_token == ""


def test_default_anonymizer_salt(clean_env):
    s = Settings(_env_file=None)
    assert s.anonymizer_salt == ""


def test_default_allow_container_designer_export(clean_env):
    s = Settings(_env_file=None)
    assert s.allow_container_designer_export is False


def test_default_bsl_host_workspace(clean_env):
    s = Settings(_env_file=None)
    assert s.bsl_host_workspace == ""


def test_default_bsl_workspace(clean_env):
    # bsl_workspace is the *container-side* mount target and matches the
    # docker-compose bind-mount at /workspace. The ambiguous BSL_WORKSPACE
    # .env variable is the HOST path and is deliberately NOT bound here.
    s = Settings(_env_file=None)
    assert s.bsl_workspace == "/workspace"


def test_default_test_runner_url(clean_env):
    s = Settings(_env_file=None)
    assert s.test_runner_url == "http://localhost:8000/sse"


def test_default_bsl_graph_url(clean_env):
    s = Settings(_env_file=None)
    assert s.bsl_graph_url == "http://localhost:8888"


def test_default_enabled_backends(clean_env):
    s = Settings(_env_file=None)
    assert s.enabled_backends == "onec-toolkit,platform-context,bsl-lsp-bridge"


def test_default_naparnik_api_key(clean_env):
    s = Settings(_env_file=None)
    assert s.naparnik_api_key == ""


def test_default_gateway_api_token(clean_env):
    s = Settings(_env_file=None)
    assert s.gateway_api_token == ""


def test_default_metadata_cache_ttl(clean_env):
    s = Settings(_env_file=None)
    assert s.metadata_cache_ttl == 600


def test_default_epf_heartbeat_ttl_covers_toolkit_command_timeout(clean_env):
    s = Settings(_env_file=None)
    assert s.epf_heartbeat_ttl_seconds >= 240


# ---------------------------------------------------------------------------
# Environment variable overrides (via monkeypatch)
# ---------------------------------------------------------------------------


def test_env_override_port(monkeypatch):
    monkeypatch.setenv("PORT", "9090")
    s = Settings(_env_file=None)
    assert s.port == 9090


def test_env_override_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"


def test_env_override_log_json(monkeypatch):
    monkeypatch.setenv("LOG_JSON", "true")
    s = Settings(_env_file=None)
    assert s.log_json is True


def test_env_override_onec_toolkit_url(monkeypatch):
    monkeypatch.setenv("ONEC_TOOLKIT_URL", "http://custom:1234/mcp")
    s = Settings(_env_file=None)
    assert s.onec_toolkit_url == "http://custom:1234/mcp"


def test_env_override_platform_context_url(monkeypatch):
    monkeypatch.setenv("PLATFORM_CONTEXT_URL", "http://other:5555/sse")
    s = Settings(_env_file=None)
    assert s.platform_context_url == "http://other:5555/sse"


def test_env_override_bsl_lsp_command(monkeypatch):
    monkeypatch.setenv("BSL_LSP_COMMAND", "/usr/local/bin/bsl-lsp")
    s = Settings(_env_file=None)
    assert s.bsl_lsp_command == "/usr/local/bin/bsl-lsp"


def test_env_override_mcp_lsp_bsl_java_xmx(monkeypatch):
    monkeypatch.setenv("MCP_LSP_BSL_JAVA_XMX", "2g")
    s = Settings(_env_file=None)
    assert s.mcp_lsp_bsl_java_xmx == "2g"


def test_env_override_mcp_lsp_bsl_java_xms(monkeypatch):
    monkeypatch.setenv("MCP_LSP_BSL_JAVA_XMS", "512m")
    s = Settings(_env_file=None)
    assert s.mcp_lsp_bsl_java_xms == "512m"


def test_env_override_ibcmd_path(monkeypatch):
    monkeypatch.setenv("IBCMD_PATH", "/usr/bin/ibcmd")
    s = Settings(_env_file=None)
    assert s.ibcmd_path == "/usr/bin/ibcmd"


def test_env_override_export_host_url(monkeypatch):
    monkeypatch.setenv("EXPORT_HOST_URL", "http://host:7777")
    s = Settings(_env_file=None)
    assert s.export_host_url == "http://host:7777"


def test_env_override_docker_control_token(monkeypatch):
    monkeypatch.setenv("DOCKER_CONTROL_TOKEN", "secret-token")
    s = Settings(_env_file=None)
    assert s.docker_control_token == "secret-token"


def test_env_override_anonymizer_salt(monkeypatch):
    monkeypatch.setenv("ANONYMIZER_SALT", "salt-token")
    s = Settings(_env_file=None)
    assert s.anonymizer_salt == "salt-token"


def test_env_override_allow_container_designer_export(monkeypatch):
    monkeypatch.setenv("ALLOW_CONTAINER_DESIGNER_EXPORT", "true")
    s = Settings(_env_file=None)
    assert s.allow_container_designer_export is True


def test_env_override_bsl_host_workspace(monkeypatch):
    monkeypatch.setenv("BSL_HOST_WORKSPACE", "/home/user/projects")
    s = Settings(_env_file=None)
    assert s.bsl_host_workspace == "/home/user/projects"


def test_env_override_bsl_workspace(monkeypatch):
    # Override uses the explicit BSL_CONTAINER_WORKSPACE alias so that the
    # HOST-path BSL_WORKSPACE (used by docker-compose for the bind-mount
    # source) cannot accidentally overwrite the container-side mount target.
    monkeypatch.setenv("BSL_CONTAINER_WORKSPACE", "/data/bsl")
    s = Settings(_env_file=None)
    assert s.bsl_workspace == "/data/bsl"


def test_bsl_workspace_ignores_host_path_variable(monkeypatch):
    """BSL_WORKSPACE in .env is the HOST path (used by docker-compose) and
    MUST NOT bleed into settings.bsl_workspace — otherwise the gateway would
    try to write exports to a host path inside the container."""
    monkeypatch.setenv("BSL_WORKSPACE", "/home/user/bsl-projects")
    s = Settings(_env_file=None)
    assert s.bsl_workspace == "/workspace"
    # But bsl_host_workspace SHOULD pick it up via its AliasChoices fallback.
    assert s.bsl_host_workspace == "/home/user/bsl-projects"


def test_env_override_test_runner_url(monkeypatch):
    monkeypatch.setenv("TEST_RUNNER_URL", "http://runner:9000/sse")
    s = Settings(_env_file=None)
    assert s.test_runner_url == "http://runner:9000/sse"


def test_env_override_bsl_graph_url(monkeypatch):
    monkeypatch.setenv("BSL_GRAPH_URL", "http://graph:4444")
    s = Settings(_env_file=None)
    assert s.bsl_graph_url == "http://graph:4444"


def test_env_override_enabled_backends(monkeypatch):
    monkeypatch.setenv("ENABLED_BACKENDS", "onec-toolkit")
    s = Settings(_env_file=None)
    assert s.enabled_backends == "onec-toolkit"


def test_env_override_naparnik_api_key(monkeypatch):
    monkeypatch.setenv("NAPARNIK_API_KEY", "sk-test-12345")
    s = Settings(_env_file=None)
    assert s.naparnik_api_key == "sk-test-12345"


def test_env_override_gateway_api_token(monkeypatch):
    monkeypatch.setenv("GATEWAY_API_TOKEN", "secret-token")
    s = Settings(_env_file=None)
    assert s.gateway_api_token == "secret-token"


def test_env_override_metadata_cache_ttl(monkeypatch):
    monkeypatch.setenv("METADATA_CACHE_TTL", "0")
    s = Settings(_env_file=None)
    assert s.metadata_cache_ttl == 0


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def test_port_coerced_from_string(monkeypatch):
    """PORT env var is a string; pydantic must coerce it to int."""
    monkeypatch.setenv("PORT", "3000")
    s = Settings(_env_file=None)
    assert isinstance(s.port, int)
    assert s.port == 3000


def test_metadata_cache_ttl_coerced_from_string(monkeypatch):
    """METADATA_CACHE_TTL env var is a string; pydantic must coerce it to int."""
    monkeypatch.setenv("METADATA_CACHE_TTL", "1200")
    s = Settings(_env_file=None)
    assert isinstance(s.metadata_cache_ttl, int)
    assert s.metadata_cache_ttl == 1200


def test_port_type_is_int(clean_env):
    s = Settings(_env_file=None)
    assert isinstance(s.port, int)


def test_metadata_cache_ttl_type_is_int(clean_env):
    s = Settings(_env_file=None)
    assert isinstance(s.metadata_cache_ttl, int)


# ---------------------------------------------------------------------------
# Optional / empty-string fields behave as expected
# ---------------------------------------------------------------------------


def test_naparnik_api_key_empty_by_default(clean_env):
    """naparnik_api_key defaults to empty string (optional feature)."""
    s = Settings(_env_file=None)
    assert s.naparnik_api_key == ""
    assert not s.naparnik_api_key  # falsy when unused


def test_bsl_lsp_command_empty_by_default(clean_env):
    """bsl_lsp_command defaults to empty string (direct binary not configured)."""
    s = Settings(_env_file=None)
    assert s.bsl_lsp_command == ""
    assert not s.bsl_lsp_command


def test_export_host_url_empty_by_default(clean_env):
    """export_host_url defaults to empty string (host service not configured)."""
    s = Settings(_env_file=None)
    assert s.export_host_url == ""
    assert not s.export_host_url


def test_bsl_host_workspace_empty_by_default(clean_env):
    """bsl_host_workspace defaults to empty string (not configured)."""
    s = Settings(_env_file=None)
    assert s.bsl_host_workspace == ""
    assert not s.bsl_host_workspace


# ---------------------------------------------------------------------------
# Multiple env vars at once
# ---------------------------------------------------------------------------


def test_multiple_env_overrides(clean_env, monkeypatch):
    """Several settings can be overridden simultaneously."""
    monkeypatch.setenv("PORT", "4000")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("NAPARNIK_API_KEY", "key-abc")
    monkeypatch.setenv("METADATA_CACHE_TTL", "300")
    monkeypatch.setenv("BSL_CONTAINER_WORKSPACE", "/custom/workspace")

    s = Settings(_env_file=None)

    assert s.port == 4000
    assert s.log_level == "WARNING"
    assert s.naparnik_api_key == "key-abc"
    assert s.metadata_cache_ttl == 300
    assert s.bsl_workspace == "/custom/workspace"
    # non-overridden fields keep defaults
    assert s.onec_toolkit_url == "http://onec-toolkit:6003/mcp"
    assert s.bsl_lsp_command == ""


def test_toolkit_dangerous_with_approval_enabled_by_default(clean_env):
    s = Settings(_env_file=None)
    assert s.toolkit_allow_dangerous_with_approval is True


def test_metadata_cache_ttl_zero_disables_cache(monkeypatch):
    """TTL of 0 means caching is disabled."""
    monkeypatch.setenv("METADATA_CACHE_TTL", "0")
    s = Settings(_env_file=None)
    assert s.metadata_cache_ttl == 0

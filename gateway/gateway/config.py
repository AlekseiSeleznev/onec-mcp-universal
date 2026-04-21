import os
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "1.9.29"

_platform_path = os.environ.get("PLATFORM_PATH", "/opt/1cv8/x86_64/8.3.27.2074")


class Settings(BaseSettings):
    # Read .env from both the container mount point (/data/.env) and the fallback
    # relative path (for tests / running outside Docker). pydantic-settings merges
    # them — later entries override earlier — so /data/.env wins inside the container.
    model_config = SettingsConfigDict(
        env_file=("/data/.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8080
    log_level: str = "INFO"
    log_json: bool = False

    # Backend URLs
    onec_toolkit_url: str = "http://onec-toolkit:6003/mcp"
    platform_context_url: str = "http://platform-context:8080/sse"
    platform_context_call_timeout_seconds: int = 20

    # LSP backend: direct binary (all-in-one mode).
    # Gateway mode uses per-database LSP containers started by docker_manager.
    bsl_lsp_command: str = ""
    mcp_lsp_bsl_java_xmx: str = "6g"
    mcp_lsp_bsl_java_xms: str = "2g"

    # 1C platform path (mounted into container via HOST_PLATFORM_PATH → /opt/1cv8)
    platform_path: str = _platform_path

    # Path to ibcmd binary (derived from platform_path, cross-platform)
    ibcmd_path: str = str(Path(_platform_path) / "ibcmd")

    # URL of host-side export service (recommended and license-safe path)
    export_host_url: str = ""

    # URL of the internal docker-control sidecar used for container lifecycle,
    # diagnostics, env writes, and LSP stdio proxying.
    docker_control_url: str = "http://localhost:8091"
    docker_control_token: str = ""
    anonymizer_salt: str = ""

    # Safety guard: exporting via 1cv8 inside a container can invalidate
    # software licenses due to hardware fingerprint mismatch.
    # Keep disabled by default; enable only for hardware dongle/CI scenarios.
    allow_container_designer_export: bool = False

    # Host-side path that maps to bsl_workspace inside the container.
    # Read from BSL_HOST_WORKSPACE first, falling back to BSL_WORKSPACE for
    # back-compat with older .env files where a single BSL_WORKSPACE held the
    # host path (docker-compose also uses it as the bind-mount source).
    bsl_host_workspace: str = Field(
        default="",
        validation_alias=AliasChoices("BSL_HOST_WORKSPACE", "BSL_WORKSPACE"),
    )

    # BSL workspace path *inside* the container — matches the docker-compose
    # bind-mount target "${BSL_WORKSPACE:-./bsl-projects}:/workspace:rw".
    # Pinned to BSL_CONTAINER_WORKSPACE so the ambiguous BSL_WORKSPACE (host
    # path) cannot accidentally override it.
    bsl_workspace: str = Field(
        default="/workspace",
        validation_alias=AliasChoices("BSL_CONTAINER_WORKSPACE",),
    )

    # Test runner backend (mcp-onec-test-runner, optional)
    test_runner_url: str = "http://localhost:8000/sse"

    # BSL Graph backend REST API (bsl-graph, optional)
    bsl_graph_url: str = "http://localhost:8888"

    # Enabled backends (comma-separated)
    enabled_backends: str = "onec-toolkit,platform-context,bsl-lsp-bridge"

    # 1C:Naparnik (1C:Naparnik) API key for ITS search
    naparnik_api_key: str = ""

    # Safe-by-default project-level toolkit flag. Applies to the static toolkit
    # container and dynamically created per-database toolkit containers.
    toolkit_allow_dangerous_with_approval: bool = True

    # Optional bearer token for mutating HTTP endpoints (/api/action/*, /api/register, /api/export-*)
    gateway_api_token: str = ""

    # REST/dashboard rate limiting. /mcp and /health are intentionally excluded.
    gateway_rate_limit_enabled: bool = True
    gateway_rate_limit_read_rpm: int = 120
    gateway_rate_limit_mutating_rpm: int = 30

    # Metadata cache TTL in seconds (0 = disabled)
    metadata_cache_ttl: int = 600

    # BSL export timeout in seconds (default 3600 = 1 hour, large configs like BP/ZUP need it)
    bsl_export_timeout: int = 3600

    # EPF liveness heartbeat TTL in seconds for dashboard status.
    # Must exceed the toolkit command timeout so long-running commands do not
    # falsely mark a healthy EPF session as disconnected.
    epf_heartbeat_ttl_seconds: int = 240


settings = Settings()

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    port: int = 8080
    log_level: str = "INFO"

    # Backend URLs
    onec_toolkit_url: str = "http://onec-toolkit:6003/mcp"
    platform_context_url: str = "http://platform-context:8080/sse"

    # LSP backend: direct binary (all-in-one mode) OR docker exec
    bsl_lsp_command: str = ""
    lsp_docker_container: str = "mcp-lsp-zup"

    # Path to ibcmd binary (for export_bsl_sources tool)
    ibcmd_path: str = "/opt/1cv8/x86_64/8.3.27.2074/ibcmd"

    # URL of host-side export service (tools/export-host-service.py)
    export_host_url: str = ""

    # Host-side path that maps to bsl_workspace inside the container
    bsl_host_workspace: str = ""

    # BSL workspace path inside the container
    bsl_workspace: str = "/projects"

    # Test runner backend (mcp-onec-test-runner, optional)
    test_runner_url: str = "http://localhost:8000/sse"

    # BSL Graph backend REST API (bsl-graph, optional)
    bsl_graph_url: str = "http://localhost:8888"

    # Enabled backends (comma-separated)
    enabled_backends: str = "onec-toolkit,platform-context,bsl-lsp-bridge"

    # 1C:Napilnik (1C:Naparnik) API key for ITS search
    napilnik_api_key: str = ""

    # Metadata cache TTL in seconds (0 = disabled)
    metadata_cache_ttl: int = 600


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8080
    log_level: str = "INFO"

    # Backend URLs
    onec_toolkit_url: str = "http://onec-toolkit:6003/mcp"
    platform_context_url: str = "http://platform-context:8080/sse"

    # LSP backend: direct binary (all-in-one mode) OR docker exec
    # If bsl_lsp_command is set — runs the binary directly (no docker exec)
    # If empty — falls back to docker exec lsp_docker_container
    bsl_lsp_command: str = ""
    lsp_docker_container: str = "mcp-lsp-zup"

    # Path to ibcmd binary (for export_bsl_sources tool)
    ibcmd_path: str = "/opt/1cv8/x86_64/8.3.27.2074/ibcmd"

    # URL of host-side export service (tools/export-host-service.py).
    # When set, gateway forwards /api/export-bsl to this URL instead of calling ibcmd directly.
    # Use host.docker.internal or host IP. Example: http://172.17.0.1:8082
    export_host_url: str = ""

    # Host-side path that corresponds to BSL_WORKSPACE inside the container.
    # The gateway replaces the container path prefix with this value before
    # forwarding to the export host service.
    # Example: if BSL_WORKSPACE=/projects and host volume is /home/user/bsl-workspace,
    # set BSL_HOST_WORKSPACE=/home/user/bsl-workspace
    bsl_host_workspace: str = ""

    # BSL workspace path inside the container (must match BSL_WORKSPACE env of LSP)
    bsl_workspace: str = "/projects"

    # Which backends to enable (comma-separated: onec-toolkit,platform-context,bsl-lsp-bridge)
    enabled_backends: str = "onec-toolkit,platform-context,bsl-lsp-bridge"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

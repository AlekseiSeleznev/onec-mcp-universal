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

    # Which backends to enable (comma-separated: onec-toolkit,platform-context,bsl-lsp-bridge)
    enabled_backends: str = "onec-toolkit,platform-context,bsl-lsp-bridge"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

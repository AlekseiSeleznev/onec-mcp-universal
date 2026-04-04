"""
Manages per-database Docker containers:
  - onec-toolkit-{db}  : HTTP MCP proxy for 1C data tools
  - mcp-lsp-{db}       : BSL Language Server for code navigation
"""
import logging
import socket
import time

import docker

log = logging.getLogger(__name__)

TOOLKIT_IMAGE = "roctup/1c-mcp-toolkit-proxy"
LSP_IMAGE = "mcp-lsp-bridge-bsl:latest"

# Docker network shared with gateway container
DOCKER_NETWORK = "onec-mcp-universal_onec-net"

_client: docker.DockerClient | None = None


def _docker() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _find_free_port(start: int = 6100) -> int:
    """Find a free host port, excluding ports already bound by Docker containers."""
    # Collect all host ports currently allocated by Docker
    used_by_docker: set[int] = set()
    try:
        for c in _docker().containers.list():
            for port_bindings in c.ports.values():
                if port_bindings:
                    for b in port_bindings:
                        try:
                            used_by_docker.add(int(b["HostPort"]))
                        except (KeyError, ValueError):
                            pass
    except Exception:
        pass

    port = start
    while port < 7000:
        if port in used_by_docker:
            port += 1
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
        port += 1
    raise RuntimeError("No free ports in 6100-7000 range")


def _container_running(name: str) -> docker.models.containers.Container | None:
    try:
        c = _docker().containers.get(name)
        if c.status == "running":
            return c
    except docker.errors.NotFound:
        pass
    return None


def _get_container_port(container: docker.models.containers.Container, env_var: str = "PORT") -> int | None:
    """Extract PORT from container env (works for host-network containers too)."""
    for env in container.attrs.get("Config", {}).get("Env", []):
        if env.startswith(f"{env_var}="):
            try:
                return int(env.split("=", 1)[1])
            except ValueError:
                pass
    return None


def start_toolkit(db_name: str) -> tuple[int, str]:
    """
    Start onec-toolkit container for db_name.
    Returns (host_port, container_name).
    """
    container_name = f"onec-toolkit-{db_name}"
    existing = _container_running(container_name)
    if existing:
        port = _get_container_port(existing, "PORT") or 6003
        log.info(f"Toolkit {container_name} already running on port {port}")
        return port, container_name

    # Remove stopped container with same name if any
    try:
        old = _docker().containers.get(container_name)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass

    port = _find_free_port(6100)
    container = _docker().containers.run(
        TOOLKIT_IMAGE,
        name=container_name,
        network=DOCKER_NETWORK,
        ports={"6003/tcp": port},    # expose on host for 1C /1c/poll
        environment={
            "PORT": "6003",          # internal port is always 6003
            "TIMEOUT": "180",
            "RESPONSE_FORMAT": "json",
            "ALLOW_DANGEROUS_WITH_APPROVAL": "true",
        },
        detach=True,
        restart_policy={"Name": "unless-stopped"},
    )

    # Wait for healthy (up to 20s)
    for _ in range(20):
        time.sleep(1)
        container.reload()
        health = container.attrs.get("State", {}).get("Health", {}).get("Status", "")
        if health == "healthy":
            break
        if health == "unhealthy":
            raise RuntimeError(f"Container {container_name} is unhealthy")
    else:
        log.warning(f"Container {container_name} health check timed out, proceeding anyway")

    log.info(f"Started {container_name} on port {port}")
    return port, container_name


def start_lsp(db_name: str, bsl_host_path: str) -> str:
    """
    Start mcp-lsp container for db_name with bsl_host_path mounted as /projects.
    Returns container_name.
    """
    container_name = f"mcp-lsp-{db_name}"
    if _container_running(container_name):
        log.info(f"LSP {container_name} already running")
        return container_name

    # Remove stopped container with same name if any
    try:
        old = _docker().containers.get(container_name)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass

    _docker().containers.run(
        LSP_IMAGE,
        name=container_name,
        network=DOCKER_NETWORK,
        volumes={bsl_host_path: {"bind": "/projects", "mode": "rw"}},
        detach=True,
        restart_policy={"Name": "unless-stopped"},
    )

    # Give LSP time to initialize
    time.sleep(3)
    log.info(f"Started LSP {container_name} for {bsl_host_path}")
    return container_name


def stop_db_containers(db_name: str):
    """Stop and remove containers for db_name."""
    for prefix in ("onec-toolkit", "mcp-lsp"):
        container_name = f"{prefix}-{db_name}"
        try:
            c = _docker().containers.get(container_name)
            c.stop(timeout=10)
            c.remove()
            log.info(f"Removed {container_name}")
        except docker.errors.NotFound:
            pass
        except Exception as exc:
            log.warning(f"Error stopping {container_name}: {exc}")

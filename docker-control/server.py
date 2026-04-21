from __future__ import annotations

import asyncio
import hmac
import io
import logging
import os
import re
import shlex
import socket
import tarfile
import time
from contextlib import AsyncExitStack, asynccontextmanager

import docker
import uvicorn
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

logger = logging.getLogger(__name__)

TOOLKIT_IMAGE = "roctup/1c-mcp-toolkit-proxy"
LSP_IMAGE = "mcp-lsp-bridge-bsl:latest"
PORT = int(os.environ.get("PORT", "8091"))
ENV_FILE_PATHS = ("/data/.env", ".env", "/app/.env")
WINDOWS_ABS_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
INVALID_PATH_CHARS = {"\x00", "\n", "\r", "`", "$", ";", "&", "|", "<", ">"}
_HEALABLE_ENV_KEYS = ("DOCKER_CONTROL_TOKEN", "ANONYMIZER_SALT")

_client: docker.DockerClient | None = None


def _docker() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def _find_free_port(start: int = 6100) -> int:
    used_by_docker: set[int] = set()
    try:
        for container in _docker().containers.list(all=True):
            for port_bindings in (container.ports or {}).values():
                if not port_bindings:
                    continue
                for binding in port_bindings:
                    try:
                        used_by_docker.add(int(binding["HostPort"]))
                    except (KeyError, ValueError, TypeError):
                        continue
            # Containers on network_mode: host do not report their ports via
            # container.ports. Fall back to PORT= in the container's env so
            # two per-DB toolkits cannot both be assigned 6100.
            env_list = (
                ((getattr(container, "attrs", {}) or {}).get("Config") or {})
                .get("Env")
            ) or []
            for item in env_list:
                if str(item).startswith("PORT="):
                    try:
                        used_by_docker.add(int(str(item).split("=", 1)[1]))
                    except (TypeError, ValueError):
                        pass
                    break
    except Exception:
        pass

    port = start
    while port < 7000:
        if port in used_by_docker:
            port += 1
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("localhost", port)) != 0:
                return port
        port += 1
    raise RuntimeError("No free ports in 6100-7000 range")


def _container_running(name: str):
    try:
        container = _docker().containers.get(name)
        if container.status == "running":
            return container
    except docker.errors.NotFound:
        return None
    return None


def _get_container_port(container, env_var: str = "PORT") -> int | None:
    for env in container.attrs.get("Config", {}).get("Env", []):
        if env.startswith(f"{env_var}="):
            try:
                return int(env.split("=", 1)[1])
            except ValueError:
                return None
    return None


def _read_env_text() -> str:
    for path in ENV_FILE_PATHS:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            continue
        except OSError:
            continue
    return ""


def _iter_env_assignments(content: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key_text, _, value = line.partition("=")
        pairs.append((key_text.strip(), value))
    return pairs


def _prepare_env_content_for_write(content: str, replace: bool = False) -> str:
    if replace:
        return content

    current = _read_env_text()
    current_keys = {key for key, _ in _iter_env_assignments(current)}
    incoming_keys = {key for key, _ in _iter_env_assignments(content)}
    if current_keys and incoming_keys and not current_keys.issubset(incoming_keys):
        raise ValueError("partial env update rejected; submit the full .env content")
    return content


def _ensure_env_key_present(key: str, value: str) -> None:
    if not value:
        return
    current = _read_env_text()
    current_keys = {env_key for env_key, _ in _iter_env_assignments(current)}
    if key in current_keys:
        return
    lines = current.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append(f"{key}={value}\n")
    new_content = "".join(lines)
    for path in ENV_FILE_PATHS:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(new_content)
            return
        except (FileNotFoundError, PermissionError, OSError):
            continue


def _heal_required_env_keys_from_environment() -> None:
    for key in _HEALABLE_ENV_KEYS:
        _ensure_env_key_present(key, os.environ.get(key, "").strip())


def _read_env_value(key: str) -> str:
    for line in _read_env_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_key, _, value = stripped.partition("=")
        if env_key.strip() == key:
            value = value.strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value
    return ""


def _docker_control_token() -> str:
    return (os.environ.get("DOCKER_CONTROL_TOKEN") or _read_env_value("DOCKER_CONTROL_TOKEN")).strip()


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth:
        return None
    scheme, _, value = auth.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _auth_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


def _require_api_token(request: Request) -> JSONResponse | None:
    expected = _docker_control_token()
    if not expected:
        return _auth_error("DOCKER_CONTROL_TOKEN is not configured.", 503)
    provided = _extract_bearer_token(request)
    if not provided or not hmac.compare_digest(provided, expected):
        return _auth_error("Missing or invalid Authorization header (expected Bearer token).", 401)
    return None


def _is_absolute_host_path(path: str) -> bool:
    return os.path.isabs(path) or bool(WINDOWS_ABS_PATH_RE.match(path))


def _is_windows_host_path(path: str) -> bool:
    return bool(WINDOWS_ABS_PATH_RE.match(path))


def _normalize_host_path(path: str) -> str:
    stripped = (path or "").strip()
    if not stripped:
        raise ValueError("mount_path required")
    if any(ch in stripped for ch in INVALID_PATH_CHARS):
        raise ValueError("mount_path contains forbidden characters")
    if not _is_absolute_host_path(stripped):
        raise ValueError("mount_path must be absolute")

    parts = stripped.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise ValueError("mount_path must not contain '..'")

    if _is_windows_host_path(stripped):
        drive = stripped[0].upper()
        remainder = stripped[2:].replace("\\", "/").lstrip("/")
        normalized = f"{drive}:/{remainder}" if remainder else f"{drive}:/"
        return normalized.rstrip("/") if normalized != f"{drive}:/" else normalized

    return os.path.realpath(stripped)


def _path_is_within_base(path: str, base: str) -> bool:
    if _is_windows_host_path(path) or _is_windows_host_path(base):
        lhs = path.replace("\\", "/").rstrip("/").lower()
        rhs = base.replace("\\", "/").rstrip("/").lower()
        return lhs == rhs or lhs.startswith(f"{rhs}/")
    lhs = os.path.realpath(path)
    rhs = os.path.realpath(base)
    return lhs == rhs or lhs.startswith(f"{rhs}{os.sep}")


def _workspace_root() -> str:
    return (
        _read_env_value("BSL_HOST_WORKSPACE")
        or _read_env_value("BSL_WORKSPACE")
        or ""
    ).strip()


def _validate_mount_path(path: str) -> str:
    normalized = _normalize_host_path(path)
    root = _workspace_root()
    if not root:
        logger.warning(
            "BSL workspace root is not configured; accepting explicit mount_path %s",
            normalized,
        )
        return normalized
    normalized_root = _normalize_host_path(root)
    if not _path_is_within_base(normalized, normalized_root):
        raise ValueError("mount_path must stay inside the configured BSL workspace")
    return normalized


def _validate_container_bsl_root(path: str) -> str:
    normalized = (path or "").strip().replace("\\", "/") or "/projects"
    if any(ch in normalized for ch in INVALID_PATH_CHARS):
        raise ValueError("bsl_root contains forbidden characters")
    if not normalized.startswith("/"):
        raise ValueError("bsl_root must be absolute")
    if any(part == ".." for part in normalized.split("/")):
        raise ValueError("bsl_root must not contain '..'")
    if normalized != "/projects" and not normalized.startswith("/projects/"):
        raise ValueError("bsl_root must stay inside /projects")
    return normalized.rstrip("/") or "/"


def _validate_container_relative_path(path: str) -> str:
    normalized = (path or "").strip().replace("\\", "/")
    if not normalized:
        raise ValueError("relative_path required")
    if normalized.startswith("/"):
        raise ValueError("relative_path must stay relative to /projects")
    if any(ch in normalized for ch in INVALID_PATH_CHARS):
        raise ValueError("relative_path contains forbidden characters")
    parts = [part for part in normalized.split("/") if part]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("relative_path must not contain '..'")
    return "/".join(parts)


def _projects_owner(container) -> str | None:
    try:
        result = container.exec_run(["stat", "-c", "%u:%g", "/projects"])
    except Exception:
        return None
    if getattr(result, "exit_code", 1) != 0:
        return None
    owner = getattr(result, "output", b"").decode("utf-8", errors="replace").strip()
    return owner or None


def _patch_toolkit_structured_output(container_name: str) -> None:
    try:
        container = _docker().containers.get(container_name)
        handler_path = "/app/onec_mcp_toolkit_proxy/mcp_handler.py"
        result = container.exec_run(f"grep -c 'structured_output=False' {handler_path}")
        if result.exit_code == 0 and result.output.decode().strip() != "0":
            return
        container.exec_run(
            f"sed -i 's/@mcp\\.tool()/@mcp.tool(structured_output=False)/g' {handler_path}"
        )
        container.restart(timeout=5)
        for _ in range(20):
            time.sleep(1)
            container.reload()
            health = container.attrs.get("State", {}).get("Health", {}).get("Status", "")
            if health == "healthy":
                break
    except Exception as exc:
        logger.warning("[%s] patch failed: %s", container_name, exc)


def _host_dir_has_entries(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except OSError:
        return False


def _container_dir_has_entries(container_name: str, path: str) -> bool:
    try:
        container = _docker().containers.get(container_name)
        result = container.exec_run(["find", path, "-mindepth", "1", "-maxdepth", "1", "-print", "-quit"])
    except Exception:
        return False
    return result.exit_code == 0 and bool(result.output.decode("utf-8", errors="replace").strip())


def _lsp_mount_source_changed(container, expected_host_path: str) -> bool:
    expected = os.path.realpath(expected_host_path)
    for mount in container.attrs.get("Mounts", []):
        if mount.get("Destination") != "/projects":
            continue
        source = os.path.realpath(mount.get("Source", ""))
        return source != expected
    return True


def start_toolkit(slug: str, dangerous_with_approval: bool) -> tuple[int, str]:
    container_name = f"onec-toolkit-{slug}"
    existing = _container_running(container_name)
    if existing:
        port = _get_container_port(existing, "PORT") or 6003
        _patch_toolkit_structured_output(container_name)
        return port, container_name

    try:
        old = _docker().containers.get(container_name)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass

    port = _find_free_port(6100)
    is_linux = os.uname().sysname == "Linux"
    run_kwargs = {
        "name": container_name,
        "environment": {
            "PORT": str(port),
            "TIMEOUT": "180",
            "RESPONSE_FORMAT": "json",
            "ALLOW_DANGEROUS_WITH_APPROVAL": "true" if dangerous_with_approval else "false",
        },
        "detach": True,
        "restart_policy": {"Name": "unless-stopped"},
    }
    if is_linux:
        run_kwargs["network_mode"] = "host"
    else:
        run_kwargs["ports"] = {f"{port}/tcp": port}

    container = _docker().containers.run(TOOLKIT_IMAGE, **run_kwargs)
    for _ in range(20):
        time.sleep(1)
        container.reload()
        health = container.attrs.get("State", {}).get("Health", {}).get("Status", "")
        if health == "healthy":
            break
        if health == "unhealthy":
            raise RuntimeError(f"Container {container_name} is unhealthy")
    _patch_toolkit_structured_output(container_name)
    return port, container_name


def start_lsp(slug: str, mount_path: str, java_xmx: str, java_xms: str) -> str | None:
    mount_path = _validate_mount_path(mount_path)
    try:
        _docker().images.get(LSP_IMAGE)
    except docker.errors.ImageNotFound:
        logger.info("LSP image %s not found locally — skipping BSL LSP for %s", LSP_IMAGE, slug)
        return None

    container_name = f"mcp-lsp-{slug}"
    if not _is_windows_host_path(mount_path):
        os.makedirs(mount_path, exist_ok=True)
    existing = _container_running(container_name)
    recreated = False
    if existing:
        if _lsp_mount_source_changed(existing, mount_path):
            existing.remove(force=True)
            existing = None
            recreated = True
        elif not _container_dir_has_entries(container_name, "/projects"):
            try:
                existing.remove(force=True)
                existing = None
                recreated = True
            except Exception as exc:
                logger.warning("Failed to recreate %s with fresh mount: %s", container_name, exc)
        if existing is not None:
            return container_name

    try:
        old = _docker().containers.get(container_name)
        old.remove(force=True)
    except docker.errors.NotFound:
        pass

    _docker().containers.run(
        LSP_IMAGE,
        name=container_name,
        volumes={mount_path: {"bind": "/projects", "mode": "rw"}},
        environment={
            "MCP_LSP_BSL_JAVA_XMX": java_xmx,
            "MCP_LSP_BSL_JAVA_XMS": java_xms,
            "WORKSPACE_ROOT": "/projects",
        },
        detach=True,
        restart_policy={"Name": "unless-stopped"},
    )
    if recreated:
        _close_lsp_proxy(slug)
    time.sleep(3)
    return container_name


def stop_db_containers(slug: str) -> None:
    _close_lsp_proxy(slug)
    for prefix in ("onec-toolkit", "mcp-lsp"):
        container_name = f"{prefix}-{slug}"
        try:
            container = _docker().containers.get(container_name)
            container.stop(timeout=10)
            container.remove()
        except docker.errors.NotFound:
            continue
        except Exception as exc:
            logger.warning("Error stopping %s: %s", container_name, exc)


def cleanup_orphan_db_containers(active_slugs: set[str]) -> int:
    prefixes = ("onec-toolkit-", "mcp-lsp-")
    removed = 0
    try:
        containers = _docker().containers.list(all=True)
    except Exception as exc:
        logger.warning("Cannot list Docker containers for orphan cleanup: %s", exc)
        return 0

    for container in containers:
        name = container.name or ""
        matched_prefix = next((prefix for prefix in prefixes if name.startswith(prefix)), "")
        if not matched_prefix:
            continue
        slug = name[len(matched_prefix):]
        if not slug or slug in active_slugs:
            continue
        try:
            container.remove(force=True)
            _close_lsp_proxy(slug)
            removed += 1
        except docker.errors.NotFound:
            continue
        except Exception as exc:
            logger.warning("Error removing orphan container %s: %s", name, exc)
    return removed


def get_docker_system_info() -> dict:
    try:
        client = _docker()
        info = client.info()
        images_size = 0
        volumes_size = 0
        try:
            df = client.df()
            images_size = sum(img.get("Size", 0) or 0 for img in df.get("Images", []))
            volumes_size = sum(
                (volume.get("UsageData") or {}).get("Size", 0) or 0
                for volume in df.get("Volumes", [])
            )
        except Exception:
            pass
        return {
            "version": info.get("ServerVersion", ""),
            "os": info.get("OperatingSystem", ""),
            "arch": info.get("Architecture", ""),
            "cpus": info.get("NCPU", 0),
            "memory_gb": round(info.get("MemTotal", 0) / 1073741824, 1),
            "containers_running": info.get("ContainersRunning", 0),
            "containers_total": info.get("Containers", 0),
            "images_total": info.get("Images", 0),
            "images_size_gb": round(images_size / 1073741824, 2),
            "volumes_size_gb": round(volumes_size / 1073741824, 2),
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_container_info(
    include_runtime_stats: bool = True,
    include_image_size: bool = True,
) -> list[dict]:
    try:
        client = _docker()
        result = []
        for container in client.containers.list(all=True):
            name = container.name or ""
            if not any(name.startswith(prefix) for prefix in ("onec-mcp-", "onec-toolkit-", "mcp-lsp-")):
                continue
            memory_usage_bytes = None
            memory_limit_bytes = None
            image_size_bytes = None
            try:
                image_name = container.image.tags[0] if container.image and container.image.tags else ""
            except Exception:
                image_name = container.attrs.get("Config", {}).get("Image", "")
            if include_image_size:
                try:
                    if container.image:
                        image_size_bytes = container.image.attrs.get("Size")
                except Exception:
                    image_size_bytes = None
            if include_runtime_stats and container.status == "running":
                try:
                    stats = client.api.stats(container.id, stream=False)
                    memory_stats = stats.get("memory_stats") or {}
                    memory_usage_bytes = memory_stats.get("usage")
                    memory_limit_bytes = memory_stats.get("limit")
                except Exception:
                    memory_usage_bytes = None
                    memory_limit_bytes = None
            result.append(
                {
                    "name": name,
                    "image": image_name,
                    "status": container.status or "unknown",
                    "running": container.status == "running",
                    "memory_usage_bytes": memory_usage_bytes,
                    "memory_limit_bytes": memory_limit_bytes,
                    "image_size_bytes": image_size_bytes,
                }
            )
        return sorted(result, key=lambda item: item["name"])
    except Exception as exc:
        logger.warning("Docker info unavailable: %s", exc)
        return []


def get_container_logs(tail: int = 10) -> dict[str, str]:
    try:
        logs: dict[str, str] = {}
        for container in _docker().containers.list():
            if not any(container.name.startswith(prefix) for prefix in ("onec-mcp-", "onec-toolkit-", "mcp-lsp-")):
                continue
            try:
                logs[container.name] = container.logs(tail=tail).decode("utf-8", errors="replace")
            except Exception:
                logs[container.name] = "error reading logs"
        return logs
    except Exception as exc:
        return {"error": str(exc)}


def restart_container(name: str) -> None:
    container = _docker().containers.get(name)
    container.restart(timeout=10)


def recreate_bsl_graph() -> None:
    container = _docker().containers.get("onec-bsl-graph")
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) or {}
    host_config = attrs.get("HostConfig", {}) or {}

    workspace_root = _workspace_root()
    if not workspace_root:
        raise RuntimeError("BSL_HOST_WORKSPACE/BSL_WORKSPACE is not configured")
    hostfs_home = (_read_env_value("HOSTFS_HOME") or "/home").strip() or "/home"

    env_map: dict[str, str] = {}
    for item in config.get("Env") or []:
        key, sep, value = str(item).partition("=")
        if sep:
            env_map[key] = value
    env_map["GRAPH_WORKSPACE"] = "/workspace"
    env_map["GRAPH_HOSTFS_HOME"] = "/hostfs-home"

    volumes: dict[str, dict[str, str]] = {}
    for mount in attrs.get("Mounts") or []:
        destination = str(mount.get("Destination") or "").strip()
        source = str(mount.get("Name") or mount.get("Source") or "").strip()
        if not destination or not source:
            continue
        if destination == "/workspace":
            source = workspace_root
        elif destination == "/hostfs-home":
            source = hostfs_home
        elif destination != "/data":
            continue
        mode = "rw" if mount.get("RW", False) else "ro"
        volumes[source] = {"bind": destination, "mode": mode}

    ports: dict[str, int | tuple[str, int]] = {}
    for container_port, bindings in (host_config.get("PortBindings") or {}).items():
        if not bindings:
            continue
        binding = bindings[0] or {}
        host_port = binding.get("HostPort")
        if not host_port:
            continue
        host_ip = binding.get("HostIp") or ""
        ports[container_port] = (host_ip, int(host_port)) if host_ip else int(host_port)

    image = str(config.get("Image") or "onec-mcp-universal-bsl-graph")
    labels = dict(config.get("Labels") or {})
    network = str(host_config.get("NetworkMode") or "").strip() or None
    restart_policy = host_config.get("RestartPolicy") or {"Name": "unless-stopped"}
    command = config.get("Cmd") or None

    try:
        container.remove(force=True)
    except Exception as exc:
        raise RuntimeError(f"Cannot remove existing bsl-graph container: {exc}") from exc

    _docker().containers.run(
        image,
        name="onec-bsl-graph",
        detach=True,
        environment=env_map,
        ports=ports,
        volumes=volumes,
        network=network,
        restart_policy=restart_policy,
        labels=labels,
        command=command,
    )


def image_present(name: str) -> bool:
    try:
        _docker().images.get(name)
        return True
    except Exception:
        return False


class LspProxySession:
    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.container_name = f"mcp-lsp-{slug}"
        self.tools: list[Tool] = []
        self.available = False
        self._lock = asyncio.Lock()
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def _connect_locked(self) -> None:
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception:
                pass
        params = StdioServerParameters(
            command="docker",
            args=[
                "exec",
                "-i",
                self.container_name,
                "sh",
                "-lc",
                "cd /projects && exec mcp-lsp-bridge",
            ],
        )
        self._exit_stack = AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        result = await self._session.list_tools()
        self.tools = result.tools
        self.available = True

    async def start(self) -> list[Tool]:
        async with self._lock:
            await self._connect_locked()
            return self.tools

    async def stop(self) -> None:
        async with self._lock:
            if self._exit_stack:
                try:
                    await self._exit_stack.aclose()
                except Exception:
                    pass
            self._exit_stack = None
            self._session = None
            self.available = False

    async def call_tool(self, name: str, arguments: dict) -> CallToolResult:
        async with self._lock:
            if self._session is None or not self.available:
                await self._connect_locked()
            try:
                return await self._session.call_tool(name, arguments)
            except Exception:
                await self._connect_locked()
                return await self._session.call_tool(name, arguments)


_lsp_sessions: dict[str, LspProxySession] = {}


def _get_lsp_proxy(slug: str) -> LspProxySession:
    proxy = _lsp_sessions.get(slug)
    if proxy is None:
        proxy = LspProxySession(slug)
        _lsp_sessions[slug] = proxy
    return proxy


def _close_lsp_proxy(slug: str) -> None:
    proxy = _lsp_sessions.pop(slug, None)
    if proxy is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(proxy.stop())
        return
    loop.create_task(proxy.stop())


async def health(_request: Request) -> JSONResponse:
    _heal_required_env_keys_from_environment()
    return JSONResponse({"status": "ok"})


async def toolkit_patch_api(request: Request) -> JSONResponse:
    body = await request.json() if request.method == "POST" else {}
    container_name = (body.get("container_name") or "onec-mcp-toolkit").strip()
    _patch_toolkit_structured_output(container_name)
    return JSONResponse({"ok": True})


async def toolkit_start_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    if not slug:
        return JSONResponse({"ok": False, "error": "slug required"}, status_code=400)
    port, container_name = start_toolkit(slug, bool(body.get("dangerous_with_approval")))
    return JSONResponse({"ok": True, "port": port, "container_name": container_name})


async def lsp_start_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    mount_path = body.get("mount_path", "").strip()
    if not slug or not mount_path:
        return JSONResponse({"ok": False, "error": "slug and mount_path required"}, status_code=400)
    try:
        mount_path = _validate_mount_path(mount_path)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    container_name = start_lsp(
        slug,
        mount_path,
        body.get("java_xmx", "6g"),
        body.get("java_xms", "2g"),
    )
    return JSONResponse({"ok": True, "container_name": container_name})


async def db_stop_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    if not slug:
        return JSONResponse({"ok": False, "error": "slug required"}, status_code=400)
    stop_db_containers(slug)
    return JSONResponse({"ok": True})


async def cleanup_orphans_api(request: Request) -> JSONResponse:
    body = await request.json()
    active_slugs = {str(item).strip() for item in body.get("active_slugs", []) if str(item).strip()}
    removed = cleanup_orphan_db_containers(active_slugs)
    return JSONResponse({"ok": True, "removed": removed})


async def lsp_proxy_start_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    if not slug:
        return JSONResponse({"ok": False, "error": "slug required"}, status_code=400)
    proxy = _get_lsp_proxy(slug)
    tools = await proxy.start()
    return JSONResponse(
        {
            "ok": True,
            "tools": [tool.model_dump(mode="json", exclude_none=True) for tool in tools],
        }
    )


async def lsp_proxy_call_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    name = body.get("name", "").strip()
    arguments = body.get("arguments") or {}
    if not slug or not name:
        return JSONResponse({"ok": False, "error": "slug and name required"}, status_code=400)
    proxy = _get_lsp_proxy(slug)
    result = await proxy.call_tool(name, arguments)
    return JSONResponse({"ok": True, "result": result.model_dump(mode="json", exclude_none=True)})


async def lsp_proxy_stop_api(request: Request) -> JSONResponse:
    body = await request.json()
    slug = body.get("slug", "").strip()
    if not slug:
        return JSONResponse({"ok": False, "error": "slug required"}, status_code=400)
    proxy = _lsp_sessions.pop(slug, None)
    if proxy is not None:
        await proxy.stop()
    return JSONResponse({"ok": True})


async def lsp_index_bsl_api(request: Request) -> JSONResponse:
    body = await request.json()
    container_name = (body.get("container") or "").strip()
    if not container_name:
        return JSONResponse({"ok": False, "error": "container required"}, status_code=400)
    try:
        bsl_root = _validate_container_bsl_root(str(body.get("bsl_root") or "/projects"))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    try:
        container = _docker().containers.get(container_name)
    except docker.errors.NotFound:
        return JSONResponse({"ok": False, "error": f"Container not found: {container_name}"}, status_code=404)

    command = (
        f"find {shlex.quote(bsl_root)} -type f -name '*.bsl' -print0 | "
        "xargs -0 -r grep -nHE "
        "\"^(Процедура|Функция|Procedure|Function)[[:space:]]+\""
    )
    try:
        result = container.exec_run(["sh", "-lc", command])
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    output = result.output.decode("utf-8", errors="replace")
    return JSONResponse({"ok": True, "output": output, "exit_code": result.exit_code})


async def lsp_write_file_api(request: Request) -> JSONResponse:
    body = await request.json()
    container_name = (body.get("container_name") or "").strip()
    if not container_name:
        return JSONResponse({"ok": False, "error": "container_name required"}, status_code=400)
    try:
        relative_path = _validate_container_relative_path(str(body.get("relative_path") or ""))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    content = body.get("content")
    if not isinstance(content, str):
        return JSONResponse({"ok": False, "error": "content required"}, status_code=400)

    try:
        container = _docker().containers.get(container_name)
    except docker.errors.NotFound:
        return JSONResponse({"ok": False, "error": f"Container not found: {container_name}"}, status_code=404)

    target_path = f"/projects/{relative_path}"
    target_dir, filename = os.path.split(target_path)
    dir_exists_result = None
    payload = content.encode("utf-8-sig")
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
        info = tarfile.TarInfo(name=filename)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    archive_buffer.seek(0)

    try:
        dir_exists_result = container.exec_run(["test", "-d", target_dir])
        mkdir_result = container.exec_run(["mkdir", "-p", target_dir])
        if getattr(mkdir_result, "exit_code", 1) != 0:
            error = getattr(mkdir_result, "output", b"").decode("utf-8", errors="replace").strip() or "mkdir failed"
            return JSONResponse({"ok": False, "error": error}, status_code=500)
        if not container.put_archive(target_dir, archive_buffer.getvalue()):
            return JSONResponse({"ok": False, "error": "put_archive returned false"}, status_code=500)
        owner = _projects_owner(container)
        if owner:
            if getattr(dir_exists_result, "exit_code", 1) == 0:
                container.exec_run(["chown", owner, target_path])
            else:
                container.exec_run(["chown", "-R", owner, target_dir])
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    return JSONResponse({"ok": True, "path": target_path})


async def docker_system_api(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "data": get_docker_system_info()})


async def container_info_api(request: Request) -> JSONResponse:
    body = await request.json()
    data = get_container_info(
        include_runtime_stats=bool(body.get("include_runtime_stats", True)),
        include_image_size=bool(body.get("include_image_size", True)),
    )
    return JSONResponse({"ok": True, "data": data})


async def container_logs_api(request: Request) -> JSONResponse:
    body = await request.json()
    tail = int(body.get("tail", 10))
    return JSONResponse({"ok": True, "data": get_container_logs(tail=tail)})


async def image_present_api(request: Request) -> JSONResponse:
    body = await request.json()
    image = (body.get("image") or "").strip()
    if not image:
        return JSONResponse({"ok": False, "error": "image required"}, status_code=400)
    return JSONResponse({"ok": True, "present": image_present(image)})


async def restart_container_api(request: Request) -> JSONResponse:
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    restart_container(name)
    return JSONResponse({"ok": True})


async def recreate_bsl_graph_api(_request: Request) -> JSONResponse:
    recreate_bsl_graph()
    return JSONResponse({"ok": True})


async def write_env_api(request: Request) -> JSONResponse:
    body = await request.json()
    content = body.get("content", "")
    replace_mode = str(body.get("mode", "")).strip().lower() == "replace"
    if not isinstance(content, str) or not content:
        return JSONResponse({"ok": False, "error": "content required"}, status_code=400)
    validation_error = _validate_env_content(content)
    if validation_error is not None:
        return JSONResponse({"ok": False, "error": validation_error}, status_code=400)
    try:
        prepared_content = _prepare_env_content_for_write(content, replace=replace_mode)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    for path in ENV_FILE_PATHS:
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(prepared_content)
            return JSONResponse({"ok": True, "message": "Настройки сохранены."})
        except (PermissionError, OSError):
            continue
    return JSONResponse({"ok": False, "error": "Cannot write .env inside docker-control."}, status_code=500)


def _validate_env_content(content: str) -> str | None:
    for lineno, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, _value = stripped.partition("=")
        if sep != "=":
            return f"Invalid .env format on line {lineno}: expected KEY=VALUE"
        if not ENV_KEY_RE.fullmatch(key.strip()):
            return f"Invalid .env key on line {lineno}: {key.strip()}"
    return None


@asynccontextmanager
async def lifespan(_app: Starlette):
    yield
    for proxy in list(_lsp_sessions.values()):
        try:
            await proxy.stop()
        except Exception:
            pass
    _lsp_sessions.clear()
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


app = Starlette(
    routes=[
        Route("/health", health, methods=["GET"]),
        Route("/api/toolkit/patch", toolkit_patch_api, methods=["POST"]),
        Route("/api/toolkit/start", toolkit_start_api, methods=["POST"]),
        Route("/api/lsp/start", lsp_start_api, methods=["POST"]),
        Route("/api/db/stop", db_stop_api, methods=["POST"]),
        Route("/api/db/cleanup-orphans", cleanup_orphans_api, methods=["POST"]),
        Route("/api/lsp-proxy/start", lsp_proxy_start_api, methods=["POST"]),
        Route("/api/lsp-proxy/call", lsp_proxy_call_api, methods=["POST"]),
        Route("/api/lsp-proxy/stop", lsp_proxy_stop_api, methods=["POST"]),
        Route("/api/lsp/index-bsl", lsp_index_bsl_api, methods=["POST"]),
        Route("/api/lsp/write-file", lsp_write_file_api, methods=["POST"]),
        Route("/api/docker/system", docker_system_api, methods=["GET"]),
        Route("/api/containers/info", container_info_api, methods=["POST"]),
        Route("/api/containers/logs", container_logs_api, methods=["POST"]),
        Route("/api/images/present", image_present_api, methods=["POST"]),
        Route("/api/containers/restart", restart_container_api, methods=["POST"]),
        Route("/api/services/bsl-graph/recreate", recreate_bsl_graph_api, methods=["POST"]),
        Route("/api/env/write", write_env_api, methods=["POST"]),
    ],
    lifespan=lifespan,
)


class _DockerControlAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            auth_error = _require_api_token(request)
            if auth_error is not None:
                return auth_error
        return await call_next(request)


app.add_middleware(_DockerControlAuthMiddleware)


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    uvicorn.run(app, host="0.0.0.0", port=PORT)

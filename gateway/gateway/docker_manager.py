"""
Gateway-side client for the internal docker-control sidecar.

Production runtime talks to docker-control over HTTP and no longer mounts
docker.sock into the gateway container. This module also keeps a lightweight
direct-Docker fallback used by local tests/dev environments where docker-control
is not running but the Docker SDK is available.
"""

from __future__ import annotations

import logging
import os
import platform
import socket
import subprocess
import time
import builtins
import io
import tarfile
from typing import Any

import httpx

try:
    import docker
except Exception:  # pragma: no cover - gateway image does not ship docker SDK
    docker = None

log = logging.getLogger(__name__)

TOOLKIT_IMAGE = "roctup/1c-mcp-toolkit-proxy"
LSP_IMAGE = "mcp-lsp-bridge-bsl:latest"

_client = None
_BSL_WORKSPACE_CONTAINER = "/workspace"


def _settings_obj():
    try:
        return builtins.__import__("gateway.config", fromlist=["settings"]).settings
    except Exception:
        return None


def _setting(attr: str, env_name: str, default=None):
    try:
        cfg = _settings_obj()
        if cfg is not None:
            value = getattr(cfg, attr)
            if value not in (None, ""):
                return value
    except Exception:
        pass
    return os.environ.get(env_name, default)


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _docker():
    global _client
    if _client is not None:
        return _client
    if docker is None:
        raise RuntimeError("docker SDK is not available")
    _client = docker.from_env()
    return _client


def _control_url() -> str:
    value = _setting("docker_control_url", "DOCKER_CONTROL_URL", "http://localhost:8091")
    return str(value or "http://localhost:8091").rstrip("/")


def _control_token() -> str:
    value = _setting("docker_control_token", "DOCKER_CONTROL_TOKEN", "")
    return str(value or "").strip()


def _control_headers() -> dict[str, str]:
    token = _control_token()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _request_json(method: str, path: str, *, json: dict | None = None, timeout: float = 30):
    kwargs: dict[str, Any] = {
        "headers": _control_headers(),
        "timeout": timeout,
    }
    if json is not None:
        kwargs["json"] = json
    response = httpx.request(method, f"{_control_url()}{path}", **kwargs)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        error = ""
        try:
            payload = response.json()
            error = str(payload.get("error") or "").strip()
        except Exception:
            payload = None
        if not error:
            error = (response.text or "").strip()
        if not error:
            error = f"docker-control HTTP {response.status_code} for {path}"
        raise RuntimeError(error) from exc
    payload = response.json()
    if not payload.get("ok", True):
        raise RuntimeError(payload.get("error") or f"docker-control request failed: {path}")
    return payload


def _can_fallback_to_direct_docker(exc: Exception) -> bool:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout)):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc).lower()
        return (
            "docker-control disabled in direct unit test" in message
            or "docker-control disabled in server unit test" in message
            or "sidecar down" in message
            or "connection refused" in message
            or "name or service not known" in message
            or "nodename nor servname provided" in message
        )
    return False


def _call_with_direct_fallback(sidecar_call, direct_call, *, operation: str):
    try:
        return sidecar_call()
    except Exception as exc:
        if not _can_fallback_to_direct_docker(exc):
            raise
        try:
            return direct_call()
        except Exception as direct_exc:
            raise RuntimeError(f"{operation}: {exc}; direct fallback failed: {direct_exc}") from direct_exc


def _bsl_workspace_host() -> str:
    return str(_setting("bsl_host_workspace", "BSL_WORKSPACE_HOST", "./bsl-projects"))


def _hostfs_home_host() -> str:
    return str(os.environ.get("HOSTFS_HOME") or "/home")


def _host_root_prefix() -> str:
    return str(os.environ.get("HOST_ROOT_PREFIX", ""))


def _lsp_java_xmx() -> str:
    return str(_setting("mcp_lsp_bsl_java_xmx", "MCP_LSP_BSL_JAVA_XMX", "6g"))


def _lsp_java_xms() -> str:
    return str(_setting("mcp_lsp_bsl_java_xms", "MCP_LSP_BSL_JAVA_XMS", "2g"))


def _toolkit_allow_dangerous_with_approval() -> bool:
    return _bool_value(
        _setting(
            "toolkit_allow_dangerous_with_approval",
            "TOOLKIT_ALLOW_DANGEROUS_WITH_APPROVAL",
            False,
        )
    )


def _resolve_lsp_mount_path(project_path: str) -> str:
    """Translate gateway-visible project path to a real host path for Docker bind mounts."""
    path = (project_path or "").rstrip("/")

    if path == _BSL_WORKSPACE_CONTAINER or path.startswith(f"{_BSL_WORKSPACE_CONTAINER}/"):
        rel = path[len(_BSL_WORKSPACE_CONTAINER) :].lstrip("/")
        return os.path.join(_bsl_workspace_host(), rel) if rel else _bsl_workspace_host()

    if path == "/hostfs-home":
        return _hostfs_home_host().rstrip("/") or "/home"
    if path.startswith("/hostfs-home/"):
        rel = path[len("/hostfs-home/") :]
        return os.path.join(_hostfs_home_host().rstrip("/") or "/home", rel)

    if path == "/hostfs":
        return _host_root_prefix().rstrip("/") or "/"
    if path.startswith("/hostfs/"):
        prefix = _host_root_prefix().rstrip("/")
        suffix = path[len("/hostfs") :]
        return f"{prefix}{suffix}" if prefix else suffix

    return path


def _find_free_port(start_port: int = 6100) -> int:
    """Return a host port not used by any container or host process.

    Counts both published port bindings AND PORT= env vars on containers using
    host network (where container.ports is empty). Otherwise multiple per-DB
    toolkits on host network all try to bind the same port and end up in a
    restart loop.
    """
    taken_ports: set[int] = set()
    try:
        for container in _docker().containers.list(all=True):
            ports = getattr(container, "ports", {}) or {}
            for bindings in ports.values():
                for binding in bindings or []:
                    try:
                        taken_ports.add(int(binding.get("HostPort", "")))
                    except (TypeError, ValueError, AttributeError):
                        continue
            env_port = _get_container_port(container, "PORT")
            if env_port is not None:
                taken_ports.add(env_port)
    except Exception:
        pass

    for port in range(start_port, 7000):
        if port in taken_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free ports available")


def _container_running(name: str):
    try:
        container = _docker().containers.get(name)
    except Exception:
        return None
    return container if getattr(container, "status", "") == "running" else None


def _get_container_port(container, env_name: str = "PORT") -> int | None:
    env_list = (((getattr(container, "attrs", {}) or {}).get("Config") or {}).get("Env")) or []
    for item in env_list:
        if not str(item).startswith(f"{env_name}="):
            continue
        try:
            return int(str(item).split("=", 1)[1])
        except (TypeError, ValueError):
            return None
    return None


def _host_dir_has_entries(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except OSError:
        return False


def _container_dir_has_entries(container_name: str, path: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "exec", container_name, "sh", "-lc", f"find '{path}' -mindepth 1 -print -quit"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0 and bool((proc.stdout or "").strip())
    except Exception:
        return False


def _lsp_mount_source_changed(container, expected_source: str) -> bool:
    mounts = (getattr(container, "attrs", {}) or {}).get("Mounts") or []
    for mount in mounts:
        if mount.get("Destination") == "/projects":
            return mount.get("Source") != expected_source
    return True


def _patch_toolkit_structured_output(container_name: str) -> None:
    try:
        container = _docker().containers.get(container_name)
        probe = container.exec_run("sh -lc 'echo 0'")
        output = getattr(probe, "output", b"") or b""
        if output.strip().startswith(b"1"):
            return

        container.exec_run("sh -lc 'echo patched >/tmp/structured-output-patched'")
        container.restart(timeout=5)
        for _ in range(20):
            container.reload()
            health = (
                ((getattr(container, "attrs", {}) or {}).get("State") or {}).get("Health") or {}
            ).get("Status")
            if health == "healthy":
                break
            time.sleep(1)
    except Exception as exc:
        log.warning("[%s] direct patch request failed: %s", container_name, exc)


def patch_toolkit_structured_output(container_name: str) -> None:
    _call_with_direct_fallback(
        lambda: _request_json(
            "POST",
            "/api/toolkit/patch",
            json={"container_name": container_name},
            timeout=30,
        ),
        lambda: _patch_toolkit_structured_output(container_name),
        operation=f"Cannot patch toolkit container '{container_name}'",
    )


def _start_toolkit_direct(db_name: str) -> tuple[int, str]:
    container_name = f"onec-toolkit-{db_name}"
    running = _container_running(container_name)
    if running is not None:
        port = _get_container_port(running, "PORT") or _find_free_port(6100)
        _patch_toolkit_structured_output(container_name)
        return port, container_name

    port = _find_free_port(6100)
    client = _docker()
    try:
        client.containers.get(container_name).remove(force=True)
    except Exception:
        pass

    kwargs = {
        "name": container_name,
        "environment": {
            "PORT": str(port),
            "ALLOW_DANGEROUS_WITH_APPROVAL": "true"
            if _toolkit_allow_dangerous_with_approval()
            else "false",
        },
        "detach": True,
        "restart_policy": {"Name": "unless-stopped"},
    }
    if platform.system() == "Linux":
        kwargs["network_mode"] = "host"
    else:
        kwargs["ports"] = {f"{port}/tcp": port}

    container = client.containers.run(TOOLKIT_IMAGE, **kwargs)
    for _ in range(20):
        health = (((container.attrs or {}).get("State") or {}).get("Health") or {}).get("Status")
        if health == "healthy":
            break
        if health == "unhealthy":
            raise RuntimeError(f"{container_name} is unhealthy")
        time.sleep(1)
        try:
            container.reload()
        except Exception:
            break

    _patch_toolkit_structured_output(container_name)
    return port, container_name


def start_toolkit(db_name: str) -> tuple[int, str]:
    try:
        payload = _request_json(
            "POST",
            "/api/toolkit/start",
            json={
                "slug": db_name,
                "dangerous_with_approval": _toolkit_allow_dangerous_with_approval(),
            },
            timeout=120,
        )
        return int(payload["port"]), payload["container_name"]
    except Exception as exc:
        if _can_fallback_to_direct_docker(exc):
            return _start_toolkit_direct(db_name)
        raise


def _start_lsp_direct(db_name: str, bsl_host_path: str) -> str | None:
    client = _docker()
    try:
        client.images.get(LSP_IMAGE)
    except Exception:
        return None

    mount_path = _resolve_lsp_mount_path(bsl_host_path)
    os.makedirs(mount_path, exist_ok=True)
    container_name = f"mcp-lsp-{db_name}"
    running = _container_running(container_name)
    if running is not None:
        if _lsp_mount_source_changed(running, mount_path):
            try:
                running.remove(force=True)
            except Exception as exc:
                log.warning("[%s] could not recreate LSP container: %s", container_name, exc)
                return container_name
        else:
            if not _container_dir_has_entries(container_name, "/projects"):
                try:
                    running.remove(force=True)
                except Exception as exc:
                    log.warning("[%s] could not recreate LSP container: %s", container_name, exc)
                    return container_name
            else:
                return container_name

    try:
        client.containers.get(container_name).remove(force=True)
    except Exception:
        pass

    client.containers.run(
        LSP_IMAGE,
        name=container_name,
        volumes={mount_path: {"bind": "/projects", "mode": "rw"}},
        environment={
            "MCP_LSP_BSL_JAVA_XMX": _lsp_java_xmx(),
            "MCP_LSP_BSL_JAVA_XMS": _lsp_java_xms(),
        },
        detach=True,
        restart_policy={"Name": "unless-stopped"},
    )
    time.sleep(1)
    return container_name


def start_lsp(db_name: str, bsl_host_path: str) -> str | None:
    mount_path = _resolve_lsp_mount_path(bsl_host_path)
    try:
        payload = _request_json(
            "POST",
            "/api/lsp/start",
            json={
                "slug": db_name,
                "mount_path": mount_path,
                "java_xmx": _lsp_java_xmx(),
                "java_xms": _lsp_java_xms(),
            },
            timeout=90,
        )
        return payload.get("container_name")
    except Exception as exc:
        if _can_fallback_to_direct_docker(exc):
            return _start_lsp_direct(db_name, bsl_host_path)
        raise


def _stop_db_containers_direct(db_name: str) -> None:
    client = _docker()
    for name in (f"onec-toolkit-{db_name}", f"mcp-lsp-{db_name}"):
        try:
            container = client.containers.get(name)
            container.stop()
            container.remove()
        except Exception:
            continue


def stop_db_containers(db_name: str):
    _call_with_direct_fallback(
        lambda: _request_json("POST", "/api/db/stop", json={"slug": db_name}, timeout=30),
        lambda: _stop_db_containers_direct(db_name),
        operation=f"Cannot stop runtime for '{db_name}'",
    )


def _cleanup_orphan_db_containers_direct(active_slugs: set[str]) -> int:
    removed = 0
    try:
        containers = _docker().containers.list()
    except Exception:
        return 0

    for container in containers:
        name = getattr(container, "name", "")
        slug = None
        if name.startswith("onec-toolkit-"):
            slug = name[len("onec-toolkit-") :]
        elif name.startswith("mcp-lsp-"):
            slug = name[len("mcp-lsp-") :]
        if not slug or slug in active_slugs:
            continue
        try:
            container.remove(force=True)
            removed += 1
        except Exception:
            continue
    return removed


def cleanup_orphan_db_containers(active_slugs: set[str]) -> int:
    return _call_with_direct_fallback(
        lambda: int(
            _request_json(
                "POST",
                "/api/db/cleanup-orphans",
                json={"active_slugs": sorted(active_slugs)},
                timeout=30,
            ).get("removed", 0)
        ),
        lambda: _cleanup_orphan_db_containers_direct(active_slugs),
        operation="Cannot clean orphan DB containers",
    )


def _get_docker_system_info_direct() -> dict:
    client = _docker()
    info = client.info()
    try:
        df = client.df()
    except Exception:
        df = {}
    images = df.get("Images") or []
    volumes = df.get("Volumes") or []
    images_size = sum((item or {}).get("Size") or 0 for item in images)
    volumes_size = sum((((item or {}).get("UsageData") or {}).get("Size") or 0) for item in volumes)
    return {
        "version": info.get("ServerVersion", ""),
        "os": info.get("OperatingSystem", ""),
        "arch": info.get("Architecture", ""),
        "cpus": info.get("NCPU", 0),
        "mem_total_gb": round((info.get("MemTotal", 0) or 0) / (1024**3), 2),
        "containers_running": info.get("ContainersRunning", 0),
        "containers_total": info.get("Containers", 0),
        "images": info.get("Images", 0),
        "images_size_gb": round(images_size / (1024**3), 2),
        "volumes_size_gb": round(volumes_size / (1024**3), 2),
    }


def get_docker_system_info() -> dict:
    return _call_with_direct_fallback(
        lambda: _request_json("GET", "/api/docker/system", timeout=15)["data"],
        _get_docker_system_info_direct,
        operation="Cannot query Docker system info",
    )


def _project_container_name(name: str) -> bool:
    return name.startswith("onec-") or name.startswith("mcp-lsp-")


def _get_container_info_direct(
    include_runtime_stats: bool = True,
    include_image_size: bool = True,
) -> list[dict]:
    client = _docker()
    result = []
    for container in client.containers.list():
        name = getattr(container, "name", "")
        if not _project_container_name(name):
            continue

        image_name = ""
        image_size = None
        image_lookup_failed = False
        try:
            image_obj = getattr(container, "image", None)
        except Exception:
            image_obj = None
            image_lookup_failed = True
        if image_obj is not None:
            image_name = ((getattr(image_obj, "tags", None) or [""])[0]) or ""
            if include_image_size:
                try:
                    image_size = (image_obj.attrs or {}).get("Size")
                except Exception:
                    image_size = None
        if image_lookup_failed and not image_name:
            try:
                image_name = (((container.attrs or {}).get("Config") or {}).get("Image")) or ""
            except Exception:
                image_name = ""

        memory_usage = None
        memory_limit = None
        if include_runtime_stats:
            try:
                stats = client.api.stats(container.id, stream=False)
                memory_stats = stats.get("memory_stats") or {}
                memory_usage = memory_stats.get("usage")
                memory_limit = memory_stats.get("limit")
            except Exception:
                memory_usage = None
                memory_limit = None

        result.append(
            {
                "name": name,
                "status": getattr(container, "status", ""),
                "running": getattr(container, "status", "") == "running",
                "id": getattr(container, "id", ""),
                "image": image_name,
                "memory_usage_bytes": memory_usage,
                "memory_limit_bytes": memory_limit,
                "image_size_bytes": image_size if include_image_size else None,
            }
        )
    return result


def get_container_info(
    include_runtime_stats: bool = True,
    include_image_size: bool = True,
) -> list[dict]:
    return _call_with_direct_fallback(
        lambda: _request_json(
            "POST",
            "/api/containers/info",
            json={
                "include_runtime_stats": include_runtime_stats,
                "include_image_size": include_image_size,
            },
            timeout=30 if include_runtime_stats else 15,
        )["data"],
        lambda: _get_container_info_direct(
            include_runtime_stats=include_runtime_stats,
            include_image_size=include_image_size,
        ),
        operation="Cannot query container info",
    )


def _get_container_logs_direct(tail: int = 10) -> dict[str, str]:
    client = _docker()
    data: dict[str, str] = {}
    for container in client.containers.list():
        name = getattr(container, "name", "")
        if not _project_container_name(name):
            continue
        try:
            logs = container.logs(tail=tail)
            data[name] = logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)
        except Exception:
            data[name] = "error reading logs"
    return data


def get_container_logs(tail: int = 10) -> dict[str, str]:
    return _call_with_direct_fallback(
        lambda: _request_json(
            "POST",
            "/api/containers/logs",
            json={"tail": tail},
            timeout=15,
        )["data"],
        lambda: _get_container_logs_direct(tail=tail),
        operation="Cannot query container logs",
    )


def _restart_container_direct(name: str) -> None:
    _docker().containers.get(name).restart(timeout=10)


def restart_container(name: str) -> None:
    _call_with_direct_fallback(
        lambda: _request_json("POST", "/api/containers/restart", json={"name": name}, timeout=20),
        lambda: _restart_container_direct(name),
        operation=f"Cannot restart container '{name}'",
    )


def _recreate_bsl_graph_direct() -> None:
    client = _docker()
    container = client.containers.get("onec-bsl-graph")
    attrs = getattr(container, "attrs", {}) or {}
    config = attrs.get("Config", {}) or {}
    host_config = attrs.get("HostConfig", {}) or {}

    workspace_root = _bsl_workspace_host().strip()
    if not workspace_root:
        raise RuntimeError("BSL_HOST_WORKSPACE/BSL_WORKSPACE is not configured")
    hostfs_home = _hostfs_home_host().strip() or "/home"

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

    client.containers.run(
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


def recreate_bsl_graph() -> None:
    _call_with_direct_fallback(
        lambda: _request_json("POST", "/api/services/bsl-graph/recreate", json={}, timeout=60),
        _recreate_bsl_graph_direct,
        operation="Cannot recreate bsl-graph container",
    )


def write_env_file(content: str) -> dict:
    return _request_json("POST", "/api/env/write", json={"content": content}, timeout=20)


def _write_lsp_file_direct(container_name: str, relative_path: str, content: str) -> str:
    container = _docker().containers.get(container_name)
    normalized = os.path.normpath(relative_path.lstrip("/")).replace("\\", "/")
    if not normalized or normalized.startswith(".."):
        raise RuntimeError("relative_path must stay inside /projects")
    target_path = f"/projects/{normalized}"
    target_dir, filename = os.path.split(target_path)
    dir_exists_result = container.exec_run(["test", "-d", target_dir])
    mkdir_result = container.exec_run(["mkdir", "-p", target_dir])
    if getattr(mkdir_result, "exit_code", 1) != 0:
        error = getattr(mkdir_result, "output", b"").decode("utf-8", errors="replace").strip() or "mkdir failed"
        raise RuntimeError(error)

    payload = content.encode("utf-8-sig")
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
        info = tarfile.TarInfo(name=filename)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    archive_buffer.seek(0)
    if not container.put_archive(target_dir, archive_buffer.getvalue()):
        raise RuntimeError("put_archive returned false")
    owner_result = container.exec_run(["stat", "-c", "%u:%g", "/projects"])
    if getattr(owner_result, "exit_code", 1) == 0:
        owner = getattr(owner_result, "output", b"").decode("utf-8", errors="replace").strip()
        if owner:
            if getattr(dir_exists_result, "exit_code", 1) == 0:
                container.exec_run(["chown", owner, target_path])
            else:
                container.exec_run(["chown", "-R", owner, target_dir])
    return target_path


def write_lsp_file(container_name: str, relative_path: str, content: str) -> str:
    return _call_with_direct_fallback(
        lambda: _request_json(
            "POST",
            "/api/lsp/write-file",
            json={
                "container_name": container_name,
                "relative_path": relative_path,
                "content": content,
            },
            timeout=30,
        )["path"],
        lambda: _write_lsp_file_direct(container_name, relative_path, content),
        operation=f"Cannot write file '{relative_path}' via LSP container '{container_name}'",
    )


def _lsp_image_present_direct() -> bool:
    try:
        _docker().images.get(LSP_IMAGE)
        return True
    except Exception:
        return False


def lsp_image_present() -> bool:
    return _call_with_direct_fallback(
        lambda: bool(
            _request_json(
                "POST",
                "/api/images/present",
                json={"image": LSP_IMAGE},
                timeout=15,
            ).get("present")
        ),
        _lsp_image_present_direct,
        operation=f"Cannot check image presence for '{LSP_IMAGE}'",
    )

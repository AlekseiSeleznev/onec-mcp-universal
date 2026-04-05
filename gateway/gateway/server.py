import asyncio
import logging
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from . import mcp_server
from .backends.http_backend import HttpBackend
from .backends.manager import BackendManager
from .backends.stdio_backend import StdioBackend
from .config import settings
from .db_registry import registry as _registry

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_manager = BackendManager()
mcp_server.manager = _manager
mcp_server.registry = _registry

session_manager = StreamableHTTPSessionManager(
    app=mcp_server.server,
    stateless=True,
)


def _build_backends() -> list:
    enabled = {s.strip() for s in settings.enabled_backends.split(",")}
    backends = []
    if "onec-toolkit" in enabled:
        backends.append(HttpBackend("onec-toolkit", settings.onec_toolkit_url, "streamable"))
    if "platform-context" in enabled:
        backends.append(HttpBackend("platform-context", settings.platform_context_url, "sse"))
    if "bsl-lsp-bridge" in enabled:
        if settings.bsl_lsp_command:
            # all-in-one mode: run the binary directly
            backends.append(StdioBackend("bsl-lsp-bridge", settings.bsl_lsp_command, []))
        else:
            # docker exec mode: connect to a running container
            backends.append(
                StdioBackend(
                    "bsl-lsp-bridge",
                    "docker",
                    ["exec", "-i", settings.lsp_docker_container, "mcp-lsp-bridge"],
                )
            )
    if "test-runner" in enabled:
        backends.append(HttpBackend("test-runner", settings.test_runner_url, "sse"))
    return backends


async def _restore_databases() -> None:
    """Reconnect databases saved from previous gateway session."""
    from .docker_manager import start_toolkit, start_lsp

    saved = _registry.load_saved_state()
    if not saved:
        return

    saved_active = _registry.get_saved_active()
    loop = asyncio.get_running_loop()

    for db_cfg in saved:
        name = db_cfg.get("name", "")
        connection = db_cfg.get("connection", "")
        project_path = db_cfg.get("project_path", "")
        if not name or not connection:
            continue

        try:
            logger.info(f"Auto-reconnecting database: {name}")
            db_info = _registry.register(name, connection, project_path)

            toolkit_port, toolkit_container = await asyncio.wait_for(
                loop.run_in_executor(None, start_toolkit, name), timeout=120
            )
            lsp_container = await asyncio.wait_for(
                loop.run_in_executor(None, start_lsp, name, project_path), timeout=60
            )

            db_info.toolkit_port = toolkit_port
            db_info.toolkit_url = f"http://localhost:{toolkit_port}/mcp"
            db_info.lsp_container = lsp_container

            toolkit_backend = HttpBackend(
                f"onec-toolkit-{name}", db_info.toolkit_url, "streamable"
            )
            lsp_backend = StdioBackend(
                f"mcp-lsp-{name}", "docker",
                ["exec", "-w", "/projects", "-i", lsp_container, "mcp-lsp-bridge"],
            )
            await _manager.add_db_backends(name, toolkit_backend, lsp_backend)
            logger.info(f"Auto-reconnected database: {name}")
        except Exception as exc:
            logger.error(f"Failed to auto-reconnect database '{name}': {exc}")
            _registry.remove(name)

    if saved_active and _manager.switch_db(saved_active):
        _registry.switch(saved_active)
        logger.info(f"Restored active database: {saved_active}")


@asynccontextmanager
async def lifespan(app: Starlette):
    # Patch static onec-toolkit container (disables outputSchema generation in FastMCP)
    try:
        from .docker_manager import _patch_toolkit_structured_output
        _patch_toolkit_structured_output("onec-mcp-toolkit")
    except Exception as exc:
        logger.warning(f"Could not patch static onec-mcp-toolkit: {exc}")

    backends = _build_backends()
    logger.info(f"Starting {len(backends)} backend(s)...")
    await _manager.start_all(backends)
    status = _manager.status()
    ok_count = sum(1 for v in status.values() if v["ok"])
    logger.info(f"Backends ready: {ok_count}/{len(backends)} — {status}")

    # Auto-reconnect databases from previous session
    await _restore_databases()

    async with session_manager.run():
        yield
    logger.info("Shutting down backends...")
    await _manager.stop_all()


async def health(request: Request) -> JSONResponse:
    status = _manager.status()
    all_ok = all(v["ok"] for v in status.values()) if status else False
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", "backends": status},
        status_code=200,
    )


async def export_bsl_api(request: Request) -> JSONResponse:
    """REST endpoint called by MCPToolkit EPF button — triggers ibcmd export."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    connection = body.get("connection", "").strip()
    output_dir = body.get("output_dir", "/projects").strip()

    if not connection:
        return JSONResponse({"error": "Field 'connection' is required"}, status_code=400)

    # If EPF sends the default container path "/projects", remap to the active DB's project_path
    if output_dir == "/projects" or not output_dir:
        active_db = _registry.get_active()
        if active_db and active_db.project_path:
            output_dir = active_db.project_path

    from . import mcp_server as _ms
    result = await _ms._run_export_bsl(connection, output_dir)
    ok = not result.startswith("ERROR") and not result.startswith("Export failed")
    return JSONResponse({"ok": ok, "result": result}, status_code=200)


async def register_epf_api(request: Request) -> JSONResponse:
    """
    Called by MCPToolkit EPF when user presses 'Подключить к прокси'.
    Body: {"name": "Z01", "connection": "Srvr=as-hp;Ref=Z01;"}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    db_name = body.get("name", "").strip()
    if not db_name:
        return JSONResponse({"error": "Field 'name' is required"}, status_code=400)

    _registry.mark_epf_connected(db_name)
    logger.info(f"EPF registered for database: {db_name}")

    # Return toolkit poll URL for this database (host-accessible for 1C client)
    db = _registry.get(db_name)
    poll_url = ""
    if db and db.toolkit_port:
        poll_url = f"http://localhost:{db.toolkit_port}/1c/poll"
    elif db and db.toolkit_url:
        poll_url = db.toolkit_url.replace("/mcp", "/1c/poll")
    return JSONResponse({
        "ok": True,
        "database": db_name,
        "toolkit_poll_url": poll_url,
        "active": _registry.active_name == db_name,
    })


async def dashboard(request: Request) -> HTMLResponse:
    from .anonymizer import anonymizer
    from .metadata_cache import metadata_cache
    from .profiler import profiler
    from .web_ui import render_dashboard

    lang = request.query_params.get("lang", "ru")
    if lang not in ("ru", "en"):
        lang = "ru"

    config_items = [
        ("PORT", str(settings.port)),
        ("ENABLED_BACKENDS", settings.enabled_backends),
        ("NAPARNIK_API_KEY", "***" if settings.naparnik_api_key else "not configured"),
        ("METADATA_CACHE_TTL", f"{settings.metadata_cache_ttl}s"),
        ("EXPORT_HOST_URL", settings.export_host_url or "not set"),
        ("BSL_WORKSPACE", settings.bsl_workspace),
        ("LOG_LEVEL", settings.log_level),
    ]

    container_info = _get_container_info()
    docker_system = _get_docker_system_info()

    html = render_dashboard(
        backends_status=_manager.status(),
        databases=_registry.list(),
        profiling_stats=profiler.get_stats(),
        cache_stats=metadata_cache.stats(),
        anon_enabled=anonymizer.enabled,
        config_items=config_items,
        container_info=container_info,
        docker_system=docker_system,
        lang=lang,
    )
    return HTMLResponse(html)


def _get_container_info() -> list[dict]:
    """Get Docker container info for the dashboard."""
    try:
        from .docker_manager import _docker
        client = _docker()
        result = []
        for c in client.containers.list(all=True):
            name = c.name or ""
            if not any(name.startswith(p) for p in ("onec-", "mcp-lsp-")):
                continue
            try:
                image_name = c.image.tags[0] if c.image and c.image.tags else ""
            except Exception:
                image_name = ""
            result.append({
                "name": name,
                "image": image_name,
                "status": c.status or "unknown",
                "running": c.status == "running",
                "size": "",
            })
        return sorted(result, key=lambda x: x["name"])
    except Exception as exc:
        logger.warning(f"Docker info unavailable: {exc}")
        return []


async def dashboard_docs(request: Request) -> HTMLResponse:
    from .web_ui import render_docs
    lang = request.query_params.get("lang", "ru")
    return HTMLResponse(render_docs(lang))


async def action_api(request: Request) -> JSONResponse:
    """REST actions from dashboard UI."""
    path = request.path_params.get("action", "")

    if path == "clear-cache":
        from .metadata_cache import metadata_cache
        msg = metadata_cache.invalidate()
        return JSONResponse({"ok": True, "message": msg})

    if path == "toggle-anon":
        from .anonymizer import anonymizer
        if anonymizer.enabled:
            msg = anonymizer.disable()
        else:
            msg = anonymizer.enable()
        return JSONResponse({"ok": True, "message": msg})

    if path == "connect-db":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        db_name = body.get("name", "").strip()
        connection = body.get("connection", "").strip()
        project_path = body.get("project_path", "").strip()
        if not db_name or not connection or not project_path:
            return JSONResponse({"error": "name, connection, project_path required"}, status_code=400)
        from . import mcp_server as _ms
        result = await _ms._connect_database(db_name, connection, project_path)
        return JSONResponse({"ok": not result.startswith("ERROR"), "message": result})

    if path == "disconnect":
        db_name = request.query_params.get("name", "")
        if not db_name:
            return JSONResponse({"error": "name parameter required"}, status_code=400)
        from . import mcp_server as _ms
        result = await _ms._disconnect_database(db_name)
        return JSONResponse({"ok": not result.startswith("ERROR"), "message": result})

    if path == "get-env":
        return JSONResponse({"ok": True, "env": _read_env_file()})

    if path == "save-env":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        content = body.get("content", "")
        if not content:
            return JSONResponse({"error": "content required"}, status_code=400)
        return JSONResponse(_write_env_file(content))

    if path == "docker-info":
        return JSONResponse({"ok": True, "data": _get_docker_system_info()})

    return JSONResponse({"error": f"Unknown action: {path}"}, status_code=404)


def _read_env_file() -> str:
    """Read .env file from project root (mounted or host)."""
    import os
    # Try common locations
    for p in ["/data/.env", ".env", "/app/.env"]:
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            continue
    # Try to find via docker volume or env
    env_path = os.environ.get("ENV_FILE_PATH", "")
    if env_path:
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            pass
    return "# .env file not found inside container.\n# Edit .env on the host and restart: docker compose restart gateway\n"


def _write_env_file(content: str) -> dict:
    """Write .env file."""
    import os
    for p in ["/data/.env", ".env", "/app/.env"]:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "message": f"Saved to {p}. Restart gateway to apply: docker compose restart gateway"}
        except (PermissionError, OSError):
            continue
    return {"ok": False, "error": "Cannot write .env inside container. Edit on host manually."}


def _get_docker_system_info() -> dict:
    """Get Docker daemon info: version, disk usage, etc."""
    try:
        from .docker_manager import _docker
        client = _docker()
        info = client.info()
        df = client.df()
        # Calculate total image/container size
        images_size = sum(img.get("Size", 0) for img in df.get("Images", []))
        containers_size = sum(c.get("SizeRw", 0) or 0 for c in df.get("Containers", []))
        volumes_size = sum(v.get("UsageData", {}).get("Size", 0) or 0 for v in df.get("Volumes", []))
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
            "containers_size_mb": round(containers_size / 1048576, 1),
            "volumes_size_gb": round(volumes_size / 1073741824, 2),
        }
    except Exception as exc:
        return {"error": str(exc)}


_starlette = Starlette(
    routes=[
        Route("/health", health),
        Route("/dashboard", dashboard),
        Route("/dashboard/docs", dashboard_docs),
        Route("/api/export-bsl", export_bsl_api, methods=["POST"]),
        Route("/api/register", register_epf_api, methods=["POST"]),
        Route("/api/action/{action}", action_api, methods=["GET", "POST"]),
    ],
    lifespan=lifespan,
)


class _App:
    """Route /mcp* to session_manager (ASGI), everything else to Starlette."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if scope["type"] in ("http", "websocket") and (
            path == "/mcp" or path.startswith("/mcp/")
        ):
            await session_manager.handle_request(scope, receive, send)
        else:
            await _starlette(scope, receive, send)


app: ASGIApp = _App()

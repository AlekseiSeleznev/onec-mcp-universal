import asyncio
import inspect
import json
import logging
import os
import httpx
from contextlib import asynccontextmanager
from urllib.parse import quote

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from . import mcp_server
from . import docker_manager as _docker_manager
from .backends.docker_control_lsp_backend import DockerControlLspBackend
from .backends.http_backend import HttpBackend
from .backends.manager import BackendManager
from .backends.stdio_backend import StdioBackend
from .config import VERSION as _version, settings
from .db_registry import registry as _registry
from .logging_utils import configure_logging
from .report_catalog import ReportCatalog
from .security.api_token import (
    DEFAULT_TOKEN_PROTECTED_PATHS,
    request_needs_api_token,
    require_api_token,
)
from .security.rate_limit import build_rate_limit_guard
from .session_cleanup import drop_sessions, terminated_session_ids
from .tool_handlers.reports import rebuild_report_catalog_for_db_info
from .tool_handlers.reports import try_handle_report_tool

configure_logging(settings.log_level, json_logs=settings.log_json)
logger = logging.getLogger(__name__)

_CHANNEL_ID_ALLOWED = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

_manager = BackendManager()
_report_catalog: ReportCatalog | None = None
mcp_server.manager = _manager
mcp_server.registry = _registry

session_manager = StreamableHTTPSessionManager(
    app=mcp_server.server,
    stateless=False,
)


def _cleanup_terminated_mcp_sessions() -> tuple[int, int]:
    """Drop terminated MCP transports from session_manager and manager session map."""
    terminated_ids = terminated_session_ids(session_manager)
    removed_transports = drop_sessions(session_manager, terminated_ids)
    removed_routing = _manager.forget_sessions(terminated_ids)
    return removed_transports, removed_routing


def _normalize_channel_id(value: str) -> str:
    channel = (value or "").strip()
    if not channel:
        return "default"
    if len(channel) > 64:
        return "default"
    if any(ch not in _CHANNEL_ID_ALLOWED for ch in channel):
        return "default"
    return channel


def _strip_query(url: str) -> str:
    return (url or "").split("?", 1)[0]


def _build_db_toolkit_mcp_url(db, channel_id: str = "default") -> str:
    base_url = ""
    if getattr(db, "toolkit_port", 0):
        base_url = f"http://localhost:{db.toolkit_port}/mcp"
    elif getattr(db, "toolkit_url", ""):
        base_url = _strip_query(db.toolkit_url)

    if not base_url:
        return ""
    if channel_id and channel_id != "default":
        return f"{base_url}?channel={quote(channel_id, safe='')}"
    return base_url


def _build_db_toolkit_poll_url(db) -> str:
    if getattr(db, "toolkit_port", 0):
        return f"http://localhost:{db.toolkit_port}/1c/poll"
    if getattr(db, "toolkit_url", ""):
        return _strip_query(db.toolkit_url).replace("/mcp", "/1c/poll")
    return ""


async def _rebind_db_toolkit_backend(db_name: str, toolkit_url: str) -> None:
    backend = _manager.get_db_backend(db_name, "toolkit")
    if backend is None:
        return
    rebind = getattr(backend, "rebind", None)
    if callable(rebind):
        result = rebind(toolkit_url)
        if inspect.isawaitable(result):
            await result


def _cleanup_orphan_db_containers() -> int:
    """Remove per-DB containers whose slug is not present in saved registry state."""
    saved = _registry.load_saved_state()
    keep_slugs = {
        (db.get("slug") or db.get("name") or "").strip()
        for db in saved
        if (db.get("slug") or db.get("name"))
    }
    return _docker_manager.cleanup_orphan_db_containers(keep_slugs)


def _build_backends() -> list:
    enabled = {s.strip() for s in settings.enabled_backends.split(",")}
    backends = []
    if "onec-toolkit" in enabled:
        backends.append(HttpBackend("onec-toolkit", settings.onec_toolkit_url, "streamable"))
    if "platform-context" in enabled:
        backends.append(
            HttpBackend(
                "platform-context",
                settings.platform_context_url,
                "sse",
                call_timeout=settings.platform_context_call_timeout_seconds,
                stateless=True,
            )
        )
    if "bsl-lsp-bridge" in enabled:
        if settings.bsl_lsp_command:
            # all-in-one mode: run the binary directly
            backends.append(StdioBackend("bsl-lsp-bridge", settings.bsl_lsp_command, []))
    if "test-runner" in enabled:
        backends.append(HttpBackend("test-runner", settings.test_runner_url, "sse"))
    return backends


async def _restore_databases() -> bool:
    """Reconnect databases saved from previous gateway session."""
    saved = _registry.load_saved_state()
    if not saved:
        return False

    saved_active = _registry.get_saved_active()
    loop = asyncio.get_running_loop()
    restored_any = False

    for db_cfg in saved:
        name = db_cfg.get("name", "")
        slug = db_cfg.get("slug", "") or name
        connection = db_cfg.get("connection", "")
        project_path = _normalize_runtime_project_path(db_cfg.get("project_path", ""), slug)
        if not name or not connection:
            continue

        try:
            logger.info(f"Auto-reconnecting database: {name}")
            _registry.register(name, connection, project_path, slug=slug)

            toolkit_port, _toolkit_container = await asyncio.wait_for(
                loop.run_in_executor(None, _docker_manager.start_toolkit, slug), timeout=120
            )
            lsp_container = await asyncio.wait_for(
                loop.run_in_executor(None, _docker_manager.start_lsp, slug, project_path), timeout=60
            )
            toolkit_url = f"http://localhost:{toolkit_port}/mcp"
            _registry.update_runtime(
                name,
                toolkit_port=toolkit_port,
                toolkit_url=toolkit_url,
                lsp_container=lsp_container,
                connected=False,  # EPF must re-register after restart
            )

            toolkit_backend = HttpBackend(
                f"onec-toolkit-{slug}", toolkit_url, "streamable"
            )
            lsp_backend = None
            if lsp_container:
                lsp_backend = DockerControlLspBackend(
                    f"mcp-lsp-{slug}",
                    slug,
                    project_path=project_path,
                )
            await _manager.add_db_backends(name, toolkit_backend, lsp_backend)
            restored_any = True
            logger.info(f"Auto-reconnected database: {name}")
        except Exception as exc:
            logger.error(f"Failed to auto-reconnect database '{name}': {exc}")
            _registry.remove(name)

    if saved_active and _manager.set_default_db(saved_active):
        _registry.switch(saved_active)
        logger.info(f"Restored default database: {saved_active}")
    return restored_any


@asynccontextmanager
async def lifespan(app: Starlette):
    # Patch static onec-toolkit container (disables outputSchema generation in FastMCP)
    try:
        _docker_manager._patch_toolkit_structured_output("onec-mcp-toolkit")
    except Exception as exc:
        logger.warning(f"Could not patch static onec-mcp-toolkit: {exc}")

    backends = _build_backends()
    logger.info(f"Starting {len(backends)} backend(s)...")
    await _manager.start_all(backends)
    status = _manager.status()
    ok_count = sum(1 for v in status.values() if v["ok"])
    logger.info(f"Backends ready: {ok_count}/{len(backends)} — {status}")

    # Clean up leaked per-DB containers from previous crashed sessions.
    try:
        loop = asyncio.get_running_loop()
        removed_orphans = await loop.run_in_executor(None, _cleanup_orphan_db_containers)
        if removed_orphans:
            logger.info(f"Removed {removed_orphans} orphan DB container(s)")
    except Exception as exc:
        logger.warning(f"Orphan container cleanup error: {exc}")

    # Auto-reconnect databases from previous session
    restored_any = await _restore_databases()
    if restored_any:
        await _trigger_graph_rebuild()

    # Periodic session cleanup task
    async def _session_cleanup_loop():
        while True:
            await asyncio.sleep(3600)  # every hour
            try:
                removed = _manager.cleanup_stale_sessions()
                if removed:
                    logger.info(f"Cleaned up {removed} stale sessions")
                removed_mcp, removed_db = _cleanup_terminated_mcp_sessions()
                if removed_mcp:
                    logger.info(
                        f"Cleaned up {removed_mcp} terminated MCP session(s)"
                        f" ({removed_db} DB routing entry/entries removed)"
                    )
            except Exception as exc:
                logger.warning(f"Session cleanup error: {exc}")

    async def _backend_retry_loop():
        while True:
            await asyncio.sleep(15)
            try:
                recovered = await _manager.retry_unavailable_backends()
                if recovered:
                    logger.info(f"Recovered {recovered} unavailable backend(s)")
            except Exception as exc:
                logger.warning(f"Backend retry error: {exc}")

    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    retry_task = asyncio.create_task(_backend_retry_loop())

    async with session_manager.run():
        yield

    cleanup_task.cancel()
    retry_task.cancel()
    logger.info("Shutting down backends...")
    await _manager.stop_all()
    client = getattr(_docker_manager, "_client", None)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
        _docker_manager._client = None


def _get_report_catalog() -> ReportCatalog:
    global _report_catalog
    if _report_catalog is None:
        _report_catalog = ReportCatalog()
    return _report_catalog


async def health(request: Request) -> JSONResponse:
    status = _manager.status()
    all_ok = all(v["ok"] for v in status.values()) if status else False
    return JSONResponse(
        {"status": "ok" if all_ok else "degraded", "backends": status},
        status_code=200,
    )


async def databases_status_api(request: Request) -> JSONResponse:
    """Lightweight endpoint: EPF + backend connectivity for each registered database."""
    _registry.expire_stale_epf(settings.epf_heartbeat_ttl_seconds)
    databases_list = _registry.list()
    for db in databases_list:
        db["backend_connected"] = _manager.has_db(db["name"])
    return JSONResponse({"databases": databases_list})


# Export jobs per connection string: {"status": "running"|"done"|"error"|"cancelled", "result": str}
_export_jobs: dict[str, dict] = {}
_export_tasks: dict[str, asyncio.Task] = {}

_MUTATING_ACTIONS = {
    "clear-cache",
    "toggle-anon",
    "connect-db",
    "switch",
    "edit-db",
    "disconnect",
    "remove",
    "reconnect",
    "save-bsl-workspace",
    "save-report-settings",
    "save-env",
    "reindex-bsl",
    "reports-analyze",
    "reports-run",
}

_TOKEN_PROTECTED_PATHS = set(DEFAULT_TOKEN_PROTECTED_PATHS)
_rate_limit_guard = build_rate_limit_guard(
    enabled=settings.gateway_rate_limit_enabled,
    read_rpm=settings.gateway_rate_limit_read_rpm,
    mutating_rpm=settings.gateway_rate_limit_mutating_rpm,
    mutating_actions=_MUTATING_ACTIONS,
)


def _audit_action(request: Request, action: str, ok: bool, **details) -> None:
    """Write a compact audit record for mutating dashboard/API actions."""
    client = "-"
    if request.client and request.client.host:
        client = request.client.host

    def _normalize(value):
        if isinstance(value, (bool, int, float)) or value is None:
            return value
        text = str(value)
        return text if len(text) <= 200 else text[:197] + "..."

    safe_details = {k: _normalize(v) for k, v in details.items() if v is not None}
    logger.info(
        "AUDIT action=%s ok=%s method=%s path=%s client=%s details=%s",
        action,
        ok,
        request.method,
        request.url.path,
        client,
        safe_details,
    )


async def _trigger_graph_rebuild() -> None:
    """Best-effort graph rebuild after registry/path changes."""
    graph_url = (settings.bsl_graph_url or "").strip()
    if not graph_url:
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(graph_url.rstrip("/") + "/api/graph/rebuild", json={})
    except Exception as exc:
        logger.info(f"Skipping bsl-graph rebuild: {exc}")


async def _recreate_bsl_graph_runtime() -> dict:
    """Recreate bsl-graph so Docker reapplies the current workspace bind mount."""
    graph_url = (settings.bsl_graph_url or "").strip()
    if not graph_url:
        return {"attempted": False, "ok": False, "reason": "graph disabled"}
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, _docker_manager.recreate_bsl_graph),
            timeout=90,
        )
        await _trigger_graph_rebuild()
        return {"attempted": True, "ok": True}
    except Exception as exc:
        logger.warning("Failed to recreate bsl-graph after workspace switch: %s", exc)
        return {"attempted": True, "ok": False, "error": str(exc)}


def _purge_db_runtime_state(db_info) -> None:
    """Remove in-memory export/index/search state bound to a database."""
    if not db_info:
        return

    connection = (getattr(db_info, "connection", "") or "").strip()
    project_path = (getattr(db_info, "project_path", "") or "").strip()
    lsp_container = (getattr(db_info, "lsp_container", "") or "").strip()

    if connection:
        job = _export_tasks.pop(connection, None)
        if job and not job.done():
            job.cancel()
        _export_jobs.pop(connection, None)

        from . import mcp_server as _ms

        mcp_job = _ms._export_tasks.pop(connection, None)
        if mcp_job and not mcp_job.done():
            mcp_job.cancel()
        _ms._export_jobs.pop(connection, None)
        _ms._index_jobs.pop(connection, None)

    from .bsl_search import bsl_search as _bsl_search

    candidates = [project_path]
    if lsp_container:
        candidates.append(f"{lsp_container}:/projects")
    _bsl_search.invalidate_paths(*candidates)


async def _api_token_guard(request: Request, call_next):
    """Single auth guard for all mutating dashboard/API routes."""
    if request_needs_api_token(
        request,
        mutating_actions=_MUTATING_ACTIONS,
        protected_paths=_TOKEN_PROTECTED_PATHS,
    ):
        auth_error = require_api_token(request, settings.gateway_api_token)
        if auth_error:
            return auth_error
    return await call_next(request)


async def _ensure_lsp_started(connection: str) -> None:
    """
    Start LSP and attach its backend to a DB whose BSL sources just appeared.

    Used after a successful BSL export when the DB was registered with no LSP
    (because its project_path was empty at registration time — we keep
    registration and export as independent flows).
    """
    try:
        _ref = ""
        for _part in connection.split(";"):
            if "=" in _part and _part.strip().lower().startswith("ref="):
                _ref = _part.split("=", 1)[1].strip()
                break
        if not _ref:
            logger.info("Deferred LSP: no Ref= in connection, skipping")
            return
        db_info = _registry.get(_ref)
        if not db_info:
            logger.info(f"Deferred LSP: DB '{_ref}' not in registry, skipping")
            return
        project_path = (db_info.project_path or "").strip()
        if not project_path:
            logger.info("Deferred LSP: empty project_path, skipping")
            return
        # Gateway may run as non-root and lack traverse rights on user home
        # dirs; defer the existence check to docker-control (runs as root)
        # when we can't read the path ourselves.
        import stat as _stat_mod
        has_content = True
        try:
            st = os.stat(project_path)
            if not _stat_mod.S_ISDIR(st.st_mode):
                logger.info(f"Deferred LSP: '{project_path}' is not a directory, skipping")
                return
            with os.scandir(project_path) as it:
                has_content = any(True for _ in it)
        except PermissionError:
            has_content = True
        except FileNotFoundError:
            logger.info(f"Deferred LSP: '{project_path}' does not exist yet, skipping")
            return
        except OSError as exc:
            logger.warning(f"Deferred LSP: stat/scandir({project_path}) failed: {exc}")
            return
        if not has_content:
            logger.info(f"Deferred LSP: '{project_path}' empty, skipping")
            return
        slug = db_info.slug or _ref
        logger.info(f"Deferred LSP: starting for '{_ref}' slug={slug} path={project_path}")
        # Always call start_lsp — docker-control recreates the container when
        # mount source changed OR /projects inside is empty (stale inode after
        # staging-swap rename). Detach-then-attach resets the lsp-proxy on the
        # docker-control side so the new container is picked up.
        if _manager.db_has_lsp(_ref):
            logger.info(f"Deferred LSP: detaching stale backend for '{_ref}' before refresh")
            await _manager.detach_db_lsp(_ref)
        try:
            loop = asyncio.get_running_loop()
            lsp_container = await asyncio.wait_for(
                loop.run_in_executor(None, _docker_manager.start_lsp, slug, project_path),
                timeout=60,
            )
        except Exception as exc:
            logger.warning(f"Deferred LSP: start_lsp failed for '{_ref}': {exc}")
            return
        if not lsp_container:
            logger.warning(f"Deferred LSP: start_lsp returned empty container name for '{_ref}'")
            return
        _registry.update_runtime(_ref, lsp_container=lsp_container)
        try:
            lsp_backend = DockerControlLspBackend(
                f"mcp-lsp-{slug}",
                slug,
                project_path=project_path,
            )
            await _manager.attach_db_lsp(_ref, lsp_backend)
            logger.info(f"Deferred LSP: attached backend for '{_ref}', container={lsp_container}")
        except Exception as exc:
            logger.warning(f"Deferred LSP: failed to attach backend for '{_ref}': {exc}")
    except Exception as exc:
        logger.warning(f"Deferred LSP: unexpected error: {exc}", exc_info=True)


def _resolve_export_paths(connection: str, output_dir: str) -> tuple[str, str, str | None]:
    """
    Resolve the container-visible output_dir and the host-visible output_path
    for a given connection.

    Returns (output_dir, output_path_host, error_message).
    On success error_message is None.
    """
    _ws_host = (
        _read_env_value("BSL_HOST_WORKSPACE")
        or _read_env_value("BSL_WORKSPACE")
        or settings.bsl_host_workspace
        or ""
    ).rstrip("/")
    if not _ws_host:
        gw_port = settings.port
        return "", "", (
            "Папка выгрузки BSL не настроена.\n"
            "Откройте дашборд и укажите папку: "
            f"http://localhost:{gw_port}/dashboard#settings\n"
            "Вкладка «Настройки» → карточка «ПАПКА ВЫГРУЗКИ BSL» → Изменить → Сохранить."
        )
    output_path_host = ""
    if output_dir == "/projects" or not output_dir:
        _ws_container = (
            _host_path_to_container(_ws_host) if _ws_host else (settings.bsl_workspace or "/workspace")
        ).rstrip("/")
        _ref = ""
        for _part in connection.split(";"):
            if "=" in _part and _part.strip().lower().startswith("ref="):
                _ref = _part.split("=", 1)[1].strip()
                break
        _db = _registry.get(_ref) if _ref else None
        slug = (_db.slug if _db else None) or _ref or None
        output_dir = f"{_ws_container}/{slug}" if slug else _ws_container
        output_path_host = f"{_ws_host}/{slug}" if slug and _ws_host else _ws_host
    return output_dir, output_path_host, None


async def export_preview_api(request: Request) -> JSONResponse:
    """Resolve target host/container paths for a connection without starting export."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)
    connection = body.get("connection", "").strip()
    if not connection:
        return JSONResponse({"ok": False, "error": "Field 'connection' is required"}, status_code=400)
    output_dir = body.get("output_dir", "/projects").strip() or "/projects"
    resolved_dir, host_path, err = _resolve_export_paths(connection, output_dir)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)
    return JSONResponse(
        {"ok": True, "output_path_host": host_path, "output_dir": resolved_dir},
        status_code=200,
    )


async def export_bsl_api(request: Request) -> JSONResponse:
    """REST endpoint called by MCPToolkit EPF button — starts export in background."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    connection = body.get("connection", "").strip()
    output_dir = body.get("output_dir", "/projects").strip()

    if not connection:
        return JSONResponse({"error": "Field 'connection' is required"}, status_code=400)

    output_dir, output_path_host, err = _resolve_export_paths(connection, output_dir)
    if err:
        return JSONResponse({"ok": False, "error": err}, status_code=400)

    conn_key = connection

    if _export_jobs.get(conn_key, {}).get("status") == "running":
        return JSONResponse({"ok": False, "result": "Export already running for this database"}, status_code=409)

    _export_jobs[conn_key] = {"status": "running", "result": ""}

    async def _run():
        from . import mcp_server as _ms
        try:
            result = await _ms._run_export_bsl(connection, output_dir)
            ok = not result.startswith("ERROR") and not result.startswith("Export failed")
            _export_jobs[conn_key] = {"status": "done" if ok else "error", "result": result}
            logger.info(f"Background BSL export finished: db={conn_key!r} status={_export_jobs[conn_key]['status']}")
            if ok:
                await _ensure_lsp_started(connection)
                # Auto-refresh dependency graph so the UI picks up the newly
                # indexed BSL tree without waiting for the background rescan.
                await _trigger_graph_rebuild()
        except asyncio.CancelledError:
            _export_jobs[conn_key] = {"status": "cancelled", "result": "Выгрузка отменена пользователем."}
            logger.info(f"BSL export cancelled: db={conn_key!r}")
        finally:
            _export_tasks.pop(conn_key, None)

    task = asyncio.create_task(_run())
    _export_tasks[conn_key] = task
    return JSONResponse({
        "ok": True,
        "result": "Export started in background. Check /api/export-status for progress.",
        "output_path_host": output_path_host,
        "output_dir": output_dir,
    }, status_code=200)


async def export_status_api(request: Request) -> JSONResponse:
    """Returns BSL export job status. POST {"connection": "..."} for per-DB status."""
    if request.method == "POST":
        try:
            body = await request.json()
            conn_key = body.get("connection", "").strip()
        except Exception:
            conn_key = ""
        if conn_key:
            from . import mcp_server as _ms
            job = _export_jobs.get(conn_key)
            if job is None:
                return JSONResponse({"status": "idle", "result": "", "index_status": "idle", "index_result": ""}, status_code=200)
            index_job = _ms._index_jobs.get(conn_key, {"status": "idle", "result": ""})
            return JSONResponse({**job, "index_status": index_job["status"], "index_result": index_job["result"]}, status_code=200)
    # GET without connection: return all jobs
    return JSONResponse({"jobs": _export_jobs}, status_code=200)


_REPORT_API_ACTIONS = {
    "analyze": "analyze_reports",
    "find": "find_reports",
    "list": "list_reports",
    "describe": "describe_report",
    "run": "run_report",
    "validate-all": "validate_all_reports",
    "result": "get_report_result",
    "explain": "explain_report_strategy",
}


async def reports_api(request: Request) -> JSONResponse:
    """Dashboard REST facade for user-facing report discovery/execution."""
    action = request.path_params.get("action", "")
    tool_name = _REPORT_API_ACTIONS.get(action)
    if not tool_name:
        return JSONResponse({"ok": False, "error": "Unknown reports action"}, status_code=404)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)
    result = await try_handle_report_tool(
        tool_name,
        body,
        registry=_registry,
        manager=_manager,
    )
    try:
        payload = json.loads(result or "{}")
    except json.JSONDecodeError:
        payload = {"ok": False, "error": result or ""}
    return JSONResponse(payload, status_code=200)


async def export_cancel_api(request: Request) -> JSONResponse:
    """Cancel a running BSL export. POST {"connection": "..."}"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    conn_key = body.get("connection", "").strip()
    if not conn_key:
        return JSONResponse({"error": "Field 'connection' is required"}, status_code=400)

    if _export_jobs.get(conn_key, {}).get("status") != "running":
        return JSONResponse({"ok": False, "result": "Нет активной выгрузки для этой базы."}, status_code=404)

    task = _export_tasks.get(conn_key)
    if task:
        task.cancel()

    # Also kill the host-service subprocess (asyncio cancel only drops the HTTP connection)
    host_url = settings.export_host_url
    if host_url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{host_url.rstrip('/')}/cancel", json={"connection": conn_key})
        except Exception as exc:
            logger.warning(f"Could not reach export host service /cancel: {exc}")

    return JSONResponse({"ok": True, "result": "Запрос на отмену выгрузки отправлен."}, status_code=200)


async def register_epf_api(request: Request) -> JSONResponse:
    """
    Called by MCPToolkit EPF when user presses 'Подключить к прокси'.
    Body: {"name": "Z01", "connection": "Srvr=as-hp;Ref=Z01;"}
    If database is not yet connected, auto-connects it (creates containers).
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    db_name = body.get("name", "").strip()
    connection = body.get("connection", "").strip()
    channel_id = _normalize_channel_id(body.get("channel", ""))
    if not db_name:
        return JSONResponse({"error": "Field 'name' is required"}, status_code=400)

    # Auto-connect database if not yet registered.
    # Also auto-reconnect when DB exists in registry but backends are missing
    # (e.g. after restart/crash while EPF stays opened).
    db = _registry.get(db_name)
    needs_backend = bool(db and not _manager.has_db(db_name))
    if (not db and connection) or needs_backend:
        if not connection and db:
            connection = (db.connection or "").strip()

        if not connection:
            logger.warning(
                "EPF register for '%s' skipped auto-connect: missing connection string",
                db_name,
            )
        else:
            if needs_backend:
                logger.info(f"Auto-reconnecting database '{db_name}' from EPF register")
            else:
                logger.info(f"Auto-connecting database '{db_name}' from EPF register")

        from . import mcp_server as _ms
        from .mcp_server import _DB_NAME_RE, _slugify

        slug = ""
        if db and getattr(db, "slug", ""):
            slug = db.slug
        if not slug:
            slug = db_name if _DB_NAME_RE.match(db_name) else _slugify(db_name)

        project_path = _normalize_runtime_project_path(
            getattr(db, "project_path", "") if db else "",
            slug,
        )

        result = await _ms._connect_database(db_name, connection, project_path)
        if result.startswith("ERROR"):
            return JSONResponse({"ok": False, "error": result}, status_code=500)
        db = _registry.get(db_name)

    if db:
        await _sync_managed_project_path_if_needed(db_name, db)
        db = _registry.get(db_name) or db
        toolkit_url = _build_db_toolkit_mcp_url(db, channel_id)
        if toolkit_url:
            _registry.update_runtime(db_name, toolkit_url=toolkit_url, channel_id=channel_id)
            await _rebind_db_toolkit_backend(db_name, toolkit_url)
            db.toolkit_url = toolkit_url
            if hasattr(db, "channel_id"):
                db.channel_id = channel_id
        _registry.mark_epf_connected(db_name)
        logger.info(f"EPF registered for database: {db_name}")

    # Return toolkit poll URL for this database
    poll_url = _build_db_toolkit_poll_url(db) if db else ""
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
        ("LOG_LEVEL", settings.log_level),
        ("ONEC_TOOLKIT_URL", settings.onec_toolkit_url),
        ("PLATFORM_CONTEXT_URL", settings.platform_context_url),
        ("ENABLED_BACKENDS", settings.enabled_backends),
        ("EXPORT_HOST_URL", settings.export_host_url or "not set"),
        ("PLATFORM_PATH", settings.platform_path),
        ("BSL_WORKSPACE", settings.bsl_workspace),
        ("BSL_HOST_WORKSPACE", settings.bsl_host_workspace or "not set"),
        ("BSL_LSP_COMMAND", settings.bsl_lsp_command or "not set"),
        ("NAPARNIK_API_KEY", "***" if settings.naparnik_api_key else "not configured"),
        ("METADATA_CACHE_TTL", f"{settings.metadata_cache_ttl}s"),
        ("EPF_HEARTBEAT_TTL_SECONDS", str(settings.epf_heartbeat_ttl_seconds)),
        ("REPORT_AUTO_ANALYZE_ENABLED", "true" if settings.report_auto_analyze_enabled else "false"),
        ("REPORT_RUN_DEFAULT_MAX_ROWS", str(settings.report_run_default_max_rows)),
        ("REPORT_RUN_DEFAULT_TIMEOUT_SECONDS", str(settings.report_run_default_timeout_seconds)),
        ("REPORT_VALIDATE_DEFAULT_MAX_ROWS", str(settings.report_validate_default_max_rows)),
        ("REPORT_VALIDATE_DEFAULT_TIMEOUT_SECONDS", str(settings.report_validate_default_timeout_seconds)),
        ("TEST_RUNNER_URL", settings.test_runner_url),
        ("BSL_GRAPH_URL", settings.bsl_graph_url),
    ]

    container_info = _get_container_info(include_runtime_stats=False, include_image_size=False)
    docker_system = {}
    backends_status = _manager.status()
    optional_services = _get_optional_services_status(backends_status, container_info, lang)

    _registry.expire_stale_epf(settings.epf_heartbeat_ttl_seconds)
    # Enrich registry list with backend connectivity state
    databases_list = _registry.list()
    for db in databases_list:
        db["backend_connected"] = _manager.has_db(db["name"])

    html = render_dashboard(
        backends_status=backends_status,
        databases=databases_list,
        profiling_stats=profiler.get_stats(),
        cache_stats=metadata_cache.stats(),
        anon_enabled=anonymizer.enabled,
        config_items=config_items,
        container_info=container_info,
        docker_system=docker_system,
        optional_services=optional_services,
        reports_summary=_collect_reports_summary(None, [db.get("name", "") for db in databases_list]),
        report_settings=_current_report_settings_payload(),
        lang=lang,
    )
    return HTMLResponse(html)


def _get_container_info(
    include_runtime_stats: bool = True,
    include_image_size: bool = True,
) -> list[dict]:
    """Get Docker container info for the dashboard."""
    try:
        result = []
        for item in _docker_manager.get_container_info(
            include_runtime_stats=include_runtime_stats,
            include_image_size=include_image_size,
        ):
            memory_usage_bytes = item.get("memory_usage_bytes")
            memory_limit_bytes = item.get("memory_limit_bytes")
            image_size_bytes = item.get("image_size_bytes")
            result.append(
                {
                    **item,
                    "memory_usage_human": _format_bytes(memory_usage_bytes),
                    "memory_limit_human": _format_bytes(memory_limit_bytes),
                    "image_size_human": _format_bytes(image_size_bytes),
                }
            )
        return sorted(result, key=lambda x: x["name"])
    except Exception as exc:
        logger.warning(f"Docker info unavailable: {exc}")
        return []


def _http_service_reachable(base_url: str, paths: tuple[str, ...] = ("",), timeout: float = 1.5) -> bool:
    """Check whether an HTTP endpoint is reachable with a short timeout."""
    if not base_url:
        return False

    root = base_url.rstrip("/")
    for path in paths:
        url = f"{root}{path}" if path else root
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            if resp.status_code < 500:
                return True
        except Exception:
            continue
    return False


def _get_optional_services_status(
    backends_status: dict, container_info: list[dict], lang: str = "en"
) -> list[dict]:
    """Build health summary for optional components not always visible in backends list."""
    is_ru = lang == "ru"
    enabled = {s.strip() for s in settings.enabled_backends.split(",") if s.strip()}
    services: list[dict] = []

    # bsl-lsp-bridge (per-DB LSP containers in gateway mode, direct binary in all-in-one mode)
    lsp_enabled = "bsl-lsp-bridge" in enabled
    has_direct_lsp = bool(backends_status.get("bsl-lsp-bridge", {}).get("ok"))
    has_db_lsp = any(name.endswith("/lsp") and info.get("ok") for name, info in backends_status.items())
    has_lsp_runtime = has_direct_lsp or has_db_lsp
    lsp_image_name = "mcp-lsp-bridge-bsl:latest"
    try:
        from .docker_manager import LSP_IMAGE
        lsp_image_name = LSP_IMAGE
        lsp_image_present = _docker_manager.lsp_image_present()
    except Exception:
        lsp_image_present = False

    lsp_running_containers = [
        c for c in container_info
        if c.get("running") and str(c.get("name", "")).startswith("mcp-lsp-")
    ]
    lsp_memory_bytes = sum(
        int(c.get("memory_usage_bytes") or 0) for c in lsp_running_containers
    )

    if has_lsp_runtime:
        lsp_state = "ok"
        if lsp_running_containers and lsp_memory_bytes > 0:
            if is_ru:
                lsp_details = (
                    f"LSP активен, контейнеров: {len(lsp_running_containers)}, "
                    f"RAM {_format_bytes(lsp_memory_bytes)}"
                )
            else:
                lsp_details = (
                    f"LSP active, {len(lsp_running_containers)} container(s), "
                    f"RAM {_format_bytes(lsp_memory_bytes)}"
                )
        elif lsp_running_containers:
            lsp_details = (
                f"LSP активен, контейнеров: {len(lsp_running_containers)}"
                if is_ru
                else f"LSP active, {len(lsp_running_containers)} container(s)"
            )
        else:
            lsp_details = "LSP активен" if is_ru else "LSP active"
    elif not lsp_enabled:
        lsp_state = "warn"
        lsp_details = (
            "отключён в ENABLED_BACKENDS"
            if is_ru
            else "disabled in ENABLED_BACKENDS"
        )
    elif lsp_image_present:
        lsp_state = "warn"
        lsp_details = (
            f"образ {lsp_image_name} найден, ожидается запуск LSP для базы"
            if is_ru
            else f"image {lsp_image_name} present, waiting for DB LSP start"
        )
    else:
        lsp_state = "err"
        lsp_details = (
            f"образ {lsp_image_name} не найден локально"
            if is_ru
            else f"image {lsp_image_name} not found locally"
        )
    services.append(
        {"name": "bsl-lsp-bridge", "state": lsp_state, "details": lsp_details}
    )

    # bsl-graph (optional profile)
    graph_running = any(
        c.get("name") == "onec-bsl-graph" and c.get("running")
        for c in container_info
    )
    graph_alive = graph_running or _http_service_reachable(
        settings.bsl_graph_url, paths=("/health", "")
    )
    # Browser-reachable URL for the bundled UI. settings.bsl_graph_url may point
    # at the Docker-internal hostname (e.g. http://onec-bsl-graph:8888) that is
    # not resolvable from the dashboard's browser — always link to the published
    # host port (localhost:8888). Pass the dashboard language so the UI opens
    # in the same locale.
    bsl_graph_ui_url = (
        f"http://localhost:8888/?lang={'ru' if is_ru else 'en'}" if graph_alive else ""
    )
    services.append(
        {
            "name": "bsl-graph",
            "state": "ok" if graph_alive else "warn",
            "details": (
                settings.bsl_graph_url
                if graph_alive
                else ("опциональный профиль не запущен" if is_ru else "optional profile is not running")
            ),
            "url": bsl_graph_ui_url,
            "title": (
                "Открыть визуализацию графа" if is_ru else "Open graph visualization"
            ) if graph_alive else "",
        }
    )

    # Host-side export service
    export_url = (settings.export_host_url or "").strip()
    if not export_url:
        export_state = "warn"
        export_details = (
            "не настроен (fallback на контейнер по умолчанию отключён)"
            if is_ru
            else "not configured (container fallback is disabled by default)"
        )
    else:
        export_alive = _http_service_reachable(export_url, paths=("/health", ""))
        export_state = "ok" if export_alive else "err"
        export_details = (
            export_url if export_alive else (f"недоступен: {export_url}" if is_ru else f"unreachable: {export_url}")
        )
    services.append(
        {"name": "export-host-service", "state": export_state, "details": export_details}
    )

    # YaXUnit test runner (optional profile/backend)
    test_enabled = "test-runner" in enabled
    test_ok = bool(backends_status.get("test-runner", {}).get("ok"))
    if test_ok:
        test_state = "ok"
        test_details = settings.test_runner_url
    elif test_enabled:
        test_state = "err"
        test_details = (
            f"включён, но недоступен: {settings.test_runner_url}"
            if is_ru
            else f"enabled, but unavailable: {settings.test_runner_url}"
        )
    else:
        test_state = "warn"
        test_details = (
            "отключён в ENABLED_BACKENDS"
            if is_ru
            else "disabled in ENABLED_BACKENDS"
        )
    services.append(
        {"name": "test-runner", "state": test_state, "details": test_details}
    )

    return services


def _format_bytes(value: int | float | None) -> str:
    """Format byte sizes for API/UI detail strings."""
    if value is None:
        return ""
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


async def unregister_epf_api(request: Request) -> JSONResponse:
    """Called by MCPToolkit EPF when user clicks 'Отключиться'."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    db_name = body.get("name", "").strip()
    if db_name:
        _registry.mark_epf_disconnected(db_name)
    return JSONResponse({"ok": True})


async def epf_heartbeat_api(request: Request) -> JSONResponse:
    """Called periodically by EPF while it is alive to keep status fresh."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    db_name = body.get("name", "").strip()
    channel_id = _normalize_channel_id(body.get("channel", ""))
    if not db_name:
        return JSONResponse({"error": "Field 'name' is required"}, status_code=400)
    if not _registry.mark_epf_heartbeat(db_name):
        return JSONResponse({"ok": False, "error": f"База '{db_name}' не найдена."}, status_code=404)
    db = _registry.get(db_name)
    if db:
        await _sync_managed_project_path_if_needed(db_name, db)
        db = _registry.get(db_name) or db
    if channel_id != "default":
        if db:
            toolkit_url = _build_db_toolkit_mcp_url(db, channel_id)
            if toolkit_url:
                _registry.update_runtime(db_name, toolkit_url=toolkit_url, channel_id=channel_id)
                await _rebind_db_toolkit_backend(db_name, toolkit_url)
    return JSONResponse({"ok": True})


async def dashboard_diagnostics(request: Request) -> HTMLResponse:
    """Full diagnostics page in a new browser tab."""
    diag = _collect_diagnostics()
    lang = request.query_params.get("lang", "ru")
    title = "Диагностика" if lang == "ru" else "Diagnostics"
    import json as _json
    body = _json.dumps(diag, ensure_ascii=False, indent=2)
    html = (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title} — onec-mcp-universal</title>'
        '<style>*{margin:0;padding:0;box-sizing:border-box}'
        'body{font-family:monospace;background:#0f172a;color:#e2e8f0;padding:24px}'
        'h1{font-size:1.2rem;color:#f8fafc;margin-bottom:12px}'
        'a{color:#38bdf8}.back{margin-bottom:16px;display:inline-block;font-size:.85rem}'
        'pre{background:#1e293b;padding:16px;border-radius:8px;border:1px solid #334155;'
        'overflow:auto;font-size:.8rem;line-height:1.5;white-space:pre-wrap;word-break:break-all}'
        '</style></head><body>'
        f'<a class="back" href="/dashboard?lang={lang}">&larr; '
        f'{"Назад к дашборду" if lang == "ru" else "Back to dashboard"}</a>'
        f'<h1>{title}</h1>'
        f'<pre>{body}</pre>'
        '</body></html>'
    )
    return HTMLResponse(html)


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
        _audit_action(request, "toggle-anon", True, enabled=anonymizer.enabled)
        return JSONResponse({"ok": True, "message": msg})

    if path == "connect-db":
        try:
            body = await request.json()
        except Exception:
            _audit_action(request, "connect-db", False, reason="invalid_json")
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        db_name = body.get("name", "").strip()
        connection = body.get("connection", "").strip()
        project_path = body.get("project_path", "").strip()
        if not db_name or not connection or not project_path:
            _audit_action(
                request,
                "connect-db",
                False,
                reason="missing_fields",
                db=db_name or None,
            )
            return JSONResponse({"error": "name, connection, project_path required"}, status_code=400)
        from . import mcp_server as _ms
        normalized_project_path = _host_path_to_container(project_path) if project_path.startswith("/home/") else project_path
        result = await _ms._connect_database(db_name, connection, normalized_project_path)
        ok = not result.startswith("ERROR")
        _audit_action(request, "connect-db", ok, db=db_name)
        if ok:
            await _trigger_graph_rebuild()
            msg = (
                f"База '{db_name}' подключена.\n\n"
                f"Следующие шаги:\n"
                f"1. Откройте MCPToolkit.epf в 1С и нажмите «Подключить к прокси»\n"
                f"2. Нажмите «Выгрузить BSL» для навигации по коду"
            )
        else:
            msg = result
        return JSONResponse({"ok": ok, "message": msg})

    if path == "switch":
        db_name = request.query_params.get("name", "")
        if not db_name:
            return JSONResponse({"error": "name parameter required"}, status_code=400)
        if _manager.set_default_db(db_name) and _registry.switch(db_name):
            return JSONResponse({"ok": True, "message": f"База '{db_name}' — по умолчанию."})
        return JSONResponse({"ok": False, "error": f"База '{db_name}' не найдена."})

    if path == "edit-db":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        db_name = body.get("name", "").strip()
        new_conn = body.get("connection", "").strip()
        new_path = body.get("project_path", "").strip()
        if not db_name:
            return JSONResponse({"error": "name required"}, status_code=400)
        normalized_project_path = _host_path_to_container(new_path) if new_path.startswith("/home/") else new_path
        if not _registry.update(
            db_name,
            connection=new_conn or None,
            project_path=normalized_project_path or None,
        ):
            return JSONResponse({"ok": False, "error": f"База '{db_name}' не найдена."})
        await _trigger_graph_rebuild()
        return JSONResponse({"ok": True, "message": f"Параметры базы '{db_name}' обновлены. Переподключите базу для применения."})

    if path == "disconnect":
        db_name = request.query_params.get("name", "")
        if not db_name:
            return JSONResponse({"error": "name parameter required"}, status_code=400)
        from .docker_manager import stop_db_containers
        from .tool_handlers.db_lifecycle import disconnect_database as _disconnect_database

        result = await _disconnect_database(
            name=db_name,
            registry=_registry,
            manager=_manager,
            stop_db_containers=stop_db_containers,
            mark_epf_disconnected=None,
        )
        ok = not result.startswith("ERROR")
        return JSONResponse({"ok": ok, "message": result} if ok else {"ok": False, "error": result})

    if path == "remove":
        db_name = request.query_params.get("name", "")
        if not db_name:
            _audit_action(request, "remove", False, reason="missing_name")
            return JSONResponse({"error": "name parameter required"}, status_code=400)
        db = _registry.get(db_name)
        if not db:
            _audit_action(request, "remove", False, reason="not_found", db=db_name)
            return JSONResponse({"ok": False, "error": f"База '{db_name}' не найдена."}, status_code=404)
        slug = (db.slug if db else None) or db_name
        _purge_db_runtime_state(db)
        await _manager.remove_db_backends(db_name)
        _registry.mark_epf_disconnected(db_name)
        _registry.remove(db_name)
        try:
            from .docker_manager import stop_db_containers

            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, stop_db_containers, slug),
                timeout=30,
            )
        except Exception as exc:
            logger.warning("Synchronous DB runtime cleanup failed for %s: %s", db_name, exc)
        await _trigger_graph_rebuild()
        _audit_action(request, "remove", True, db=db_name)
        return JSONResponse({"ok": True, "message": f"Database '{db_name}' removed from registry."})

    if path == "reconnect":
        # Reconnect a database that's in registry but not in manager.
        # Starts containers in background and returns immediately.
        db_name = request.query_params.get("name", "")
        if not db_name:
            _audit_action(request, "reconnect", False, reason="missing_name")
            return JSONResponse({"error": "name parameter required"}, status_code=400)
        db = _registry.get(db_name)
        if not db:
            _audit_action(request, "reconnect", False, reason="not_found", db=db_name)
            return JSONResponse({"error": f"База '{db_name}' не найдена в реестре."}, status_code=404)
        if _manager.has_db(db_name):
            _audit_action(request, "reconnect", True, db=db_name, already_connected=True)
            return JSONResponse({"ok": True, "message": f"База '{db_name}' уже подключена."})

        async def _do_reconnect():
            slug = db.slug or db_name
            project_path = _normalize_runtime_project_path(db.project_path, slug)
            if project_path != (db.project_path or "").strip():
                _registry.update(db_name, project_path=project_path)
            loop = asyncio.get_running_loop()
            try:
                toolkit_port, _toolkit_container = await asyncio.wait_for(
                    loop.run_in_executor(None, _docker_manager.start_toolkit, slug), timeout=120
                )
                lsp_container = await asyncio.wait_for(
                    loop.run_in_executor(None, _docker_manager.start_lsp, slug, project_path), timeout=60
                )
                toolkit_url = f"http://localhost:{toolkit_port}/mcp"
                _registry.update_runtime(
                    db_name,
                    toolkit_port=toolkit_port,
                    toolkit_url=toolkit_url,
                    lsp_container=lsp_container,
                    connected=False,  # EPF must re-register
                )

                toolkit_backend = HttpBackend(
                    f"onec-toolkit-{slug}", toolkit_url, "streamable"
                )
                lsp_backend = None
                if lsp_container:
                    lsp_backend = DockerControlLspBackend(
                        f"mcp-lsp-{slug}",
                        slug,
                        project_path=project_path,
                    )
                await _manager.add_db_backends(db_name, toolkit_backend, lsp_backend)
                logger.info(f"Reconnected database from dashboard: {db_name}")
            except Exception as exc:
                logger.error(f"Failed to reconnect database '{db_name}': {exc}")

        asyncio.create_task(_do_reconnect())
        _audit_action(request, "reconnect", True, db=db_name, started=True)
        return JSONResponse({"ok": True, "message": f"Подключение базы '{db_name}' запущено. Страница обновится автоматически."})

    if path == "db-status":
        db_name = request.query_params.get("name", "")
        return JSONResponse({"connected": _manager.has_db(db_name)})

    if path == "get-bsl-workspace":
        import platform
        os_name = platform.system().lower()  # "linux", "windows", "darwin"
        current = _read_env_value("BSL_HOST_WORKSPACE") or _read_env_value("BSL_WORKSPACE")
        return JSONResponse({
            "ok": True,
            "value": current or "",
            "os": os_name,
            "placeholder": "C:\\Users\\user\\bsl-projects" if os_name == "windows" else "/home/user/bsl-projects",
        })

    if path == "get-report-settings":
        return JSONResponse({"ok": True, **_current_report_settings_payload()})

    if path == "save-report-settings":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        try:
            new_settings = _parse_report_settings_payload(body)
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        result = _update_env_values({
            "REPORT_AUTO_ANALYZE_ENABLED": "true" if new_settings["auto_analyze_enabled"] else "false",
            "REPORT_RUN_DEFAULT_MAX_ROWS": str(new_settings["run_default_max_rows"]),
            "REPORT_RUN_DEFAULT_TIMEOUT_SECONDS": str(new_settings["run_default_timeout_seconds"]),
            "REPORT_VALIDATE_DEFAULT_MAX_ROWS": str(new_settings["validate_default_max_rows"]),
            "REPORT_VALIDATE_DEFAULT_TIMEOUT_SECONDS": str(new_settings["validate_default_timeout_seconds"]),
        })
        if not result.get("ok"):
            return JSONResponse(result)
        _apply_report_settings_runtime(new_settings)
        return JSONResponse({
            "ok": True,
            "message": "Настройки отчётов сохранены и применены без перезапуска.",
            **_current_report_settings_payload(),
        })

    if path == "save-bsl-workspace":
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        new_value = body.get("value", "").strip()
        if not new_value:
            return JSONResponse({"ok": False, "error": "value required"}, status_code=400)
        result = _update_env_value("BSL_HOST_WORKSPACE", new_value)
        if result.get("ok"):
            # BSL_WORKSPACE controls the docker volume mount — keep in sync with BSL_HOST_WORKSPACE
            _update_env_value("BSL_WORKSPACE", new_value)
            export_url = (_read_env_value("EXPORT_HOST_URL") or settings.export_host_url or "").strip()
            if not export_url:
                host_root_prefix = (_read_env_value("HOST_ROOT_PREFIX") or os.environ.get("HOST_ROOT_PREFIX", "")).strip()
                export_url = (
                    "http://host.docker.internal:8082"
                    if host_root_prefix
                    else "http://localhost:8082"
                )
                _update_env_value("EXPORT_HOST_URL", export_url)

            apply_result = await _apply_bsl_workspace_runtime(new_value, export_url)
            graph_result = await _recreate_bsl_graph_runtime()
            db_sync = apply_result.get("db_reconfigured", 0)
            db_err = apply_result.get("db_errors", 0)
            if db_err:
                result["message"] = (
                    f"Папка выгрузки BSL сохранена и применена. "
                    f"Базы: обновлено {db_sync}, ошибок {db_err}."
                )
            else:
                result["message"] = (
                    f"Папка выгрузки BSL сохранена и применена. "
                    f"Базы обновлены: {db_sync}."
                )
            if graph_result.get("attempted"):
                if graph_result.get("ok"):
                    result["message"] += " Граф пересоздан."
                else:
                    result["message"] += " Граф не удалось пересоздать автоматически."
        return JSONResponse(result)

    if path == "get-env":
        return JSONResponse({"ok": True, "env": _mask_env_for_ui(_read_env_file())})

    if path == "save-env":
        try:
            body = await request.json()
        except Exception:
            _audit_action(request, "save-env", False, reason="invalid_json")
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        content = body.get("content", "")
        replace_mode = str(body.get("mode", "")).strip().lower() == "replace"
        if not content:
            _audit_action(request, "save-env", False, reason="empty_content")
            return JSONResponse({"error": "content required"}, status_code=400)
        try:
            prepared_content = _prepare_env_content_for_write(content, replace=replace_mode)
        except ValueError as exc:
            _audit_action(request, "save-env", False, reason="partial_content")
            return JSONResponse({"error": str(exc)}, status_code=400)
        result = _write_env_file(prepared_content)
        if result.get("ok"):
            # Auto-restart gateway container
            _restart_gateway()
            result["message"] = "Настройки сохранены. Шлюз перезапускается..."
        _audit_action(request, "save-env", bool(result.get("ok")), bytes=len(content))
        return JSONResponse(result)

    if path == "reindex-bsl":
        db_name = request.query_params.get("name", "")
        if db_name:
            db = _registry.get(db_name)
            if not db:
                return JSONResponse({"ok": False, "error": f"База '{db_name}' не найдена."})
            from .bsl_search import bsl_search as _bsl_search

            index_message = _bsl_search.build_index(db.project_path, db.lsp_container or "")
            if index_message.startswith("ERROR"):
                return JSONResponse({"ok": False, "error": index_message})

            lsp_message = "LSP недоступен — rebuilt только full-text индекс."
            if db.lsp_container:
                try:
                    lsp = _manager.get_db_backend(db_name, "lsp")
                    if lsp:
                        result = await lsp.call_tool(
                            "did_change_watched_files",
                            {"language": "bsl", "changes_json": "[]"},
                        )
                        resp = result.content[0].text if result.content else ""
                        lsp_message = f"LSP переиндексация запущена.\n{resp}"
                except Exception as exc:
                    lsp_message = f"Ошибка LSP-переиндексации: {exc}"
            try:
                await rebuild_report_catalog_for_db_info(db_name, db)
            except Exception as exc:
                logger.info("Skipping report catalog refresh after dashboard reindex for %s: %s", db_name, exc)
            return JSONResponse({"ok": True, "message": f"{index_message}\n{lsp_message}"})
        from . import mcp_server as _ms
        result = await _ms._reindex_bsl("")
        return JSONResponse({"ok": True, "message": result})

    if path == "docker-info":
        return JSONResponse(
            {
                "ok": True,
                "data": {
                    "docker_system": _get_docker_system_info(),
                    "container_info": _get_container_info(
                        include_runtime_stats=True,
                        include_image_size=True,
                    ),
                    "reports_summary": _collect_reports_summary(None, [db.get("name", "") for db in _registry.list()]),
                },
            }
        )

    if path == "diagnostics":
        return JSONResponse({"ok": True, "data": _collect_diagnostics()})

    return JSONResponse({"error": f"Unknown action: {path}"}, status_code=404)


def _host_path_to_container(host_path: str) -> str:
    """Translate a host-side BSL workspace path to its container-accessible equivalent.

    /home/...  → /hostfs-home/...  (mounted rw, no restart needed when path changes)
    C:\\...    → /workspace        (Windows paths cannot be mapped directly)
    anything else → /workspace     (old behaviour, requires BSL_WORKSPACE env var)
    """
    p = host_path.rstrip("/").rstrip("\\")
    if p.startswith("/home/"):
        return "/hostfs-home/" + p[len("/home/"):]
    # Windows paths (C:\...) or other Unix paths fall back to /workspace
    return "/workspace"


def _managed_workspace_root_container() -> str:
    host_root = (_read_env_value("BSL_HOST_WORKSPACE") or _read_env_value("BSL_WORKSPACE")).strip()
    host_root = host_root.rstrip("/").rstrip("\\")
    if host_root:
        return _host_path_to_container(host_root)
    return "/workspace"


def _normalize_runtime_project_path(project_path: str, slug: str) -> str:
    current = (project_path or "").strip()
    if current.startswith("/home/"):
        current = _host_path_to_container(current)

    desired_root = _managed_workspace_root_container().rstrip("/")
    if not desired_root:
        desired_root = "/workspace"
    desired_path = f"{desired_root}/{slug}" if slug else desired_root

    if not current:
        return desired_path

    if current in {"/projects", "/workspace", "/hostfs-home", desired_root}:
        return desired_path

    if _is_managed_project_path(current):
        desired_prefix = f"{desired_root}/"
        if current != desired_path and not current.startswith(desired_prefix):
            return desired_path

    return current


async def _sync_managed_project_path_if_needed(db_name: str, db_info=None) -> bool:
    """
    Self-heal stale managed project_path values on live register/heartbeat.

    Why this exists:
    - registry entries may still carry an old managed path like `/workspace/Z02`
      even though the real exported BSL tree already lives under the current
      hostfs workspace root (for example `/hostfs-home/as/Z/Z02`)
    - graph and future LSP restarts read registry state, so stale managed paths
      make one database appear empty after reinstall/reopen even while EPF and
      existing LSP containers are otherwise alive
    """
    db = db_info or _registry.get(db_name)
    if not db:
        return False

    slug = (getattr(db, "slug", "") or db_name).strip()
    current_path = (getattr(db, "project_path", "") or "").strip()
    normalized_path = _normalize_runtime_project_path(current_path, slug)
    if not normalized_path or normalized_path == current_path:
        return False

    _registry.update(db_name, project_path=normalized_path)
    logger.info(
        "Normalized managed project_path for '%s': %s -> %s",
        db_name,
        current_path,
        normalized_path,
    )

    refreshed_db = _registry.get(db_name) or db
    if _manager.has_db(db_name) and getattr(refreshed_db, "connection", "").strip():
        await _ensure_lsp_started(refreshed_db.connection)

    await _trigger_graph_rebuild()
    return True


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


_MASKED_ENV_KEYS = ("DOCKER_CONTROL_TOKEN", "ANONYMIZER_SALT")
_MASKED_ENV_KEY_SET = set(_MASKED_ENV_KEYS)
_MASKED_ENV_PLACEHOLDER = "***hidden***"


def _mask_env_for_ui(content: str) -> str:
    lines = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key_text, _, value = line.partition("=")
        key = key_text.strip()
        if key in _MASKED_ENV_KEY_SET and value.strip():
            newline = "\n" if line.endswith("\n") else ""
            lines.append(f"{key}={_MASKED_ENV_PLACEHOLDER}{newline}")
            continue
        lines.append(line)
    return "".join(lines)


def _restore_masked_env_secrets(content: str) -> str:
    current_values = {key: _read_env_value(key) for key in _MASKED_ENV_KEYS}
    found_keys: set[str] = set()
    new_lines = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key_text, _, value = line.partition("=")
        key = key_text.strip()
        if key in _MASKED_ENV_KEY_SET:
            found_keys.add(key)
            newline = "\n" if line.endswith("\n") else ""
            raw_value = value.rstrip("\n")
            if raw_value.strip() == _MASKED_ENV_PLACEHOLDER:
                new_lines.append(f"{key}={current_values.get(key, '')}{newline}")
                continue
        new_lines.append(line)

    for key in _MASKED_ENV_KEYS:
        if key in found_keys:
            continue
        current_value = current_values.get(key, "")
        if not current_value:
            continue
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={current_value}\n")

    return "".join(new_lines)


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
    restored = _restore_masked_env_secrets(content)
    if replace:
        return restored

    current = _read_env_file()
    if current.startswith("# .env file not found"):
        return restored

    current_keys = {key for key, _ in _iter_env_assignments(current)}
    restored_keys = {key for key, _ in _iter_env_assignments(restored)}
    if current_keys and restored_keys and not current_keys.issubset(restored_keys):
        raise ValueError("partial env update rejected; submit the full .env content")
    return restored


def _write_env_file(content: str) -> dict:
    """Write .env file through docker-control."""
    import os

    preferred_paths = ["/data/.env"] if os.path.exists("/data/.env") else [".env", "/app/.env"]
    for p in preferred_paths:
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return {"ok": True, "message": "Настройки сохранены."}
        except FileNotFoundError:
            continue
        except (PermissionError, OSError):
            continue
    try:
        return _docker_manager.write_env_file(content)
    except Exception:
        return {"ok": False, "error": "Cannot write .env via docker-control. Edit on host manually."}


def _read_env_value(key: str) -> str:
    """Read a single key value from the .env file."""
    content = _read_env_file()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        k, _, v = stripped.partition("=")
        if k.strip() == key:
            # Strip optional surrounding quotes
            v = v.strip()
            if len(v) >= 2 and v[0] in ('"', "'") and v[-1] == v[0]:
                v = v[1:-1]
            return v
    return ""


def _update_env_value(key: str, value: str) -> dict:
    """Update or append a key=value line in the .env file, preserving comments."""
    return _update_env_values({key: value})


def _update_env_values(updates: dict[str, str]) -> dict:
    """Update or append several key=value lines in the .env file atomically."""
    content = _read_env_file()
    lines = content.splitlines(keepends=True)
    pending = {str(key): str(value) for key, value in updates.items()}
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and "=" in stripped:
            k, _, _ = stripped.partition("=")
            key_name = k.strip()
            if key_name in pending:
                new_lines.append(f"{key_name}={pending.pop(key_name)}\n")
                continue
        new_lines.append(line)
    for key, value in pending.items():
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f"{key}={value}\n")
    return _write_env_file("".join(new_lines))


def _current_report_settings_payload() -> dict:
    return {
        "auto_analyze_enabled": bool(settings.report_auto_analyze_enabled),
        "run_default_max_rows": int(settings.report_run_default_max_rows),
        "run_default_timeout_seconds": int(settings.report_run_default_timeout_seconds),
        "validate_default_max_rows": int(settings.report_validate_default_max_rows),
        "validate_default_timeout_seconds": int(settings.report_validate_default_timeout_seconds),
    }


def _parse_bool_value(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be true or false")


def _parse_non_negative_int(value, field_name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


def _parse_report_settings_payload(body: dict) -> dict:
    return {
        "auto_analyze_enabled": _parse_bool_value(body.get("auto_analyze_enabled", True), "auto_analyze_enabled"),
        "run_default_max_rows": _parse_non_negative_int(body.get("run_default_max_rows", settings.report_run_default_max_rows), "run_default_max_rows"),
        "run_default_timeout_seconds": _parse_non_negative_int(body.get("run_default_timeout_seconds", settings.report_run_default_timeout_seconds), "run_default_timeout_seconds"),
        "validate_default_max_rows": _parse_non_negative_int(body.get("validate_default_max_rows", settings.report_validate_default_max_rows), "validate_default_max_rows"),
        "validate_default_timeout_seconds": _parse_non_negative_int(body.get("validate_default_timeout_seconds", settings.report_validate_default_timeout_seconds), "validate_default_timeout_seconds"),
    }


def _apply_report_settings_runtime(new_settings: dict) -> None:
    os.environ["REPORT_AUTO_ANALYZE_ENABLED"] = "true" if new_settings["auto_analyze_enabled"] else "false"
    os.environ["REPORT_RUN_DEFAULT_MAX_ROWS"] = str(new_settings["run_default_max_rows"])
    os.environ["REPORT_RUN_DEFAULT_TIMEOUT_SECONDS"] = str(new_settings["run_default_timeout_seconds"])
    os.environ["REPORT_VALIDATE_DEFAULT_MAX_ROWS"] = str(new_settings["validate_default_max_rows"])
    os.environ["REPORT_VALIDATE_DEFAULT_TIMEOUT_SECONDS"] = str(new_settings["validate_default_timeout_seconds"])
    settings.report_auto_analyze_enabled = new_settings["auto_analyze_enabled"]
    settings.report_run_default_max_rows = new_settings["run_default_max_rows"]
    settings.report_run_default_timeout_seconds = new_settings["run_default_timeout_seconds"]
    settings.report_validate_default_max_rows = new_settings["validate_default_max_rows"]
    settings.report_validate_default_timeout_seconds = new_settings["validate_default_timeout_seconds"]


def _is_managed_project_path(path: str) -> bool:
    normalized = (path or "").strip()
    if not normalized:
        return True
    return (
        normalized == "/projects"
        or normalized.startswith("/workspace/")
        or normalized.startswith("/hostfs-home/")
    )


async def _apply_bsl_workspace_runtime(new_workspace: str, export_host_url: str) -> dict:
    """
    Apply BSL workspace change immediately in the running gateway process.

    Why this exists:
    - `docker restart` does not re-read env vars from docker-compose/.env.
    - dashboard users expect path switch to affect reindex/export right away.

    This function synchronizes:
    1. process env + settings
    2. managed DB project paths
    3. per-DB LSP mounts (recreates LSP container when mount source changed)
    """
    from .mcp_server import _DB_NAME_RE, _slugify

    # Keep runtime settings/env in sync without requiring gateway container recreation.
    os.environ["BSL_HOST_WORKSPACE"] = new_workspace
    os.environ["BSL_WORKSPACE_HOST"] = new_workspace
    os.environ["BSL_WORKSPACE"] = new_workspace
    os.environ["EXPORT_HOST_URL"] = export_host_url
    settings.bsl_host_workspace = new_workspace
    settings.export_host_url = export_host_url

    loop = asyncio.get_running_loop()
    db_reconfigured = 0
    db_errors = 0
    errors: list[str] = []

    for db in _registry.list():
        name = (db.get("name") or "").strip()
        if not name:
            continue
        db_info = _registry.get(name)
        if not db_info:
            continue

        slug = db_info.slug or (name if _DB_NAME_RE.match(name) else _slugify(name))
        host_root = new_workspace.rstrip("/").rstrip("\\")
        if host_root:
            desired_path = _host_path_to_container(f"{host_root}/{slug}")
        else:
            desired_path = f"/workspace/{slug}"
        current_path = (db_info.project_path or "").strip()
        if _is_managed_project_path(current_path) and current_path != desired_path:
            _registry.update(name, project_path=desired_path)
            db_info = _registry.get(name) or db_info

        # Reconfigure running DBs immediately so reindex/export use the new location.
        if not _manager.has_db(name):
            continue
        # Skip LSP (re)start if the target directory doesn't exist yet — Docker
        # would auto-create it as root when binding the mount, which silently
        # pollutes the freshly selected workspace with empty per-DB subfolders.
        # The directory is created naturally on first BSL export.
        # Gateway may run as non-root and lack traverse rights on user home
        # dirs; treat PermissionError as "likely exists" and defer to docker-control.
        try:
            _missing = not os.path.isdir(db_info.project_path)
        except PermissionError:
            _missing = False
        if _missing:
            logger.info(
                f"Skipping LSP reconfigure for '{name}': {db_info.project_path} does not exist yet "
                f"(will be created on first BSL export)."
            )
            continue
        try:
            lsp_container = await asyncio.wait_for(
                loop.run_in_executor(None, _docker_manager.start_lsp, slug, db_info.project_path),
                timeout=90,
            )
            _registry.update_runtime(name, lsp_container=lsp_container or "")
            db_reconfigured += 1
        except Exception as exc:
            db_errors += 1
            errors.append(f"{name}: {exc}")
            logger.warning(f"Failed to reconfigure LSP for '{name}' after workspace switch: {exc}")

    return {
        "db_reconfigured": db_reconfigured,
        "db_errors": db_errors,
        "errors": errors,
    }


def _collect_diagnostics() -> dict:
    """Collect full diagnostic info about the gateway."""
    from .anonymizer import anonymizer
    from .metadata_cache import metadata_cache
    from .profiler import profiler

    backends_status = _manager.status()
    container_info = _get_container_info()

    diag = {
        "gateway": {
            "version": f"v{_version}",
            "port": settings.port,
            "log_level": settings.log_level,
            "stateful_sessions": True,
            "session_idle_timeout": 28800,
            "active_sessions": _manager.session_count,
        },
        "backends": backends_status,
        "databases": _registry.list(),
        "default_db": _manager.active_db,
        "profiling": profiler.get_stats(),
        "cache": metadata_cache.stats(),
        "anonymization": {"enabled": anonymizer.enabled},
        "docker": _get_docker_system_info(),
        "containers": container_info,
        "optional_services": _get_optional_services_status(backends_status, container_info),
        "reports_summary": _collect_reports_summary(None, [db.get("name", "") for db in _registry.list()]),
        "config": {
            "ENABLED_BACKENDS": settings.enabled_backends,
            "ONEC_TOOLKIT_URL": settings.onec_toolkit_url,
            "PLATFORM_CONTEXT_URL": settings.platform_context_url,
            "EXPORT_HOST_URL": settings.export_host_url,
            "PLATFORM_PATH": settings.platform_path,
            "BSL_WORKSPACE": settings.bsl_workspace,
            "BSL_HOST_WORKSPACE": settings.bsl_host_workspace,
            "BSL_LSP_COMMAND": settings.bsl_lsp_command,
            "NAPARNIK_API_KEY": "***" if settings.naparnik_api_key else "",
            "METADATA_CACHE_TTL": settings.metadata_cache_ttl,
            "EPF_HEARTBEAT_TTL_SECONDS": settings.epf_heartbeat_ttl_seconds,
            "REPORT_AUTO_ANALYZE_ENABLED": settings.report_auto_analyze_enabled,
            "REPORT_RUN_DEFAULT_MAX_ROWS": settings.report_run_default_max_rows,
            "REPORT_RUN_DEFAULT_TIMEOUT_SECONDS": settings.report_run_default_timeout_seconds,
            "REPORT_VALIDATE_DEFAULT_MAX_ROWS": settings.report_validate_default_max_rows,
            "REPORT_VALIDATE_DEFAULT_TIMEOUT_SECONDS": settings.report_validate_default_timeout_seconds,
            "TEST_RUNNER_URL": settings.test_runner_url,
            "BSL_GRAPH_URL": settings.bsl_graph_url,
        },
    }

    # Container logs (last 10 lines each)
    try:
        diag["container_logs"] = _docker_manager.get_container_logs(tail=10)
    except Exception as exc:
        diag["container_logs"] = {"error": str(exc)}

    return diag


def _collect_reports_summary(catalog: ReportCatalog | None = None, databases: list[str] | None = None) -> list[dict]:
    try:
        catalog = catalog or _get_report_catalog()
        names = [str(name or "").strip() for name in (databases or []) if str(name or "").strip()]
        return catalog.summarize_databases(names or None)
    except Exception as exc:
        logger.warning("Report summary unavailable: %s", exc)
        return []


def _restart_gateway() -> None:
    """Restart the gateway container via docker-control."""
    import threading
    def _do_restart():
        import time
        time.sleep(1)  # let the HTTP response finish
        try:
            _docker_manager.restart_container("onec-mcp-gw")
        except Exception as exc:
            logger.error(f"Auto-restart failed: {exc}")
    threading.Thread(target=_do_restart, daemon=True).start()


def _get_docker_system_info() -> dict:
    """Get Docker daemon info from docker-control."""
    try:
        return _docker_manager.get_docker_system_info()
    except Exception as exc:
        return {"error": str(exc)}


_HOSTFS = "/hostfs"
# On Windows the host root mounted into /hostfs is not the real root — it is a
# subdirectory (typically %USERPROFILE%). HOST_ROOT_PREFIX holds the host-side path
# of whatever is mounted at /hostfs, so the API can translate between host paths
# (shown to the user, e.g. "C:/Users/Alex/projects") and container paths
# ("/hostfs/projects"). Empty string on Linux where "/" is mounted directly.
_HOST_ROOT_PREFIX = os.environ.get("HOST_ROOT_PREFIX", "").rstrip("/")


async def _browse_via_host_service(path: str) -> dict | None:
    """Ask the host-side export service to enumerate directories with host permissions."""
    base_url = (settings.export_host_url or "").strip()
    if not base_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(base_url.rstrip("/") + "/browse", params={"path": path})
    except Exception:
        return None

    try:
        data = resp.json()
    except ValueError:
        return None

    if resp.status_code != 200 and "error" not in data:
        data = {"error": f"Host browse failed with HTTP {resp.status_code}"}
    return data


async def _select_directory_via_host_service(current_path: str) -> dict | None:
    """Ask the host-side service to open the native OS directory chooser."""
    base_url = (settings.export_host_url or "").strip()
    if not base_url:
        return {
            "ok": False,
            "error": "Сервис выгрузки BSL на хосте не настроен. Укажите EXPORT_HOST_URL и запустите export-host-service.py.",
        }
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                base_url.rstrip("/") + "/select-directory",
                json={"currentPath": current_path},
            )
    except Exception:
        return {
            "ok": False,
            "error": "Не удалось связаться с сервисом выгрузки BSL на хосте.",
        }

    try:
        data = resp.json()
    except ValueError:
        return {
            "ok": False,
            "error": "Сервис выгрузки BSL вернул некорректный ответ.",
        }

    if resp.status_code != 200 and "error" not in data:
        data = {"ok": False, "error": f"Host directory selection failed with HTTP {resp.status_code}"}
    return data


async def select_directory_api(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON body"}, status_code=400)
    result = await _select_directory_via_host_service(str(body.get("currentPath", "") or ""))
    return JSONResponse(result or {"ok": False, "error": "Directory selection is unavailable."})


async def browse_api(request: Request) -> JSONResponse:
    """Return subdirectories for a given host path (used by folder picker in dashboard).

    The gateway container mounts / → /hostfs (read-only).
    The API receives and returns HOST paths (e.g. /home/user/projects).
    Internally it prepends /hostfs for actual filesystem access.
    """
    import os as _os
    raw = request.query_params.get("path", "")
    if raw == "~" or not raw:
        # Default: infer a sensible host home from current BSL_WORKSPACE, falling
        # back to the host-root prefix (Windows) or /home (Linux)
        raw = (
            _read_env_value("BSL_HOST_WORKSPACE")
            or _read_env_value("BSL_WORKSPACE")
            or _HOST_ROOT_PREFIX
            or "/home"
        )
    raw = raw.replace("\\", "/").rstrip("/") or "/"

    # Translate host path → relative-to-mount path.
    # Linux: prefix empty, raw="/home/user" → rel="home/user"
    # Windows: prefix="C:/Users/Alex", raw="C:/Users/Alex/projects" → rel="projects"
    rel = raw
    if _HOST_ROOT_PREFIX and (rel == _HOST_ROOT_PREFIX or rel.startswith(_HOST_ROOT_PREFIX + "/")):
        rel = rel[len(_HOST_ROOT_PREFIX):]
    rel = rel.lstrip("/")

    # Sanitize: resolve ../ to prevent path traversal attacks
    container_path = _os.path.realpath(_os.path.join(_HOSTFS, rel))
    if not container_path.startswith(_os.path.realpath(_HOSTFS)):
        return JSONResponse({"error": "Invalid path"}, status_code=400)

    host_result = await _browse_via_host_service(raw)
    if host_result is not None:
        return JSONResponse(host_result, status_code=200)

    def _to_host(container_abs: str) -> str:
        real_hostfs = _os.path.realpath(_HOSTFS)
        sub = container_abs[len(real_hostfs):].lstrip("/")
        if _HOST_ROOT_PREFIX:
            return (_HOST_ROOT_PREFIX + "/" + sub).rstrip("/") or _HOST_ROOT_PREFIX
        return "/" + sub if sub else "/"

    try:
        if not _os.path.isdir(container_path):
            container_path = _os.path.dirname(container_path)

        host_path = _to_host(container_path)
        parent_container = _os.path.dirname(container_path)
        real_hostfs = _os.path.realpath(_HOSTFS)
        if not parent_container.startswith(real_hostfs):
            parent_container = real_hostfs
        host_parent = _to_host(parent_container)

        dirs = sorted(
            d for d in _os.listdir(container_path)
            if _os.path.isdir(_os.path.join(container_path, d)) and not d.startswith(".")
        )
        return JSONResponse({"path": host_path, "parent": host_parent, "dirs": dirs})
    except PermissionError:
        return JSONResponse({"path": raw, "parent": raw, "dirs": [], "error": "Permission denied"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


_starlette = Starlette(
    routes=[
        Route("/health", health),
        Route("/dashboard", dashboard),
        Route("/dashboard/docs", dashboard_docs),
        Route("/dashboard/diagnostics", dashboard_diagnostics),
        Route("/api/export-bsl", export_bsl_api, methods=["POST"]),
        Route("/api/export-preview", export_preview_api, methods=["POST"]),
        Route("/api/export-status", export_status_api, methods=["GET", "POST"]),
        Route("/api/export-cancel", export_cancel_api, methods=["POST"]),
        Route("/api/reports/{action}", reports_api, methods=["POST"]),
        Route("/api/databases", databases_status_api, methods=["GET"]),
        Route("/api/unregister", unregister_epf_api, methods=["POST"]),
        Route("/api/register", register_epf_api, methods=["POST"]),
        Route("/api/epf-heartbeat", epf_heartbeat_api, methods=["POST"]),
        Route("/api/select-directory", select_directory_api, methods=["POST"]),
        Route("/api/action/{action}", action_api, methods=["GET", "POST"]),
        Route("/api/browse", browse_api, methods=["GET"]),
    ],
    lifespan=lifespan,
    middleware=[
        Middleware(BaseHTTPMiddleware, dispatch=_rate_limit_guard),
        Middleware(BaseHTTPMiddleware, dispatch=_api_token_guard),
    ],
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

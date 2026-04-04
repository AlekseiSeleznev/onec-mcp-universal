import logging
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from . import mcp_server
from .backends.http_backend import HttpBackend
from .backends.manager import BackendManager
from .backends.stdio_backend import StdioBackend
from .config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_manager = BackendManager()
mcp_server.manager = _manager

session_manager = StreamableHTTPSessionManager(
    app=mcp_server.server,
    stateless=False,
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
    return backends


@asynccontextmanager
async def lifespan(app: Starlette):
    backends = _build_backends()
    logger.info(f"Starting {len(backends)} backend(s)...")
    await _manager.start_all(backends)
    status = _manager.status()
    ok_count = sum(1 for v in status.values() if v["ok"])
    logger.info(f"Backends ready: {ok_count}/{len(backends)} — {status}")
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

    from . import mcp_server as _ms
    result = await _ms._run_export_bsl(connection, output_dir)
    ok = not result.startswith("ERROR") and not result.startswith("Export failed")
    return JSONResponse({"ok": ok, "result": result}, status_code=200)


_starlette = Starlette(
    routes=[
        Route("/health", health),
        Route("/api/export-bsl", export_bsl_api, methods=["POST"]),
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

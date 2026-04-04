import asyncio
import json
import os
import subprocess
from pathlib import Path

from mcp.server import Server
from mcp.types import CallToolResult, TextContent, Tool

from .backends.manager import BackendManager
from .config import settings
from .db_registry import DatabaseRegistry

server = Server("onec-universal-mcp")
manager: BackendManager  # injected by server.py before lifespan starts
registry: DatabaseRegistry  # injected by server.py before lifespan starts

GW_TOOLS = [
    Tool(
        name="get_server_status",
        description=(
            "Get health status of all MCP backends: 1C data connection (onec-toolkit), "
            "BSL code navigation (bsl-lsp-bridge), and 1C platform docs (platform-context). "
            "Returns which backends are available and how many tools each exposes."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="export_bsl_sources",
        description=(
            "Export 1C configuration source files (BSL) to the project directory using ibcmd. "
            "After export the BSL Language Server automatically re-indexes the new files. "
            "Use this to keep the code navigation tools up to date after configuration changes. "
            "Connection string examples:\n"
            "  Server DB:  'Srvr=server1c;Ref=zup_base;'\n"
            "  File DB:    'File=/path/to/ib'\n"
            "  With auth:  'Srvr=srv;Ref=base;Usr=user;Pwd=pass'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection": {
                    "type": "string",
                    "description": (
                        "1C connection string. "
                        "Examples: 'Srvr=server1c;Ref=zup;' or 'File=/path/to/ib'"
                    ),
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Directory to export BSL files into. "
                        "Default: /projects (the mounted BSL volume)"
                    ),
                    "default": "/projects",
                },
            },
            "required": ["connection"],
        },
    ),
    Tool(
        name="connect_database",
        description=(
            "Register a 1C database in the gateway and prepare its backends "
            "(onec-toolkit + BSL LSP). Call this when starting work with a new database. "
            "After calling this tool, open the EPF in the 1C client, press 'Подключить' "
            "and 'Выгрузить BSL' to export sources to the project folder. "
            "The database becomes the active context for all subsequent tool calls."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Database identifier, e.g. 'Z01' or 'ERP_DEMO'",
                },
                "connection": {
                    "type": "string",
                    "description": "1C connection string, e.g. 'Srvr=as-hp;Ref=Z01;'",
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Absolute host path to the project folder where BSL files "
                        "will be exported and LSP will index. "
                        "Use the current working directory of the Cursor project."
                    ),
                },
            },
            "required": ["name", "connection", "project_path"],
        },
    ),
    Tool(
        name="list_databases",
        description="List all registered 1C databases and their connection status.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="switch_database",
        description=(
            "Switch the active 1C database context. All tool calls (execute_query, "
            "BSL navigation, etc.) will route to the selected database."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Database name to switch to (must be registered first)",
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="disconnect_database",
        description=(
            "Disconnect a 1C database: stop its containers (onec-toolkit + LSP) "
            "and remove it from the registry."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Database name to disconnect",
                },
            },
            "required": ["name"],
        },
    ),
]


async def _run_export_bsl(connection: str, output_dir: str) -> str:
    # If a host-side export service URL is configured, delegate to it.
    if settings.export_host_url:
        import httpx

        host_dir = output_dir
        # Remap container path → host path if BSL_HOST_WORKSPACE is set
        if settings.bsl_host_workspace and settings.bsl_workspace:
            container_ws = settings.bsl_workspace.rstrip("/")
            host_ws = settings.bsl_host_workspace.rstrip("/")
            if host_dir.startswith(container_ws):
                host_dir = host_ws + host_dir[len(container_ws):]
            elif host_dir == "/projects" or not host_dir:
                host_dir = host_ws

        url = settings.export_host_url.rstrip("/") + "/export-bsl"
        try:
            async with httpx.AsyncClient(timeout=1800) as client:
                resp = await client.post(url, json={"connection": connection, "output_dir": host_dir})
                data = resp.json()
                return data.get("result", str(data))
        except Exception as exc:
            return f"ERROR calling export host service at {url}: {exc}"

    # Fallback: try ibcmd (works only with standalone 1C server, not cluster)
    ibcmd = Path(settings.ibcmd_path)
    if not ibcmd.exists():
        return (
            f"ERROR: ibcmd not found at {ibcmd} and EXPORT_HOST_URL is not set. "
            f"Run tools/export-host-service.py on the host and set "
            f"EXPORT_HOST_URL=http://<host-ip>:8082"
        )

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ibcmd),
        "infobase", "config", "export",
        "--connection", connection,
        "--dir", output_dir,
        "--force",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "LD_LIBRARY_PATH": "/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu"},
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
        output = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            # Count exported files
            bsl_count = sum(1 for _ in out_path.rglob("*.bsl"))
            result = f"Export completed successfully.\nBSL files in {output_dir}: {bsl_count}\n\nOutput:\n{output}"

            # Notify BSL LS about changed files via did_change_watched_files
            if "bsl-lsp-bridge" in manager._tool_map:
                try:
                    await manager.call_tool("did_change_watched_files", {"path": output_dir})
                except Exception:
                    pass  # not critical

            return result
        else:
            return f"Export failed (rc={proc.returncode}):\n{output}"

    except asyncio.TimeoutError:
        return "ERROR: ibcmd timed out after 10 minutes"
    except Exception as exc:
        return f"ERROR: {exc}"


@server.list_tools()
async def list_tools() -> list[Tool]:
    return GW_TOOLS + manager.get_all_tools()


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_server_status":
        return [TextContent(type="text", text=json.dumps(manager.status(), ensure_ascii=False, indent=2))]

    if name == "export_bsl_sources":
        connection = arguments.get("connection", "")
        output_dir = arguments.get("output_dir", "/projects")
        result = await _run_export_bsl(connection, output_dir)
        return [TextContent(type="text", text=result)]

    if name == "connect_database":
        return [TextContent(type="text", text=await _connect_database(
            arguments["name"], arguments["connection"], arguments["project_path"]
        ))]

    if name == "list_databases":
        dbs = registry.list()
        return [TextContent(type="text", text=json.dumps(dbs, ensure_ascii=False, indent=2))]

    if name == "switch_database":
        db_name = arguments["name"]
        if manager.switch_db(db_name) and registry.switch(db_name):
            return [TextContent(type="text", text=f"Switched to database: {db_name}")]
        return [TextContent(type="text", text=f"ERROR: Database '{db_name}' not found. Use list_databases() to see registered databases.")]

    if name == "disconnect_database":
        return [TextContent(type="text", text=await _disconnect_database(arguments["name"]))]

    result: CallToolResult = await manager.call_tool(name, arguments)
    return result.content


async def _connect_database(name: str, connection: str, project_path: str) -> str:
    import asyncio
    from .docker_manager import start_toolkit, start_lsp
    from .backends.http_backend import HttpBackend
    from .backends.stdio_backend import StdioBackend

    try:
        # Register in registry
        db_info = registry.register(name, connection, project_path)

        # Start containers (blocking I/O — run in thread)
        loop = asyncio.get_event_loop()

        toolkit_port, toolkit_container = await loop.run_in_executor(
            None, start_toolkit, name
        )
        lsp_container = await loop.run_in_executor(
            None, start_lsp, name, project_path
        )

        # Update registry with container info
        # gateway uses host network → reach toolkit via localhost
        toolkit_internal_url = f"http://localhost:{toolkit_port}/mcp"
        db_info.toolkit_port = toolkit_port      # host port (for 1C /1c/poll)
        db_info.toolkit_url = toolkit_internal_url
        db_info.lsp_container = lsp_container

        # Create and start backends
        toolkit_backend = HttpBackend(
            f"onec-toolkit-{name}", toolkit_internal_url, "streamable"
        )
        lsp_backend = StdioBackend(
            f"mcp-lsp-{name}", "docker",
            ["exec", "-i", lsp_container, "mcp-lsp-bridge"]
        )
        await manager.add_db_backends(name, toolkit_backend, lsp_backend)

        # Switch to this database
        manager.switch_db(name)
        registry.switch(name)

        return (
            f"Database '{name}' connected successfully.\n"
            f"  onec-toolkit: {db_info.toolkit_url}\n"
            f"  LSP container: {lsp_container}\n"
            f"  BSL workspace: {project_path}\n\n"
            f"Next steps:\n"
            f"1. In the 1C EPF, set database name to '{name}' and press 'Подключить к прокси'\n"
            f"2. Press 'Выгрузить BSL' to export sources to {project_path}\n"
            f"3. BSL navigation will be available after indexing completes"
        )
    except Exception as exc:
        return f"ERROR connecting database '{name}': {exc}"


async def _disconnect_database(name: str) -> str:
    import asyncio
    from .docker_manager import stop_db_containers

    db = registry.get(name)
    if not db:
        return f"ERROR: Database '{name}' not found."

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, stop_db_containers, name)
        await manager.remove_db_backends(name)
        registry.remove(name)
        return f"Database '{name}' disconnected and containers removed."
    except Exception as exc:
        return f"ERROR disconnecting database '{name}': {exc}"

import asyncio
import json
import os
import subprocess
from pathlib import Path

from mcp.server import Server
from mcp.types import CallToolResult, TextContent, Tool

from .backends.manager import BackendManager
from .config import settings

server = Server("onec-universal-mcp")
manager: BackendManager  # injected by server.py before lifespan starts

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
]


async def _run_export_bsl(connection: str, output_dir: str) -> str:
    ibcmd = Path(settings.ibcmd_path)
    if not ibcmd.exists():
        return f"ERROR: ibcmd not found at {ibcmd}. Set IBCMD_PATH env variable."

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(ibcmd),
        "infobase", "config", "export",
        f"--connection={connection}",
        f"--dir={output_dir}",
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

    result: CallToolResult = await manager.call_tool(name, arguments)
    return result.content

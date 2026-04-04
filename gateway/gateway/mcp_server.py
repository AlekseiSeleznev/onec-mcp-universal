import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.types import CallToolResult, Resource, TextContent, TextResourceContents, Tool

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
    Tool(
        name="validate_query",
        description=(
            "Validate 1C query syntax without executing it or returning data. "
            "Performs static checks (balanced parentheses, required keywords, common mistakes) "
            "and, if a database is active, sends the query to the server with ПЕРВЫЕ 0 "
            "to catch server-side syntax errors. "
            "Use this to iteratively fix queries before running execute_query."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "1C query text to validate (ВЫБРАТЬ ...)",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="graph_stats",
        description=(
            "Get statistics of the BSL dependency graph: total number of nodes, edges, "
            "and breakdown by object type (documents, catalogs, registers, etc.). "
            "Requires the bsl-graph service to be running."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="graph_search",
        description=(
            "Search for 1C configuration objects in the dependency graph. "
            "Returns matching nodes with their types and IDs for use in graph_related. "
            "Requires the bsl-graph service to be running."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (object name or part of it)",
                },
                "types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Filter by object types, e.g. ['DOCUMENT', 'CATALOG', 'REGISTER']. "
                        "Leave empty to search all types."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 20)",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="graph_related",
        description=(
            "Find all objects related to a given configuration object in the dependency graph. "
            "Shows what the object uses and what uses it — useful for impact analysis "
            "('what breaks if I change X'). "
            "Use graph_search first to get the object ID. "
            "Requires the bsl-graph service to be running."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "object_id": {
                    "type": "string",
                    "description": "Object ID from graph_search result",
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth (1 = direct neighbors, 2 = two hops). Default 1.",
                    "default": 1,
                },
            },
            "required": ["object_id"],
        },
    ),
]

_SYNTAX_RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "syntax_1c.txt"


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


@server.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri="file:///syntax_1c.txt",
            name="1C BSL Syntax Reference",
            description=(
                "Syntax reference for the 1C:Enterprise built-in language (BSL): "
                "types, operators, control structures, procedures, exceptions, "
                "preprocessor directives. Use as context when writing BSL code."
            ),
            mimeType="text/markdown",
        )
    ]


@server.read_resource()
async def read_resource(uri) -> str:
    if str(uri) == "file:///syntax_1c.txt":
        return _SYNTAX_RESOURCE_PATH.read_text(encoding="utf-8")
    raise ValueError(f"Unknown resource: {uri}")


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

    if name == "validate_query":
        result_text = await _validate_query(arguments.get("query", ""))
        return [TextContent(type="text", text=result_text)]

    if name == "graph_stats":
        result_text = await _graph_request("GET", "/api/graph/stats")
        return [TextContent(type="text", text=result_text)]

    if name == "graph_search":
        payload = {
            "query": arguments.get("query", ""),
            "types": arguments.get("types", []),
            "limit": arguments.get("limit", 20),
        }
        result_text = await _graph_request("POST", "/api/graph/search", payload)
        return [TextContent(type="text", text=result_text)]

    if name == "graph_related":
        object_id = arguments.get("object_id", "")
        depth = arguments.get("depth", 1)
        result_text = await _graph_request(
            "GET", f"/api/graph/related/{object_id}", params={"depth": depth}
        )
        return [TextContent(type="text", text=result_text)]

    result: CallToolResult = await manager.call_tool(name, arguments)
    return result.content


def _validate_query_static(query: str) -> tuple[bool, list[str], list[str]]:
    """Static syntax check for 1C queries. Returns (valid, errors, warnings)."""
    stripped = query.strip()
    if not stripped:
        return False, ["Запрос пуст"], []

    errors: list[str] = []
    warnings: list[str] = []

    # Strip single-line comments for keyword analysis
    clean = re.sub(r'//[^\n]*', '', stripped)
    upper = clean.upper()

    # Must contain ВЫБРАТЬ
    if 'ВЫБРАТЬ' not in upper:
        errors.append("В запросе отсутствует ключевое слово ВЫБРАТЬ")

    # Balanced parentheses (skip string literals)
    depth = 0
    i = 0
    while i < len(clean):
        c = clean[i]
        if c == '"':
            i += 1
            while i < len(clean) and clean[i] != '"':
                i += 1
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth < 0:
                errors.append("Лишняя закрывающая скобка ')'")
                depth = 0
        i += 1

    if depth > 0:
        errors.append(f"Несбалансированные скобки: {depth} незакрытых '('")

    # Warn: virtual table params in WHERE instead of inside brackets
    vt_pattern = r'\.(Остатки|ОстаткиИОбороты|Обороты|СрезПоследних|СрезПервых)\s*\)'
    if re.search(vt_pattern, clean, re.IGNORECASE) and 'ГДЕ' in upper:
        warnings.append(
            "Параметры виртуальной таблицы могут быть в ГДЕ вместо скобок — "
            "это снижает производительность. Фильтруйте внутри .Остатки(...)"
        )

    # Warn: SELECT *
    if re.search(r'ВЫБРАТЬ\s+(\w+\s+)*\*', upper):
        warnings.append("Рекомендуется выбирать конкретные поля вместо *")

    return len(errors) == 0, errors, warnings


def _add_limit_zero(query: str) -> str:
    """Insert ПЕРВЫЕ 0 after the outermost ВЫБРАТЬ (skips sub-queries)."""
    # Find the position of the first top-level ВЫБРАТЬ
    match = re.search(r'\bВЫБРАТЬ\b', query, re.IGNORECASE)
    if not match:
        return query
    pos = match.end()
    # Skip РАЗЛИЧНЫЕ if present
    tail = query[pos:]
    diff_match = re.match(r'\s+РАЗЛИЧНЫЕ\b', tail, re.IGNORECASE)
    if diff_match:
        pos += diff_match.end()
    # Skip existing ПЕРВЫЕ N if present
    tail = query[pos:]
    first_match = re.match(r'\s+ПЕРВЫЕ\s+\d+\b', tail, re.IGNORECASE)
    if first_match:
        # Replace the existing limit with 0
        return query[:pos] + re.sub(
            r'(\s+ПЕРВЫЕ\s+)\d+', r'\g<1>0', tail, count=1, flags=re.IGNORECASE
        )
    return query[:pos] + ' ПЕРВЫЕ 0 ' + tail


async def _validate_query(query: str) -> str:
    valid, errors, warnings = _validate_query_static(query)
    result: dict = {}

    if errors:
        result["valid"] = False
        result["errors"] = errors
        if warnings:
            result["warnings"] = warnings
        return json.dumps(result, ensure_ascii=False, indent=2)

    # Static checks passed — try server-side validation if DB is active
    try:
        active = registry.get_active()
        if active:
            toolkit = manager._tool_map.get("execute_query")
            if toolkit:
                limited_query = _add_limit_zero(query)
                call_result = await toolkit.call_tool(
                    "execute_query", {"query": limited_query}
                )
                response_text = (
                    call_result.content[0].text if call_result.content else ""
                )
                # Detect server-reported syntax errors
                low = response_text.lower()
                if any(
                    kw in low
                    for kw in ("синтаксическ", "syntax error", "ошибка синтакс",
                               "недопустимый", "unexpected token", "parse error")
                ):
                    result["valid"] = False
                    result["errors"] = [f"Ошибка синтаксиса от сервера 1С: {response_text[:600]}"]
                else:
                    result["valid"] = True
                    result["source"] = "server"
                    result["message"] = "Запрос проверен на сервере 1С — синтаксис корректен"
                if warnings:
                    result["warnings"] = warnings
                return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception:
        pass  # fall through to static-only result

    result["valid"] = True
    result["source"] = "static"
    result["message"] = "Статическая проверка пройдена (база данных не подключена)"
    if warnings:
        result["warnings"] = warnings
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _graph_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> str:
    base_url = settings.bsl_graph_url.rstrip("/")
    url = base_url + path
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, json=body, params=params)
            resp.raise_for_status()
            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception:
                return resp.text
    except httpx.ConnectError:
        return (
            f"ERROR: bsl-graph service not available at {base_url}. "
            "Start it with: docker compose --profile bsl-graph up -d"
        )
    except Exception as exc:
        return f"ERROR: {exc}"


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
            ["exec", "-w", "/projects", "-i", lsp_container, "mcp-lsp-bridge"]
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

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.types import CallToolResult, Resource, TextContent, Tool

from .anonymizer import anonymizer
from .backends.manager import BackendManager
from .bsl_search import bsl_search
from .config import settings
from .db_registry import DatabaseRegistry
from .metadata_cache import metadata_cache
from .napilnik_client import NapilnikClient
from .profiler import profiler

log = logging.getLogger(__name__)

server = Server("onec-universal-mcp")
manager: BackendManager  # injected by server.py before lifespan starts
registry: DatabaseRegistry  # injected by server.py before lifespan starts

_DB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")

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
                    "description": (
                        "Database identifier (letters, digits, hyphens, underscores). "
                        "Examples: 'ERP', 'ZUP_TEST', 'buh-main'"
                    ),
                },
                "connection": {
                    "type": "string",
                    "description": "1C connection string, e.g. 'Srvr=as-hp;Ref=Z01;'",
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Absolute host path to the project folder where BSL files "
                        "will be exported and LSP will index."
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
        name="reindex_bsl",
        description=(
            "Trigger BSL Language Server re-indexing for the active database. "
            "Use after editing BSL files outside the LSP (e.g. manual file changes, "
            "git pull, or external export). Notifies the LSP about changed files "
            "so code navigation stays up to date."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path to re-index. Default: the project_path of the active database."
                    ),
                },
            },
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
    # --- Write BSL ---
    Tool(
        name="write_bsl",
        description=(
            "Write BSL code to a module file in the active database's BSL workspace. "
            "Use this to modify 1C configuration source code (e.g. common modules, "
            "object modules, form modules). After writing, the LSP will automatically "
            "re-index the changed file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": (
                        "Relative path to BSL file within the project, "
                        "e.g. 'CommonModules/МойМодуль/Ext/Module.bsl'"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "BSL code to write to the file",
                },
            },
            "required": ["file", "content"],
        },
    ),
    # --- BSL Search ---
    Tool(
        name="bsl_index",
        description=(
            "Build a full-text search index over BSL source files in the active database's project. "
            "Indexes all procedures and functions with their parameters, comments, and module paths. "
            "Run this once after BSL export, then use bsl_search to find functions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to BSL files root. Default: /projects (LSP container workspace).",
                },
            },
        },
    ),
    Tool(
        name="bsl_search_tool",
        description=(
            "Search for procedures and functions in the BSL source code index. "
            "Find BSP functions by name or description, search exported API, "
            "locate code patterns across the configuration. "
            "Run bsl_index first to build the index."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term: function name, module name, or keyword from comments",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 20)",
                    "default": 20,
                },
                "export_only": {
                    "type": "boolean",
                    "description": "Only show exported (public API) symbols",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    ),
    # --- Anonymization ---
    Tool(
        name="enable_anonymization",
        description=(
            "Enable PII anonymization for query results. "
            "Masks personal data (FIO, INN, SNILS, phones, emails, company names) "
            "with stable fake replacements. Same original value always maps to same fake. "
            "Use this before working with production databases containing personal data."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="disable_anonymization",
        description="Disable PII anonymization. Query results will contain original data.",
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- ITS Search ---
    Tool(
        name="its_search",
        description=(
            "Search 1C ITS documentation and standard configurations via 1C:Napilnik API. "
            "Ask questions about 1C platform, BSP (Standard Subsystem Library), "
            "typical configurations, and best practices. "
            "Requires NAPILNIK_API_KEY in .env file (get at https://code.1c.ai)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Question about 1C platform, BSP, or standard configurations",
                },
            },
            "required": ["query"],
        },
    ),
    # --- Metadata cache ---
    Tool(
        name="invalidate_metadata_cache",
        description=(
            "Clear the metadata cache. Use after configuration changes "
            "to ensure get_metadata returns fresh data."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Query profiling ---
    Tool(
        name="query_stats",
        description=(
            "Show execute_query performance statistics: total queries, avg/max/min duration, "
            "slow queries count, error rate."
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    # --- Form screenshot ---
    Tool(
        name="capture_form",
        description=(
            "Request a screenshot of the currently open form in the 1C client. "
            "The EPF must be running and connected. Returns the screenshot as a base64 image."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Image format: png or jpg (default: png)",
                    "default": "png",
                },
            },
        },
    ),
]

_SYNTAX_RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "syntax_1c.txt"

GW_TOOL_NAMES = {t.name for t in GW_TOOLS}


# ---------------------------------------------------------------------------
# Export BSL sources
# ---------------------------------------------------------------------------

async def _run_export_bsl(connection: str, output_dir: str) -> str:
    if settings.export_host_url:
        host_dir = output_dir
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
            bsl_count = sum(1 for _ in out_path.rglob("*.bsl"))
            result = f"Export completed successfully.\nBSL files in {output_dir}: {bsl_count}\n\nOutput:\n{output}"

            if manager.has_tool("did_change_watched_files"):
                try:
                    await manager.call_tool("did_change_watched_files", {"path": output_dir})
                except Exception:
                    pass
            return result
        else:
            return f"Export failed (rc={proc.returncode}):\n{output}"

    except asyncio.TimeoutError:
        return "ERROR: ibcmd timed out after 10 minutes"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# MCP Tools — list & dispatch
# ---------------------------------------------------------------------------

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

    if name == "reindex_bsl":
        return [TextContent(type="text", text=await _reindex_bsl(arguments.get("path", "")))]

    if name == "graph_stats":
        return [TextContent(type="text", text=await _graph_request("GET", "/api/graph/stats"))]

    if name == "graph_search":
        payload = {"query": arguments.get("query", ""), "types": arguments.get("types", []), "limit": arguments.get("limit", 20)}
        return [TextContent(type="text", text=await _graph_request("POST", "/api/graph/search", payload))]

    if name == "graph_related":
        oid = arguments.get("object_id", "")
        return [TextContent(type="text", text=await _graph_request("GET", f"/api/graph/related/{oid}", params={"depth": arguments.get("depth", 1)}))]

    # --- Write BSL ---
    if name == "write_bsl":
        return [TextContent(type="text", text=await _write_bsl(
            arguments.get("file", ""), arguments.get("content", ""),
        ))]

    # --- BSL Search ---
    if name == "bsl_index":
        path = arguments.get("path", "").strip() or "/projects"
        active = registry.get_active()
        container = active.lsp_container if active else ""
        return [TextContent(type="text", text=bsl_search.build_index(path, container=container))]
    if name == "bsl_search_tool":
        results = bsl_search.search(
            arguments.get("query", ""),
            limit=arguments.get("limit", 20),
            export_only=arguments.get("export_only", False),
        )
        if not results:
            if not bsl_search.indexed:
                return [TextContent(type="text", text="Index not built. Run bsl_index first.")]
            return [TextContent(type="text", text="No results found.")]
        return [TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

    # --- Anonymization ---
    if name == "enable_anonymization":
        return [TextContent(type="text", text=anonymizer.enable())]
    if name == "disable_anonymization":
        return [TextContent(type="text", text=anonymizer.disable())]

    # --- ITS Search ---
    if name == "its_search":
        return [TextContent(type="text", text=await _its_search(arguments.get("query", "")))]

    # --- Metadata cache ---
    if name == "invalidate_metadata_cache":
        return [TextContent(type="text", text=metadata_cache.invalidate())]

    # --- Query profiling ---
    if name == "query_stats":
        return [TextContent(type="text", text=json.dumps(profiler.get_stats(), ensure_ascii=False, indent=2))]

    # --- Form screenshot ---
    if name == "capture_form":
        return [TextContent(type="text", text=await _capture_form(arguments.get("format", "png")))]

    # --- Metadata cache check ---
    if name == "get_metadata" and settings.metadata_cache_ttl > 0:
        cached = metadata_cache.get(arguments)
        if cached is not None:
            return [TextContent(type="text", text=cached)]

    # --- Proxy to backend with profiling + anonymization ---
    t0 = time.monotonic()
    result: CallToolResult = await manager.call_tool(name, arguments)
    elapsed_ms = (time.monotonic() - t0) * 1000

    # Profiling for execute_query
    if name == "execute_query":
        query_text = arguments.get("query", "")
        response_text = result.content[0].text if result.content else ""
        try:
            rdata = json.loads(response_text)
            row_count = len(rdata.get("data", [])) if isinstance(rdata.get("data"), list) else 0
            success = rdata.get("success", True)
        except (json.JSONDecodeError, TypeError):
            row_count = 0
            success = True
        profiler.record(query_text, elapsed_ms, success, row_count)
        response_text = profiler.format_profiling_result(query_text, elapsed_ms, response_text)
        response_text = anonymizer.process_tool_response(name, response_text)
        return [TextContent(type="text", text=response_text)]

    # Metadata caching for get_metadata
    if name == "get_metadata":
        response_text = result.content[0].text if result.content else ""
        metadata_cache.put(arguments, response_text)
        return result.content

    # Anonymization for data tools
    if anonymizer.enabled and result.content:
        processed = []
        for content in result.content:
            if hasattr(content, "text"):
                processed.append(TextContent(
                    type="text",
                    text=anonymizer.process_tool_response(name, content.text),
                ))
            else:
                processed.append(content)
        return processed

    return result.content


# ---------------------------------------------------------------------------
# validate_query
# ---------------------------------------------------------------------------

def _validate_query_static(query: str) -> tuple[bool, list[str], list[str]]:
    stripped = query.strip()
    if not stripped:
        return False, ["Запрос пуст"], []

    errors: list[str] = []
    warnings: list[str] = []

    clean = re.sub(r'//[^\n]*', '', stripped)
    upper = clean.upper()

    if 'ВЫБРАТЬ' not in upper:
        errors.append("В запросе отсутствует ключевое слово ВЫБРАТЬ")

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

    vt_pattern = r'\.(Остатки|ОстаткиИОбороты|Обороты|СрезПоследних|СрезПервых)\s*\)'
    if re.search(vt_pattern, clean, re.IGNORECASE) and 'ГДЕ' in upper:
        warnings.append(
            "Параметры виртуальной таблицы могут быть в ГДЕ вместо скобок — "
            "это снижает производительность. Фильтруйте внутри .Остатки(...)"
        )

    if re.search(r'ВЫБРАТЬ\s+(РАЗЛИЧНЫЕ\s+)?(ПЕРВЫЕ\s+\d+\s+)?\*', upper, re.DOTALL):
        warnings.append("Рекомендуется выбирать конкретные поля вместо *")

    return len(errors) == 0, errors, warnings


def _add_limit_zero(query: str) -> str:
    match = re.search(r'\bВЫБРАТЬ\b', query, re.IGNORECASE)
    if not match:
        return query
    pos = match.end()
    tail = query[pos:]

    # Skip optional РАЗЛИЧНЫЕ
    diff_match = re.match(r'(\s+РАЗЛИЧНЫЕ)\b', tail, re.IGNORECASE)
    if diff_match:
        pos += diff_match.end()
        tail = query[pos:]

    # Replace existing ПЕРВЫЕ N or insert ПЕРВЫЕ 0
    first_match = re.match(r'(\s+ПЕРВЫЕ\s+)\d+', tail, re.IGNORECASE)
    if first_match:
        return query[:pos] + first_match.group(1) + '0' + tail[first_match.end():]
    return query[:pos] + ' ПЕРВЫЕ 0' + tail


async def _validate_query(query: str) -> str:
    valid, errors, warnings = _validate_query_static(query)
    result: dict = {}

    if errors:
        result["valid"] = False
        result["errors"] = errors
        if warnings:
            result["warnings"] = warnings
        return json.dumps(result, ensure_ascii=False, indent=2)

    try:
        active = registry.get_active()
        if active:
            toolkit = manager.get_backend_for_tool("execute_query")
            if toolkit:
                limited_query = _add_limit_zero(query)
                call_result = await toolkit.call_tool("execute_query", {"query": limited_query})
                response_text = call_result.content[0].text if call_result.content else ""
                low = response_text.lower()
                if any(kw in low for kw in ("синтаксическ", "syntax error", "ошибка синтакс",
                                             "недопустимый", "unexpected token", "parse error")):
                    result["valid"] = False
                    result["errors"] = [f"Ошибка синтаксиса от сервера 1С: {response_text[:600]}"]
                else:
                    result["valid"] = True
                    result["source"] = "server"
                    result["message"] = "Запрос проверен на сервере 1С — синтаксис корректен"
                if warnings:
                    result["warnings"] = warnings
                return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.warning(f"Server-side query validation failed: {exc}")

    result["valid"] = True
    result["source"] = "static"
    result["message"] = "Статическая проверка пройдена (база данных не подключена)"
    if warnings:
        result["warnings"] = warnings
    return json.dumps(result, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# BSL re-indexing
# ---------------------------------------------------------------------------

async def _reindex_bsl(path: str) -> str:
    active = registry.get_active()
    if not active:
        return "ERROR: No active database. Connect a database first."

    reindex_path = path.strip() if path else "/projects"

    if not manager.has_tool("did_change_watched_files"):
        return "ERROR: LSP backend not available — cannot trigger re-index."

    try:
        result = await manager.call_tool("did_change_watched_files", {"path": reindex_path})
        response_text = result.content[0].text if result.content else ""
        return f"Re-indexing triggered for '{active.name}' at {reindex_path}.\n{response_text}"
    except Exception as exc:
        return f"ERROR triggering re-index: {exc}"


# ---------------------------------------------------------------------------
# bsl-graph REST wrapper
# ---------------------------------------------------------------------------

async def _graph_request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> str:
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
        return f"ERROR: bsl-graph service not available at {base_url}. Start it with: docker compose --profile bsl-graph up -d"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Write BSL
# ---------------------------------------------------------------------------

async def _write_bsl(file: str, content: str) -> str:
    active = registry.get_active()
    if not active:
        return "ERROR: No active database. Connect a database first."

    # Write to LSP container via docker exec
    container = active.lsp_container
    if not container:
        return "ERROR: No LSP container for active database."

    file_path = f"/projects/{file.lstrip('/')}"
    try:
        import subprocess
        # Ensure directory exists
        dir_path = str(Path(file_path).parent)
        subprocess.run(
            ["docker", "exec", container, "mkdir", "-p", dir_path],
            check=True, capture_output=True, timeout=10,
        )
        # Write file via stdin
        proc = subprocess.run(
            ["docker", "exec", "-i", container, "tee", file_path],
            input=content.encode("utf-8-sig"),
            capture_output=True, timeout=10,
        )
        if proc.returncode != 0:
            return f"ERROR writing file: {proc.stderr.decode()}"

        # Notify LSP about changed file
        if manager.has_tool("did_change_watched_files"):
            try:
                await manager.call_tool("did_change_watched_files", {"path": dir_path})
            except Exception:
                pass

        return f"Written {len(content)} chars to {file_path} in container {container}."
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# ITS Search via 1C:Napilnik
# ---------------------------------------------------------------------------

async def _its_search(query: str) -> str:
    if not settings.napilnik_api_key:
        return (
            "ERROR: NAPILNIK_API_KEY not configured.\n"
            "Get your API key at https://code.1c.ai (Profile → API token).\n"
            "Add to .env: NAPILNIK_API_KEY=your-key-here"
        )
    client = NapilnikClient(settings.napilnik_api_key)
    return await client.search(query)


# ---------------------------------------------------------------------------
# Form screenshot
# ---------------------------------------------------------------------------

async def _capture_form(fmt: str) -> str:
    active = registry.get_active()
    if not active:
        return "ERROR: No active database. Connect a database first."
    if not active.toolkit_url:
        return "ERROR: No toolkit URL for active database."

    # Request screenshot from toolkit via its REST API
    base_url = active.toolkit_url.replace("/mcp", "")
    url = f"{base_url}/1c/screenshot"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json={"format": fmt})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    return json.dumps(data, ensure_ascii=False)
                return f"ERROR: {data.get('error', 'Unknown error')}"
            if resp.status_code == 404:
                return (
                    "ERROR: Screenshot endpoint not available. "
                    "Update MCPToolkit.epf to the latest version."
                )
            return f"ERROR: Screenshot request failed: {resp.status_code}"
    except Exception as exc:
        return f"ERROR: {exc}"


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------

async def _connect_database(name: str, connection: str, project_path: str) -> str:
    from .docker_manager import start_toolkit, start_lsp
    from .backends.http_backend import HttpBackend
    from .backends.stdio_backend import StdioBackend

    if not _DB_NAME_RE.match(name):
        return f"ERROR: Invalid database name '{name}'. Use only letters, digits, hyphens and underscores."

    try:
        db_info = registry.register(name, connection, project_path)

        loop = asyncio.get_running_loop()
        try:
            toolkit_port, toolkit_container = await asyncio.wait_for(
                loop.run_in_executor(None, start_toolkit, name), timeout=120
            )
            lsp_container = await asyncio.wait_for(
                loop.run_in_executor(None, start_lsp, name, project_path), timeout=60
            )
        except Exception:
            registry.remove(name)
            raise

        toolkit_internal_url = f"http://localhost:{toolkit_port}/mcp"
        db_info.toolkit_port = toolkit_port
        db_info.toolkit_url = toolkit_internal_url
        db_info.lsp_container = lsp_container

        toolkit_backend = HttpBackend(f"onec-toolkit-{name}", toolkit_internal_url, "streamable")
        lsp_backend = StdioBackend(
            f"mcp-lsp-{name}", "docker",
            ["exec", "-w", "/projects", "-i", lsp_container, "mcp-lsp-bridge"]
        )
        await manager.add_db_backends(name, toolkit_backend, lsp_backend)

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
    from .docker_manager import stop_db_containers

    db = registry.get(name)
    if not db:
        return f"ERROR: Database '{name}' not found."

    try:
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, stop_db_containers, name), timeout=30
        )
        await manager.remove_db_backends(name)
        registry.remove(name)
        return f"Database '{name}' disconnected and containers removed."
    except Exception as exc:
        return f"ERROR disconnecting database '{name}': {exc}"

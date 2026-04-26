import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.types import (
    CallToolResult,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)

from .anonymizer import anonymizer
from .backends.manager import BackendManager
from .bsl_search import bsl_search
from .config import settings
from .db_registry import DatabaseRegistry
from .metadata_cache import metadata_cache
from .profiler import profiler
from .tool_handlers.graph import graph_request as _graph_request_impl
from .tool_handlers.graph import try_handle_graph_tool
from .tool_handlers.its import its_search as _its_search_impl
from .tool_handlers.db_lifecycle import connect_database as _connect_database_impl
from .tool_handlers.db_lifecycle import disconnect_database as _disconnect_database_impl
from .tool_handlers.export import build_index_with_fallback
from .tool_handlers.export import find_1cv8_binaries as _find_1cv8_binaries_impl
from .tool_handlers.export import pick_1cv8 as _pick_1cv8_impl
from .tool_handlers.export import run_designer_export as _run_designer_export_impl
from .tool_handlers.export import run_export_bsl as _run_export_bsl_impl
from .tool_handlers.reindex import reindex_bsl as _reindex_bsl_impl
from .tool_handlers.reports import report_tools
from .tool_handlers.reports import rebuild_report_catalog_for_db_info
from .tool_handlers.reports import try_handle_report_tool
from .tool_handlers.validate_query import add_limit_zero as _add_limit_zero_impl
from .tool_handlers.validate_query import validate_query as _validate_query_impl
from .tool_handlers.validate_query import validate_query_static as _validate_query_static_impl
from .tool_handlers.write_bsl import write_bsl as _write_bsl_impl

log = logging.getLogger(__name__)

# Per-connection BSL export/index job state.
_export_jobs: dict[str, dict] = {}
_export_tasks: dict[str, asyncio.Task] = {}
_index_jobs: dict[str, dict] = {}

AGENT_INSTRUCTIONS = """
You are connected to **onec-mcp-universal** — a gateway to 1C:Enterprise
databases at http://localhost:8080/mcp. For ANY 1C-related task (reading
data, writing BSL, exploring a configuration, working with 1C APIs or BSP),
**use these MCP tools first; do NOT guess or invent BSL from memory**.

Intent recognition — when the user's request is a 1C task, route it here:
  User phrases that pin the session to this MCP:
    «1С / 1C / онек / onec», «используем 1С <имя_базы>»,
    «работаем с 1С <имя>», «подключись к 1С <имя>»,
    «в базе 1С <имя>», «switch to 1C <name>».
  1C-specific terminology (any of these → use THIS MCP):
    BSL / язык 1С, Справочник/Документ/Регистр/Перечисление/Отчёт/
    Обработка/БизнесПроцесс/ПланВидов*, Конфигурация, БСП, ИТС,
    1С:Напарник, MCPToolkit.epf, connection strings starting with
    `Srvr=...;Ref=...;` or `File=...`.
  Typical DB-name patterns: Z01, Z02, ZUP*, ERP*, БП*, УТ*, КА*,
    Розница, TST_*.
  Action when user names a base («используем 1С Z01»):
    1) list_databases → if Z01 present, switch_database name=Z01.
    2) If not present, ask the user for connection string and call
       connect_database. Do NOT guess.
  If the user says «база X» without specifying 1C, call list_databases
  here first; if X is present, proceed. If not, say so and ask — do NOT
  invent a connection.

Core flows:
  • Before writing BSL that calls an existing function:
      symbol_explore or bsl_search_tool → hover / definition → then write.
  • Before running a query:
      get_metadata (structure) → validate_query → execute_query.
  • Before answering from a 1C report:
      use report tools first, not execute_query/execute_code against
      registers. Start with
      find_reports(database=..., query=user-visible title) or
      list_reports(database=...) when browsing the catalog →
      describe_report(database=..., title/report/variant=...) →
      run_report(database=..., title/report=..., period/filters/params/context).
      If the result is paged, continue with
      get_report_result(database=..., run_id=...).
      If run_report returns needs_input, fill only the explicitly requested
      fields and call run_report again. Report tools require explicit
      `database`; do not rely on the active session.
  • Before modifying a module:
      document_diagnostics → write_bsl (never edit BSL files directly).
  • For BSP / ITS questions (works when NAPARNIK_API_KEY is set):
      its_search first — it searches 1C:ИТС / 1С:Напарник.
  • For configuration-wide impact analysis / "where is X used":
      graph_search / graph_related / find_references_to_object.
      A visual viewer is served at http://localhost:8888/.
  • For language syntax (platform built-ins, not BSP):
      get_bsl_syntax_help.

If a required backend is offline or the target DB is not connected, tell the
user explicitly — do NOT silently fall back to hallucinated code. Check
get_server_status / list_databases first when unsure.

Tool categories:
  data: execute_query, execute_code, get_metadata, get_event_log,
        get_object_by_link, get_link_of_object, find_references_to_object,
        get_access_rights, query_stats.
  reports: analyze_reports, find_reports, list_reports, describe_report,
        run_report, get_report_result, explain_report_strategy.
  BSL search: bsl_index, bsl_search_tool, reindex_bsl.
  LSP navigation: symbol_explore, definition, hover, document_diagnostics,
        call_hierarchy, call_graph, project_analysis, code_actions, rename,
        prepare_rename, get_range_content, selection_range,
        did_change_watched_files, lsp_status.
  BSL write: write_bsl (triggers auto-reindex).
  Graph: graph_stats, graph_search, graph_related.
  Lifecycle: connect_database, list_databases, switch_database,
        disconnect_database, export_bsl_sources, get_export_status.
  Platform docs: get_bsl_syntax_help.
  ITS / 1С:Напарник (optional): its_search.
  Misc: enable_anonymization, disable_anonymization,
        invalidate_metadata_cache, get_server_status.

Common pitfalls — read this before calling unfamiliar tools:
  • Always inspect `tools/list` and read inputSchema before a first call.
    Do NOT invent argument names. Most tool-level errors in logs are
    `'X' is a required property` — they mean you skipped the schema.
  • Active DB is pinned to the current Mcp-Session-Id. Call
    `switch_database` once per session. Two clients can hold different
    active DBs concurrently — sessions are independent.
  • LSP URIs use the per-DB LSP container's mount: every path is
    `file:///projects/<relative-to-db-root>` — NOT
    `file:///projects/<db_name>/...`. Each database has its own LSP
    container whose /projects volume is that DB's workspace root.
  • Tool-specific argument shapes that trip agents up:
      - write_bsl:            `file` (not `path`), `content`.
      - get_range_content:    `uri`, `start_line`, `start_character`,
                              `end_line`, `end_character`
                              (NOT a `range:{start,end}` object).
      - project_analysis:     `analysis_type` must be one of
                              workspace_symbols, document_symbols,
                              references, definitions, text_search,
                              workspace_analysis, symbol_relationships,
                              file_analysis, pattern_analysis.
      - find_references_to_object:
                              `target_object_description` is an object
                              `{"fullName": "Справочник.X"}` (or with
                              `_objectRef`), `search_scope` is an ARRAY
                              of metadata object names, NOT paths.
      - get_object_by_link / get_link_of_object:
                              the description must contain `_objectRef`
                              plus `УникальныйИдентификатор` and
                              `ТипОбъекта`; a plain string will fail.
      - did_change_watched_files:
                              `language` required; `changes_json` is a
                              JSON-encoded STRING, not an array.
      - info:                 `name` + `type` (method/property/type).
      - getMembers / getMember / getConstructors: `typeName` must be a
                              1C type known to platform-context
                              (СправочникМенеджер, Массив, etc.), not
                              a BSL primitive alias.
      - search (LSP):         `type` is the LSP symbol kind enum
                              (class/function/method/variable/…), NOT
                              "function" — check the facade's enum.
  • If a tool call returns HTTP 404 or the session stops responding,
    re-initialize: the gateway drops expired sessions. Do NOT retry on
    the same Mcp-Session-Id.
  • `epf_connected: false` in list_databases means the 1C-side EPF is
    not running. execute_query/execute_code will return "EPF for
    database 'X' is not connected". Ask the user to open MCPToolkit.epf
    in 1C and press "Подключиться" — do NOT fabricate query results.
  • Platform-context tools (info/getMembers/getMember/getConstructors)
    live in a separate backend from the 1C connection — they work even
    without an active DB, and their "type not found" is a real content
    response, not a gateway failure.
""".strip()


server = Server("onec-universal-mcp", instructions=AGENT_INSTRUCTIONS)
manager: BackendManager | None = None  # injected by server.py before lifespan starts
registry: DatabaseRegistry | None = None  # injected by server.py before lifespan starts

_DB_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}$")

_CYR_MAP = str.maketrans({
    'А':'A','Б':'B','В':'V','Г':'G','Д':'D','Е':'E','Ё':'E','Ж':'J','З':'Z',
    'И':'I','Й':'J','К':'K','Л':'L','М':'M','Н':'N','О':'O','П':'P','Р':'R',
    'С':'S','Т':'T','У':'U','Ф':'F','Х':'H','Ц':'C','Ч':'C','Ш':'S','Щ':'S',
    'Ъ':'_','Ы':'Y','Ь':'_','Э':'E','Ю':'U','Я':'Y',
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'j','з':'z',
    'и':'i','й':'j','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r',
    'с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'c','ш':'s','щ':'s',
    'ъ':'_','ы':'y','ь':'_','э':'e','ю':'u','я':'y',
})


def _slugify(name: str) -> str:
    """Convert any database name (including Cyrillic) to a Docker-safe slug."""
    slug = name.translate(_CYR_MAP)
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_-")
    if not slug or not slug[0].isalnum():
        slug = "db_" + slug
    return slug[:63]

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
            "Export 1C configuration source files (BSL) to the project directory using "
            "1cv8 DESIGNER /DumpConfigToFiles. Automatically detects installed platform versions "
            "and handles client/server version mismatches by retrying with matching binary. "
            "After export the BSL Language Server re-indexes the new files. "
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
                "wait": {
                    "type": "boolean",
                    "description": (
                        "When false (default), start export in background and return "
                        "immediately. Use get_export_status to track completion."
                    ),
                    "default": False,
                },
            },
            "required": ["connection"],
        },
    ),
    Tool(
        name="get_export_status",
        description=(
            "Get status of background BSL export started by export_bsl_sources. "
            "Pass connection string for a specific database, or omit to list all jobs."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection": {
                    "type": "string",
                    "description": "Exact 1C connection string used to start the export job.",
                },
            },
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
                        "Path inside the gateway container where BSL files will be "
                        "exported and LSP will index. Use '/workspace/{slug}' format, "
                        "e.g. '/workspace/ZUP_TEST'. The /workspace directory is "
                        "mounted from BSL_WORKSPACE on the host."
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
            "Disconnect a 1C database: stop its runtime containers (onec-toolkit + LSP) "
            "and detach it from the active session, but keep it registered in the gateway."
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
]
GW_TOOLS.extend(report_tools())

_SYNTAX_RESOURCE_PATH = Path(__file__).parent.parent / "resources" / "syntax_1c.txt"

GW_TOOL_NAMES = {t.name for t in GW_TOOLS}


def _dedupe_tools(tools: list[Tool]) -> list[Tool]:
    """Return tools with stable first-seen ordering and unique names."""
    unique: list[Tool] = []
    seen: set[str] = set()
    for tool in tools:
        if tool.name in seen:
            continue
        seen.add(tool.name)
        unique.append(tool)
    return unique


def _search_syntax_reference(keywords: list[str], limit: int = 20) -> str:
    """Fallback implementation for get_bsl_syntax_help using the bundled syntax reference."""
    text = _SYNTAX_RESOURCE_PATH.read_text(encoding="utf-8")
    normalized = [k.strip().lower() for k in keywords if k and k.strip()]
    if not normalized:
        return json.dumps(
            {"success": False, "data": None, "error": "keywords must contain at least one non-empty item"},
            ensure_ascii=False,
            indent=2,
        )

    sections: list[tuple[str, str, int]] = []
    current_title = "Document"
    current_lines: list[str] = []
    current_score = 0

    def flush_section() -> None:
        nonlocal current_title, current_lines, current_score
        body = "\n".join(current_lines).strip()
        if body:
            lowered = f"{current_title}\n{body}".lower()
            score = sum(1 for kw in normalized if kw in lowered)
            sections.append((current_title, body, score))
        current_lines = []

    for line in text.splitlines():
        if line.startswith("#"):
            flush_section()
            current_title = line.lstrip("#").strip() or "Section"
        current_lines.append(line)
    flush_section()

    matches = [
        (title, body, score)
        for title, body, score in sections
        if score > 0
    ]
    matches.sort(key=lambda item: (-item[2], item[0]))

    candidates = [
        {"title": title, "score": score}
        for title, _, score in matches[:limit]
    ]

    content = None
    if len(matches) == 1 or (matches and matches[0][2] == len(normalized)):
        content = f"## {matches[0][0]}\n\n{matches[0][1][:4000]}"

    return json.dumps(
        {
            "success": True,
            "data": {
                "candidates": candidates,
                "total": len(matches),
                "content": content,
            },
            "error": None,
        },
        ensure_ascii=False,
        indent=2,
    )


# ---------------------------------------------------------------------------
# Export BSL sources
# ---------------------------------------------------------------------------

def _find_1cv8_binaries() -> dict[str, Path]:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return _find_1cv8_binaries_impl()


def _pick_1cv8(preferred_version: str = "") -> Path | None:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return _pick_1cv8_impl(preferred_version, find_binaries=_find_1cv8_binaries)


async def _run_designer_export(
    v8_path: Path, connection_args: list[str], output_dir: str,
    timeout: int | None = None,
) -> tuple[int, str]:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return await _run_designer_export_impl(
        v8_path=v8_path,
        connection_args=connection_args,
        output_dir=output_dir,
        timeout=timeout,
        default_timeout=settings.bsl_export_timeout,
        logger=log,
    )


async def _run_export_bsl(connection: str, output_dir: str) -> str:
    from . import docker_manager as _docker_manager

    async def _refresh_lsp(slug: str, project_path: str) -> None:
        """Recreate mcp-lsp-<slug> if its bind-mount became stale (post staging-swap)."""
        if not slug:
            return
        loop = asyncio.get_running_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, _docker_manager.start_lsp, slug, project_path),
            timeout=60,
        )

    result = await _run_export_bsl_impl(
        connection=connection,
        output_dir=output_dir,
        settings=settings,
        manager=manager,
        index_jobs=_index_jobs,
        get_session_active=_get_session_active,
        get_connection_active=_get_connection_active,
        build_index=bsl_search.build_index,
        find_binaries=_find_1cv8_binaries,
        pick_binary=_pick_1cv8,
        run_designer_export_fn=_run_designer_export,
        logger=log,
        refresh_lsp_fn=_refresh_lsp,
    )
    if not result.startswith("ERROR") and not result.startswith("Export failed"):
        await _auto_analyze_reports_for_db(_get_connection_active(connection), "export_bsl_sources")
    return result


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
# MCP Prompts — ready-to-run playbooks for typical 1C tasks
# ---------------------------------------------------------------------------

_PROMPTS: list[tuple[Prompt, str]] = [
    (
        Prompt(
            name="connect_and_inspect",
            description=(
                "Connect a 1C database via EPF and show an overview of the "
                "configuration: metadata summary + top object types from the "
                "dependency graph."
            ),
            arguments=[],
        ),
        (
            "Use MCP onec-mcp-universal to: "
            "1) call list_databases; if empty, tell the user to run the EPF "
            "connection flow. "
            "2) call get_metadata (no filter) to show counts by object type. "
            "3) if graph_stats is available, show totalNodes / totalEdges and "
            "top types from graph. "
            "Never write BSL from memory before this overview is complete."
        ),
    ),
    (
        Prompt(
            name="describe_object",
            description=(
                "Describe a 1C configuration object: metadata, access rights, "
                "neighbours in the dependency graph, sample usages."
            ),
            arguments=[
                PromptArgument(
                    name="metadata_object",
                    description="Fully-qualified object, e.g. 'Справочник.Валюты'",
                    required=True,
                ),
            ],
        ),
        (
            "For {metadata_object}: "
            "1) get_metadata with name_mask and meta_type derived from the "
            "object name. "
            "2) get_access_rights. "
            "3) graph_search + graph_related to show connected objects. "
            "4) bsl_search_tool for the object name to list usages. "
            "Summarise. Do NOT invent attributes — rely on tool output."
        ),
    ),
    (
        Prompt(
            name="safe_query",
            description=(
                "Validate a 1C query, explain it, then run it with a small "
                "limit. Stop if validation fails."
            ),
            arguments=[
                PromptArgument(
                    name="query",
                    description="1C query in Russian or English BSL syntax",
                    required=True,
                ),
            ],
        ),
        (
            "For the query: {query}\n"
            "1) validate_query. If invalid, stop and report errors. "
            "2) explain what the query returns and which metadata it touches. "
            "3) execute_query with an implicit limit of 100 rows. "
            "4) summarise results for the user."
        ),
    ),
    (
        Prompt(
            name="find_usage",
            description=(
                "Find every place in the configuration where a symbol "
                "(procedure / function / object) is referenced."
            ),
            arguments=[
                PromptArgument(
                    name="symbol",
                    description="Function, procedure or metadata object name",
                    required=True,
                ),
            ],
        ),
        (
            "To locate usages of '{symbol}': "
            "1) symbol_explore query='{symbol}'. "
            "2) for each match, run hover/definition to confirm the API. "
            "3) find_references_to_object (if it looks like a metadata ref). "
            "4) bsl_search_tool '{symbol}' for raw text hits. "
            "Present results grouped by file."
        ),
    ),
    (
        Prompt(
            name="bsp_api",
            description=(
                "Answer a 'how do I solve X with BSP (Standard Subsystems "
                "Library)' question using its_search, local BSL sources, and "
                "BSP skill packs."
            ),
            arguments=[
                PromptArgument(
                    name="task",
                    description="What the developer wants to achieve",
                    required=True,
                ),
            ],
        ),
        (
            "Answer a BSP-how-to for: {task}\n"
            "1) if its_search tool exists, call it first (official ИТС API). "
            "2) bsl_search_tool for candidate BSP common-module names to find "
            "working usages in the current config. "
            "3) for the most relevant function — hover/definition to read its "
            "doc-comment. "
            "4) compose an answer with links/paths to sources, then provide a "
            "ready-to-paste BSL snippet based on what you saw, NOT memory."
        ),
    ),
    (
        Prompt(
            name="reindex_after_export",
            description=(
                "Rebuild BSL indexes and dependency graph after a fresh "
                "export_bsl_sources run."
            ),
            arguments=[],
        ),
        (
            "Post-export refresh sequence: "
            "1) get_export_status — confirm status=done. "
            "2) bsl_index (re-populates full-text index). "
            "3) reindex_bsl (triggers LSP to re-parse). "
            "4) graph_stats — confirm totalNodes increased (if graph is up)."
        ),
    ),
]


@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [prompt for prompt, _body in _PROMPTS]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    for prompt, body in _PROMPTS:
        if prompt.name == name:
            args = arguments or {}
            try:
                text = body.format(**args)
            except KeyError:
                text = body
            return GetPromptResult(
                description=prompt.description,
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=text),
                    )
                ],
            )
    raise ValueError(f"Unknown prompt: {name}")


# ---------------------------------------------------------------------------
# MCP Tools — list & dispatch
# ---------------------------------------------------------------------------

_ITS_SEARCH_TOOL = Tool(
    name="its_search",
    description=(
        "Search 1C ITS documentation and standard configurations via 1C:Naparnik API. "
        "Ask questions about 1C platform, BSP (Standard Subsystem Library), "
        "typical configurations, and best practices."
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
)


@server.list_tools()
async def list_tools() -> list[Tool]:
    tools = GW_TOOLS + (manager.get_all_tools() if manager is not None else [])
    if settings.naparnik_api_key:
        tools.append(_ITS_SEARCH_TOOL)
    return _dedupe_tools(tools)


def _get_session_active() -> 'DatabaseInfo | None':
    """Get active DatabaseInfo for the current session."""
    if manager is None or registry is None:
        return None
    sid = _get_session_id()
    db_name = manager.get_active_db(sid)
    if db_name:
        return registry.get(db_name)
    return registry.get_active()


def _get_connection_active(connection: str) -> 'DatabaseInfo | None':
    """Resolve DB runtime info from Ref=<db> when background work has no MCP session."""
    if registry is None:
        return None
    ref_name = ""
    for part in (connection or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key.strip().lower() == "ref":
            ref_name = value.strip()
            break
    if ref_name:
        db = registry.get(ref_name)
        if db is not None:
            return db
    return registry.get_active()


def _get_session_id() -> str | None:
    """Extract MCP session ID from the current request context."""
    try:
        from mcp.server.lowlevel.server import request_ctx
        ctx = request_ctx.get()
        if ctx.request:
            return ctx.request.headers.get("mcp-session-id")
    except (LookupError, AttributeError):
        pass
    return None


def _ok(text: str) -> CallToolResult:
    """Return a successful tool result."""
    return CallToolResult(content=[TextContent(type="text", text=text)])


def _err(text: str) -> CallToolResult:
    """Return a tool error result (isError=True per MCP spec)."""
    return CallToolResult(content=[TextContent(type="text", text=text)], isError=True)


def _result(text: str) -> CallToolResult:
    """Return ok or error based on ERROR prefix convention."""
    if text.startswith("ERROR"):
        return _err(text)
    return _ok(text)


def _epf_connectivity_error_for_tool(name: str, session_id: str | None) -> str | None:
    """Return user-facing error when a DB toolkit tool is called without connected EPF."""
    db_name = manager.get_active_db(session_id)
    if not db_name:
        return None

    db = registry.get(db_name)
    if db is None:
        return None

    registry.expire_stale_epf(settings.epf_heartbeat_ttl_seconds)
    backend = manager.get_backend_for_tool(name, session_id=session_id)
    db_toolkit = manager.get_db_backend(db_name, "toolkit")
    if backend is db_toolkit and not db.connected:
        return (
            f"ERROR: EPF for database '{db_name}' is not connected. "
            "Open MCPToolkit.epf in this base and click 'Подключиться'."
        )
    return None


def _ensure_active_bsl_search_index_loaded() -> bool:
    active = _get_session_active()
    if not active:
        return bsl_search.indexed

    project_path = getattr(active, "project_path", "").strip()
    if not project_path:
        return bsl_search.indexed

    target = (
        f"{active.lsp_container}:{project_path}"
        if getattr(active, "lsp_container", "")
        else project_path
    )
    return bsl_search.ensure_loaded(target) or bsl_search.ensure_loaded(project_path)


def _resolve_export_output_dir(connection: str, output_dir: str) -> str:
    """Resolve MCP export placeholders to a concrete host path when possible."""
    normalized = (output_dir or "").strip() or "/projects"
    placeholders = {"/projects", "/workspace", (settings.bsl_workspace or "").rstrip("/")}
    if normalized not in placeholders:
        return normalized

    host_root = (settings.bsl_host_workspace or "").rstrip("/")
    if not host_root:
        legacy_root = (settings.bsl_workspace or "").rstrip("/")
        if legacy_root and legacy_root not in {"/projects", "/workspace"}:
            host_root = legacy_root
    if not host_root:
        return normalized

    ref_name = ""
    for part in connection.split(";"):
        if "=" in part and part.strip().lower().startswith("ref="):
            ref_name = part.split("=", 1)[1].strip()
            break

    db = registry.get(ref_name) if registry is not None and ref_name else None
    slug = (db.slug if db else None) or ref_name or None
    return f"{host_root}/{slug}" if slug else host_root


def _export_status_payload(connection: str | None = None) -> dict:
    if connection:
        export_job = _export_jobs.get(connection, {"status": "idle", "result": ""})
        index_job = _index_jobs.get(connection, {"status": "idle", "result": ""})
        return {
            "connection": connection,
            "status": export_job["status"],
            "result": export_job["result"],
            "index_status": index_job["status"],
            "index_result": index_job["result"],
        }

    jobs = {}
    for conn, job in _export_jobs.items():
        index_job = _index_jobs.get(conn, {"status": "idle", "result": ""})
        jobs[conn] = {
            "status": job["status"],
            "result": job["result"],
            "index_status": index_job["status"],
            "index_result": index_job["result"],
        }
    return {"jobs": jobs}


async def _sync_export_status_from_host(connection: str) -> None:
    """Refresh export status from host-side export service after gateway restarts."""
    if not settings.export_host_url or not connection:
        return

    status_url = settings.export_host_url.rstrip("/") + "/export-status"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(status_url, params={"connection": connection})
            data = resp.json()
    except Exception:
        return

    status = data.get("status", "")
    result = data.get("result", "")
    if status not in {"running", "done", "error"}:
        return

    _export_jobs[connection] = {"status": status, "result": result}

    if status == "done" and _index_jobs.get(connection, {}).get("status") != "done":
        output_dir = _resolve_export_output_dir(connection, "/projects")
        _index_jobs[connection] = {"status": "running", "result": ""}
        try:
            active = _get_session_active()
            index_ok, index_result = build_index_with_fallback(
                output_dir,
                build_index=bsl_search.build_index,
                active_db=active,
            )
            if index_ok:
                _index_jobs[connection] = {"status": "done", "result": index_result}
                await _auto_analyze_reports_for_db(_get_connection_active(connection), "host_export_status")
            else:
                _index_jobs[connection] = {"status": "error", "result": index_result}
        except Exception as exc:
            _index_jobs[connection] = {"status": "error", "result": str(exc)}


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    session_id = _get_session_id()

    if name == "get_server_status":
        return _ok(json.dumps(manager.status(), ensure_ascii=False, indent=2))

    if name == "export_bsl_sources":
        connection = arguments.get("connection", "")
        output_dir = _resolve_export_output_dir(
            connection,
            arguments.get("output_dir", "/projects"),
        )
        conn_key = connection.strip()
        if not conn_key:
            return _err("Field 'connection' is required")
        wait = bool(arguments.get("wait", False))
        if wait:
            result = await _run_export_bsl(connection, output_dir)
            return _result(result)

        if _export_jobs.get(conn_key, {}).get("status") == "running":
            return _err("Export already running for this database")

        _export_jobs[conn_key] = {"status": "running", "result": ""}

        async def _run_export_task() -> None:
            try:
                result = await _run_export_bsl(connection, output_dir)
                ok = not result.startswith("ERROR") and not result.startswith("Export failed")
                _export_jobs[conn_key] = {"status": "done" if ok else "error", "result": result}
            except asyncio.CancelledError:
                _export_jobs[conn_key] = {"status": "cancelled", "result": "Выгрузка отменена пользователем."}
                raise
            except Exception as exc:
                _export_jobs[conn_key] = {"status": "error", "result": str(exc)}
            finally:
                _export_tasks.pop(conn_key, None)

        _export_tasks[conn_key] = asyncio.create_task(_run_export_task())
        return _ok(
            "Export started in background. "
            "Use get_export_status with the same connection string to track progress."
        )

    if name == "get_export_status":
        connection = (arguments.get("connection", "") or "").strip()
        if connection:
            await _sync_export_status_from_host(connection)
        return _ok(json.dumps(_export_status_payload(connection or None), ensure_ascii=False, indent=2))

    if name == "connect_database":
        result = await _connect_database(
            arguments["name"], arguments["connection"], arguments["project_path"]
        )
        # Set new DB as active for this session
        if not result.startswith("ERROR") and session_id:
            manager.switch_db(arguments["name"], session_id=session_id)
        return _result(result)

    if name == "list_databases":
        registry.expire_stale_epf(settings.epf_heartbeat_ttl_seconds)
        dbs = registry.list()
        active_db = manager.get_active_db(session_id) or registry.active_name
        for db in dbs:
            db["active"] = db["name"] == active_db
        return _ok(json.dumps(dbs, ensure_ascii=False, indent=2))

    if name == "switch_database":
        db_name = arguments["name"]
        if manager.switch_db(db_name, session_id=session_id):
            return _ok(f"Switched to database: {db_name}")
        return _err(f"Database '{db_name}' not found. Use list_databases() to see registered databases.")

    if name == "disconnect_database":
        return _result(await _disconnect_database(arguments["name"]))

    if name == "validate_query":
        return _ok(await _validate_query(arguments.get("query", "")))

    if name == "reindex_bsl":
        return _result(await _reindex_bsl(arguments.get("path", "")))

    report_result = await try_handle_report_tool(
        name,
        arguments,
        registry=registry,
        manager=manager,
    )
    if report_result is not None:
        return _ok(report_result)

    graph_result = await try_handle_graph_tool(
        name,
        arguments,
        _graph_request,
        active_db=manager.get_active_db(session_id),
    )
    if graph_result is not None:
        return _result(graph_result)

    # --- Write BSL ---
    if name == "write_bsl":
        return _result(await _write_bsl(
            arguments.get("file", ""), arguments.get("content", ""),
        ))

    # --- BSL Search ---
    if name == "bsl_index":
        active = _get_session_active()
        path = (
            arguments.get("path", "").strip()
            or (getattr(active, "project_path", "") if active else "")
            or "/projects"
        )
        active = _get_session_active()
        container = active.lsp_container if active else ""
        result = bsl_search.build_index(path, container=container)
        if not str(result).startswith("ERROR"):
            await _auto_analyze_reports_for_db(active, "bsl_index")
        return _result(result)
    if name == "bsl_search_tool":
        _ensure_active_bsl_search_index_loaded()
        results = bsl_search.search(
            arguments.get("query", ""),
            limit=arguments.get("limit", 20),
            export_only=arguments.get("export_only", False),
        )
        if not results:
            if not bsl_search.indexed:
                return _err("Index not built. Run bsl_index first.")
            return _ok("No results found.")
        return _ok(json.dumps(results, ensure_ascii=False, indent=2))

    # --- Anonymization ---
    if name == "enable_anonymization":
        return _ok(anonymizer.enable())
    if name == "disable_anonymization":
        return _ok(anonymizer.disable())

    # --- ITS Search ---
    if name == "its_search":
        return _result(await _its_search(arguments.get("query", "")))

    # --- Metadata cache ---
    if name == "invalidate_metadata_cache":
        return _ok(metadata_cache.invalidate())

    # --- Query profiling ---
    if name == "query_stats":
        return _ok(json.dumps(profiler.get_stats(), ensure_ascii=False, indent=2))

    if name == "get_bsl_syntax_help":
        return _ok(
            _search_syntax_reference(
                arguments.get("keywords", []),
                limit=arguments.get("limit", 20),
            )
        )

    # --- Metadata cache check ---
    if name == "get_metadata" and settings.metadata_cache_ttl > 0:
        cached = metadata_cache.get(arguments)
        if cached is not None:
            return _ok(cached)

    # --- EPF connectivity precheck for per-DB toolkit tools ---
    epf_error = _epf_connectivity_error_for_tool(name, session_id)
    if epf_error is not None:
        return _err(epf_error)

    # --- Proxy to backend with profiling + anonymization ---
    t0 = time.monotonic()
    result: CallToolResult = await manager.call_tool(name, arguments, session_id=session_id)
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
        return CallToolResult(content=[TextContent(type="text", text=response_text)])

    # Metadata caching for get_metadata
    if name == "get_metadata":
        response_text = result.content[0].text if result.content else ""
        metadata_cache.put(arguments, response_text)
        return result

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
        return CallToolResult(content=processed)

    return result


# ---------------------------------------------------------------------------
# validate_query
# ---------------------------------------------------------------------------

def _validate_query_static(query: str) -> tuple[bool, list[str], list[str]]:
    return _validate_query_static_impl(query)


def _add_limit_zero(query: str) -> str:
    return _add_limit_zero_impl(query)


async def _validate_query(query: str) -> str:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return await _validate_query_impl(
        query=query,
        get_active=_get_session_active,
        get_toolkit=lambda: manager.get_backend_for_tool("execute_query", session_id=_get_session_id()),
    )


# ---------------------------------------------------------------------------
# BSL re-indexing
# ---------------------------------------------------------------------------

async def _reindex_bsl(path: str) -> str:
    # Backward-compatible wrapper kept for existing tests and integrations.
    result = await _reindex_bsl_impl(
        path=path,
        get_active=_get_session_active,
        has_tool=manager.has_tool,
        call_tool=manager.call_tool,
        build_search_index=bsl_search.build_index,
    )
    if not result.startswith("ERROR"):
        await _auto_analyze_reports_for_db(_get_session_active(), "reindex_bsl")
    return result


async def _auto_analyze_reports_for_db(db, reason: str) -> None:
    """Best-effort report catalog refresh after export/index lifecycle events."""
    if not settings.report_auto_analyze_enabled:
        return
    if db is None:
        return
    database = str(getattr(db, "name", "") or "").strip()
    project_path = str(getattr(db, "project_path", "") or "").strip()
    if not database or not project_path:
        return
    try:
        summary = await rebuild_report_catalog_for_db_info(database, db)
        log.info("Report catalog refreshed after %s: %s", reason, summary)
    except Exception as exc:
        log.info("Skipping report catalog refresh after %s for %s: %s", reason, database, exc)


# ---------------------------------------------------------------------------
# bsl-graph REST wrapper
# ---------------------------------------------------------------------------

async def _graph_request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> str:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return await _graph_request_impl(
        settings.bsl_graph_url,
        method,
        path,
        body=body,
        params=params,
    )


# ---------------------------------------------------------------------------
# Write BSL
# ---------------------------------------------------------------------------

async def _write_bsl(file: str, content: str) -> str:
    # Backward-compatible wrapper kept for existing tests and integrations.
    from .docker_manager import write_lsp_file

    return await _write_bsl_impl(
        file=file,
        content=content,
        get_active=_get_session_active,
        has_tool=manager.has_tool,
        call_tool=manager.call_tool,
        write_via_runtime=write_lsp_file,
    )


# ---------------------------------------------------------------------------
# ITS Search via 1C:Naparnik
# ---------------------------------------------------------------------------

async def _its_search(query: str) -> str:
    # Backward-compatible wrapper kept for existing tests and integrations.
    return await _its_search_impl(query, settings.naparnik_api_key)


# ---------------------------------------------------------------------------
# Database management
# ---------------------------------------------------------------------------

async def _connect_database(name: str, connection: str, project_path: str) -> str:
    from .docker_manager import start_toolkit, start_lsp
    from .backends.docker_control_lsp_backend import DockerControlLspBackend
    from .backends.http_backend import HttpBackend

    normalized_project_path = (project_path or "").strip()
    if normalized_project_path.startswith("/home/"):
        normalized_project_path = "/hostfs-home/" + normalized_project_path[len("/home/") :]

    # Backward-compatible wrapper kept for existing tests and integrations.
    result = await _connect_database_impl(
        name=name,
        connection=connection,
        project_path=normalized_project_path,
        registry=registry,
        manager=manager,
        db_name_re=_DB_NAME_RE,
        slugify=_slugify,
        start_toolkit=start_toolkit,
        start_lsp=start_lsp,
        http_backend_factory=HttpBackend,
        lsp_backend_factory=lambda backend_name, backend_slug, backend_project_path: DockerControlLspBackend(
            backend_name,
            backend_slug,
            project_path=backend_project_path,
        ),
    )
    if not result.startswith("ERROR"):
        await _auto_analyze_reports_for_db(registry.get(name), "connect_database")
    return result


async def _disconnect_database(name: str) -> str:
    from .docker_manager import stop_db_containers

    # Backward-compatible wrapper kept for existing tests and integrations.
    return await _disconnect_database_impl(
        name=name,
        registry=registry,
        manager=manager,
        stop_db_containers=stop_db_containers,
        mark_epf_disconnected=None,
    )

"""MCP tool handlers for user-facing 1C report discovery and execution."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from mcp.types import Tool

from ..config import settings
from ..naparnik_client import NaparnikClient
from ..report_analyzer import ReportAnalyzer
from ..report_catalog import ReportCatalog
from ..report_docs import build_report_doc_query, parse_report_doc_response
from ..report_runner import ReportRunner, ToolkitReportTransport


REPORT_TOOL_NAMES = {
    "analyze_reports",
    "enrich_report_docs",
    "find_reports",
    "list_reports",
    "describe_report",
    "run_report",
    "validate_all_reports",
    "get_report_result",
    "explain_report_strategy",
}

_DEFAULT_CATALOG: ReportCatalog | None = None


def get_default_catalog() -> ReportCatalog:
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = ReportCatalog()
    return _DEFAULT_CATALOG


def _int_arg(arguments: dict, key: str, default: int) -> int:
    value = arguments.get(key, default)
    if value in (None, ""):
        return default
    return int(value)


def _float_arg(arguments: dict, key: str, default: float) -> float:
    value = arguments.get(key, default)
    if value in (None, ""):
        return default
    return float(value)


async def load_report_graph_hints(database: str, graph_url: str | None = None) -> dict:
    """Best-effort bsl-graph snapshot for report analysis.

    Report cataloging must work without bsl-graph, so every error is converted
    into diagnostics instead of failing analysis.
    """
    base_url = (settings.bsl_graph_url if graph_url is None else graph_url or "").strip()
    if not base_url:
        return {"available": False, "nodes": [], "edges": [], "error": "bsl-graph disabled"}

    nodes: list[dict] = []
    edges: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            for payload in (
                {"query": "", "types": ["report", "commonModule"], "limit": 200, "dbs": [database]},
                {"query": "ЗарплатаКадрыОтчеты", "types": ["commonModule"], "limit": 20, "dbs": [database]},
            ):
                response = await client.post(base_url.rstrip("/") + "/api/graph/search", json=payload)
                response.raise_for_status()
                data = response.json()
                nodes.extend(item for item in data.get("nodes", []) if isinstance(item, dict))
                edges.extend(item for item in data.get("edges", []) if isinstance(item, dict))
    except Exception as exc:
        return {"available": False, "nodes": [], "edges": [], "error": str(exc)}

    return {"available": True, "nodes": _dedupe_nodes(nodes), "edges": _dedupe_edges(edges), "error": ""}


async def rebuild_report_catalog_for_db_info(
    database: str,
    db,
    *,
    catalog: ReportCatalog | None = None,
    graph_url: str | None = None,
) -> dict:
    """Analyze reports for one explicit DB using static BSL/XML + graph hints."""
    catalog = catalog or get_default_catalog()
    graph_hints = await load_report_graph_hints(database, graph_url=graph_url)
    project_path = _resolve_readable_project_path(database, db)
    return ReportAnalyzer(catalog, graph_hints=graph_hints).analyze_database(database, project_path)


def report_tools() -> list[Tool]:
    return [
        Tool(
            name="analyze_reports",
            description="Build or rebuild the per-database report catalog from exported BSL/XML sources.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "force": {"type": "boolean", "default": False}},
                "required": ["database"],
            },
        ),
        Tool(
            name="enrich_report_docs",
            description="Fetch and cache ITS/1C:Naparnik descriptions for cataloged reports to improve accountant-facing search and strategy diagnostics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "query": {"type": "string", "default": ""},
                    "title": {"type": "string"},
                    "report": {"type": "string"},
                    "variant": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "force": {"type": "boolean", "default": False},
                },
                "required": ["database"],
            },
        ),
        Tool(
            name="find_reports",
            description="Find 1C reports by user-facing title, alias, variant, or technical name.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "default": 10}},
                "required": ["database", "query"],
            },
        ),
        Tool(
            name="list_reports",
            description="List cataloged reports for an explicit database.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "query": {"type": "string", "default": ""}, "limit": {"type": "integer", "default": 50}},
                "required": ["database"],
            },
        ),
        Tool(
            name="describe_report",
            description="Resolve a user-facing report title to technical report, variant, params, and launch strategies.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "title": {"type": "string"},
                    "report": {"type": "string"},
                    "variant": {"type": "string"},
                    "include_diagnostics": {"type": "boolean", "default": False},
                },
                "required": ["database"],
            },
        ),
        Tool(
            name="run_report",
            description="Run a 1C report by accountant-facing title or exact technical report name against an explicit database.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "title": {"type": "string"},
                    "report": {"type": "string"},
                    "variant": {"type": "string"},
                    "period": {"type": "object"},
                    "filters": {"type": "object", "default": {}},
                    "params": {"type": "object", "default": {}},
                    "context": {"type": "object", "default": {}},
                    "output": {"type": "string", "default": "rows"},
                    "strategy": {"type": "string", "default": "auto"},
                    "wait": {"type": "boolean", "default": True},
                    "max_rows": {"type": "integer", "default": settings.report_run_default_max_rows},
                    "timeout_seconds": {"type": "number", "default": settings.report_run_default_timeout_seconds},
                },
                "required": ["database"],
            },
        ),
        Tool(
            name="validate_all_reports",
            description="Sequentially validate every cataloged report/variant for one database, executing available strategies and recording unsupported diagnostics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "analyze": {"type": "boolean", "default": False},
                    "include_unsupported": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 0},
                    "period": {"type": "object"},
                    "strategy": {"type": "string", "default": "auto"},
                    "max_rows": {"type": "integer", "default": settings.report_validate_default_max_rows},
                    "timeout_seconds": {"type": "number", "default": settings.report_validate_default_timeout_seconds},
                },
                "required": ["database"],
            },
        ),
        Tool(
            name="get_report_result",
            description="Fetch a stored report run result page.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "run_id": {"type": "string"}, "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 1000}},
                "required": ["database", "run_id"],
            },
        ),
        Tool(
            name="explain_report_strategy",
            description="Explain why the gateway selected a report launch strategy.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "title": {"type": "string"}},
                "required": ["database", "title"],
            },
        ),
    ]


async def try_handle_report_tool(
    name: str,
    arguments: dict,
    *,
    registry,
    manager,
    catalog: ReportCatalog | None = None,
) -> str | None:
    if name not in REPORT_TOOL_NAMES:
        return None
    catalog = catalog or get_default_catalog()
    database = str(arguments.get("database") or "").strip()
    db = registry.get(database) if registry is not None and database else None
    if db is None:
        return _dump({"ok": False, "error_code": "database_not_found", "error": f"Database '{database}' is not registered"})

    if name == "analyze_reports":
        return _dump(await rebuild_report_catalog_for_db_info(database, db, catalog=catalog))
    if name == "enrich_report_docs":
        return _dump(await enrich_report_docs(
            database,
            catalog,
            query=str(arguments.get("query") or ""),
            title=arguments.get("title"),
            report=arguments.get("report"),
            variant=arguments.get("variant"),
            limit=int(arguments.get("limit") or 10),
            force=bool(arguments.get("force", False)),
        ))
    if name == "find_reports":
        return _dump({"ok": True, "data": catalog.find_reports(database, str(arguments.get("query") or ""), int(arguments.get("limit") or 10))})
    if name == "list_reports":
        return _dump({"ok": True, "data": catalog.list_reports(database, str(arguments.get("query") or ""), int(arguments.get("limit") or 50))})
    if name == "describe_report":
        return _dump(await _describe_report_with_lazy_analysis(
            catalog,
            database,
            db,
            title=arguments.get("title"),
            report=arguments.get("report"),
            variant=arguments.get("variant"),
        ))
    if name == "get_report_result":
        return _dump(catalog.get_report_result(
            database,
            str(arguments.get("run_id") or ""),
            int(arguments.get("offset") or 0),
            int(arguments.get("limit") or 1000),
        ))
    if name == "explain_report_strategy":
        described = await _describe_report_with_lazy_analysis(
            catalog,
            database,
            db,
            title=str(arguments.get("title") or ""),
        )
        return _dump({**described, "explanation": _explain(described)})

    if name == "validate_all_reports":
        if bool(arguments.get("analyze", False)):
            await rebuild_report_catalog_for_db_info(database, db, catalog=catalog)
        if not getattr(db, "connected", False):
            return _dump({"ok": False, "error_code": "toolkit_not_connected", "error": f"EPF for database '{database}' is not connected"})
        return _dump(await validate_all_reports(
            database,
            catalog,
            ReportRunner(catalog, ToolkitReportTransport(manager)),
            include_unsupported=bool(arguments.get("include_unsupported", True)),
            limit=int(arguments.get("limit") or 0),
            period=arguments.get("period"),
            strategy=str(arguments.get("strategy") or "auto"),
            max_rows=_int_arg(arguments, "max_rows", settings.report_validate_default_max_rows),
            timeout_seconds=_float_arg(arguments, "timeout_seconds", float(settings.report_validate_default_timeout_seconds)),
        ))

    await _describe_report_with_lazy_analysis(
        catalog,
        database,
        db,
        title=str(arguments.get("title") or ""),
        report=arguments.get("report"),
        variant=arguments.get("variant"),
    )
    if not getattr(db, "connected", False):
        return _dump({"ok": False, "error_code": "toolkit_not_connected", "error": f"EPF for database '{database}' is not connected"})
    runner = ReportRunner(catalog, ToolkitReportTransport(manager))
    result = await runner.run_report(
        database=database,
        title=str(arguments.get("title") or ""),
        report=arguments.get("report"),
        variant=arguments.get("variant"),
        period=arguments.get("period"),
        filters=arguments.get("filters") or {},
        params=arguments.get("params") or {},
        context=arguments.get("context") or {},
        output=str(arguments.get("output") or "rows"),
        strategy=str(arguments.get("strategy") or "auto"),
        wait=bool(arguments.get("wait", True)),
        max_rows=_int_arg(arguments, "max_rows", settings.report_run_default_max_rows),
        timeout_seconds=_float_arg(arguments, "timeout_seconds", float(settings.report_run_default_timeout_seconds)),
    )
    return _dump(result)


async def _describe_report_with_lazy_analysis(
    catalog: ReportCatalog,
    database: str,
    db,
    *,
    title: str | None = None,
    report: str | None = None,
    variant: str | None = None,
) -> dict:
    described = catalog.describe_report(database, title=title, report=report, variant=variant)
    if described.get("ok") or described.get("error_code") != "report_not_found":
        return described
    summary = await rebuild_report_catalog_for_db_info(database, db, catalog=catalog)
    refreshed = catalog.describe_report(database, title=title, report=report, variant=variant)
    if refreshed.get("ok"):
        refreshed["analysis"] = summary
    return refreshed


async def validate_all_reports(
    database: str,
    catalog: ReportCatalog,
    runner: ReportRunner,
    *,
    include_unsupported: bool = True,
    limit: int = 0,
    period: dict | None = None,
    strategy: str = "auto",
    max_rows: int = 5,
    timeout_seconds: float = 60,
) -> dict:
    targets = _validation_targets(catalog, database)
    if limit > 0:
        targets = targets[:limit]
    counts = {"done": 0, "needs_input": 0, "error": 0, "unsupported": 0}
    items: list[dict] = []
    for target in targets:
        described = catalog.describe_report(database, report=target["report"], variant=target.get("variant", ""))
        strategies = described.get("strategies") or []
        if not strategies:
            if not include_unsupported:
                continue
            run_id = catalog.create_run(
                database=database,
                report_name=target["report"],
                variant_key=target.get("variant", ""),
                title=target.get("title") or target["report"],
                strategy="",
                params={"bulk_validation": True},
            )
            diagnostics = {"report": described.get("report", target), "reason": "No executable report strategy is available"}
            catalog.finish_run(database, run_id, status="unsupported", diagnostics=diagnostics, error=diagnostics["reason"])
            counts["unsupported"] += 1
            items.append(
                {
                    "database": database,
                    "report": target["report"],
                    "variant": target.get("variant", ""),
                    "title": target.get("title") or target["report"],
                    "status": "unsupported",
                    "run_id": run_id,
                    "error": diagnostics["reason"],
                    "kind": target.get("kind", ""),
                }
            )
            continue

        result = await runner.run_report(
            database=database,
            title="",
            report=target["report"],
            variant=target.get("variant", ""),
            period=period,
            filters={},
            params={},
            strategy=strategy,
            wait=True,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
        )
        if result.get("ok"):
            status = "done"
        elif result.get("error_code") in {"required_context", "parameter_request"}:
            status = "needs_input"
        elif result.get("error_code") in {"unsupported_runtime", "report_timeout"}:
            status = "unsupported"
        else:
            status = "error"
        counts[status] += 1
        items.append(
            {
                "database": database,
                "report": target["report"],
                "variant": target.get("variant", ""),
                "title": target.get("title") or target["report"],
                "status": status,
                "run_id": result.get("run_id", ""),
                "error_code": result.get("error_code"),
                "error": result.get("error"),
                "missing": result.get("missing"),
                "required_context": result.get("required_context"),
                "rows": len(result.get("rows") or []) if isinstance(result.get("rows"), list) else None,
                "warnings": result.get("warnings") or [],
            }
        )
    return {"ok": True, "database": database, "total": len(items), "counts": counts, "items": items}


def _validation_targets(catalog: ReportCatalog, database: str) -> list[dict]:
    """Return one validation target per report, preferring executable aliases."""
    rows = catalog.list_reports(database, limit=1_000_000)
    rows.sort(key=lambda item: (item.get("status") != "supported", item.get("report", ""), item.get("variant", "")))
    targets: dict[str, dict] = {}
    for row in rows:
        report = str(row.get("report") or "")
        if not report or report in targets:
            continue
        targets[report] = row
    return list(targets.values())


async def enrich_report_docs(
    database: str,
    catalog: ReportCatalog,
    *,
    query: str = "",
    title: str | None = None,
    report: str | None = None,
    variant: str | None = None,
    limit: int = 10,
    force: bool = False,
) -> dict:
    api_key = settings.naparnik_api_key
    if not api_key:
        return {
            "ok": False,
            "error_code": "naparnik_not_configured",
            "error": "NAPARNIK_API_KEY is not configured",
        }

    targets = _select_doc_targets(catalog, database, query=query, title=title, report=report, variant=variant, limit=limit)
    client = NaparnikClient(api_key)
    items: list[dict] = []
    fetched = 0
    skipped = 0
    errors = 0
    for target in targets[: max(0, limit)]:
        docs = catalog.get_report_docs(database, target["report"], target.get("variant", ""))
        if docs and not force:
            skipped += 1
            items.append({"report": target["report"], "variant": target.get("variant", ""), "status": "skipped_existing"})
            continue
        doc_query = build_report_doc_query(database, target)
        content = await client.search(doc_query)
        parsed = parse_report_doc_response(content, fallback_title=str(target.get("title") or ""))
        error = content if content.startswith("ERROR:") else ""
        if error:
            errors += 1
        else:
            fetched += 1
        catalog.upsert_report_doc(
            database=database,
            report_name=target["report"],
            variant_key=target.get("variant", ""),
            source="naparnik",
            query=doc_query,
            content=content,
            parsed=parsed,
            error=error,
        )
        items.append(
            {
                "report": target["report"],
                "variant": target.get("variant", ""),
                "title": parsed.get("title") or target.get("title") or "",
                "status": "error" if error else "fetched",
                "aliases": parsed.get("aliases") or [],
            }
        )
    return {
        "ok": errors == 0,
        "database": database,
        "fetched": fetched,
        "skipped": skipped,
        "errors": errors,
        "items": items,
    }


def _select_doc_targets(
    catalog: ReportCatalog,
    database: str,
    *,
    query: str = "",
    title: str | None = None,
    report: str | None = None,
    variant: str | None = None,
    limit: int = 10,
) -> list[dict]:
    if report or title:
        described = catalog.describe_report(database, title=title, report=report, variant=variant)
        if described.get("ok"):
            return [described["report"]]
        return _dedupe_report_targets(described.get("candidates") or [])[: max(0, limit)]
    if query:
        return _dedupe_report_targets(catalog.find_reports(database, query, limit=max(1, limit)))
    return _dedupe_report_targets(catalog.list_reports(database, limit=max(1, limit)))


def _dedupe_report_targets(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen = set()
    for row in rows:
        key = (row.get("report"), row.get("variant", ""))
        if not key[0] or key in seen:
            continue
        result.append(row)
        seen.add(key)
    return result


def _explain(described: dict) -> str:
    if not described.get("ok"):
        return described.get("error_code", "report is not resolved")
    strategies = described.get("strategies") or []
    if not strategies:
        return "No executable strategy is cataloged for this report."
    first = strategies[0]
    return f"Selected {first.get('strategy')} with priority {first.get('priority')} and confidence {first.get('confidence')}."


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _resolve_readable_project_path(database: str, db) -> Path:
    """Pick a BSL project path readable by the non-root gateway process."""
    raw_project_path = str(getattr(db, "project_path", "") or "").strip()
    candidates = _project_path_candidates(database, raw_project_path, str(getattr(db, "slug", "") or ""))
    for candidate in candidates:
        reports = candidate / "Reports"
        try:
            if reports.is_dir():
                # Force a directory read: is_dir() can be true while traversal is denied.
                next(reports.iterdir(), None)
                return candidate
        except PermissionError:
            continue
        except OSError:
            continue
    return candidates[0] if candidates else Path(raw_project_path or ".")


def _project_path_candidates(database: str, project_path: str, slug: str = "") -> list[Path]:
    candidates: list[Path] = []

    def add(value: str) -> None:
        if not value:
            return
        path = Path(value)
        if path not in candidates:
            candidates.append(path)

    add(project_path)

    workspace = (settings.bsl_workspace or "/workspace").rstrip("/")
    host_workspace = (settings.bsl_host_workspace or "").rstrip("/")
    if project_path and host_workspace and workspace:
        hostfs_workspace = _host_to_hostfs_path(host_workspace).rstrip("/")
        for prefix in (host_workspace, hostfs_workspace):
            if prefix and (project_path == prefix or project_path.startswith(prefix + "/")):
                add(workspace + project_path[len(prefix):])

    for name in (slug, database):
        if name and workspace:
            add(workspace + "/" + name)

    return candidates


def _host_to_hostfs_path(host_path: str) -> str:
    if host_path == "/home":
        return "/hostfs-home"
    if host_path.startswith("/home/"):
        return "/hostfs-home/" + host_path[len("/home/"):]
    return host_path


def _dedupe_nodes(nodes: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for node in nodes:
        key = str(node.get("id") or "")
        if not key or key in seen:
            continue
        result.append(node)
        seen.add(key)
    return result


def _dedupe_edges(edges: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for edge in edges:
        key = (
            str(edge.get("sourceId") or ""),
            str(edge.get("targetId") or ""),
            str(edge.get("type") or ""),
        )
        if key in seen:
            continue
        result.append(edge)
        seen.add(key)
    return result

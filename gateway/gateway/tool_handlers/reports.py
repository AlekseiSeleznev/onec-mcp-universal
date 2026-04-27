"""MCP tool handlers for user-facing 1C report discovery and execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
from mcp.types import Tool

from ..config import settings
from ..naparnik_client import NaparnikClient
from ..report_analyzer import ReportAnalyzer
from ..report_catalog import ReportCatalog, normalize_report_query
from ..report_contracts import build_observed_signature, build_verified_output_contract, compare_output_contract
from ..report_docs import build_report_doc_query, parse_report_doc_response
from ..report_fixtures import ReportFixtureProvider
from ..report_orchestrator import ReportEngineSettings, ReportOrchestrator
from ..report_result_extractor import ReportResultExtractor
from ..report_runner import ReportRunner, ToolkitReportTransport
from ..report_ui_runner import ReportUiRunner, WebTestReportClient


REPORT_TOOL_NAMES = {
    "analyze_reports",
    "enrich_report_docs",
    "find_reports",
    "list_reports",
    "describe_report",
    "run_report",
    "validate_all_reports",
    "validate_report_contracts",
    "get_report_result",
    "get_report_validation_campaign",
    "explain_report_strategy",
}

_DEFAULT_CATALOG: ReportCatalog | None = None
_VALIDATION_STOP_STATES = {"deferred_engine_gap", "deferred_analyzer_gap", "error"}


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
                    "runner": {"type": "string", "enum": ["auto", "api", "ui"], "default": "auto"},
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
            name="validate_report_contracts",
            description="Run heavy per-variant report contract validation, compare declared/verified structure to actual output, and persist a validation campaign.",
            inputSchema={
                "type": "object",
                "properties": {
                    "database": {"type": "string"},
                    "analyze": {"type": "boolean", "default": False},
                    "stop_on_mismatch": {"type": "boolean", "default": True},
                    "resume_campaign_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 0},
                    "max_targets_per_call": {"type": "integer", "default": 0},
                    "period": {"type": "object"},
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
            name="get_report_validation_campaign",
            description="Fetch a persisted heavy report validation campaign by campaign_id.",
            inputSchema={
                "type": "object",
                "properties": {"database": {"type": "string"}, "campaign_id": {"type": "string"}},
                "required": ["database", "campaign_id"],
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
    if name == "get_report_validation_campaign":
        return _dump(catalog.get_validation_campaign(str(arguments.get("campaign_id") or "")))
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
    if name == "validate_report_contracts":
        if bool(arguments.get("analyze", False)):
            await rebuild_report_catalog_for_db_info(database, db, catalog=catalog)
        if not getattr(db, "connected", False):
            return _dump({"ok": False, "error_code": "toolkit_not_connected", "error": f"EPF for database '{database}' is not connected"})
        transport = ToolkitReportTransport(manager)
        runner = ReportRunner(catalog, transport)
        fixture_provider = ReportFixtureProvider(transport)
        return _dump(await validate_report_contracts(
            database,
            catalog,
            runner,
            fixture_provider,
            stop_on_mismatch=bool(arguments.get("stop_on_mismatch", True)),
            resume_campaign_id=str(arguments.get("resume_campaign_id") or ""),
            limit=int(arguments.get("limit") or 0),
            max_targets_per_call=int(arguments.get("max_targets_per_call") or 0),
            period=arguments.get("period"),
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
    requested_runner = str(arguments.get("runner") or "auto").lower()
    api_enabled = bool(settings.report_api_runner_enabled)
    ui_enabled = bool(settings.report_ui_runner_enabled)
    if requested_runner != "ui" and api_enabled and not getattr(db, "connected", False):
        return _dump({"ok": False, "error_code": "toolkit_not_connected", "error": f"EPF for database '{database}' is not connected"})
    api_runner = ReportRunner(catalog, ToolkitReportTransport(manager)) if api_enabled and getattr(db, "connected", False) else None
    ui_runner = _build_ui_report_runner(catalog) if ui_enabled else None
    orchestrator = ReportOrchestrator(
        catalog=catalog,
        api_runner=api_runner,
        ui_runner=ui_runner,
        settings=ReportEngineSettings(
            api_enabled=api_enabled,
            ui_enabled=ui_enabled,
            ui_fallback_enabled=bool(settings.report_ui_fallback_enabled),
            ui_export_format=str(settings.report_ui_export_format or "xlsx"),
            keep_ui_error_artifacts=bool(settings.report_ui_keep_error_artifacts),
        ),
    )
    result = await orchestrator.run_report(
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
        runner=requested_runner,
        wait=bool(arguments.get("wait", True)),
        max_rows=_int_arg(arguments, "max_rows", settings.report_run_default_max_rows),
        timeout_seconds=_float_arg(arguments, "timeout_seconds", float(settings.report_run_default_timeout_seconds)),
    )
    return _dump(result)


def _build_ui_report_runner(catalog: ReportCatalog) -> ReportUiRunner:
    return ReportUiRunner(
        catalog=catalog,
        client=WebTestReportClient(
            run_mjs=settings.report_ui_runner_script,
            web_url_template=settings.report_ui_web_url_template,
        ),
        extractor=ReportResultExtractor(keep_error_artifacts=bool(settings.report_ui_keep_error_artifacts)),
        artifacts_dir=settings.report_ui_artifacts_dir,
    )


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


async def validate_report_contracts(
    database: str,
    catalog: ReportCatalog,
    runner: ReportRunner,
    fixture_provider: ReportFixtureProvider,
    *,
    stop_on_mismatch: bool = True,
    resume_campaign_id: str = "",
    limit: int = 0,
    max_targets_per_call: int = 0,
    period: dict | None = None,
    max_rows: int = 5,
    timeout_seconds: float = 60,
) -> dict:
    computed_targets = _contract_validation_targets(catalog, database)
    existing_campaign: dict = {}
    if resume_campaign_id:
        existing_campaign = catalog.get_validation_campaign(resume_campaign_id)
        if not existing_campaign.get("ok"):
            return existing_campaign
        if str(existing_campaign.get("database") or "") != database:
            return {
                "ok": False,
                "error_code": "campaign_database_mismatch",
                "error": f"Validation campaign '{resume_campaign_id}' belongs to '{existing_campaign.get('database')}', not '{database}'.",
            }
        targets = _merge_validation_order(list(existing_campaign.get("order") or []), computed_targets)
        if not targets:
            targets = computed_targets[:]
        if limit > 0:
            targets = targets[:limit]
        refreshed_fixture_pack = await fixture_provider.build_fixture_pack(database)
        fixture_pack = _merge_fixture_packs(existing_campaign.get("fixture_pack") or {}, refreshed_fixture_pack)
        campaign_id = resume_campaign_id
        catalog.update_validation_campaign_fixture_pack(campaign_id, fixture_pack)
        catalog.update_validation_campaign_order(campaign_id, targets)
        catalog.mark_validation_campaign_running(campaign_id)
        resume_from_ordinal = _resume_campaign_ordinal(existing_campaign)
    else:
        targets = computed_targets[:]
        if limit > 0:
            targets = targets[:limit]
        fixture_pack = await fixture_provider.build_fixture_pack(database)
        campaign_id = catalog.create_validation_campaign(
            database,
            mode="contracts",
            fixture_pack=fixture_pack,
            order=targets,
            stop_on_mismatch=stop_on_mismatch,
        )
        resume_from_ordinal = 1
    items: list[dict] = []
    stopped = False
    stop_reason = ""
    batch_limit_reached = False
    for ordinal, target in enumerate(targets, start=1):
        if ordinal < resume_from_ordinal:
            continue
        if max_targets_per_call > 0 and len(items) >= max_targets_per_call:
            batch_limit_reached = True
            stop_reason = "batch_limit"
            break
        described = catalog.describe_report(database, report=target["report"], variant=target.get("variant", ""))
        item = await _validate_contract_target(
            database,
            target,
            described,
            catalog,
            runner,
            fixture_provider,
            fixture_pack,
            period=period,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
        )
        terminal_state = str(item.get("terminal_state") or "")
        catalog.upsert_validation_item(
            campaign_id,
            ordinal=ordinal,
            database=database,
            report_name=target["report"],
            variant_key=target.get("variant", ""),
            title=target.get("title") or target["report"],
            status=terminal_state or "error",
            terminal_state=terminal_state or "error",
            strategy=str(item.get("strategy") or ""),
            run_id=str(item.get("run_id") or ""),
            contract_source=str(item.get("contract_source") or ""),
            contract_hash=str(item.get("contract_hash") or ""),
            observed=item.get("observed") or {},
            mismatch_code=str(item.get("mismatch_code") or ""),
            root_cause_class=str(item.get("root_cause_class") or ""),
            diagnostics=item.get("diagnostics") or {},
            error=str(item.get("error") or ""),
        )
        items.append(item)
        if stop_on_mismatch and terminal_state in _VALIDATION_STOP_STATES:
            stopped = True
            stop_reason = terminal_state
            break
    campaign_snapshot = catalog.summarize_validation_campaign(campaign_id)
    summary = dict(campaign_snapshot.get("summary") or {})
    summary["total_targets"] = len(targets)
    status = "stopped" if stopped else ("paused" if batch_limit_reached else "completed")
    catalog.finish_validation_campaign(
        campaign_id,
        status=status,
        counts=campaign_snapshot.get("counts") or {},
        summary=summary,
        stop_reason=stop_reason,
    )
    return {
        "ok": True,
        "database": database,
        "campaign_id": campaign_id,
        "fixture_pack": fixture_pack,
        "total": int(summary.get("processed") or 0),
        "processed_in_call": len(items),
        "counts": campaign_snapshot.get("counts") or {},
        "status": status,
        "stop_reason": stop_reason,
        "resume_from_ordinal": int(summary.get("resume_from_ordinal") or 1),
        "summary": summary,
        "items": items,
    }


def _resume_campaign_ordinal(campaign: dict) -> int:
    items = list(campaign.get("items") or [])
    if not items:
        return 1
    status = str(campaign.get("status") or "")
    if status == "stopped":
        stopper_ordinals = sorted(
            int(item.get("ordinal") or 0)
            for item in items
            if str(item.get("terminal_state") or item.get("status") or "") in _VALIDATION_STOP_STATES
        )
        if stopper_ordinals:
            return max(1, stopper_ordinals[0])
    return max(int(item.get("ordinal") or 0) for item in items) + 1


def _merge_fixture_packs(existing: dict, refreshed: dict) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    refreshed = refreshed if isinstance(refreshed, dict) else {}
    samples = dict(existing.get("samples") or {})
    samples.update({key: value for key, value in dict(refreshed.get("samples") or {}).items() if value not in (None, "")})
    context = dict(existing.get("context") or {})
    context.update({key: value for key, value in dict(refreshed.get("context") or {}).items() if value not in (None, "")})
    base_period = existing.get("period") if isinstance(existing.get("period"), dict) else {}
    new_period = refreshed.get("period") if isinstance(refreshed.get("period"), dict) else {}
    period = {
        "from": str(new_period.get("from") or base_period.get("from") or "2024-01-01"),
        "to": str(new_period.get("to") or base_period.get("to") or new_period.get("from") or base_period.get("from") or "2024-12-31"),
    }
    candidate_periods = []
    seen: set[tuple[str, str]] = set()
    for raw in list(refreshed.get("candidate_periods") or []) + list(existing.get("candidate_periods") or []):
        if not isinstance(raw, dict):
            continue
        date_from = str(raw.get("from") or raw.get("start") or "").strip()
        date_to = str(raw.get("to") or raw.get("end") or date_from).strip()
        if not date_from or not date_to:
            continue
        key = (date_from, date_to)
        if key in seen:
            continue
        seen.add(key)
        candidate_periods.append({"from": date_from, "to": date_to})
    diagnostics = dict(existing.get("diagnostics") or {})
    refreshed_diagnostics = dict(refreshed.get("diagnostics") or {})
    if refreshed_diagnostics:
        diagnostics.update(refreshed_diagnostics)
        diagnostics["resume_refresh"] = True
    return {
        "period": period,
        "candidate_periods": candidate_periods or [period],
        "samples": samples,
        "context": context,
        "diagnostics": diagnostics,
    }


def _merge_validation_order(existing: list[dict], computed: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row in list(existing or []) + list(computed or []):
        if not isinstance(row, dict):
            continue
        report = str(row.get("report") or "")
        variant = str(row.get("variant") or "")
        if not report:
            continue
        key = (report, variant)
        if key in seen:
            continue
        result.append(row)
        seen.add(key)
    return result


async def _validate_contract_target(
    database: str,
    target: dict,
    described: dict,
    catalog: ReportCatalog,
    runner: ReportRunner,
    fixture_provider: ReportFixtureProvider,
    fixture_pack: dict,
    *,
    period: dict | None,
    max_rows: int,
    timeout_seconds: float,
) -> dict:
    strategies = described.get("strategies") or []
    if not strategies:
        return {
            "database": database,
            "report": target["report"],
            "variant": target.get("variant", ""),
            "title": target.get("title") or target["report"],
            "terminal_state": "deferred_unsupported",
            "contract_source": "",
            "contract_hash": "",
            "root_cause_class": "no_strategy",
            "mismatch_code": "",
            "diagnostics": {"reason": "no_executable_strategy"},
            "error": "No executable report strategy is available",
        }
    chosen_contract = _choose_output_contract(described)
    contract = chosen_contract["contract"]
    contract_hash = hashlib.sha256(json.dumps(contract, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest() if contract else ""
    plan = fixture_provider.plan_inputs(described, fixture_pack, period_override=period)
    attempts: list[dict] = []
    for index, strategy in enumerate(strategies):
        strategy_name = str(strategy.get("strategy") or "auto")
        strategy_max_rows = max_rows
        result = await runner.run_report(
            database=database,
            report=target["report"],
            variant=target.get("variant", ""),
            period=plan.get("period"),
            filters=dict(plan.get("filters") or {}),
            params=dict(plan.get("params") or {}),
            context=dict(plan.get("context") or {}),
            strategy=strategy_name,
            wait=True,
            max_rows=strategy_max_rows,
            timeout_seconds=timeout_seconds,
        )
        resolved = await _retry_with_resolved_inputs(
            result,
            database,
            target,
            runner,
            fixture_provider,
            fixture_pack,
            plan,
            strategy=strategy_name,
            max_rows=strategy_max_rows,
            timeout_seconds=timeout_seconds,
        )
        result = resolved["result"]
        attempt = {
            "strategy": strategy.get("strategy"),
            "ok": bool(result.get("ok")),
            "error_code": result.get("error_code"),
            "run_id": result.get("run_id", ""),
        }
        if result.get("ok"):
            observed = result.get("observed_signature") or build_observed_signature(result)
            comparison = compare_output_contract(contract, observed) if contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
            if _should_retry_with_larger_limit(result, observed, comparison, strategy_max_rows):
                strategy_max_rows = _next_row_limit(result, observed, strategy_max_rows)
                retried = await runner.run_report(
                    database=database,
                    report=target["report"],
                    variant=target.get("variant", ""),
                    period=plan.get("period"),
                    filters=dict(plan.get("filters") or {}),
                    params=dict(plan.get("params") or {}),
                    context=dict(plan.get("context") or {}),
                    strategy=strategy_name,
                    wait=True,
                    max_rows=strategy_max_rows,
                    timeout_seconds=timeout_seconds,
                )
                if retried.get("ok"):
                    result = retried
                    observed = result.get("observed_signature") or build_observed_signature(result)
                    comparison = compare_output_contract(contract, observed) if contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
            if comparison.get("mismatch_code") in {"header_only", "missing_detail_rows"}:
                retried_filters = await _retry_with_candidate_filters(
                    database,
                    target,
                    runner,
                    fixture_provider,
                    fixture_pack,
                    plan,
                    strategy=strategy_name,
                    max_rows=strategy_max_rows,
                    timeout_seconds=timeout_seconds,
                    contract=contract,
                    result=result,
                    observed=observed,
                    comparison=comparison,
                )
                result = retried_filters["result"]
                observed = retried_filters["observed"]
                comparison = retried_filters["comparison"]
            if period is None and comparison.get("mismatch_code") in {"header_only", "missing_detail_rows"}:
                retried_period = await _retry_with_candidate_periods(
                    database,
                    target,
                    runner,
                    fixture_provider,
                    fixture_pack,
                    plan,
                    strategy=strategy_name,
                    max_rows=strategy_max_rows,
                    timeout_seconds=timeout_seconds,
                    contract=contract,
                    result=result,
                    observed=observed,
                    comparison=comparison,
                )
                result = retried_period["result"]
                observed = retried_period["observed"]
                comparison = retried_period["comparison"]
            attempt["comparison"] = comparison
            attempts.append(attempt)
            if comparison.get("matched"):
                return {
                    "database": database,
                    "report": target["report"],
                    "variant": target.get("variant", ""),
                    "title": target.get("title") or target["report"],
                    "terminal_state": "matched",
                    "strategy": strategy.get("strategy"),
                    "run_id": result.get("run_id", ""),
                    "contract_source": chosen_contract["source"],
                    "contract_hash": contract_hash,
                    "observed": observed,
                    "mismatch_code": "",
                    "root_cause_class": "strategy_ranking" if index > 0 else "",
                    "diagnostics": {"attempts": attempts, "comparison": comparison},
                    "error": "",
                }
            if comparison.get("acceptable_with_verified"):
                verified = build_verified_output_contract(observed, strategy_name=str(strategy.get("strategy") or ""))
                catalog.upsert_output_contract(database, target["report"], target.get("variant", ""), "verified", verified)
                return {
                    "database": database,
                    "report": target["report"],
                    "variant": target.get("variant", ""),
                    "title": target.get("title") or target["report"],
                    "terminal_state": "matched",
                    "strategy": strategy.get("strategy"),
                    "run_id": result.get("run_id", ""),
                    "contract_source": chosen_contract["source"],
                    "contract_hash": contract_hash,
                    "observed": observed,
                    "mismatch_code": "weak_declared_contract",
                    "root_cause_class": "analyzer_gap",
                    "diagnostics": {"attempts": attempts, "comparison": comparison},
                    "error": "",
                }
            attempt["observed"] = observed
            continue
        attempt["error"] = result.get("error", "")
        attempt["message"] = result.get("message", "")
        attempt["missing"] = list(result.get("missing") or [])
        attempt["required_context"] = list(result.get("required_context") or [])
        attempts.append(attempt)

    root_cause_class, terminal_state, mismatch_code, error = _classify_contract_attempts(attempts)
    observed = next((attempt.get("observed") for attempt in attempts if attempt.get("observed")), {})
    return {
        "database": database,
        "report": target["report"],
        "variant": target.get("variant", ""),
        "title": target.get("title") or target["report"],
        "terminal_state": terminal_state,
        "strategy": next((attempt.get("strategy") for attempt in attempts if attempt.get("strategy")), ""),
        "run_id": next((attempt.get("run_id") for attempt in attempts if attempt.get("run_id")), ""),
        "contract_source": chosen_contract["source"],
        "contract_hash": contract_hash,
        "observed": observed or {},
        "mismatch_code": mismatch_code,
        "root_cause_class": root_cause_class,
        "diagnostics": {"attempts": attempts},
        "error": error,
    }


def _should_retry_with_larger_limit(result: dict, observed: dict, comparison: dict, current_limit: int) -> bool:
    if comparison.get("mismatch_code") not in {"header_only", "missing_expected_columns", "semantic_mismatch"}:
        return False
    warnings = list(result.get("warnings") or observed.get("warnings") or [])
    if "Result truncated by max_rows." not in warnings:
        return False
    tabular_height = int((observed.get("metadata") or {}).get("tabular_height") or (result.get("metadata") or {}).get("tabular_height") or 0)
    return tabular_height > max(0, int(current_limit or 0))


def _next_row_limit(result: dict, observed: dict, current_limit: int) -> int:
    tabular_height = int((observed.get("metadata") or {}).get("tabular_height") or (result.get("metadata") or {}).get("tabular_height") or 0)
    if tabular_height > 0:
        return min(1000, max(tabular_height, current_limit))
    return min(1000, max(current_limit * 5, current_limit + 50, 100))


async def _retry_with_candidate_filters(
    database: str,
    target: dict,
    runner: ReportRunner,
    fixture_provider: ReportFixtureProvider,
    fixture_pack: dict,
    plan: dict,
    *,
    strategy: str,
    max_rows: int,
    timeout_seconds: float,
    contract: dict,
    result: dict,
    observed: dict,
    comparison: dict,
) -> dict:
    current_filters = dict(plan.get("filters") or {})
    if not current_filters:
        return {"result": result, "observed": observed, "comparison": comparison}
    candidate_getter = getattr(fixture_provider, "candidate_filter_values", None)
    if not callable(candidate_getter):
        return {"result": result, "observed": observed, "comparison": comparison}

    best_result = result
    best_observed = observed
    best_comparison = comparison
    best_score = float(comparison.get("score") or 0)

    for filter_name, current_value in current_filters.items():
        candidates = list(candidate_getter(fixture_pack, filter_name, current_value) or [])
        if not candidates:
            continue
        for candidate_value in candidates:
            candidate_filters = dict(current_filters)
            candidate_filters[filter_name] = candidate_value
            candidate_params = dict(plan.get("params") or {})
            if normalize_report_query(filter_name) == normalize_report_query("Организация"):
                for param_name in list(candidate_params):
                    if normalize_report_query(param_name) == normalize_report_query("Организация"):
                        candidate_params[param_name] = candidate_value
            retried = await runner.run_report(
                database=database,
                report=target["report"],
                variant=target.get("variant", ""),
                period=plan.get("period"),
                filters=candidate_filters,
                params=candidate_params,
                context=dict(plan.get("context") or {}),
                strategy=strategy,
                wait=True,
                max_rows=max_rows,
                timeout_seconds=timeout_seconds,
            )
            if not retried.get("ok"):
                continue
            candidate_observed = retried.get("observed_signature") or build_observed_signature(retried)
            candidate_comparison = compare_output_contract(contract, candidate_observed) if contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
            candidate_score = float(candidate_comparison.get("score") or 0)
            if candidate_comparison.get("matched") or candidate_comparison.get("acceptable_with_verified"):
                plan["filters"] = candidate_filters
                plan["params"] = candidate_params
                samples = fixture_pack.get("samples") if isinstance(fixture_pack.get("samples"), dict) else None
                if samples is not None and normalize_report_query(filter_name) == normalize_report_query("Организация"):
                    samples["organization"] = candidate_value
                return {"result": retried, "observed": candidate_observed, "comparison": candidate_comparison}
            if candidate_score > best_score:
                best_result = retried
                best_observed = candidate_observed
                best_comparison = candidate_comparison
                best_score = candidate_score
    return {"result": best_result, "observed": best_observed, "comparison": best_comparison}


async def _retry_with_candidate_periods(
    database: str,
    target: dict,
    runner: ReportRunner,
    fixture_provider: ReportFixtureProvider,
    fixture_pack: dict,
    plan: dict,
    *,
    strategy: str,
    max_rows: int,
    timeout_seconds: float,
    contract: dict,
    result: dict,
    observed: dict,
    comparison: dict,
) -> dict:
    best_result = result
    best_observed = observed
    best_comparison = comparison
    best_score = float(comparison.get("score") or 0)
    current_period = plan.get("period") if isinstance(plan.get("period"), dict) else {}
    for candidate_period in fixture_provider.candidate_periods(fixture_pack, current_period):
        if candidate_period == current_period:
            continue
        retried = await runner.run_report(
            database=database,
            report=target["report"],
            variant=target.get("variant", ""),
            period=candidate_period,
            filters=dict(plan.get("filters") or {}),
            params=dict(plan.get("params") or {}),
            context=dict(plan.get("context") or {}),
            strategy=strategy,
            wait=True,
            max_rows=max_rows,
            timeout_seconds=timeout_seconds,
        )
        if not retried.get("ok"):
            continue
        candidate_observed = retried.get("observed_signature") or build_observed_signature(retried)
        candidate_comparison = compare_output_contract(contract, candidate_observed) if contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
        candidate_score = float(candidate_comparison.get("score") or 0)
        if candidate_comparison.get("matched") or candidate_comparison.get("acceptable_with_verified"):
            plan["period"] = candidate_period
            return {"result": retried, "observed": candidate_observed, "comparison": candidate_comparison}
        if candidate_score > best_score:
            best_result = retried
            best_observed = candidate_observed
            best_comparison = candidate_comparison
            best_score = candidate_score
    return {"result": best_result, "observed": best_observed, "comparison": best_comparison}


async def _retry_with_resolved_inputs(
    result: dict,
    database: str,
    target: dict,
    runner: ReportRunner,
    fixture_provider: ReportFixtureProvider,
    fixture_pack: dict,
    plan: dict,
    *,
    strategy: str,
    max_rows: int,
    timeout_seconds: float,
) -> dict:
    if result.get("ok"):
        return {"result": result}
    if result.get("error_code") not in {"parameter_request", "required_context"}:
        return {"result": result}
    resolved = fixture_provider.resolve_missing(
        list(result.get("missing") or []),
        list(result.get("required_context") or []),
        fixture_pack,
    )
    if resolved["unresolved"] or (not resolved["params"] and not resolved["context"]):
        return {"result": result}
    merged_params = dict(plan.get("params") or {})
    merged_params.update(resolved["params"])
    merged_context = dict(plan.get("context") or {})
    merged_context.update(resolved["context"])
    retried = await runner.run_report(
        database=database,
        report=target["report"],
        variant=target.get("variant", ""),
        period=plan.get("period"),
        filters=dict(plan.get("filters") or {}),
        params=merged_params,
        context=merged_context,
        strategy=strategy,
        wait=True,
        max_rows=max_rows,
        timeout_seconds=timeout_seconds,
    )
    plan["params"] = merged_params
    plan["context"] = merged_context
    return {"result": retried}


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


def _contract_validation_targets(catalog: ReportCatalog, database: str) -> list[dict]:
    rows = catalog.list_reports(database, limit=1_000_000)
    rows.sort(key=lambda item: (item.get("status") != "supported", item.get("report", ""), item.get("variant", "")))
    variantful_reports = {str(row.get("report") or "") for row in rows if str(row.get("variant") or "")}
    targets: dict[tuple[str, str], dict] = {}
    for row in rows:
        report = str(row.get("report") or "")
        variant = str(row.get("variant") or "")
        if not variant and report in variantful_reports:
            continue
        key = (report, variant)
        if not report or key in targets:
            continue
        targets[key] = row
    return list(targets.values())


def _choose_output_contract(described: dict) -> dict:
    items = described.get("output_contracts") or []
    if items:
        first = next((item for item in items if not _looks_like_value_locked_verified_contract(item, described)), items[0])
        return {
            "source": str(first.get("source") or ""),
            "contract": first.get("contract") if isinstance(first.get("contract"), dict) else {},
        }
    return {"source": "", "contract": {}}


def _looks_like_value_locked_verified_contract(item: dict, described: dict) -> bool:
    if str(item.get("source") or "") != "verified":
        return False
    contract = item.get("contract") if isinstance(item.get("contract"), dict) else {}
    if not contract:
        return False
    expected_columns = [str(value or "") for value in contract.get("expected_columns") or []]
    if not expected_columns:
        return False
    numeric_like = 0
    repeated = len(expected_columns) - len(set(expected_columns))
    for value in expected_columns:
        normalized = normalize_report_query(value)
        if any(char.isdigit() for char in normalized) or "\xa0" in value:
            numeric_like += 1
    if numeric_like <= 0 and repeated <= 1:
        return False
    return any(str(other.get("source") or "") == "declared" for other in described.get("output_contracts") or [])


def _classify_contract_attempts(attempts: list[dict]) -> tuple[str, str, str, str]:
    mismatches = [item for item in attempts if item.get("comparison") and not item["comparison"].get("matched")]
    if mismatches:
        first = mismatches[0]
        comparison = first.get("comparison") or {}
        mismatch_code = str(comparison.get("mismatch_code") or "semantic_mismatch")
        if mismatch_code == "weak_declared_contract":
            return "analyzer_gap", "deferred_analyzer_gap", mismatch_code, ""
        if mismatch_code in {"header_only", "missing_detail_rows"} and _all_attempts_are_empty_headers(mismatches):
            return "fixture_gap", "deferred_context", mismatch_code, "По тестовым параметрам отчет вернул только шапку; нужен другой период, отбор или прикладной контекст."
        return "engine_gap", "deferred_engine_gap", mismatch_code, ""
    for item in attempts:
        error_code = str(item.get("error_code") or "")
        if error_code in {"parameter_request", "required_context"}:
            return "missing_context", "deferred_context", "", _attempt_message(item)
        if error_code in {"unsupported_runtime", "report_timeout"}:
            return "unsupported_runtime", "deferred_unsupported", "", _attempt_message(item)
    error = next((_attempt_message(item) for item in attempts if _attempt_message(item)), "")
    return "runtime_error", "error", "", error


def _all_attempts_are_empty_headers(attempts: list[dict]) -> bool:
    if not attempts:
        return False
    for item in attempts:
        observed = item.get("observed") if isinstance(item.get("observed"), dict) else {}
        if int(observed.get("detail_rows_count") or 0) > 0:
            return False
        if int(observed.get("artifacts_count") or 0) > 0:
            return False
        code = str((item.get("comparison") or {}).get("mismatch_code") or "")
        if code not in {"header_only", "missing_detail_rows"}:
            return False
    return True


def _attempt_message(item: dict) -> str:
    error = str(item.get("error") or "").strip()
    if error:
        return error
    message = str(item.get("message") or "").strip()
    if message:
        return message
    missing = [str(raw.get("name") or "").strip() for raw in item.get("missing") or [] if isinstance(raw, dict)]
    missing = [name for name in missing if name]
    if missing:
        return "Для запуска отчета нужно уточнить параметры: " + ", ".join(missing)
    required_context = [str(raw.get("name") or "").strip() for raw in item.get("required_context") or [] if isinstance(raw, dict)]
    required_context = [name for name in required_context if name]
    if required_context:
        return "Для запуска отчета нужен дополнительный контекст: " + ", ".join(required_context)
    return ""


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
    validation = described.get("last_contract_validation") or {}
    if validation:
        status = validation.get("terminal_state") or validation.get("status") or "unknown"
        mismatch = validation.get("mismatch_code") or "none"
        return (
            f"Selected {first.get('strategy')} with priority {first.get('priority')} and confidence {first.get('confidence')}. "
            f"Last contract validation: {status}, mismatch={mismatch}."
        )
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

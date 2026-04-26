from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent

from gateway.db_registry import DatabaseRegistry
from gateway.report_catalog import ReportCatalog
from gateway.tool_handlers import reports as reports_mod
from gateway.tool_handlers.reports import (
    get_default_catalog,
    load_report_graph_hints,
    report_tools,
    rebuild_report_catalog_for_db_info,
    try_handle_report_tool,
)


class FakeBackend:
    async def call_tool(self, name, arguments):
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps({"columns": ["A"], "rows": [{"A": 1}], "totals": {}, "metadata": {}}),
                )
            ]
        )


class FakeManager:
    def get_db_backend(self, db_name, role):
        return FakeBackend() if db_name == "Z01" and role == "toolkit" else None


class ErrorBackend:
    def __init__(self, error: str):
        self.error = error

    async def call_tool(self, name, arguments):
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({"success": False, "error": self.error}, ensure_ascii=False))])


class ErrorManager:
    def __init__(self, error: str):
        self.error = error

    def get_db_backend(self, db_name, role):
        return ErrorBackend(self.error) if db_name == "Z01" and role == "toolkit" else None


@pytest.fixture()
def registry(tmp_path):
    reg = DatabaseRegistry(state_file=tmp_path / "state.json")
    reg.register("Z01", "Srvr=localhost;Ref=Z01;", str(tmp_path / "Z01"), slug="Z01")
    reg.update_runtime("Z01", connected=True)
    return reg


def test_report_tools_require_explicit_database():
    schemas = {tool.name: tool.inputSchema for tool in report_tools()}

    assert "database" in schemas["run_report"]["required"]
    assert "database" in schemas["find_reports"]["required"]
    assert "database" in schemas["analyze_reports"]["required"]
    assert "database" in schemas["enrich_report_docs"]["required"]
    assert "database" in schemas["validate_all_reports"]["required"]
    assert "context" in schemas["run_report"]["properties"]


@pytest.mark.asyncio
async def test_try_handle_report_tool_analyzes_and_finds_reports(tmp_path, registry):
    project = tmp_path / "Z01"
    template = project / "Reports/АнализНачисленийИУдержаний/Templates/ПФ_MXL_РасчетныйЛисток.xml"
    template.parent.mkdir(parents=True)
    template.write_text("<root>Расчетный листок</root>", encoding="utf-8")
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    analyzed = await try_handle_report_tool(
        "analyze_reports",
        {"database": "Z01"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    )
    found = await try_handle_report_tool(
        "find_reports",
        {"database": "Z01", "query": "Расчетный листок"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    )

    assert json.loads(analyzed)["reports"] == 1
    assert json.loads(found)["data"][0]["title"] == "Расчетный листок"


@pytest.mark.asyncio
async def test_try_handle_report_tool_enriches_report_docs_and_searches_by_doc_alias(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "АнализНачисленийИУдержаний",
                    "synonym": "Анализ начислений и удержаний",
                    "aliases": [{"alias": "Анализ начислений и удержаний", "confidence": 0.8}],
                }
            ]
        },
    )

    class FakeNaparnik:
        def __init__(self, api_key):
            self.api_key = api_key

        async def search(self, query):
            assert "Отчет.АнализНачисленийИУдержаний" in query
            return json.dumps(
                {
                    "title": "Расчетный листок",
                    "aliases": ["Анализ начислений и удержаний"],
                    "summary": "Данные о начислениях, удержаниях и выплатах сотруднику.",
                    "source_urls": ["https://its.1c.ru/db/example"],
                    "confidence": 0.93,
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(reports_mod.settings, "naparnik_api_key", "token")
    monkeypatch.setattr(reports_mod, "NaparnikClient", FakeNaparnik)

    enriched = json.loads(await try_handle_report_tool(
        "enrich_report_docs",
        {"database": "Z01", "report": "АнализНачисленийИУдержаний", "limit": 1},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))
    found = json.loads(await try_handle_report_tool(
        "find_reports",
        {"database": "Z01", "query": "расчетка сотрудника"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert enriched["ok"] is True
    assert enriched["fetched"] == 1
    assert enriched["items"][0]["report"] == "АнализНачисленийИУдержаний"
    assert found["data"][0]["report"] == "АнализНачисленийИУдержаний"
    assert found["data"][0]["alias_source"] == "doc:naparnik"


@pytest.mark.asyncio
async def test_try_handle_report_tool_enrich_requires_naparnik_key(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "Отчет", "aliases": [{"alias": "Отчет"}]}]})
    monkeypatch.setattr(reports_mod.settings, "naparnik_api_key", "")

    result = json.loads(await try_handle_report_tool(
        "enrich_report_docs",
        {"database": "Z01", "limit": 1},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert result["ok"] is False
    assert result["error_code"] == "naparnik_not_configured"


@pytest.mark.asyncio
async def test_enrich_report_docs_skips_existing_and_records_naparnik_errors(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "Отчет", "aliases": [{"alias": "Отчет"}]}]})
    catalog.upsert_report_doc(
        database="Z01",
        report_name="Отчет",
        source="naparnik",
        query="old",
        content="old",
        parsed={"title": "Отчет", "confidence": 0.7},
    )

    class ErrorNaparnik:
        def __init__(self, api_key):
            self.api_key = api_key

        async def search(self, query):
            return "ERROR: unavailable"

    monkeypatch.setattr(reports_mod.settings, "naparnik_api_key", "token")
    monkeypatch.setattr(reports_mod, "NaparnikClient", ErrorNaparnik)

    skipped = await reports_mod.enrich_report_docs("Z01", catalog, report="Отчет", force=False)
    errored = await reports_mod.enrich_report_docs("Z01", catalog, report="Отчет", force=True)

    assert skipped["skipped"] == 1
    assert skipped["items"][0]["status"] == "skipped_existing"
    assert errored["ok"] is False
    assert errored["errors"] == 1
    assert errored["items"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_try_handle_report_tool_run_requires_connected_epf(tmp_path, registry):
    registry.mark_epf_disconnected("Z01", force=True)
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "Отчет", "aliases": [{"alias": "Отчет"}]}]})

    result = await try_handle_report_tool(
        "run_report",
        {"database": "Z01", "title": "Отчет"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    )

    payload = json.loads(result)
    assert payload["ok"] is False
    assert payload["error_code"] == "toolkit_not_connected"


@pytest.mark.asyncio
async def test_try_handle_report_tool_unknown_database(tmp_path):
    result = await try_handle_report_tool(
        "list_reports",
        {"database": "NOPE"},
        registry=DatabaseRegistry(state_file=tmp_path / "state.json"),
        manager=SimpleNamespace(),
        catalog=ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results"),
    )

    payload = json.loads(result)
    assert payload["ok"] is False
    assert payload["error_code"] == "database_not_found"


@pytest.mark.asyncio
async def test_try_handle_report_tool_all_read_facades_and_default_catalog(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "aliases": [{"alias": "Отчет", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "priority": 50, "confidence": 0.7}],
                }
            ]
        },
    )
    monkeypatch.setattr(reports_mod, "_DEFAULT_CATALOG", catalog)

    assert get_default_catalog() is catalog
    assert await try_handle_report_tool("not_report", {}, registry=registry, manager=FakeManager(), catalog=catalog) is None

    listed = json.loads(await try_handle_report_tool("list_reports", {"database": "Z01"}, registry=registry, manager=FakeManager(), catalog=catalog))
    described = json.loads(await try_handle_report_tool("describe_report", {"database": "Z01", "title": "Отчет"}, registry=registry, manager=FakeManager(), catalog=catalog))
    explained = json.loads(await try_handle_report_tool("explain_report_strategy", {"database": "Z01", "title": "Отчет"}, registry=registry, manager=FakeManager(), catalog=catalog))
    missing_explained = json.loads(await try_handle_report_tool("explain_report_strategy", {"database": "Z01", "title": "missing"}, registry=registry, manager=FakeManager(), catalog=catalog))

    run_id = catalog.create_run(database="Z01", report_name="Отчет", variant_key="", title="Отчет", strategy="raw", params={})
    result = json.loads(await try_handle_report_tool("get_report_result", {"database": "Z01", "run_id": run_id}, registry=registry, manager=FakeManager(), catalog=catalog))

    assert listed["data"][0]["report"] == "Отчет"
    assert described["ok"] is True
    assert "Selected raw_skd_runner" in explained["explanation"]
    assert missing_explained["explanation"] == "report_not_found"
    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_try_handle_report_tool_runs_successfully(tmp_path, registry):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "aliases": [{"alias": "Отчет", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "priority": 50, "confidence": 0.7}],
                }
            ]
        },
    )

    payload = json.loads(await try_handle_report_tool(
        "run_report",
        {"database": "Z01", "title": "Отчет", "strategy": "raw_skd_runner"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert payload["ok"] is True
    assert payload["rows"] == [{"A": 1}]


@pytest.mark.asyncio
async def test_run_report_lazy_analyzes_missing_catalog(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    calls = []

    async def fake_rebuild(database, db, *, catalog=None, graph_url=None):
        calls.append((database, db.name))
        catalog.replace_analysis(
            database,
            "/projects/Z01",
            {
                "reports": [
                    {
                        "name": "ЛенивыйОтчет",
                        "aliases": [{"alias": "Ленивый отчет", "confidence": 1.0}],
                        "strategies": [{"strategy": "raw_skd_runner", "priority": 50, "confidence": 0.7}],
                    }
                ]
            },
        )
        return {"ok": True, "database": database, "reports": 1}

    monkeypatch.setattr(reports_mod, "rebuild_report_catalog_for_db_info", fake_rebuild)

    payload = json.loads(await try_handle_report_tool(
        "run_report",
        {"database": "Z01", "report": "ЛенивыйОтчет", "strategy": "raw_skd_runner"},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert calls == [("Z01", "Z01")]
    assert payload["ok"] is True
    assert payload["rows"] == [{"A": 1}]


@pytest.mark.asyncio
async def test_validate_all_reports_runs_every_catalog_entry(tmp_path, registry):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "РабочийОтчет",
                    "aliases": [{"alias": "Рабочий отчет", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "priority": 50, "confidence": 0.7}],
                },
                {
                    "name": "НеподдержанныйОтчет",
                    "aliases": [{"alias": "Неподдержанный отчет", "confidence": 1.0}],
                    "kind": "form_or_regulated",
                },
                {
                    "name": "ОтчетСКонтекстом",
                    "aliases": [{"alias": "Отчет с контекстом", "confidence": 1.0}],
                    "strategies": [
                        {
                            "strategy": "form_artifact_runner",
                            "priority": 30,
                            "confidence": 0.6,
                            "details": {"requires_object_ref": True},
                        }
                    ],
                },
            ]
        },
    )

    payload = json.loads(await try_handle_report_tool(
        "validate_all_reports",
        {"database": "Z01", "max_rows": 1, "include_unsupported": True},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert payload["ok"] is True
    assert payload["total"] == 3
    assert payload["counts"] == {"done": 1, "needs_input": 1, "error": 0, "unsupported": 1}
    assert [item["report"] for item in payload["items"]] == ["ОтчетСКонтекстом", "РабочийОтчет", "НеподдержанныйОтчет"]
    assert payload["items"][0]["status"] == "needs_input"
    assert payload["items"][1]["status"] == "done"
    assert payload["items"][2]["status"] == "unsupported"


@pytest.mark.asyncio
async def test_validate_all_reports_counts_runtime_limit_as_unsupported(tmp_path, registry):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "ДинамическийОтчет",
                    "aliases": [{"alias": "Динамический отчет", "confidence": 1.0}],
                    "strategies": [{"strategy": "bsp_variant_report_runner", "priority": 50, "confidence": 0.7}],
                }
            ]
        },
    )

    payload = json.loads(await try_handle_report_tool(
        "validate_all_reports",
        {"database": "Z01", "max_rows": 1, "include_unsupported": True},
        registry=registry,
        manager=ErrorManager('{(14, 2)}: Таблица не найдена "ВТКандидаты"'),
        catalog=catalog,
    ))

    assert payload["counts"] == {"done": 0, "needs_input": 0, "error": 0, "unsupported": 1}
    assert payload["items"][0]["status"] == "unsupported"
    assert payload["items"][0]["error_code"] == "unsupported_runtime"


@pytest.mark.asyncio
async def test_validate_all_reports_counts_timeout_as_unsupported(tmp_path, registry, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "МедленныйОтчет",
                    "aliases": [{"alias": "Медленный отчет", "confidence": 1.0}],
                    "strategies": [{"strategy": "bsp_variant_report_runner", "priority": 50, "confidence": 0.7}],
                }
            ]
        },
    )

    class TimeoutRunner:
        async def run_report(self, **kwargs):
            return {"ok": False, "error_code": "report_timeout", "error": "Report execution timed out after 30 seconds"}

    payload = await reports_mod.validate_all_reports(
        "Z01",
        catalog,
        TimeoutRunner(),
        include_unsupported=True,
        max_rows=1,
        timeout_seconds=30,
    )

    assert payload["counts"] == {"done": 0, "needs_input": 0, "error": 0, "unsupported": 1}
    assert payload["items"][0]["status"] == "unsupported"
    assert payload["items"][0]["error_code"] == "report_timeout"


def test_explain_handles_resolved_report_without_strategies(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "Отчет", "aliases": [{"alias": "Отчет"}]}]})
    described = catalog.describe_report("Z01", title="Отчет")

    assert reports_mod._explain(described) == "No executable strategy is cataloged for this report."


def test_validation_targets_are_report_level_not_alias_level(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "МногоВариантов",
                    "aliases": [
                        {"alias": "Первый", "variant": "A", "confidence": 1.0},
                        {"alias": "Второй", "variant": "B", "confidence": 0.9},
                    ],
                    "variants": [
                        {"key": "A", "presentation": "Первый"},
                        {"key": "B", "presentation": "Второй"},
                    ],
                    "strategies": [
                        {"strategy": "raw_skd_runner", "variant": "A", "priority": 50},
                        {"strategy": "raw_skd_runner", "variant": "B", "priority": 50},
                    ],
                },
                {"name": "ОдинОтчет", "aliases": [{"alias": "Один отчет"}]},
            ]
        },
    )

    targets = reports_mod._validation_targets(catalog, "Z01")

    assert [target["report"] for target in targets] == ["МногоВариантов", "ОдинОтчет"]
    assert len(targets) == 2


def test_select_doc_targets_uses_candidates_query_and_list_paths(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "ПервыйОтчет",
                    "aliases": [{"alias": "Общий отчет", "variant": "A", "confidence": 0.91}],
                    "variants": [{"key": "A", "presentation": "Общий отчет A"}],
                },
                {
                    "name": "ВторойОтчет",
                    "aliases": [{"alias": "Общий отчет", "variant": "B", "confidence": 0.90}],
                    "variants": [{"key": "B", "presentation": "Общий отчет B"}],
                },
            ]
        },
    )

    ambiguous = reports_mod._select_doc_targets(catalog, "Z01", title="Общий отчет", limit=1)
    by_query = reports_mod._select_doc_targets(catalog, "Z01", query="Общий", limit=10)
    listed = reports_mod._select_doc_targets(catalog, "Z01", limit=10)
    deduped = reports_mod._dedupe_report_targets(
        [
            {"report": "", "variant": ""},
            {"report": "ПервыйОтчет", "variant": "A"},
            {"report": "ПервыйОтчет", "variant": "A"},
            {"report": "ПервыйОтчет", "variant": "B"},
        ]
    )

    assert len(ambiguous) == 1
    assert {row["report"] for row in by_query} == {"ПервыйОтчет", "ВторойОтчет"}
    assert {row["report"] for row in listed} == {"ПервыйОтчет", "ВторойОтчет"}
    assert deduped == [
        {"report": "ПервыйОтчет", "variant": "A"},
        {"report": "ПервыйОтчет", "variant": "B"},
    ]


def test_get_default_catalog_creates_singleton_when_missing(tmp_path, monkeypatch):
    created = ReportCatalog(tmp_path / "default.sqlite", tmp_path / "default-results")
    monkeypatch.setattr(reports_mod, "_DEFAULT_CATALOG", None)
    monkeypatch.setattr(reports_mod, "ReportCatalog", lambda: created)

    assert get_default_catalog() is created


def test_project_path_candidates_map_hostfs_to_workspace(monkeypatch):
    monkeypatch.setattr(reports_mod.settings, "bsl_host_workspace", "/home/as/Z")
    monkeypatch.setattr(reports_mod.settings, "bsl_workspace", "/workspace")

    candidates = reports_mod._project_path_candidates("Z01", "/hostfs-home/as/Z/Z01", "z01")

    assert candidates[0].as_posix() == "/hostfs-home/as/Z/Z01"
    assert Path("/workspace/Z01") in candidates
    assert Path("/workspace/z01") in candidates


def test_project_path_candidates_and_hostfs_mapping_cover_empty_and_non_home(monkeypatch):
    monkeypatch.setattr(reports_mod.settings, "bsl_host_workspace", "/data")
    monkeypatch.setattr(reports_mod.settings, "bsl_workspace", "/workspace")

    candidates = reports_mod._project_path_candidates("Z01", "", "")

    assert candidates == [Path("/workspace/Z01")]
    assert reports_mod._host_to_hostfs_path("/home") == "/hostfs-home"
    assert reports_mod._host_to_hostfs_path("/data/project") == "/data/project"


def test_resolve_readable_project_path_skips_permission_denied_candidate(tmp_path, monkeypatch):
    denied = tmp_path / "denied"
    readable = tmp_path / "workspace" / "Z01"
    (denied / "Reports").mkdir(parents=True)
    (readable / "Reports" / "Отчет").mkdir(parents=True)
    monkeypatch.setattr(reports_mod.settings, "bsl_host_workspace", "/home/as/Z")
    monkeypatch.setattr(reports_mod.settings, "bsl_workspace", str(tmp_path / "workspace"))

    original_iterdir = Path.iterdir

    def fake_iterdir(path):
        if path == denied / "Reports":
            raise PermissionError("denied")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    db = SimpleNamespace(project_path=str(denied), slug="Z01")

    assert reports_mod._resolve_readable_project_path("Z01", db) == readable


def test_resolve_readable_project_path_skips_os_errors_and_returns_first_fallback(tmp_path, monkeypatch):
    broken = tmp_path / "broken"
    fallback = tmp_path / "workspace" / "Z01"
    (broken / "Reports").mkdir(parents=True)
    monkeypatch.setattr(reports_mod.settings, "bsl_host_workspace", "/home/as/Z")
    monkeypatch.setattr(reports_mod.settings, "bsl_workspace", str(tmp_path / "workspace"))

    original_iterdir = Path.iterdir

    def fake_iterdir(path):
        if path == broken / "Reports":
            raise OSError("broken")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    db = SimpleNamespace(project_path=str(broken), slug="")

    assert reports_mod._resolve_readable_project_path("Z01", db) == broken
    assert fallback in reports_mod._project_path_candidates("Z01", str(broken), "")


@pytest.mark.asyncio
async def test_load_report_graph_hints_collects_and_deduplicates_nodes(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            self.calls.append((url, json))
            node = {
                "id": "Z01:CommonModules:ЗарплатаКадрыОтчеты",
                "type": "commonModule",
                "properties": {"name": "ЗарплатаКадрыОтчеты", "db": "Z01"},
            }
            return FakeResponse({"nodes": [node, node], "edges": [{"sourceId": "a", "targetId": "b", "type": "references"}]})

    monkeypatch.setattr(reports_mod.httpx, "AsyncClient", FakeClient)

    hints = await load_report_graph_hints("Z01", graph_url="http://graph")

    assert hints["available"] is True
    assert len(hints["nodes"]) == 1
    assert hints["nodes"][0]["properties"]["name"] == "ЗарплатаКадрыОтчеты"


@pytest.mark.asyncio
async def test_load_report_graph_hints_is_best_effort_when_disabled_or_failed(monkeypatch):
    class BrokenClient:
        async def __aenter__(self):
            raise RuntimeError("down")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    disabled = await load_report_graph_hints("Z01", graph_url="")
    monkeypatch.setattr(reports_mod.httpx, "AsyncClient", lambda *args, **kwargs: BrokenClient())
    failed = await load_report_graph_hints("Z01", graph_url="http://graph")

    assert disabled["available"] is False
    assert failed["available"] is False
    assert "down" in failed["error"]


@pytest.mark.asyncio
async def test_rebuild_report_catalog_for_db_info_uses_graph_hints(tmp_path, monkeypatch):
    project = tmp_path / "Z01"
    template = project / "Reports/АнализНачисленийИУдержаний/Templates/ПФ_MXL_РасчетныйЛисток.xml"
    template.parent.mkdir(parents=True)
    template.write_text("<root>Расчетный листок</root>", encoding="utf-8")
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    async def fake_graph_hints(database, graph_url=None):
        return {
            "available": True,
            "nodes": [
                {
                    "id": "Z01:CommonModules:ЗарплатаКадрыОтчеты",
                    "type": "commonModule",
                    "properties": {"name": "ЗарплатаКадрыОтчеты", "db": database},
                }
            ],
            "edges": [],
        }

    monkeypatch.setattr(reports_mod, "load_report_graph_hints", fake_graph_hints)

    summary = await rebuild_report_catalog_for_db_info("Z01", SimpleNamespace(project_path=str(project)), catalog=catalog)
    described = catalog.describe_report("Z01", title="Расчетный листок")

    assert summary["reports"] == 1
    assert described["strategies"][0]["details"]["source"] == "graph"

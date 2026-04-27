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
    assert "database" in schemas["validate_report_contracts"]["required"]
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


@pytest.mark.asyncio
async def test_validate_report_contracts_is_variant_aware_and_persists_campaign(tmp_path, registry):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "МногоВариантов",
                    "aliases": [
                        {"alias": "Первый вариант", "variant": "A", "confidence": 1.0},
                        {"alias": "Второй вариант", "variant": "B", "confidence": 1.0},
                    ],
                    "variants": [
                        {"key": "A", "presentation": "Первый вариант"},
                        {"key": "B", "presentation": "Второй вариант"},
                    ],
                    "strategies": [
                        {"strategy": "raw_skd_runner", "variant": "A", "priority": 50, "confidence": 0.8},
                        {"strategy": "raw_skd_runner", "variant": "B", "priority": 50, "confidence": 0.8},
                    ],
                    "output_contracts": [
                        {"variant": "A", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False, "confidence": "low"}},
                        {"variant": "B", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False, "confidence": "low"}},
                    ],
                }
            ]
        },
    )

    payload = json.loads(await try_handle_report_tool(
        "validate_report_contracts",
        {"database": "Z01", "stop_on_mismatch": True, "max_rows": 1},
        registry=registry,
        manager=FakeManager(),
        catalog=catalog,
    ))

    assert payload["ok"] is True
    assert payload["counts"]["matched"] == 2
    assert payload["counts"]["error"] == 0
    assert [item["variant"] for item in payload["items"]] == ["A", "B"]
    campaign = catalog.get_validation_campaign(payload["campaign_id"])
    assert campaign["items"][0]["terminal_state"] == "matched"


@pytest.mark.asyncio
async def test_validate_report_contracts_retries_with_larger_row_limit_after_truncated_header_only(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "aliases": [{"alias": "Отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Отчет"}],
                    "strategies": [{"strategy": "raw_skd_probe_runner", "variant": "Основной", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "Основной", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": True, "confidence": "medium", "expected_columns": []}}],
                }
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}, "diagnostics": {"source": "stub"}}

        def plan_inputs(self, described, fixture_pack, *, period_override=None):
            return {"period": fixture_pack["period"], "params": {}, "filters": {}, "context": {}, "missing": []}

        def resolve_missing(self, missing_items, required_context, fixture_pack):
            return {"params": {}, "context": {}, "unresolved": list(missing_items) + list(required_context)}

    class RetryRunner:
        def __init__(self):
            self.calls = []

        async def run_report(self, **kwargs):
            self.calls.append(kwargs["max_rows"])
            if len(self.calls) == 1:
                return {
                    "ok": True,
                    "run_id": "first",
                    "output_type": "rows",
                    "columns": ["C1", "C2", "C3"],
                    "rows": [
                        {"C1": "Заголовок отчета", "C2": "", "C3": ""},
                        {"C1": "Колонка 1", "C2": "Колонка 2", "C3": "Колонка 3"},
                    ],
                    "metadata": {"tabular_height": 120},
                    "warnings": ["Result truncated by max_rows."],
                    "observed_signature": {
                        "output_type": "rows",
                        "row_count": 2,
                        "column_count": 3,
                        "header_rows": ["Заголовок отчета", "Колонка 1 | Колонка 2 | Колонка 3"],
                        "detail_rows_count": 0,
                        "detail_sample": [],
                        "detail_column_count": 0,
                        "max_nonempty_cells": 3,
                        "has_totals": False,
                        "has_hierarchy": False,
                        "artifacts_count": 0,
                        "warnings": ["Result truncated by max_rows."],
                        "observed_tokens": ["Заголовок отчета", "Колонка 1", "Колонка 2", "Колонка 3"],
                        "observed_tokens_norm": ["заголовок отчета", "колонка 1", "колонка 2", "колонка 3"],
                        "metadata": {"tabular_height": 120},
                    },
                    "contract_validation": {"matched": False, "mismatch_code": "header_only", "acceptable_with_verified": False, "score": 0.1},
                }
            return {
                "ok": True,
                "run_id": "second",
                "output_type": "rows",
                "columns": ["C1", "C2"],
                "rows": [{"C1": "Строка", "C2": "1"}],
                "metadata": {"tabular_height": 120},
                "warnings": [],
                "observed_signature": {
                    "output_type": "rows",
                    "row_count": 1,
                    "column_count": 2,
                    "header_rows": [],
                    "detail_rows_count": 1,
                    "detail_sample": [{"C1": "Строка", "C2": "1"}],
                    "detail_column_count": 2,
                    "max_nonempty_cells": 2,
                    "has_totals": False,
                    "has_hierarchy": False,
                    "artifacts_count": 0,
                    "warnings": [],
                    "observed_tokens": ["Строка", "1"],
                    "observed_tokens_norm": ["строка", "1"],
                    "metadata": {"tabular_height": 120},
                },
                "contract_validation": {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0},
            }

    runner = RetryRunner()
    payload = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner,
        StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=20,
        timeout_seconds=30,
    )

    assert payload["counts"]["matched"] == 1
    assert runner.calls == [20, 120]


@pytest.mark.asyncio
async def test_validate_report_contracts_retries_with_larger_row_limit_after_truncated_semantic_mismatch(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "aliases": [{"alias": "Отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Отчет"}],
                    "strategies": [{"strategy": "raw_skd_probe_runner", "variant": "Основной", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [
                        {
                            "variant": "Основной",
                            "source": "declared",
                            "contract": {
                                "output_type": "rows",
                                "expects_detail_rows": True,
                                "confidence": "high",
                                "confidence_score": 0.82,
                                "expected_columns": ["Период", "Сумма", "Налог"],
                            },
                        }
                    ],
                }
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}, "diagnostics": {"source": "stub"}}

        def plan_inputs(self, described, fixture_pack, *, period_override=None):
            return {"period": fixture_pack["period"], "params": {}, "filters": {}, "context": {}, "missing": []}

        def resolve_missing(self, missing_items, required_context, fixture_pack):
            return {"params": {}, "context": {}, "unresolved": list(missing_items) + list(required_context)}

    class RetryRunner:
        def __init__(self):
            self.calls = []

        async def run_report(self, **kwargs):
            self.calls.append(kwargs["max_rows"])
            if len(self.calls) == 1:
                return {
                    "ok": True,
                    "run_id": "first",
                    "output_type": "rows",
                    "columns": ["C1", "C2"],
                    "rows": [
                        {"C1": "Отчет", "C2": ""},
                        {"C1": "Период", "C2": "Январь 2024 - Декабрь 2024"},
                    ],
                    "metadata": {"tabular_height": 40},
                    "warnings": ["Result truncated by max_rows."],
                    "observed_signature": {
                        "output_type": "rows",
                        "row_count": 2,
                        "column_count": 2,
                        "columns": ["C1", "C2"],
                        "header_rows": ["Отчет"],
                        "detail_rows_count": 1,
                        "detail_sample": [{"C1": "Период", "C2": "Январь 2024 - Декабрь 2024"}],
                        "detail_column_count": 2,
                        "max_nonempty_cells": 2,
                        "has_totals": False,
                        "has_hierarchy": False,
                        "artifacts_count": 0,
                        "warnings": ["Result truncated by max_rows."],
                        "observed_tokens": ["Отчет", "Период", "Январь 2024 - Декабрь 2024"],
                        "observed_tokens_norm": ["отчет", "период", "январь 2024 декабрь 2024"],
                        "metadata": {"tabular_height": 40},
                    },
                    "contract_validation": {"matched": False, "mismatch_code": "semantic_mismatch", "acceptable_with_verified": False, "score": 0.2},
                }
            return {
                "ok": True,
                "run_id": "second",
                "output_type": "rows",
                    "columns": ["C1", "C2"],
                    "rows": [{"C1": "Период", "C2": "100"}],
                    "metadata": {"tabular_height": 40},
                    "warnings": [],
                    "observed_signature": {
                        "output_type": "rows",
                        "row_count": 1,
                        "column_count": 3,
                        "columns": ["C1", "C2", "C3"],
                        "header_rows": [],
                        "detail_rows_count": 1,
                        "detail_sample": [{"C1": "Период", "C2": "Сумма", "C3": "Налог"}],
                        "detail_column_count": 3,
                        "max_nonempty_cells": 3,
                        "has_totals": False,
                        "has_hierarchy": False,
                        "artifacts_count": 0,
                        "warnings": [],
                        "observed_tokens": ["Период", "Сумма", "Налог"],
                        "observed_tokens_norm": ["период", "сумма", "налог"],
                        "metadata": {"tabular_height": 40},
                    },
                    "contract_validation": {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0},
                }

    runner = RetryRunner()
    payload = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner,
        StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=5,
        timeout_seconds=30,
    )

    assert payload["counts"]["matched"] == 1
    assert runner.calls == [5, 40]


@pytest.mark.asyncio
async def test_validate_report_contracts_retries_candidate_periods_for_empty_results(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "synonym": "Отчет",
                    "aliases": [{"alias": "Отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Отчет"}],
                    "strategies": [{"strategy": "bsp_variant_report_runner", "variant": "Основной", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "Основной", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": True, "confidence": "medium", "expected_columns": []}}],
                }
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {
                "period": {"from": "2025-05-01", "to": "2025-05-31"},
                "candidate_periods": [
                    {"from": "2025-05-01", "to": "2025-05-31"},
                    {"from": "2024-04-01", "to": "2024-04-30"},
                ],
                "samples": {},
                "context": {},
                "diagnostics": {"source": "stub"},
            }

        def plan_inputs(self, described, fixture_pack, *, period_override=None):
            return {"period": fixture_pack["period"], "params": {}, "filters": {}, "context": {}, "missing": []}

        def resolve_missing(self, missing_items, required_context, fixture_pack):
            return {"params": {}, "context": {}, "unresolved": list(missing_items) + list(required_context)}

        def candidate_periods(self, fixture_pack, chosen_period):
            return list(fixture_pack["candidate_periods"])

    class RetryPeriodRunner:
        def __init__(self):
            self.calls = []

        async def run_report(self, **kwargs):
            self.calls.append(kwargs["period"])
            if kwargs["period"]["from"] == "2025-05-01":
                return {
                    "ok": True,
                    "run_id": "first",
                    "output_type": "rows",
                    "columns": [],
                    "rows": [],
                    "metadata": {"tabular_height": 0},
                    "warnings": [],
                    "observed_signature": {
                        "output_type": "rows",
                        "row_count": 0,
                        "column_count": 0,
                        "columns": [],
                        "header_rows": [],
                        "detail_rows_count": 0,
                        "detail_sample": [],
                        "detail_column_count": 0,
                        "max_nonempty_cells": 0,
                        "has_totals": False,
                        "has_hierarchy": False,
                        "artifacts_count": 0,
                        "warnings": [],
                        "observed_tokens": [],
                        "observed_tokens_norm": [],
                        "metadata": {"tabular_height": 0},
                    },
                }
            return {
                "ok": True,
                "run_id": "second",
                "output_type": "rows",
                "columns": ["C1", "C2"],
                "rows": [{"C1": "Строка", "C2": "1"}],
                "metadata": {"tabular_height": 1},
                "warnings": [],
                "observed_signature": {
                    "output_type": "rows",
                    "row_count": 1,
                    "column_count": 2,
                    "columns": ["C1", "C2"],
                    "header_rows": [],
                    "detail_rows_count": 1,
                    "detail_sample": [{"C1": "Строка", "C2": "1"}],
                    "detail_column_count": 2,
                    "max_nonempty_cells": 2,
                    "has_totals": False,
                    "has_hierarchy": False,
                    "artifacts_count": 0,
                    "warnings": [],
                    "observed_tokens": ["Строка", "1"],
                    "observed_tokens_norm": ["строка", "1"],
                    "metadata": {"tabular_height": 1},
                },
            }

    runner = RetryPeriodRunner()
    payload = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner,
        StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=20,
        timeout_seconds=30,
    )

    assert payload["counts"]["matched"] == 1
    assert runner.calls == [
        {"from": "2025-05-01", "to": "2025-05-31"},
        {"from": "2024-04-01", "to": "2024-04-30"},
    ]


@pytest.mark.asyncio
async def test_validate_report_contracts_retries_candidate_organization_filters_for_empty_results(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "synonym": "Отчет",
                    "aliases": [{"alias": "Отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Отчет"}],
                    "strategies": [{"strategy": "raw_skd_dataset_query_runner", "variant": "Основной", "priority": 40, "confidence": 0.8}],
                    "output_contracts": [{"variant": "Основной", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": True, "confidence": "medium", "expected_columns": []}}],
                }
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {
                "period": {"from": "2024-01-01", "to": "2024-12-31"},
                "samples": {
                    "organization": "Пустая организация",
                    "organization_candidates": ["Пустая организация", "Рабочая организация"],
                },
                "context": {},
                "diagnostics": {"source": "stub"},
            }

        def plan_inputs(self, described, fixture_pack, *, period_override=None):
            return {
                "period": fixture_pack["period"],
                "params": {},
                "filters": {"Организация": fixture_pack["samples"]["organization"]},
                "context": {},
                "missing": [],
            }

        def resolve_missing(self, missing_items, required_context, fixture_pack):
            return {"params": {}, "context": {}, "unresolved": list(missing_items) + list(required_context)}

        def candidate_filter_values(self, fixture_pack, filter_name, current_value):
            if filter_name == "Организация":
                return ["Рабочая организация"] if current_value == "Пустая организация" else []
            return []

    class RetryOrganizationRunner:
        def __init__(self):
            self.calls = []

        async def run_report(self, **kwargs):
            self.calls.append(dict(kwargs["filters"]))
            if kwargs["filters"]["Организация"] == "Пустая организация":
                return {
                    "ok": True,
                    "run_id": "first",
                    "output_type": "rows",
                    "columns": [],
                    "rows": [],
                    "metadata": {"tabular_height": 0},
                    "warnings": [],
                    "observed_signature": {
                        "output_type": "rows",
                        "row_count": 0,
                        "column_count": 0,
                        "columns": [],
                        "header_rows": [],
                        "detail_rows_count": 0,
                        "detail_sample": [],
                        "detail_column_count": 0,
                        "max_nonempty_cells": 0,
                        "has_totals": False,
                        "has_hierarchy": False,
                        "artifacts_count": 0,
                        "warnings": [],
                        "observed_tokens": [],
                        "observed_tokens_norm": [],
                        "metadata": {"tabular_height": 0},
                    },
                }
            return {
                "ok": True,
                "run_id": "second",
                "output_type": "rows",
                "columns": ["C1", "C2"],
                "rows": [{"C1": "Строка", "C2": "1"}],
                "metadata": {"tabular_height": 1},
                "warnings": [],
                "observed_signature": {
                    "output_type": "rows",
                    "row_count": 1,
                    "column_count": 2,
                    "columns": ["C1", "C2"],
                    "header_rows": [],
                    "detail_rows_count": 1,
                    "detail_sample": [{"C1": "Строка", "C2": "1"}],
                    "detail_column_count": 2,
                    "max_nonempty_cells": 2,
                    "has_totals": False,
                    "has_hierarchy": False,
                    "artifacts_count": 0,
                    "warnings": [],
                    "observed_tokens": ["Строка", "1"],
                    "observed_tokens_norm": ["строка", "1"],
                    "metadata": {"tabular_height": 1},
                },
            }

    runner = RetryOrganizationRunner()
    payload = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner,
        StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=20,
        timeout_seconds=30,
    )

    assert payload["counts"]["matched"] == 1
    assert runner.calls == [
        {"Организация": "Пустая организация"},
        {"Организация": "Рабочая организация"},
    ]


@pytest.mark.asyncio
async def test_validate_report_contracts_classifies_stable_header_only_as_context_gap(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет",
                    "synonym": "Отчет",
                    "aliases": [{"alias": "Отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Отчет"}],
                    "strategies": [{"strategy": "raw_skd_probe_runner", "variant": "Основной", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "Основной", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": True, "confidence": "medium", "expected_columns": ["Количество к оформлению"]}}],
                }
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}, "diagnostics": {"source": "stub"}}

        def plan_inputs(self, described, fixture_pack, *, period_override=None):
            return {"period": fixture_pack["period"], "params": {}, "filters": {}, "context": {}, "missing": []}

        def resolve_missing(self, missing_items, required_context, fixture_pack):
            return {"params": {}, "context": {}, "unresolved": list(missing_items) + list(required_context)}

        def candidate_periods(self, fixture_pack, chosen_period):
            return [fixture_pack["period"]]

    class HeaderOnlyRunner:
        async def run_report(self, **kwargs):
            return {
                "ok": True,
                "run_id": "header-only",
                "output_type": "rows",
                "columns": ["C1", "C2"],
                "rows": [
                    {"C1": "Параметры:", "C2": "Период:"},
                    {"C1": "Отбор:", "C2": "Количество к оформлению Не равно \"0\""},
                ],
                "observed_signature": {
                    "output_type": "rows",
                    "row_count": 2,
                    "column_count": 2,
                    "columns": ["C1", "C2"],
                    "header_rows": ["Параметры: | Период:", "Отбор: | Количество к оформлению Не равно \"0\""],
                    "detail_rows_count": 0,
                    "detail_sample": [],
                    "detail_column_count": 0,
                    "max_nonempty_cells": 2,
                    "has_totals": False,
                    "has_hierarchy": False,
                    "artifacts_count": 0,
                    "warnings": [],
                    "observed_tokens": ["Параметры:", "Период:", "Отбор:", "Количество к оформлению Не равно \"0\""],
                    "observed_tokens_norm": ["параметры", "период", "отбор", "количество к оформлению не равно 0"],
                    "metadata": {},
                },
            }

    payload = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        HeaderOnlyRunner(),
        StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=20,
        timeout_seconds=30,
    )

    assert payload["counts"]["deferred_context"] == 1
    assert payload["counts"]["deferred_engine_gap"] == 0
    assert payload["items"][0]["root_cause_class"] == "fixture_gap"
    assert payload["items"][0]["mismatch_code"] == "header_only"


@pytest.mark.asyncio
async def test_validate_report_contracts_resume_restarts_from_stopper_and_recomputes_counts(tmp_path, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": "Отчет1",
                    "aliases": [{"alias": "Отчет 1", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False, "confidence": "low"}}],
                },
                {
                    "name": "Отчет2",
                    "aliases": [{"alias": "Отчет 2", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False, "confidence": "low"}}],
                },
                {
                    "name": "Отчет3",
                    "aliases": [{"alias": "Отчет 3", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False, "confidence": "low"}}],
                },
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}, "diagnostics": {"source": "stub"}}

    phase = {"value": 1}
    calls: list[tuple[int, str]] = []

    async def fake_validate_target(
        database,
        target,
        described,
        catalog,
        runner,
        fixture_provider,
        fixture_pack,
        *,
        period,
        max_rows,
        timeout_seconds,
    ):
        report = str(target.get("report") or "")
        calls.append((phase["value"], report))
        if phase["value"] == 1 and report == "Отчет2":
            return {
                "database": database,
                "report": report,
                "variant": "",
                "title": report,
                "terminal_state": "deferred_engine_gap",
                "strategy": "raw_skd_runner",
                "run_id": "run-2a",
                "contract_source": "declared",
                "contract_hash": "hash",
                "mismatch_code": "header_only",
                "root_cause_class": "engine_gap",
                "observed": {"row_count": 2},
                "diagnostics": {"phase": 1},
                "error": "",
            }
        return {
            "database": database,
            "report": report,
            "variant": "",
            "title": report,
            "terminal_state": "matched",
            "strategy": "raw_skd_runner",
            "run_id": f"run-{phase['value']}-{report}",
            "contract_source": "declared",
            "contract_hash": "hash",
            "mismatch_code": "",
            "root_cause_class": "",
            "observed": {"row_count": 1},
            "diagnostics": {"phase": phase["value"]},
            "error": "",
        }

    monkeypatch.setattr(reports_mod, "_validate_contract_target", fake_validate_target)

    first = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        stop_on_mismatch=True,
        max_rows=20,
        timeout_seconds=30,
    )

    phase["value"] = 2
    second = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        stop_on_mismatch=True,
        resume_campaign_id=first["campaign_id"],
        max_rows=20,
        timeout_seconds=30,
    )
    campaign = catalog.get_validation_campaign(first["campaign_id"])

    assert first["status"] == "stopped"
    assert first["counts"]["matched"] == 1
    assert first["counts"]["deferred_engine_gap"] == 1
    assert first["resume_from_ordinal"] == 2
    assert second["status"] == "completed"
    assert second["counts"]["matched"] == 3
    assert second["counts"]["deferred_engine_gap"] == 0
    assert second["total"] == 3
    assert second["processed_in_call"] == 2
    assert calls == [
        (1, "Отчет1"),
        (1, "Отчет2"),
        (2, "Отчет2"),
        (2, "Отчет3"),
    ]
    assert campaign["status"] == "completed"
    assert [item["terminal_state"] for item in campaign["items"]] == ["matched", "matched", "matched"]


@pytest.mark.asyncio
async def test_validate_report_contracts_resume_extends_limited_campaign_order(tmp_path, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": f"Отчет{i}",
                    "aliases": [{"alias": f"Отчет {i}", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False}}],
                }
                for i in range(1, 4)
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}}

    calls: list[str] = []

    async def fake_validate_target(
        database,
        target,
        described,
        catalog,
        runner,
        fixture_provider,
        fixture_pack,
        *,
        period,
        max_rows,
        timeout_seconds,
    ):
        report = str(target.get("report") or "")
        calls.append(report)
        return {
            "database": database,
            "report": report,
            "variant": "",
            "title": report,
            "terminal_state": "matched",
            "strategy": "raw_skd_runner",
            "run_id": f"run-{report}",
            "contract_source": "declared",
            "contract_hash": "hash",
            "mismatch_code": "",
            "root_cause_class": "",
            "observed": {"row_count": 1},
            "diagnostics": {},
            "error": "",
        }

    monkeypatch.setattr(reports_mod, "_validate_contract_target", fake_validate_target)

    first = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        limit=1,
    )
    second = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        resume_campaign_id=first["campaign_id"],
    )
    campaign = catalog.get_validation_campaign(first["campaign_id"])

    assert first["summary"]["total_targets"] == 1
    assert second["summary"]["total_targets"] == 3
    assert second["processed_in_call"] == 2
    assert second["counts"]["matched"] == 3
    assert len(campaign["order"]) == 3
    assert calls == ["Отчет1", "Отчет2", "Отчет3"]


@pytest.mark.asyncio
async def test_validate_report_contracts_processes_resume_in_batches(tmp_path, monkeypatch):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP",
        "/projects/ERP",
        {
            "reports": [
                {
                    "name": f"Отчет{i}",
                    "aliases": [{"alias": f"Отчет {i}", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.8}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"output_type": "rows", "expects_detail_rows": False}}],
                }
                for i in range(1, 5)
            ]
        },
    )

    class StubFixtureProvider:
        async def build_fixture_pack(self, database):
            return {"period": {"from": "2024-01-01", "to": "2024-12-31"}, "samples": {}, "context": {}}

    async def fake_validate_target(
        database,
        target,
        described,
        catalog,
        runner,
        fixture_provider,
        fixture_pack,
        *,
        period,
        max_rows,
        timeout_seconds,
    ):
        report = str(target.get("report") or "")
        return {
            "database": database,
            "report": report,
            "variant": "",
            "title": report,
            "terminal_state": "matched",
            "strategy": "raw_skd_runner",
            "run_id": f"run-{report}",
            "contract_source": "declared",
            "contract_hash": "hash",
            "mismatch_code": "",
            "root_cause_class": "",
            "observed": {"row_count": 1},
            "diagnostics": {},
            "error": "",
        }

    monkeypatch.setattr(reports_mod, "_validate_contract_target", fake_validate_target)

    first = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        max_targets_per_call=2,
    )
    second = await reports_mod.validate_report_contracts(
        "ERP",
        catalog,
        runner=object(),
        fixture_provider=StubFixtureProvider(),
        resume_campaign_id=first["campaign_id"],
        max_targets_per_call=2,
    )

    assert first["status"] == "paused"
    assert first["stop_reason"] == "batch_limit"
    assert first["processed_in_call"] == 2
    assert first["summary"]["resume_from_ordinal"] == 3
    assert second["status"] == "completed"
    assert second["processed_in_call"] == 2
    assert second["counts"]["matched"] == 4


def test_merge_fixture_packs_prefers_refreshed_samples_and_keeps_candidates():
    merged = reports_mod._merge_fixture_packs(
        {
            "period": {"from": "2024-01-01", "to": "2024-12-31"},
            "candidate_periods": [{"from": "2024-01-01", "to": "2024-12-31"}],
            "samples": {"employee": "Кузнецов", "organization": "Металл-Сервис"},
            "context": {},
            "diagnostics": {"source": "existing"},
        },
        {
            "period": {"from": "2024-02-01", "to": "2024-02-29"},
            "candidate_periods": [{"from": "2024-02-01", "to": "2024-02-29"}],
            "samples": {"payroll_employee": "Белкина", "payroll_organization": "Андромеда Плюс"},
            "context": {"object_description": {"_objectRef": "Document.X(1)"}},
            "diagnostics": {"source": "refreshed"},
        },
    )

    assert merged["period"] == {"from": "2024-02-01", "to": "2024-02-29"}
    assert merged["candidate_periods"] == [
        {"from": "2024-02-01", "to": "2024-02-29"},
        {"from": "2024-01-01", "to": "2024-12-31"},
    ]
    assert merged["samples"]["employee"] == "Кузнецов"
    assert merged["samples"]["payroll_employee"] == "Белкина"
    assert merged["samples"]["payroll_organization"] == "Андромеда Плюс"
    assert merged["context"]["object_description"] == {"_objectRef": "Document.X(1)"}
    assert merged["diagnostics"]["resume_refresh"] is True


def test_choose_output_contract_skips_value_locked_verified_contract():
    described = {
        "output_contracts": [
            {
                "source": "verified",
                "contract": {
                    "output_type": "rows",
                    "expected_columns": ["Услуги переработчика", "Услуги переработчика", "15\xa0000,00"],
                },
            },
            {
                "source": "declared",
                "contract": {
                    "output_type": "rows",
                    "expected_columns": ["Количество затрат", "Стоимость затрат"],
                },
            },
        ]
    }

    chosen = reports_mod._choose_output_contract(described)

    assert chosen["source"] == "declared"
    assert chosen["contract"]["expected_columns"] == ["Количество затрат", "Стоимость затрат"]


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


def test_classify_contract_attempts_prefers_primary_required_context_and_keeps_context_message():
    root_cause, terminal_state, mismatch_code, error = reports_mod._classify_contract_attempts(
        [
            {
                "strategy": "bsp_variant_report_runner",
                "error_code": "required_context",
                "message": "Для запуска отчета нужен существующий объект 1С.",
                "required_context": [{"name": "object_description", "type": "_objectRef"}],
            },
            {
                "strategy": "raw_skd_probe_runner",
                "error_code": "unsupported_runtime",
                "error": '{(14, 2)}: Таблица не найдена "ВТКандидаты"',
            },
        ]
    )

    assert root_cause == "missing_context"
    assert terminal_state == "deferred_context"
    assert mismatch_code == ""
    assert error == "Для запуска отчета нужен существующий объект 1С."


def test_classify_contract_attempts_prefers_earlier_unsupported_over_later_context():
    root_cause, terminal_state, mismatch_code, error = reports_mod._classify_contract_attempts(
        [
            {
                "strategy": "raw_skd_probe_runner",
                "error_code": "unsupported_runtime",
                "error": '{(14, 2)}: Таблица не найдена "ВТКандидаты"',
            },
            {
                "strategy": "bsp_variant_report_runner",
                "error_code": "required_context",
                "message": "Для запуска отчета нужен существующий объект 1С.",
                "required_context": [{"name": "object_description", "type": "_objectRef"}],
            },
        ]
    )

    assert root_cause == "unsupported_runtime"
    assert terminal_state == "deferred_unsupported"
    assert mismatch_code == ""
    assert error == '{(14, 2)}: Таблица не найдена "ВТКандидаты"'


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

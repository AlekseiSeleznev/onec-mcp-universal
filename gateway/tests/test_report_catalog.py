from __future__ import annotations

import json

from gateway.report_catalog import ReportCatalog, _json_loads, normalize_report_query


def _analysis_payload():
    return {
        "reports": [
            {
                "name": "АнализНачисленийИУдержаний",
                "synonym": "Анализ начислений и удержаний",
                "kind": "external_datasets_required",
                "status": "supported",
                "confidence": 0.97,
                "diagnostics": {"reason": "adapter found"},
                "aliases": [
                    {
                        "alias": "Расчетный листок",
                        "source": "template",
                        "variant": "РасчетныйЛисток",
                        "confidence": 0.99,
                    },
                    {
                        "alias": "Анализ начислений и удержаний",
                        "source": "report",
                        "confidence": 0.90,
                    },
                ],
                "variants": [
                    {
                        "key": "РасчетныйЛисток",
                        "presentation": "Расчетный листок",
                        "template": "ПФ_MXL_РасчетныйЛисток",
                    }
                ],
                "params": [
                    {
                        "name": "Сотрудник",
                        "presentation": "Сотрудник",
                        "type_name": "СправочникСсылка.Сотрудники",
                        "required": False,
                        "default": None,
                        "source": "adapter",
                    }
                ],
                "strategies": [
                    {
                        "strategy": "adapter_entrypoint",
                        "priority": 10,
                        "confidence": 0.99,
                        "entrypoint": "ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков",
                        "output_type": "rows",
                        "requires_runtime_probe": False,
                        "blocked_reason": "",
                        "details": {"adapter": "payroll_sheet"},
                    }
                ],
            }
        ]
    }


def test_normalize_report_query_handles_cyrillic_camelcase_and_punctuation():
    assert normalize_report_query("  РасчётныйЛисток!!! ") == "расчетный листок"


def test_catalog_stores_and_searches_user_facing_aliases(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    summary = catalog.replace_analysis("Z01", "/projects/Z01", _analysis_payload())

    found = catalog.find_reports("Z01", "расчетный листок", limit=5)
    described = catalog.describe_report("Z01", title="Расчетный листок")

    assert summary["reports"] == 1
    assert found[0]["title"] == "Расчетный листок"
    assert found[0]["report"] == "АнализНачисленийИУдержаний"
    assert described["ok"] is True
    assert described["report"]["variant"] == "РасчетныйЛисток"
    assert described["strategies"][0]["strategy"] == "adapter_entrypoint"


def test_catalog_stores_report_runner_policy_and_observations(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")

    catalog.upsert_report_runner_policy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        preferred_runner="ui",
        api_enabled=True,
        ui_enabled=True,
        reason="API returns header-only",
        updated_by="test",
    )
    catalog.add_report_runner_observation(
        database="ERP_DEMO",
        report_name="АнализСебестоимости",
        variant_key="Основной",
        runner_used="ui",
        extractor_used="xlsx_export",
        run_id="run-1",
        artifact_hash="abc",
        observed_signature={"detail_rows_count": 1},
        recommendation="prefer_ui",
    )

    policy = catalog.get_report_runner_policy("ERP_DEMO", "АнализСебестоимости", "Основной")
    observations = catalog.get_report_runner_observations("ERP_DEMO", "АнализСебестоимости", "Основной")

    assert policy["preferred_runner"] == "ui"
    assert policy["api_enabled"] is True
    assert policy["ui_enabled"] is True
    assert observations[0]["runner_used"] == "ui"
    assert observations[0]["observed_signature"]["detail_rows_count"] == 1


def test_catalog_stores_report_ui_strategy(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")

    catalog.upsert_report_ui_strategy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        {
            "open": {"mode": "metadata_link", "metadata_path": "Отчет.АнализСебестоимости"},
            "parameter_map": {"Организация": "Организация", "start": "Начало периода", "end": "Конец периода"},
            "generate_action": {"type": "click_text", "text": "Сформировать"},
            "export": {"format": "xlsx", "action": "save_as"},
        },
        source="verified",
    )

    strategy = catalog.get_report_ui_strategy("ERP_DEMO", "АнализСебестоимости", "Основной")

    assert strategy["source"] == "verified"
    assert strategy["strategy"]["open"]["metadata_path"] == "Отчет.АнализСебестоимости"
    assert strategy["strategy"]["parameter_map"]["Организация"] == "Организация"


def test_describe_report_returns_runner_policy_and_highest_priority_ui_strategy(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "aliases": [{"alias": "Анализ себестоимости"}],
                    "variants": [{"key": "Основной", "presentation": "Основной"}],
                }
            ]
        },
    )
    catalog.upsert_report_runner_policy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        preferred_runner="ui",
        api_enabled=True,
        ui_enabled=True,
        reason="Пользователь выбрал UI для точного табличного результата",
        updated_by="operator",
    )
    catalog.upsert_report_ui_strategy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        {"open": {"mode": "metadata_link", "metadata_path": "Отчет.АнализСебестоимости"}},
        source="verified",
    )
    catalog.upsert_report_ui_strategy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        {"open": {"mode": "section_command", "section": "Производство", "command": "Анализ себестоимости"}},
        source="manual",
    )

    described = catalog.describe_report("ERP_DEMO", title="Анализ себестоимости", variant="Основной")

    assert described["ok"] is True
    assert described["runner_policy"]["preferred_runner"] == "ui"
    assert described["runner_policy"]["updated_by"] == "operator"
    assert described["ui_strategy"]["source"] == "manual"
    assert described["ui_strategy"]["strategy"]["open"]["mode"] == "section_command"


def test_catalog_reports_variant_status_from_variant_strategy(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "СложныйОтчет",
                    "status": "supported",
                    "aliases": [
                        {"alias": "Рабочий вариант", "variant": "Рабочий", "confidence": 0.99},
                        {"alias": "Нерабочий вариант", "variant": "Нерабочий", "confidence": 0.99},
                    ],
                    "variants": [
                        {"key": "Рабочий", "presentation": "Рабочий вариант"},
                        {"key": "Нерабочий", "presentation": "Нерабочий вариант"},
                    ],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "Рабочий", "confidence": 0.7}],
                }
            ]
        },
    )

    rows = {row["title"]: row for row in catalog.list_reports("Z01", limit=10)}

    assert rows["Рабочий вариант"]["status"] == "supported"
    assert rows["Нерабочий вариант"]["status"] == "unsupported"


def test_catalog_stores_report_docs_and_uses_them_for_accountant_search(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
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

    catalog.upsert_report_doc(
        database="Z01",
        report_name="АнализНачисленийИУдержаний",
        variant_key="РасчетныйЛисток",
        source="naparnik",
        query="описание расчетного листка",
        content="Отчет Расчетный листок показывает начисления, удержания и выплату сотруднику.",
        parsed={
            "title": "Расчетный листок",
            "aliases": ["расчетка сотрудника", "листок по зарплате"],
            "summary": "Начисления и удержания сотрудника за период.",
            "source_urls": ["https://its.1c.ru/example"],
            "confidence": 0.91,
        },
    )

    found = catalog.find_reports("Z01", "расчетка сотрудника", limit=5)
    described = catalog.describe_report("Z01", title="листок по зарплате")

    assert found[0]["report"] == "АнализНачисленийИУдержаний"
    assert found[0]["variant"] == "РасчетныйЛисток"
    assert found[0]["alias_source"] == "doc:naparnik"
    assert described["ok"] is True
    assert described["report"]["variant"] == "РасчетныйЛисток"
    assert described["docs"][0]["summary"] == "Начисления и удержания сотрудника за период."
    assert described["docs"][0]["source_urls"] == ["https://its.1c.ru/example"]


def test_catalog_expands_known_accountant_aliases_from_report_doc_title(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {"name": "АнализНачисленийИУдержаний", "aliases": [{"alias": "Расчетный листок"}]},
                {"name": "ОтчетыПоСотрудникам", "aliases": [{"alias": "Отчеты по сотрудникам", "confidence": 0.99}]},
            ]
        },
    )
    catalog.upsert_report_doc(
        database="Z01",
        report_name="АнализНачисленийИУдержаний",
        variant_key="РасчетныйЛисток",
        source="naparnik",
        query="описание",
        content="Официальное описание отчета.",
        parsed={"title": "Расчетный листок", "aliases": [], "summary": "Официальное описание.", "confidence": 0.9},
    )

    found = catalog.find_reports("Z01", "расчетка сотрудника", limit=3)

    assert found[0]["report"] == "АнализНачисленийИУдержаний"
    assert found[0]["alias_source"] == "doc:naparnik"
    assert "doc_norm" not in found[0]


def test_catalog_uses_report_doc_summary_as_alias_when_title_and_aliases_absent(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {"name": "ОтчетБезНазвания", "aliases": [{"alias": "Техническое описание"}]},
            ]
        },
    )
    catalog.upsert_report_doc(
        database="Z01",
        report_name="ОтчетБезНазвания",
        source="naparnik",
        query="описание",
        content="",
        parsed={"summary": "Документальный alias из описания отчета", "confidence": 0.8},
    )

    found = catalog.find_reports("Z01", "документальный alias", limit=3)

    assert found[0]["report"] == "ОтчетБезНазвания"
    assert found[0]["title"] == "Документальный alias из описания отчета"
    assert ReportCatalog._doc_aliases({}, "") == []


def test_catalog_keeps_databases_isolated(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    payload = _analysis_payload()
    catalog.replace_analysis("Z01", "/projects/Z01", payload)
    payload["reports"][0]["name"] = "ДругойОтчет"
    payload["reports"][0]["aliases"][0]["alias"] = "Расчетный листок ERP"
    catalog.replace_analysis("ERP_DEMO", "/projects/ERP_DEMO", payload)

    z01 = catalog.find_reports("Z01", "Расчетный листок", limit=10)
    erp = catalog.find_reports("ERP_DEMO", "Расчетный листок", limit=10)

    assert [row["report"] for row in z01] == ["АнализНачисленийИУдержаний"]
    assert [row["report"] for row in erp] == ["ДругойОтчет"]


def test_catalog_result_storage_is_paged_and_gzipped(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    payload = {"columns": ["N"], "rows": [{"N": i} for i in range(5)], "totals": {}, "metadata": {}}
    run_id = catalog.create_run(
        database="Z01",
        report_name="АнализНачисленийИУдержаний",
        variant_key="РасчетныйЛисток",
        title="Расчетный листок",
        strategy="adapter_entrypoint",
        params={"period": {"from": "2025-12-01", "to": "2025-12-31"}},
    )
    catalog.finish_run("Z01", run_id, status="done", result=payload, diagnostics={"ok": True})

    page = catalog.get_report_result("Z01", run_id, offset=2, limit=2)
    result_file = tmp_path / "results" / "Z01" / f"{run_id}.json.gz"

    assert result_file.exists()
    assert page["ok"] is True
    assert page["rows"] == [{"N": 2}, {"N": 3}]
    assert page["total_rows"] == 5
    assert json.loads(page["diagnostics_json"]) == {"ok": True}


def test_catalog_prefers_verified_output_contract_and_reorders_strategies(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "Себестоимость",
                    "aliases": [{"alias": "Анализ себестоимости", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Анализ себестоимости"}],
                    "strategies": [
                        {"strategy": "raw_skd_runner", "variant": "Основной", "priority": 50, "confidence": 0.6},
                        {"strategy": "bsp_variant_report_runner", "variant": "Основной", "priority": 60, "confidence": 0.8},
                    ],
                    "output_contracts": [
                        {
                            "variant": "Основной",
                            "source": "declared",
                            "contract": {"output_type": "rows", "preferred_strategy": "raw_skd_runner", "confidence": "medium"},
                        }
                    ],
                }
            ]
        },
    )

    catalog.upsert_output_contract(
        "Z01",
        "Себестоимость",
        "Основной",
        "verified",
        {"output_type": "rows", "preferred_strategy": "bsp_variant_report_runner", "confidence": "high"},
    )
    described = catalog.describe_report("Z01", title="Анализ себестоимости")

    assert described["output_contract"]["source"] == "verified"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"


def test_catalog_skips_value_locked_verified_output_contract(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "aliases": [{"alias": "Анализ себестоимости", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Анализ себестоимости"}],
                    "strategies": [
                        {"strategy": "ui_xlsx_runner", "variant": "Основной", "priority": 10, "confidence": 0.9},
                        {"strategy": "bsp_variant_report_runner", "variant": "Основной", "priority": 20, "confidence": 0.8},
                    ],
                    "output_contracts": [
                        {
                            "variant": "Основной",
                            "source": "declared",
                            "contract": {
                                "output_type": "rows",
                                "expected_columns": ["Количество затрат", "Стоимость затрат"],
                                "preferred_strategy": "bsp_variant_report_runner",
                            },
                        }
                    ],
                }
            ]
        },
    )
    catalog.upsert_output_contract(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        "verified",
        {
            "output_type": "rows",
            "expected_columns": ["Услуги переработчика", "15\xa0000,00", "300,00"],
            "preferred_strategy": "ui_xlsx_runner",
        },
    )

    described = catalog.describe_report("ERP_DEMO", title="Анализ себестоимости")

    assert described["output_contract"]["source"] == "declared"
    assert described["output_contract"]["expected_columns"] == ["Количество затрат", "Стоимость затрат"]
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"


def test_catalog_skips_filter_value_locked_verified_output_contract(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "aliases": [{"alias": "Анализ себестоимости", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Анализ себестоимости"}],
                    "strategies": [
                        {"strategy": "ui_xlsx_runner", "variant": "Основной", "priority": 10, "confidence": 0.9},
                        {"strategy": "bsp_variant_report_runner", "variant": "Основной", "priority": 20, "confidence": 0.8},
                    ],
                    "output_contracts": [
                        {
                            "variant": "Основной",
                            "source": "declared",
                            "contract": {
                                "output_type": "rows",
                                "expected_columns": ["Количество затрат", "Стоимость затрат"],
                                "preferred_strategy": "bsp_variant_report_runner",
                            },
                        }
                    ],
                }
            ]
        },
    )
    catalog.upsert_output_contract(
        "ERP_DEMO",
        "АнализСебестоимости",
        "Основной",
        "verified",
        {
            "output_type": "rows",
            "expected_columns": ["Организация", "Металл-Сервис"],
            "preferred_strategy": "ui_xlsx_runner",
        },
    )

    described = catalog.describe_report("ERP_DEMO", title="Анализ себестоимости")

    assert described["output_contract"]["source"] == "declared"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"


def test_catalog_can_upsert_single_report_analysis_without_clobbering_others(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "Отчет1",
                    "aliases": [{"alias": "Отчет 1", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.6}],
                    "output_contracts": [{"variant": "", "source": "declared", "contract": {"preferred_strategy": "raw_skd_runner"}}],
                },
                {
                    "name": "Отчет2",
                    "aliases": [{"alias": "Отчет 2", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "variant": "", "priority": 50, "confidence": 0.6}],
                },
            ]
        },
    )

    updated = catalog.upsert_report_analysis(
        "Z01",
        "/projects/Z01",
        {
            "name": "Отчет1",
            "aliases": [{"alias": "Обновленный отчет 1", "confidence": 1.0}],
            "strategies": [{"strategy": "raw_skd_dataset_query_runner", "variant": "", "priority": 40, "confidence": 0.9}],
            "output_contracts": [{"variant": "", "source": "declared", "contract": {"preferred_strategy": "raw_skd_dataset_query_runner"}}],
        },
    )

    first = catalog.describe_report("Z01", report="Отчет1")
    second = catalog.describe_report("Z01", report="Отчет2")
    found = catalog.find_reports("Z01", "обновленный отчет 1", limit=5)

    assert updated["ok"] is True
    assert first["strategies"][0]["strategy"] == "raw_skd_dataset_query_runner"
    assert first["output_contract"]["preferred_strategy"] == "raw_skd_dataset_query_runner"
    assert second["strategies"][0]["strategy"] == "raw_skd_runner"
    assert found[0]["report"] == "Отчет1"


def test_catalog_covers_error_and_edge_branches(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {},
                {
                    "name": "ОтчетБезСтратегии",
                    "synonym": "Синоним отчета",
                    "aliases": [{"alias": "", "source": "empty"}],
                    "variants": [{"key": ""}],
                    "params": [{"name": ""}],
                    "strategies": [{"strategy": ""}],
                },
            ]
        },
    )

    assert _json_loads("", {"fallback": True}) == {"fallback": True}
    assert _json_loads("{bad", {"fallback": True}) == {"fallback": True}
    assert catalog.list_reports("Z01", query="Синоним", limit=1)[0]["report"] == "ОтчетБезСтратегии"
    assert catalog.find_reports("Z01", "", limit=1)
    assert catalog.describe_report("Z01", title="не найден")["error_code"] == "report_not_found"
    assert catalog.describe_report("Z01", report="нет такого")["error_code"] == "report_not_found"
    assert catalog.resolve_report("EMPTY", title="что угодно")["error_code"] == "report_not_found"
    assert catalog.get_report_result("Z01", "missing")["error_code"] == "report_result_not_found"


def test_catalog_fetches_technical_report_when_alias_rows_are_missing(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "ТехническийОтчет"}]})
    with catalog._connect() as conn:
        conn.execute("DELETE FROM report_aliases WHERE db_slug = ?", ("Z01",))

    resolved = catalog.describe_report("Z01", report="ТехническийОтчет", variant="Вариант")

    assert resolved["ok"] is True
    assert resolved["report"]["title"] == "ТехническийОтчет"
    assert resolved["report"]["variant"] == "Вариант"


def test_catalog_summarizes_validation_campaign_and_resume_point(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    campaign_id = catalog.create_validation_campaign(
        "ERP_DEMO",
        mode="contracts",
        fixture_pack={"period": {"from": "2024-01-01", "to": "2024-12-31"}},
        order=[
            {"report": "Отчет1", "variant": ""},
            {"report": "Отчет2", "variant": ""},
            {"report": "Отчет3", "variant": ""},
        ],
        stop_on_mismatch=True,
    )
    catalog.upsert_validation_item(
        campaign_id,
        ordinal=1,
        database="ERP_DEMO",
        report_name="Отчет1",
        variant_key="",
        title="Отчет 1",
        status="matched",
        terminal_state="matched",
    )
    catalog.upsert_validation_item(
        campaign_id,
        ordinal=2,
        database="ERP_DEMO",
        report_name="Отчет2",
        variant_key="",
        title="Отчет 2",
        status="deferred_engine_gap",
        terminal_state="deferred_engine_gap",
        mismatch_code="missing_detail_rows",
    )
    catalog.finish_validation_campaign(
        campaign_id,
        status="stopped",
        counts={"matched": 1, "deferred_engine_gap": 1},
        summary={"processed": 2, "total_targets": 3},
        stop_reason="deferred_engine_gap",
    )

    summary = catalog.summarize_validation_campaign(campaign_id)
    catalog.mark_validation_campaign_running(campaign_id)
    campaign = catalog.get_validation_campaign(campaign_id)

    assert summary["counts"]["matched"] == 1
    assert summary["counts"]["deferred_engine_gap"] == 1
    assert summary["summary"]["processed"] == 2
    assert summary["summary"]["total_targets"] == 3
    assert summary["summary"]["resume_from_ordinal"] == 2
    assert summary["stopper_item"]["report"] == "Отчет2"
    assert campaign["status"] == "running"
    assert campaign["stop_reason"] == ""


def test_catalog_get_validation_campaign_recomputes_counts_from_items(tmp_path):
    catalog = ReportCatalog(tmp_path / "report-catalog.sqlite", tmp_path / "results")
    campaign_id = catalog.create_validation_campaign(
        "ERP_DEMO",
        mode="contracts",
        order=[{"report": "Отчет1", "variant": ""}],
        stop_on_mismatch=True,
    )
    catalog.upsert_validation_item(
        campaign_id,
        ordinal=1,
        database="ERP_DEMO",
        report_name="Отчет1",
        variant_key="",
        title="Отчет 1",
        status="deferred_engine_gap",
        terminal_state="deferred_engine_gap",
    )
    catalog.finish_validation_campaign(
        campaign_id,
        status="stopped",
        counts={"deferred_engine_gap": 1},
        summary={"processed": 1, "resume_from_ordinal": 1},
        stop_reason="deferred_engine_gap",
    )
    catalog.upsert_validation_item(
        campaign_id,
        ordinal=1,
        database="ERP_DEMO",
        report_name="Отчет1",
        variant_key="",
        title="Отчет 1",
        status="matched",
        terminal_state="matched",
    )

    campaign = catalog.get_validation_campaign(campaign_id)

    assert campaign["counts"]["matched"] == 1
    assert campaign["counts"]["deferred_engine_gap"] == 0
    assert campaign["summary"]["resume_from_ordinal"] == 2
    assert campaign["items"][0]["terminal_state"] == "matched"

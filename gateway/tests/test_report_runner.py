from __future__ import annotations

import asyncio
import json

import pytest
from mcp.types import CallToolResult, TextContent

from gateway.report_catalog import ReportCatalog
from gateway.report_failure import effective_report_run_status
from gateway.report_runner import ReportRunner, ToolkitReportTransport, _bsl_date_literal, _bsl_string, _columns_from_rows


class FakeBackend:
    def __init__(self, payload: dict | str | None = None):
        self.calls = []
        self.payload = payload or {
            "columns": ["Сотрудник", "Начислено"],
            "rows": [{"Сотрудник": "Селезнев", "Начислено": 2633.30}],
            "totals": {"Начислено": 2633.30},
            "metadata": {"source": "fake"},
        }

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return CallToolResult(content=[TextContent(type="text", text=text)])


class SequenceBackend:
    def __init__(self, payloads):
        self.calls = []
        self.payloads = list(payloads)

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        payload = self.payloads.pop(0)
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return CallToolResult(content=[TextContent(type="text", text=text)])


class FakeManager:
    def __init__(self, backend):
        self.backend = backend

    def get_db_backend(self, db_name, role):
        return self.backend if db_name == "Z01" and role == "toolkit" else None


class SlowBackend:
    async def call_tool(self, name, arguments):
        await asyncio.sleep(1)
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({"rows": []}))])


def _catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "АнализНачисленийИУдержаний",
                    "aliases": [{"alias": "Расчетный листок", "source": "template", "confidence": 1.0}],
                    "variants": [{"key": "РасчетныйЛисток", "presentation": "Расчетный листок"}],
                    "strategies": [
                        {
                            "strategy": "adapter_entrypoint",
                            "priority": 10,
                            "confidence": 1.0,
                            "entrypoint": "ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков",
                            "details": {"adapter": "payroll_sheet"},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _raw_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "raw.sqlite", tmp_path / "raw-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "ПростойОтчет",
                    "aliases": [{"alias": "Простой отчет", "variant": "Макет", "confidence": 1.0}],
                    "variants": [{"key": "Макет", "presentation": "Макет", "template": "Макет"}],
                    "strategies": [
                        {
                            "strategy": "raw_skd_runner",
                            "priority": 50,
                            "confidence": 0.7,
                            "variant": "Макет",
                            "details": {"template": "Макет"},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _raw_probe_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "raw-probe.sqlite", tmp_path / "raw-probe-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "ПробныйОтчет",
                    "aliases": [{"alias": "Пробный отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Основной", "template": "ОсновнаяСхемаКомпоновкиДанных"}],
                    "strategies": [
                        {
                            "strategy": "raw_skd_probe_runner",
                            "priority": 90,
                            "confidence": 0.35,
                            "variant": "Основной",
                            "requires_runtime_probe": True,
                            "details": {"template": "ОсновнаяСхемаКомпоновкиДанных"},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _bsp_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "bsp.sqlite", tmp_path / "bsp-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "АнализПравДоступа",
                    "aliases": [{"alias": "Анализ прав доступа", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Основной", "template": "ОсновнаяСхемаКомпоновкиДанных"}],
                    "strategies": [
                        {
                            "strategy": "bsp_variant_report_runner",
                            "priority": 25,
                            "confidence": 0.8,
                            "variant": "Основной",
                            "output_type": "rows",
                            "details": {"template": "ОсновнаяСхемаКомпоновкиДанных"},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _form_artifact_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "form.sqlite", tmp_path / "form-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "РегламентированноеУведомление",
                    "aliases": [{"alias": "Регламентированное уведомление", "confidence": 1.0}],
                    "strategies": [
                        {
                            "strategy": "form_artifact_runner",
                            "priority": 30,
                            "confidence": 0.6,
                            "output_type": "artifact",
                            "details": {"requires_object_ref": True},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _bsp_context_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "bsp-context.sqlite", tmp_path / "bsp-context-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "КонтекстныйОтчет",
                    "aliases": [{"alias": "Контекстный отчет", "variant": "Основной", "confidence": 1.0}],
                    "variants": [{"key": "Основной", "presentation": "Основной", "template": "ОсновнаяСхемаКомпоновкиДанных"}],
                    "strategies": [
                        {
                            "strategy": "bsp_variant_report_runner",
                            "priority": 25,
                            "confidence": 0.8,
                            "variant": "Основной",
                            "details": {"template": "ОсновнаяСхемаКомпоновкиДанных", "requires_object_ref": True},
                        }
                    ],
                }
            ]
        },
    )
    return catalog


def _manager_function_catalog(tmp_path):
    catalog = ReportCatalog(tmp_path / "manager.sqlite", tmp_path / "manager-results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "ВизуализацияУстаревшихУведомлений",
                    "aliases": [{"alias": "Информация для печати", "confidence": 1.0}],
                    "strategies": [
                        {
                            "strategy": "manager_no_arg_function_runner",
                            "priority": 35,
                            "confidence": 0.75,
                            "entrypoint": "ИнформацияДляПечати",
                            "output_type": "rows",
                        }
                    ],
                }
            ]
        },
    )
    return catalog


@pytest.mark.asyncio
async def test_runner_executes_adapter_report_and_persists_result(tmp_path):
    backend = FakeBackend()
    runner = ReportRunner(_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Расчетный листок",
        period={"from": "2025-12-01", "to": "2025-12-31"},
        filters={"Сотрудник": "Селезнев"},
        params={},
        max_rows=100,
    )

    assert result["ok"] is True
    assert result["rows"][0]["Сотрудник"] == "Селезнев"
    assert "ДанныеРасчетныхЛистков" in backend.calls[0][1]["code"]
    assert "Дата(2025, 12, 1)" in backend.calls[0][1]["code"]
    assert "РегистрСведений.ТекущиеКадровыеДанныеСотрудников" in backend.calls[0][1]["code"]
    assert "ДокументРезультат.Область" in backend.calls[0][1]["code"]
    assert backend.calls[0][1]["execution_context"] == "server"
    assert runner.catalog.get_report_result("Z01", result["run_id"])["total_rows"] == 1


@pytest.mark.asyncio
async def test_runner_reports_missing_toolkit_backend(tmp_path):
    runner = ReportRunner(_catalog(tmp_path), ToolkitReportTransport(FakeManager(None)))

    result = await runner.run_report(
        database="Z01",
        title="Расчетный листок",
        period=None,
        filters={},
        params={},
    )

    assert result["ok"] is False
    assert result["error_code"] == "toolkit_not_connected"


@pytest.mark.asyncio
async def test_runner_rejects_unsupported_strategy(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "Отчет", "aliases": [{"alias": "Отчет"}]}]})
    runner = ReportRunner(catalog, ToolkitReportTransport(FakeManager(FakeBackend())))

    result = await runner.run_report(database="Z01", title="Отчет", period=None, filters={}, params={})

    assert result["ok"] is False
    assert result["error_code"] == "report_strategy_failed"


@pytest.mark.asyncio
async def test_runner_propagates_resolver_error_without_transport_call(tmp_path):
    backend = FakeBackend()
    runner = ReportRunner(_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(database="Z01", title="нет такого", period=None, filters={}, params={})

    assert result["ok"] is False
    assert result["error_code"] == "report_not_found"
    assert backend.calls == []


@pytest.mark.asyncio
async def test_runner_executes_raw_skd_when_requested(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}], "metadata": {"raw": True}}})
    runner = ReportRunner(_raw_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Простой отчет",
        period={"start": "2025-01-01"},
        filters={"X": '"quote"'},
        params={"Организация": "Ромашка", "ДатаОстатков": "2025-12-31", "ВключатьУволенных": True},
        strategy="raw_skd_runner",
        max_rows=10,
    )

    assert result["ok"] is True
    assert result["columns"] == ["A"]
    assert "raw SKD runner" in backend.calls[0][1]["code"]
    assert "ПроцессорВыводаРезультатаКомпоновкиДанныхВТабличныйДокумент" in backend.calls[0][1]["code"]
    assert 'ИмяМакетаСКД = "Макет"' in backend.calls[0][1]["code"]
    assert "ПолучитьМакет(ИмяМакетаСКД)" in backend.calls[0][1]["code"]
    assert "ВариантыНастроек.Найти(КлючВарианта)" in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("Период", ДатаОкончанияПериода)' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("СтандартныйПериод", СтандартныйПериодСКД)' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("Дата", ДатаОкончанияПериода)' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("ДатаОстатков", ДатаОкончанияПериода)' in backend.calls[0][1]["code"]
    assert 'Новый ПараметрКомпоновкиДанных("Период")' in backend.calls[0][1]["code"]
    assert 'Новый ПараметрКомпоновкиДанных("Пользователи")' not in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("Пользователи"' not in backend.calls[0][1]["code"]
    assert 'ИмяПараметраСКД = "пользователь"' in backend.calls[0][1]["code"]
    assert 'Найти(ИмяПараметраСКД, "пользовател") > 0' not in backend.calls[0][1]["code"]
    assert "Пользователи.ТекущийПользователь()" in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("X", """quote""")' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("Организация", "Ромашка")' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("ДатаОстатков", Дата(2025, 12, 31))' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("ВключатьУволенных", Истина)' in backend.calls[0][1]["code"]


@pytest.mark.asyncio
async def test_runner_retries_with_standard_period_when_report_needs_period_object(tmp_path):
    backend = SequenceBackend(
        [
            {"success": False, "error": "{<Неизвестный модуль>(355)}: Значение не является значением объектного типа (ДатаНачала)"},
            {"success": True, "data": {"rows": [{"A": 1}], "metadata": {"retry": "standard_period"}}},
        ]
    )
    runner = ReportRunner(_raw_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Простой отчет",
        period={"from": "2025-01-01", "to": "2025-12-31"},
        filters={},
        params={},
        strategy="raw_skd_runner",
    )

    assert result["ok"] is True
    assert len(backend.calls) == 2
    assert 'Настройки.УстановитьЗначениеПараметра("Период", ДатаОкончанияПериода)' in backend.calls[0][1]["code"]
    assert 'Настройки.УстановитьЗначениеПараметра("Период", СтандартныйПериодСКД)' in backend.calls[1][1]["code"]
    assert "{period_value}" not in backend.calls[0][1]["code"]
    assert "{period_value}" not in backend.calls[1][1]["code"]
    assert result["metadata"]["retry"] == "standard_period"


@pytest.mark.asyncio
async def test_runner_can_resolve_exact_technical_report_name(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}]}})
    runner = ReportRunner(_raw_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="",
        report="ПростойОтчет",
        variant="Макет",
        period=None,
        filters={},
        params={},
        strategy="raw_skd_runner",
    )

    assert result["ok"] is True
    assert "ПростойОтчет" in backend.calls[0][1]["code"]


@pytest.mark.asyncio
async def test_runner_executes_raw_skd_probe_strategy(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}], "warnings": ["probe"]}})
    runner = ReportRunner(_raw_probe_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        report="ПробныйОтчет",
        variant="Основной",
        period=None,
        filters={},
        params={},
        strategy="auto",
        max_rows=1,
    )

    assert result["ok"] is True
    assert result["warnings"] == ["probe"]
    assert 'ИмяОтчета = "ПробныйОтчет"' in backend.calls[0][1]["code"]


@pytest.mark.asyncio
async def test_runner_executes_bsp_variant_report_strategy(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}], "metadata": {"source": "bsp"}}})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period={"from": "2025-01-01", "to": "2025-12-31"},
        filters={},
        params={},
        strategy="auto",
        max_rows=1,
    )

    code = backend.calls[0][1]["code"]
    assert result["ok"] is True
    assert "ВариантыОтчетов.СформироватьОтчет" in code
    assert 'ПараметрыФормирования.ПолноеИмя = "Отчет.АнализПравДоступа"' in code
    assert "ПараметрыФормирования.Объект = ОтчетОбъект" in code
    assert "ОтчетОбъект.ИнициализироватьОтчет();" in code
    assert code.index("ОтчетОбъект.ИнициализироватьОтчет();") < code.index("СхемаКомпоновкиДанных = ОтчетОбъект.СхемаКомпоновкиДанных")
    assert "ПараметрыФормирования.СсылкаОтчета" in code
    assert "Справочник.ВариантыОтчетов" in code
    assert 'Настройки.УстановитьЗначениеПараметра("Период", ДатаОкончанияПериода)' in code
    assert 'Настройки.УстановитьЗначениеПараметра("СтандартныйПериод", СтандартныйПериодСКД)' in code


@pytest.mark.asyncio
async def test_runner_applies_user_params_to_bsp_skd_settings(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}]}})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={"Договор": "000000001", "Сценарии": ["План", "Факт"]},
        strategy="auto",
        max_rows=1,
    )

    code = backend.calls[0][1]["code"]
    assert result["ok"] is True
    assert 'Настройки.УстановитьЗначениеПараметра("Договор", "000000001")' in code
    assert "ПользовательскийПараметрСКД" in code
    assert 'ПользовательскийПараметрСКД1.Добавить("План")' in code
    assert 'ПользовательскийПараметрСКД1.Добавить("Факт")' in code
    assert 'Настройки.УстановитьЗначениеПараметра("Сценарии", ПользовательскийПараметрСКД1)' in code


@pytest.mark.asyncio
async def test_runner_executes_manager_no_arg_function_strategy(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"ИмяФормы": "Форма2014_1"}]}})
    runner = ReportRunner(_manager_function_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Информация для печати",
        period=None,
        filters={},
        params={},
        strategy="auto",
        max_rows=1,
    )

    code = backend.calls[0][1]["code"]
    assert result["ok"] is True
    assert "Отчеты.ВизуализацияУстаревшихУведомлений.ИнформацияДляПечати()" in code
    assert "Тип(\"ТаблицаЗначений\")" in code
    assert "source\", \"manager_no_arg_function_runner\"" in code


@pytest.mark.asyncio
async def test_runner_requests_object_ref_for_form_artifact_strategy(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}]}})
    runner = ReportRunner(_form_artifact_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Регламентированное уведомление",
        period=None,
        filters={},
        params={},
        context={},
    )

    assert result["ok"] is False
    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["name"] == "object_description"
    assert result["required_context"][0]["type"] == "_objectRef"
    assert backend.calls == []
    stored = runner.catalog.get_report_result("Z01", result["run_id"])
    assert stored["status"] == "needs_input"


@pytest.mark.asyncio
async def test_runner_requests_object_ref_for_bsp_context_strategy(tmp_path):
    backend = FakeBackend({"success": True, "data": {"rows": [{"A": 1}]}})
    runner = ReportRunner(_bsp_context_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Контекстный отчет",
        period=None,
        filters={},
        params={},
        context={},
    )

    assert result["ok"] is False
    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["type"] == "_objectRef"
    assert backend.calls == []
    stored = runner.catalog.get_report_result("Z01", result["run_id"])
    assert stored["status"] == "needs_input"


@pytest.mark.asyncio
async def test_runner_converts_required_parameter_failure_to_parameter_request(tmp_path):
    backend = FakeBackend({"success": False, "error": 'Ошибка компоновки макета: Не установлено значение параметра "Организация"'})
    runner = ReportRunner(_raw_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Простой отчет",
        period=None,
        filters={},
        params={},
        strategy="raw_skd_runner",
    )

    assert result["ok"] is False
    assert result["error_code"] == "parameter_request"
    assert result["missing"] == [{"name": "Организация", "type": "", "source": "1c_error"}]
    assert "Организация" in result["message"]
    assert result["run_id"]
    stored = runner.catalog.get_report_result("Z01", result["run_id"])
    assert stored["status"] == "needs_input"


@pytest.mark.asyncio
async def test_runner_converts_bsp_missing_arguments_to_parameter_request(tmp_path):
    backend = FakeBackend(
        {
            "success": False,
            "error": 'При вызове процедуры "ВариантыОтчетов.ПодключитьОтчетИЗагрузитьНастройки" не указаны значения параметров "СсылкаВарианта, СсылкаОтчета, КлючВарианта".',
        }
    )
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["ok"] is False
    assert result["error_code"] == "parameter_request"
    assert result["missing"] == [
        {"name": "СсылкаВарианта", "type": "", "source": "1c_error"},
        {"name": "СсылкаОтчета", "type": "", "source": "1c_error"},
        {"name": "КлючВарианта", "type": "", "source": "1c_error"},
    ]


@pytest.mark.asyncio
async def test_runner_converts_unfilled_parameter_to_parameter_request(tmp_path):
    backend = FakeBackend({"success": False, "error": 'Не заполнено значение параметра "Сценарий".'})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "parameter_request"
    assert result["missing"] == [{"name": "Сценарий", "type": "", "source": "1c_error"}]


@pytest.mark.asyncio
async def test_runner_converts_business_selection_errors_to_parameter_request(tmp_path):
    backend = FakeBackend({"success": False, "error": "Не выбран договор"})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "parameter_request"
    assert result["missing"] == [{"name": "Договор", "type": "", "source": "1c_error"}]


@pytest.mark.asyncio
async def test_runner_converts_document_form_error_to_required_context(tmp_path):
    backend = FakeBackend({"success": False, "error": "Отчет о движениях документа возможно открыть из формы документа."})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["name"] == "object_description"
    assert result["run_id"]


@pytest.mark.asyncio
async def test_runner_converts_open_card_error_to_required_context(tmp_path):
    backend = FakeBackend({"success": False, "error": 'Откройте карточку пользователя, перейдите по ссылке "Права доступа".'})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["type"] == "_objectRef"


@pytest.mark.asyncio
async def test_runner_converts_document_only_report_to_required_context(tmp_path):
    backend = FakeBackend({"success": False, "error": "Формирование отчета предусмотрено только для документов с настройкой по сегментам товаров."})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["type"] == "_objectRef"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        'Ошибка создания набора данных "КонтролируемыеСделки": Не найден внешний набор данных "КонтролируемыеСделки"',
        "Данный отчет предназначен только для расшифровки данных показателя бюджетов.",
    ],
)
async def test_runner_converts_external_dataset_errors_to_required_context(tmp_path, error):
    backend = FakeBackend({"success": False, "error": error})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["type"] == "external_dataset_context"


@pytest.mark.asyncio
async def test_runner_converts_headless_runtime_limit_to_unsupported_runtime(tmp_path):
    backend = FakeBackend({"success": False, "error": '{(14, 2)}: Таблица не найдена "ВТКандидаты"'})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "unsupported_runtime"
    assert result["unsupported_reason"]
    assert result["run_id"]
    stored = runner.catalog.get_report_result("Z01", result["run_id"])
    assert stored["status"] == "unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        'Ошибка при вызове метода контекста (УстановитьТекстЗапроса): {(7163, 3)}: Синтаксическая ошибка "ЛЕВОЕ"',
        'Ошибка в схеме компоновки данных: Повторяющийся псевдоним "УченаяСтепень"',
        'Ошибка в выражении: Синтаксическая ошибка "Константы.БазоваяВалютаПоУмолчанию.Получить"',
        "Неизвестное значение перечисления: 31.12.2025 0:00:00",
        "Недопустимое значение параметра (параметр номер '1')",
        'Не удалось записать: "Задания к расчету амортизации ОС"!',
        "Преобразование значения к типу Булево не может быть выполнено",
        'Неверные параметры "ДобавитьКДате"',
        "Неверные параметры в операции сравнения. Нельзя сравнивать поля неограниченной длины и поля несовместимых типов.",
        'Несоответствие типов (Параметр номер ""1"")',
    ],
)
async def test_runner_converts_schema_compilation_limits_to_unsupported_runtime(tmp_path, error):
    backend = FakeBackend({"success": False, "error": error})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "unsupported_runtime"


def test_effective_status_reclassifies_legacy_timeout_row():
    status, diagnostics = effective_report_run_status("error", {}, "Report execution timed out after 15 seconds")

    assert status == "unsupported"
    assert diagnostics["error_code"] == "report_timeout"
    assert diagnostics["unsupported_reason"] == "report_timeout"


@pytest.mark.asyncio
async def test_runner_converts_form_elements_error_to_required_context(tmp_path):
    backend = FakeBackend({"success": False, "error": "Значение не является значением объектного типа (Элементы)"})
    runner = ReportRunner(_bsp_catalog(tmp_path), ToolkitReportTransport(FakeManager(backend)))

    result = await runner.run_report(
        database="Z01",
        title="Анализ прав доступа",
        period=None,
        filters={},
        params={},
    )

    assert result["error_code"] == "required_context"
    assert result["required_context"][0]["type"] == "form_context"


@pytest.mark.asyncio
async def test_transport_handles_invalid_json_and_structured_backend_error(tmp_path):
    invalid = await ToolkitReportTransport(FakeManager(FakeBackend("not-json"))).execute_code("Z01", "code")
    structured = await ToolkitReportTransport(FakeManager(FakeBackend({"ok": False, "error_code": "boom"}))).execute_code("Z01", "code")
    execute_code_error = await ToolkitReportTransport(FakeManager(FakeBackend({"success": False, "error": "bsl failed"}))).execute_code("Z01", "code")

    assert invalid["error_code"] == "report_strategy_failed"
    assert structured["error_code"] == "boom"
    assert execute_code_error["error"] == "bsl failed"


@pytest.mark.asyncio
async def test_runner_times_out_report_execution_and_finishes_run(tmp_path):
    runner = ReportRunner(_raw_catalog(tmp_path), ToolkitReportTransport(FakeManager(SlowBackend())))

    result = await runner.run_report(
        database="Z01",
        report="ПростойОтчет",
        variant="Макет",
        period=None,
        filters={},
        params={},
        strategy="raw_skd_runner",
        timeout_seconds=0.01,
    )

    stored = runner.catalog.get_report_result("Z01", result["run_id"])

    assert result["ok"] is False
    assert result["error_code"] == "report_timeout"
    assert stored["status"] == "unsupported"
    assert stored["error"] == "Report execution timed out after 0.01 seconds"


def test_runner_helpers_cover_empty_rows_and_unknown_strategy_code():
    assert _columns_from_rows([]) == []
    assert _columns_from_rows([1]) == []
    assert _bsl_string('a"b') == 'a""b'
    assert _bsl_date_literal("2025-12-31", "2025-01-01") == "Дата(2025, 12, 31)"
    assert _bsl_date_literal("31.12.2025", "2025-01-01") == 'Дата("31.12.2025")'
    assert _bsl_date_literal("", "2025-01-01") == "Дата(2025, 1, 1)"
    assert ReportRunner._normalize_payload(["x"], 10)["rows"] == [{"value": "x"}]
    assert ReportRunner._normalize_payload("scalar", 10)["rows"] == [{"value": "scalar"}]
    assert ReportRunner._select_strategy([{"strategy": "unsupported_probe"}], "auto") is None
    assert ReportRunner._select_strategy([{"strategy": "raw_skd_runner"}], "adapter_entrypoint") is None
    assert ReportRunner._build_code({}, {"strategy": "unknown"}, {}, {}, {}, 1) == 'Результат = "{}";'

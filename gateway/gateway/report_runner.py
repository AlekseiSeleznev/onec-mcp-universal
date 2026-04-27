"""Runtime execution of cataloged 1C reports via onec-toolkit execute_code."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Protocol

from mcp.types import CallToolResult

from .report_catalog import ReportCatalog, normalize_report_query
from .report_contracts import build_observed_signature, build_verified_output_contract, compare_output_contract
from .report_failure import classify_report_failure, status_from_error_code


_REQUIRED_PARAMETER_RE = re.compile(r'Не установлено значение параметра "([^"]+)"', re.IGNORECASE)
_PARAMETER_NOT_FOUND_RE = re.compile(r'Параметр не найден "([^"]+)"', re.IGNORECASE)
_VALUE_PARAMETER_RE = re.compile(r'Не (?:задано|заполнено) значение параметра "([^"]+)"', re.IGNORECASE)
_MISSING_ARGUMENTS_RE = re.compile(r'не указаны значения параметров "([^"]+)"', re.IGNORECASE)
_DOCUMENT_CONTEXT_RE = re.compile(
    r"(?:возможно открыть из формы документа|предназначен только для открытия в документе|значение должно быть ссылкой|"
    r"откройте карточку пользователя|отчет может быть вызван только|предназначен для использования из вида бюджета)",
    re.IGNORECASE,
)
_FORM_CONTEXT_RE = re.compile(
    r"(?:значение не является значением объектного типа \(элементы\)|поле объекта не обнаружено \(элементы\))",
    re.IGNORECASE,
)
_EXTERNAL_DATASET_CONTEXT_RE = re.compile(
    r"(?:Не найден внешний набор данных|предназначен только для расшифровки данных показателя бюджетов)",
    re.IGNORECASE,
)
_UNSUPPORTED_RUNTIME_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Таблица не найдена", re.IGNORECASE), "dynamic_temporary_table"),
    (re.compile(r"Поле не найдено|Поле объекта не обнаружено", re.IGNORECASE), "dynamic_or_stale_field"),
    (re.compile(r"В выбранных полях диаграммы допускается использование только полей-ресурсов", re.IGNORECASE), "chart_variant_shape"),
    (re.compile(r"Синтаксическая ошибка \"ТекущаяДатаСеанса\"", re.IGNORECASE), "session_date_expression"),
    (re.compile(r"Синтаксическая ошибка \"[^\"]+\.[^\"]+\"", re.IGNORECASE), "unsupported_skd_expression"),
    (re.compile(r"Операция не разрешена в предложении \"ГДЕ\"", re.IGNORECASE), "query_parameter_type"),
    (re.compile(r"Синтаксическая ошибка \"ЛЕВОЕ\"", re.IGNORECASE), "dynamic_query_join_syntax"),
    (re.compile(r"Повторяющийся псевдоним", re.IGNORECASE), "schema_duplicate_alias"),
    (re.compile(r"Неизвестное значение перечисления", re.IGNORECASE), "enum_value_mismatch"),
    (re.compile(r"Недопустимое значение параметра", re.IGNORECASE), "invalid_runtime_parameter"),
    (re.compile(r"Не удалось записать", re.IGNORECASE), "runtime_write_side_effect"),
    (re.compile(r"Преобразование значения к типу Булево не может быть выполнено", re.IGNORECASE), "boolean_conversion_mismatch"),
    (re.compile(r"Неверные параметры \"(?:НАЧАЛОПЕРИОДА|КОНЕЦПЕРИОДА)\"", re.IGNORECASE), "period_expression_type"),
    (re.compile(r"Значение не является значением объектного типа \(Дата\)", re.IGNORECASE), "date_object_expression"),
    (re.compile(r"В настройку отчета внесены критичные изменения", re.IGNORECASE), "critical_settings_change"),
    (re.compile(r"Среди кадровых данных сотрудников нет данных с именем", re.IGNORECASE), "configuration_field_mismatch"),
)
_BUSINESS_PARAMETER_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    (re.compile(r"Не выбран договор", re.IGNORECASE), ("Договор",)),
    (re.compile(r"Не выбрано соглашение", re.IGNORECASE), ("Соглашение",)),
    (re.compile(r"необходимо выбрать карту", re.IGNORECASE), ("Карта",)),
    (re.compile(r"необходимо выбрать счет, вид субконто или значение субконто", re.IGNORECASE), ("Счет", "ВидСубконто", "ЗначениеСубконто")),
)


class ReportTransport(Protocol):
    async def execute_code(self, database: str, code: str) -> dict: ...


class ToolkitReportTransport:
    """Execute generated BSL code against the explicit database toolkit backend."""

    def __init__(self, manager):
        self.manager = manager

    async def execute_code(self, database: str, code: str) -> dict:
        backend = self.manager.get_db_backend(database, "toolkit") if self.manager else None
        if backend is None:
            return {"ok": False, "error_code": "toolkit_not_connected", "error": f"Toolkit backend for '{database}' is not connected"}
        result: CallToolResult = await backend.call_tool(
            "execute_code",
            {"code": code, "execution_context": "server"},
        )
        text = result.content[0].text if result.content else ""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {"ok": False, "error_code": "report_strategy_failed", "error": text}
        if isinstance(payload, dict) and "success" in payload:
            if payload.get("success") is False:
                return {
                    "ok": False,
                    "error_code": "report_strategy_failed",
                    "error": payload.get("error") or "execute_code failed",
                }
            return {"ok": True, "data": payload.get("data")}
        if isinstance(payload, dict) and payload.get("ok") is False:
            return payload
        return {"ok": True, "data": payload}


class ReportRunner:
    """Resolve and execute reports, storing every successful run."""

    def __init__(self, catalog: ReportCatalog, transport: ReportTransport):
        self.catalog = catalog
        self.transport = transport

    async def run_report(
        self,
        *,
        database: str,
        title: str = "",
        report: str | None = None,
        variant: str | None = None,
        period: dict | None,
        filters: dict,
        params: dict,
        output: str = "rows",
        strategy: str = "auto",
        wait: bool = True,
        max_rows: int = 1000,
        timeout_seconds: float = 0,
        context: dict | None = None,
    ) -> dict:
        described = self.catalog.describe_report(
            database,
            title=title,
            report=report,
            variant=variant,
        )
        if not described["ok"]:
            return described
        strategies = described.get("strategies") or []
        selected = self._select_strategy(strategies, strategy)
        if selected is None:
            return {
                "ok": False,
                "error_code": "report_strategy_failed",
                "error": "No executable report strategy is available",
                "report": described["report"],
            }
        run_title = title or described["report"].get("title") or described["report"].get("report", "")
        run_id = self.catalog.create_run(
            database=database,
            report_name=described["report"]["report"],
            variant_key=described["report"].get("variant", ""),
            title=run_title,
            strategy=selected["strategy"],
            params={"period": period, "filters": filters, "params": params, "context": context or {}, "output": output, "wait": wait},
        )
        missing_context = self._missing_context_for_strategy(selected, context or {})
        if missing_context:
            self.catalog.finish_run(
                database,
                run_id,
                status="needs_input",
                diagnostics={"strategy": selected, "error_code": "required_context", "required_context": missing_context},
                error="Для запуска отчета нужен дополнительный контекст.",
            )
            return {
                "ok": False,
                "error_code": "required_context",
                "required_context": missing_context,
                "message": "Для запуска отчета нужен дополнительный контекст.",
                "report": described["report"],
                "run_id": run_id,
            }
        code = self._build_code(described, selected, period or {}, filters or {}, params or {}, max_rows, context or {})
        attempts = [{"period_style": "date"}]
        try:
            if timeout_seconds and timeout_seconds > 0:
                executed = await asyncio.wait_for(self.transport.execute_code(database, code), timeout=timeout_seconds)
            else:
                executed = await self.transport.execute_code(database, code)
        except asyncio.TimeoutError:
            error = f"Report execution timed out after {timeout_seconds:g} seconds"
            self.catalog.finish_run(
                database,
                run_id,
                status="unsupported",
                diagnostics={"strategy": selected, "attempts": attempts, "error_code": "report_timeout", "unsupported_reason": "report_timeout"},
                error=error,
            )
            return {"ok": False, "error_code": "report_timeout", "error": error, "run_id": run_id}
        if not executed["ok"] and _should_retry_with_standard_period(executed):
            attempts.append({"period_style": "standard_period", "previous_error": executed.get("error", "")})
            retry_code = self._build_code(
                described,
                selected,
                period or {},
                filters or {},
                params or {},
                max_rows,
                context or {},
                period_style="standard_period",
            )
            try:
                if timeout_seconds and timeout_seconds > 0:
                    executed = await asyncio.wait_for(self.transport.execute_code(database, retry_code), timeout=timeout_seconds)
                else:
                    executed = await self.transport.execute_code(database, retry_code)
            except asyncio.TimeoutError:
                error = f"Report execution timed out after {timeout_seconds:g} seconds"
                self.catalog.finish_run(
                    database,
                    run_id,
                    status="unsupported",
                    diagnostics={"strategy": selected, "attempts": attempts, "error_code": "report_timeout", "unsupported_reason": "report_timeout"},
                    error=error,
                )
                return {"ok": False, "error_code": "report_timeout", "error": error, "run_id": run_id}
        if not executed["ok"]:
            structured = _structured_execution_error(executed, run_id)
            if not structured and executed.get("error_code"):
                structured = dict(executed)
                structured.setdefault("run_id", run_id)
            if structured:
                persisted_status, diagnostics = self._failure_diagnostics(selected, attempts, structured)
                self.catalog.finish_run(database, run_id, status=persisted_status, diagnostics=diagnostics, error=executed.get("error", ""))
            else:
                self.catalog.finish_run(database, run_id, status="error", diagnostics={"strategy": selected, "attempts": attempts}, error=executed.get("error", ""))
            return structured or executed
        result = self._normalize_payload(executed["data"], max_rows)
        observed_signature = build_observed_signature(result)
        expected_contract = described.get("output_contract") or {}
        comparison = compare_output_contract(expected_contract, observed_signature) if expected_contract else {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}
        diagnostics = {
            "strategy": selected,
            "attempts": attempts,
            "observed_signature": observed_signature,
            "contract_validation": comparison,
        }
        if comparison.get("matched") or comparison.get("acceptable_with_verified"):
            verified_contract = build_verified_output_contract(observed_signature, strategy_name=str(selected.get("strategy") or ""))
            self.catalog.upsert_output_contract(
                database,
                described["report"]["report"],
                described["report"].get("variant", ""),
                "verified",
                verified_contract,
            )
        self.catalog.finish_run(database, run_id, status="done", result=result, diagnostics=diagnostics)
        return {
            "ok": True,
            "run_id": run_id,
            "observed_signature": observed_signature,
            "contract_validation": comparison,
            **result,
        }

    @staticmethod
    def _select_strategy(strategies: list[dict], requested: str) -> dict | None:
        if requested and requested != "auto":
            for strategy in strategies:
                if strategy.get("strategy") == requested:
                    return strategy
            return None
        for strategy in strategies:
            if strategy.get("strategy") in {
                "adapter_entrypoint",
                "bsp_variant_report_runner",
                "context_defaults_runner",
                "raw_skd_dataset_query_runner",
                "raw_skd_runner",
                "raw_skd_probe_runner",
                "form_artifact_runner",
                "manager_no_arg_function_runner",
            }:
                return strategy
        return None

    @staticmethod
    def _build_code(
        described: dict,
        strategy: dict,
        period: dict,
        filters: dict,
        params: dict,
        max_rows: int,
        context: dict | None = None,
        *,
        period_style: str = "date",
    ) -> str:
        report = described.get("report") or {}
        strategy_name = strategy.get("strategy")
        standard_period_params = ReportRunner._standard_period_param_names(described)
        if strategy_name == "adapter_entrypoint" and strategy.get("details", {}).get("adapter") == "payroll_sheet":
            return _payroll_sheet_code(period, filters, params, max_rows)
        if strategy_name in {"bsp_variant_report_runner", "context_defaults_runner"}:
            return _bsp_variant_report_code(
                report.get("report", ""),
                report.get("variant", ""),
                ReportRunner._raw_skd_template_name(described, strategy),
                period,
                filters,
                params,
                max_rows,
                period_style=period_style,
                standard_period_params=standard_period_params,
            )
        if strategy_name == "form_artifact_runner":
            return _form_artifact_code(report.get("report", ""), report.get("variant", ""), context or {}, max_rows)
        if strategy_name == "manager_no_arg_function_runner":
            return _manager_no_arg_function_code(report.get("report", ""), strategy.get("entrypoint", ""), max_rows)
        if strategy_name == "raw_skd_dataset_query_runner":
            details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
            return _raw_skd_dataset_query_code(
                report.get("report", ""),
                report.get("variant", ""),
                ReportRunner._raw_skd_template_name(described, strategy),
                str(details.get("query_text") or ""),
                list(details.get("selected_fields") or []),
                dict(details.get("field_titles") or {}),
                period,
                filters,
                params,
                max_rows,
                period_style=period_style,
                standard_period_params=standard_period_params,
            )
        if strategy_name in {"raw_skd_runner", "raw_skd_probe_runner"}:
            return _raw_skd_code(
                report.get("report", ""),
                report.get("variant", ""),
                ReportRunner._raw_skd_template_name(described, strategy),
                period,
                filters,
                params,
                max_rows,
                period_style=period_style,
                standard_period_params=standard_period_params,
            )
        return "Результат = \"{}\";"

    @staticmethod
    def _standard_period_param_names(described: dict) -> list[str]:
        names = ["ПериодОтчета"]
        for item in described.get("params") or []:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            normalized_name = normalize_report_query(name)
            normalized_type = normalize_report_query(str(item.get("type_name") or ""))
            if "standardperiod" in normalized_type or ("период" in normalized_name and "отчет" in normalized_name):
                names.append(name)
        unique: list[str] = []
        seen: set[str] = set()
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            unique.append(name)
        return unique

    @staticmethod
    def _missing_context_for_strategy(strategy: dict, context: dict) -> list[dict]:
        details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
        if not details.get("requires_object_ref"):
            return []
        object_description = context.get("object_description") if isinstance(context.get("object_description"), dict) else {}
        if object_description.get("_objectRef") or context.get("object_link"):
            return []
        return [
            {
                "name": "object_description",
                "type": "_objectRef",
                "message": "Передайте существующий объект 1С для формы отчета.",
            }
        ]

    @staticmethod
    def _raw_skd_template_name(described: dict, strategy: dict) -> str:
        details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
        template = str(details.get("template") or "").strip()
        if template:
            return template
        report = described.get("report") or {}
        variant_key = str(report.get("variant") or "").strip()
        for variant in described.get("variants") or []:
            if str(variant.get("key") or "") == variant_key:
                template = str(variant.get("template") or "").strip()
                if template:
                    return template
        return "ОсновнаяСхемаКомпоновкиДанных"

    @staticmethod
    def _normalize_payload(payload: dict, max_rows: int) -> dict:
        if isinstance(payload, list):
            payload = {"rows": payload}
        if not isinstance(payload, dict):
            payload = {"rows": [{"value": payload}]}
        rows = list(payload.get("rows") or payload.get("data") or [])
        if rows and not isinstance(rows[0], dict):
            rows = [{"value": item} for item in rows]
        return {
            "columns": payload.get("columns") or _columns_from_rows(rows),
            "rows": rows[: max(0, int(max_rows or 0))],
            "totals": payload.get("totals") or {},
            "metadata": payload.get("metadata") or {},
            "warnings": payload.get("warnings") or [],
            "output_type": payload.get("output_type") or "rows",
            "artifacts": payload.get("artifacts") or [],
            "preview": payload.get("preview") or {},
        }

    @staticmethod
    def _failure_diagnostics(selected: dict, attempts: list[dict], payload: dict) -> tuple[str, dict]:
        error_code = str(payload.get("error_code") or "").strip()
        persisted_status = status_from_error_code(error_code) or "error"
        diagnostics = {"strategy": selected, "attempts": attempts}
        if error_code:
            diagnostics["error_code"] = error_code
        for key in ("missing", "required_context", "unsupported_reason", "message"):
            value = payload.get(key)
            if value not in (None, "", [], {}):
                diagnostics[key] = value
        return persisted_status, diagnostics


def _columns_from_rows(rows: list) -> list[str]:
    if not rows or not isinstance(rows[0], dict):
        return []
    return list(rows[0].keys())


def _bsl_string(value: object) -> str:
    return str(value if value is not None else "").replace('"', '""')


def _bsl_identifier(value: object) -> str:
    raw = str(value or "")
    return raw if re.fullmatch(r"[A-Za-zА-Яа-яЁё_][A-Za-zА-Яа-яЁё0-9_]*", raw) else ""


def _bsl_query_text_literal(value: object) -> str:
    lines = [str(line).rstrip() for line in str(value or "").splitlines()]
    if not lines:
        return ""
    if len(lines) == 1:
        return _bsl_string(lines[0])
    return "\n".join([_bsl_string(lines[0]), *[_bsl_string("|" + line) for line in lines[1:]]])


def _bsl_date_literal(value: object, fallback: str) -> str:
    raw = str(value or fallback)
    parts = raw[:10].split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        year, month, day = (int(part) for part in parts)
        return f"Дата({year}, {month}, {day})"
    return f'Дата("{_bsl_string(raw)}")'


def _bsl_parameter_value_expr(name: str, value: object) -> str:
    if isinstance(value, dict):
        for key in ("value", "date", "_objectRef", "object_ref", "ref", "link"):
            if key in value:
                return _bsl_parameter_value_expr(name, value.get(key))
        return f'"{_bsl_string(json.dumps(value, ensure_ascii=False, sort_keys=True))}"'
    if value is None:
        return "Неопределено"
    if isinstance(value, bool):
        return "Истина" if value else "Ложь"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value == value and value not in {float("inf"), float("-inf")}:
            return repr(value)
        return "Неопределено"
    raw = str(value)
    lowered_name = name.lower()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[tT ].*)?", raw) and any(part in lowered_name for part in ("дата", "период", "день", "начал", "оконч")):
        return _bsl_date_literal(raw, raw)
    return f'"{_bsl_string(raw)}"'


def _user_skd_parameter_code(params: dict) -> str:
    if not isinstance(params, dict):
        params = {}
    blocks = []
    for index, (raw_name, value) in enumerate(params.items()):
        name = str(raw_name or "").strip()
        if not name or value is None:
            continue
        preamble, resolved_expr = _resolve_parameter_value_expr(name, value, index)
        blocks.extend(preamble)
        if isinstance(value, (list, tuple)):
            variable = f"ПользовательскийПараметрСКД{index}"
            blocks.append(f"{variable} = Новый Массив;")
            for item in value:
                if item is None:
                    continue
                blocks.append(f"{variable}.Добавить({_bsl_parameter_value_expr(name, item)});")
            blocks.append(_set_skd_parameter_block(name, variable))
            continue
        blocks.append(_set_skd_parameter_block(name, resolved_expr))
    return "\n".join(blocks)


def _resolve_filter_value_expr(name: str, value: object, index: int) -> tuple[list[str], str]:
    expr = _bsl_parameter_value_expr(name, value)
    normalized = normalize_report_query(name)
    if normalized not in {"организация", "organization"}:
        return [], expr
    if isinstance(value, (list, tuple, dict)) or value is None:
        return [], expr
    variable = f"ЗначениеОтбораСКД{index}"
    search_var = f"СтрокаЗначенияОтбораСКД{index}"
    query_var = f"ЗапросЗначенияОтбораСКД{index}"
    scan_var = f"ВыборкаЗначенияОтбораСКД{index}"
    blocks = [
        f"{search_var} = {expr};",
        f"{variable} = {search_var};",
        "Попытка",
        f"    Если Не ПустаяСтрока({search_var}) Тогда",
        f"        {query_var} = Новый Запрос;",
        f'        {query_var}.Текст = "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1',
        '|   Организации.Ссылка КАК Ссылка',
        '|ИЗ',
        '|   Справочник.Организации КАК Организации',
        '|ГДЕ',
        '|   Организации.Наименование = &ТочноеИмя',
        '|    ИЛИ Организации.Наименование ПОДОБНО &Поиск";',
        f'        {query_var}.УстановитьПараметр("ТочноеИмя", {search_var});',
        f'        {query_var}.УстановитьПараметр("Поиск", "%" + {search_var} + "%");',
        f"        {scan_var} = {query_var}.Выполнить().Выбрать();",
        f"        Если {scan_var}.Следующий() Тогда",
        f"            {variable} = {scan_var}.Ссылка;",
        "        КонецЕсли;",
        "    КонецЕсли;",
        "Исключение",
        f'    Предупреждения.Добавить("Filter reference { _bsl_string(name) } not resolved: " + ОписаниеОшибки());',
        "КонецПопытки;",
    ]
    return blocks, variable


def _resolve_parameter_value_expr(name: str, value: object, index: int) -> tuple[list[str], str]:
    expr = _bsl_parameter_value_expr(name, value)
    normalized = normalize_report_query(name)
    if normalized not in {"пользователь", "user"}:
        return [], expr
    if isinstance(value, (list, tuple, dict)) or value is None:
        return [], expr
    variable = f"ЗначениеПараметраСКД{index}"
    search_var = f"СтрокаЗначенияПараметраСКД{index}"
    query_var = f"ЗапросЗначенияПараметраСКД{index}"
    scan_var = f"ВыборкаЗначенияПараметраСКД{index}"
    blocks = [
        f"{search_var} = {expr};",
        f"{variable} = Неопределено;",
        "Попытка",
        f"    Если Не ПустаяСтрока({search_var}) Тогда",
        f"        {query_var} = Новый Запрос;",
        f'        {query_var}.Текст = "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1',
        '|   Пользователи.Ссылка КАК Ссылка',
        '|ИЗ',
        '|   Справочник.Пользователи КАК Пользователи',
        '|ГДЕ',
        '|   Пользователи.Наименование = &ТочноеИмя',
        '|    ИЛИ Пользователи.Наименование ПОДОБНО &Поиск";',
        f'        {query_var}.УстановитьПараметр("ТочноеИмя", {search_var});',
        f'        {query_var}.УстановитьПараметр("Поиск", "%" + {search_var} + "%");',
        f"        {scan_var} = {query_var}.Выполнить().Выбрать();",
        f"        Если {scan_var}.Следующий() Тогда",
        f"            {variable} = {scan_var}.Ссылка;",
        "        КонецЕсли;",
        "    КонецЕсли;",
        "Исключение",
        f'    Предупреждения.Добавить("Parameter reference { _bsl_string(name) } not resolved: " + ОписаниеОшибки());',
        "КонецПопытки;",
    ]
    return blocks, variable


def _set_skd_filter_block(name: str, value_expr: str) -> str:
    safe_name = _bsl_string(name)
    return f"""
Попытка
    ПолеОтбораСКД = Новый ПолеКомпоновкиДанных("{safe_name}");
    ФильтрСКД = ВариантыОтчетовСлужебныйКлиентСервер.ФильтрРазделаОтчета(Настройки.Отбор, ПолеОтбораСКД);
    Если ФильтрСКД = Неопределено Тогда
        ФильтрСКД = Настройки.Отбор.Элементы.Добавить(Тип("ЭлементОтбораКомпоновкиДанных"));
        ФильтрСКД.ЛевоеЗначение = ПолеОтбораСКД;
    КонецЕсли;
    ФильтрСКД.ВидСравнения = ВидСравненияКомпоновкиДанных.Равно;
    ФильтрСКД.ПравоеЗначение = {value_expr};
    ФильтрСКД.Использование = Истина;
    Если Не ЗначениеЗаполнено(ФильтрСКД.ИдентификаторПользовательскойНастройки) Тогда
        ФильтрСКД.ИдентификаторПользовательскойНастройки = Строка(Новый УникальныйИдентификатор);
    КонецЕсли;
    ФильтрСКД.РежимОтображения = РежимОтображенияЭлементаНастройкиКомпоновкиДанных.БыстрыйДоступ;
Исключение
    Предупреждения.Добавить("SKD filter {safe_name} not set: " + ОписаниеОшибки());
КонецПопытки;
""".strip()


def _user_skd_filter_code(filters: dict) -> str:
    if not isinstance(filters, dict):
        filters = {}
    blocks: list[str] = []
    for index, (raw_name, value) in enumerate(filters.items()):
        name = str(raw_name or "").strip()
        if not name or value is None:
            continue
        if isinstance(value, (list, tuple)):
            continue
        preamble, value_expr = _resolve_filter_value_expr(name, value, index)
        blocks.extend(preamble)
        blocks.append(_set_skd_filter_block(name, value_expr))
    return "\n".join(blocks)


def _query_parameter_set_block(name: str, value_expr: str) -> str:
    safe_name = _bsl_string(name)
    return f"""
Попытка
    Запрос.УстановитьПараметр("{safe_name}", {value_expr});
Исключение
    Предупреждения.Добавить("Query parameter {safe_name} not set: " + ОписаниеОшибки());
КонецПопытки;
""".strip()


def _query_parameter_code(
    period: dict,
    filters: dict,
    params: dict,
    *,
    period_style: str = "date",
    standard_period_params: list[str] | None = None,
) -> str:
    date_from = _bsl_date_literal(period.get("from") or period.get("start"), "0001-01-01")
    date_to = _bsl_date_literal(period.get("to") or period.get("end") or period.get("from") or period.get("start"), "0001-01-01")
    period_value = "СтандартныйПериодЗапроса" if period_style == "standard_period" else "ДатаОкончанияПериода"
    date_params = {
        "НачалоПериода": "ДатаНачалаПериода",
        "Дата": "ДатаОкончанияПериода",
        "ТекущаяДата": "ДатаОкончанияПериода",
        "ДатаНачала": "ДатаНачалаПериода",
        "ДатаС": "ДатаНачалаПериода",
        "ДатаОстатков": "ДатаОкончанияПериода",
        "ПериодНачало": "ДатаНачалаПериода",
        "КонецПериода": "ДатаОкончанияПериода",
        "ДатаОкончания": "ДатаОкончанияПериода",
        "ДатаПо": "ДатаОкончанияПериода",
        "ПериодОкончание": "ДатаОкончанияПериода",
        "Период": period_value,
        "ПериодОтчета": "СтандартныйПериодЗапроса",
        "СтандартныйПериод": "СтандартныйПериодЗапроса",
        "День": "ДатаОкончанияПериода",
    }
    for name in standard_period_params or []:
        clean_name = str(name or "").strip()
        if clean_name:
            date_params.setdefault(clean_name, "СтандартныйПериодЗапроса")
    blocks = [
        f"ДатаНачалаПериода = {date_from};",
        f"ДатаОкончанияПериода = {date_to};",
        "СтандартныйПериодЗапроса = ДатаОкончанияПериода;",
        "Попытка",
        "    СтандартныйПериодЗапроса = Новый СтандартныйПериод(ДатаНачалаПериода, ДатаОкончанияПериода);",
        "Исключение",
        "    СтандартныйПериодЗапроса = ДатаОкончанияПериода;",
        "КонецПопытки;",
    ]
    for name, value in date_params.items():
        blocks.append(_query_parameter_set_block(name, value))
    for index, (raw_name, value) in enumerate((params or {}).items()):
        name = str(raw_name or "").strip()
        if not name or value is None:
            continue
        blocks.extend(_query_parameter_item_blocks(name, value, index))
    offset = len(params or {})
    for index, (raw_name, value) in enumerate((filters or {}).items(), start=offset):
        name = str(raw_name or "").strip()
        if not name or value is None:
            continue
        preamble, value_expr = _resolve_filter_value_expr(name, value, index)
        blocks.extend(preamble)
        blocks.extend(_query_parameter_item_blocks(name, value, index, value_expr=value_expr))
    return "\n".join(blocks)


def _query_parameter_item_blocks(name: str, value: object, index: int, *, value_expr: str | None = None) -> list[str]:
    if value_expr is not None:
        return [_query_parameter_set_block(name, value_expr)]
    if isinstance(value, (list, tuple)):
        variable = f"ПараметрЗапроса{index}"
        blocks = [f"{variable} = Новый Массив;"]
        for item in value:
            if item is None:
                continue
            blocks.append(f"{variable}.Добавить({_bsl_parameter_value_expr(name, item)});")
        blocks.append(_query_parameter_set_block(name, variable))
        return blocks
    preamble, resolved_expr = _resolve_parameter_value_expr(name, value, index)
    return [*preamble, _query_parameter_set_block(name, resolved_expr)]


def _dataset_query_row_field_block(field_name: str, column_title: str, row_key: str, index: int) -> str:
    identifier = _bsl_identifier(field_name)
    if not identifier:
        return ""
    row_identifier = _bsl_identifier(row_key)
    if not row_identifier:
        return ""
    value_var = f"ЗначениеПоляЗапроса{index}"
    type_var = f"ТипЗначенияПоляЗапроса{index}"
    json_var = f"ЗначениеПоляJSON{index}"
    return f"""
    {value_var} = СтрокаТаблицы.{identifier};
    Если {value_var} = Неопределено Тогда
        {json_var} = "";
    Иначе
        {type_var} = ТипЗнч({value_var});
        Если {type_var} = Тип("Строка")
            Или {type_var} = Тип("Число")
            Или {type_var} = Тип("Булево") Тогда
            {json_var} = {value_var};
        ИначеЕсли {type_var} = Тип("Дата") Тогда
            {json_var} = Формат({value_var}, "ДЛФ=yyyy-MM-ddTHH:mm:ss");
        Иначе
            {json_var} = Строка({value_var});
        КонецЕсли;
    КонецЕсли;
    СтрокаРезультата.Вставить("{_bsl_string(row_identifier)}", {json_var});
""".strip()


def _dataset_query_runtime_filter_code(filters: dict, *, start_index: int = 0) -> str:
    if not isinstance(filters, dict):
        filters = {}
    blocks: list[str] = []
    for index, (raw_name, value) in enumerate(filters.items(), start=start_index):
        name = str(raw_name or "").strip()
        if not name or value is None or isinstance(value, dict):
            continue
        safe_name = _bsl_string(name)
        has_column_var = f"ЕстьПолеОтбораЗапроса{index}"
        cell_var = f"ЗначениеПоляОтбораЗапроса{index}"
        normalized_actual_var = f"НормализованноеПолеОтбораЗапроса{index}"
        normalized_expected_var = f"НормализованноеЗначениеОтбораЗапроса{index}"
        if isinstance(value, (list, tuple)):
            continue
        value_expr = _resolve_filter_value_expr(name, value, index)[1]
        blocks.extend(
            [
                f'{has_column_var} = ИсходнаяТаблица.Колонки.Найти("{safe_name}") <> Неопределено;',
                f"Если {has_column_var} Тогда",
                f'    {cell_var} = СтрокаТаблицы["{safe_name}"];',
                f"    Если {cell_var} <> {value_expr} Тогда",
                f'        {normalized_actual_var} = "";',
                f'        {normalized_expected_var} = "";',
                "        Попытка",
                f"            {normalized_actual_var} = СокрЛП(НРег(Строка({cell_var})));",
                "        Исключение",
                "        КонецПопытки;",
                "        Попытка",
                f"            {normalized_expected_var} = СокрЛП(НРег(Строка({value_expr})));",
                "        Исключение",
                "        КонецПопытки;",
                f"        Если {normalized_actual_var} <> {normalized_expected_var} Тогда",
                "            Продолжить;",
                "        КонецЕсли;",
                "    КонецЕсли;",
                "КонецЕсли;",
            ]
        )
    return "\n".join(blocks)


def _payroll_sheet_code(period: dict, filters: dict, params: dict, max_rows: int) -> str:
    employee = _bsl_string(filters.get("Сотрудник") or filters.get("employee") or params.get("Сотрудник") or "")
    organization = _bsl_string(filters.get("Организация") or filters.get("organization") or params.get("Организация") or "")
    date_from = _bsl_date_literal(period.get("from") or period.get("start"), "0001-01-01")
    date_to = _bsl_date_literal(period.get("to") or period.get("end"), str(period.get("from") or period.get("start") or "0001-01-01"))
    return f"""
// Generated by onec-mcp-universal report runner.
Предупреждения = Новый Массив;
ПараметрыЗапуска = Новый Структура;
ПараметрыЗапуска.Вставить("Сотрудник", "{employee}");
ПараметрыЗапуска.Вставить("Организация", "{organization}");
ПараметрыЗапуска.Вставить("ДатаНачала", {date_from});
ПараметрыЗапуска.Вставить("ДатаОкончания", {date_to});
ПараметрыЗапуска.Вставить("МаксимумСтрок", {int(max_rows or 0)});

ФизическиеЛица = Новый Массив;
Организация = Справочники.Организации.ПустаяСсылка();

Если Не ПустаяСтрока(ПараметрыЗапуска.Сотрудник) Тогда
    ЗапросСотрудников = Новый Запрос;
    ЗапросСотрудников.Текст =
        "ВЫБРАТЬ ПЕРВЫЕ 50
        |   Сотрудники.ФизическоеЛицо КАК ФизическоеЛицо,
        |   Кадры.ТекущаяОрганизация КАК ТекущаяОрганизация,
        |   Кадры.ГоловнаяОрганизация КАК ГоловнаяОрганизация
        |ИЗ
        |   Справочник.Сотрудники КАК Сотрудники
        |       ЛЕВОЕ СОЕДИНЕНИЕ РегистрСведений.ТекущиеКадровыеДанныеСотрудников КАК Кадры
        |       ПО Кадры.Сотрудник = Сотрудники.Ссылка
        |ГДЕ
        |   Сотрудники.Наименование ПОДОБНО &Поиск";
    ЗапросСотрудников.УстановитьПараметр("Поиск", "%" + ПараметрыЗапуска.Сотрудник + "%");
    Попытка
        ВыборкаСотрудников = ЗапросСотрудников.Выполнить().Выбрать();
        Пока ВыборкаСотрудников.Следующий() Цикл
            Если ЗначениеЗаполнено(ВыборкаСотрудников.ФизическоеЛицо) Тогда
                ФизическиеЛица.Добавить(ВыборкаСотрудников.ФизическоеЛицо);
            КонецЕсли;
            Если Не ЗначениеЗаполнено(Организация) Тогда
                Если ЗначениеЗаполнено(ВыборкаСотрудников.ТекущаяОрганизация) Тогда
                    Организация = ВыборкаСотрудников.ТекущаяОрганизация;
                ИначеЕсли ЗначениеЗаполнено(ВыборкаСотрудников.ГоловнаяОрганизация) Тогда
                    Организация = ВыборкаСотрудников.ГоловнаяОрганизация;
                КонецЕсли;
            КонецЕсли;
        КонецЦикла;
    Исключение
        Предупреждения.Добавить("Employee organization lookup failed: " + ОписаниеОшибки());
    КонецПопытки;
КонецЕсли;

Если ФизическиеЛица.Количество() = 0 И Не ПустаяСтрока(ПараметрыЗапуска.Сотрудник) Тогда
    ЗапросФизЛиц = Новый Запрос;
    ЗапросФизЛиц.Текст =
        "ВЫБРАТЬ ПЕРВЫЕ 50
        |   ФизическиеЛица.Ссылка КАК ФизическоеЛицо
        |ИЗ
        |   Справочник.ФизическиеЛица КАК ФизическиеЛица
        |ГДЕ
        |   ФизическиеЛица.Наименование ПОДОБНО &Поиск";
    ЗапросФизЛиц.УстановитьПараметр("Поиск", "%" + ПараметрыЗапуска.Сотрудник + "%");
    ВыборкаФизЛиц = ЗапросФизЛиц.Выполнить().Выбрать();
    Пока ВыборкаФизЛиц.Следующий() Цикл
        ФизическиеЛица.Добавить(ВыборкаФизЛиц.ФизическоеЛицо);
    КонецЦикла;
КонецЕсли;

Если Не ПустаяСтрока(ПараметрыЗапуска.Организация) Тогда
    ЗапросОрганизации = Новый Запрос;
    ЗапросОрганизации.Текст =
        "ВЫБРАТЬ ПЕРВЫЕ 1
        |   Организации.Ссылка КАК Организация
        |ИЗ
        |   Справочник.Организации КАК Организации
        |ГДЕ
        |   Организации.Наименование ПОДОБНО &Поиск";
    ЗапросОрганизации.УстановитьПараметр("Поиск", "%" + ПараметрыЗапуска.Организация + "%");
    ВыборкаОрганизации = ЗапросОрганизации.Выполнить().Выбрать();
    Если ВыборкаОрганизации.Следующий() Тогда
        Организация = ВыборкаОрганизации.Организация;
    КонецЕсли;
КонецЕсли;

Если ФизическиеЛица.Количество() = 0 Тогда
    Предупреждения.Добавить("Employee filter did not match any physical person.");
    Результат = Новый Структура(
        "columns, rows, totals, metadata, warnings",
        Новый Массив,
        Новый Массив,
        Новый Структура,
        Новый Структура("source, report, employee_filter", "payroll_sheet_adapter", "АнализНачисленийИУдержаний", ПараметрыЗапуска.Сотрудник),
        Предупреждения);
Иначе
    // Adapter entrypoint discovered from BSL graph/static analysis.
    РезультатДанных = ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков(
        ФизическиеЛица,
        Организация,
        ПараметрыЗапуска.ДатаНачала,
        ПараметрыЗапуска.ДатаОкончания);

    ДокументРезультат = РезультатДанных.ДокументРезультат;
    Колонки = Новый Массив;
    Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
        Колонки.Добавить("C" + Строка(НомерКолонки));
    КонецЦикла;

    Строки = Новый Массив;
    ВсегоСтрок = ДокументРезультат.ВысотаТаблицы;
    Если ПараметрыЗапуска.МаксимумСтрок > 0 И ВсегоСтрок > ПараметрыЗапуска.МаксимумСтрок Тогда
        ВсегоСтрок = ПараметрыЗапуска.МаксимумСтрок;
        Предупреждения.Добавить("Result truncated by max_rows.");
    КонецЕсли;

    Для НомерСтроки = 1 По ВсегоСтрок Цикл
        СтрокаРезультата = Новый Структура;
        ЕстьДанные = Ложь;
        Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
            ИмяКолонки = "C" + Строка(НомерКолонки);
            ТекстЯчейки = "";
            Попытка
                ТекстЯчейки = СокрЛП(Строка(ДокументРезультат.Область(НомерСтроки, НомерКолонки).Текст));
            Исключение
                ТекстЯчейки = "";
            КонецПопытки;
            Если Не ПустаяСтрока(ТекстЯчейки) Тогда
                ЕстьДанные = Истина;
            КонецЕсли;
            СтрокаРезультата.Вставить(ИмяКолонки, ТекстЯчейки);
        КонецЦикла;
        Если ЕстьДанные Тогда
            Строки.Добавить(СтрокаРезультата);
        КонецЕсли;
    КонецЦикла;

    МетаданныеРезультата = Новый Структура;
    МетаданныеРезультата.Вставить("source", "payroll_sheet_adapter");
    МетаданныеРезультата.Вставить("report", "АнализНачисленийИУдержаний");
    МетаданныеРезультата.Вставить("variant", "РасчетныйЛисток");
    МетаданныеРезультата.Вставить("tabular_height", ДокументРезультат.ВысотаТаблицы);
    МетаданныеРезультата.Вставить("tabular_width", ДокументРезультат.ШиринаТаблицы);
    МетаданныеРезультата.Вставить("employee_filter", ПараметрыЗапуска.Сотрудник);
    МетаданныеРезультата.Вставить("organization_filter", ПараметрыЗапуска.Организация);

    Результат = Новый Структура("columns, rows, totals, metadata, warnings", Колонки, Строки, Новый Структура, МетаданныеРезультата, Предупреждения);
КонецЕсли;
""".strip()


def _bsp_variant_report_code(
    report_name: str,
    variant: str,
    template_name: str,
    period: dict,
    filters: dict,
    params: dict,
    max_rows: int,
    *,
    period_style: str = "date",
    standard_period_params: list[str] | None = None,
) -> str:
    report_ref = _bsl_string(report_name)
    variant_key = _bsl_string(variant)
    template_ref = _bsl_string(template_name or "ОсновнаяСхемаКомпоновкиДанных")
    payload = _bsl_string(json.dumps({"period": period, "filters": filters, "params": params, "max_rows": max_rows}, ensure_ascii=False))
    parameter_code = _raw_skd_parameter_code(
        period or {},
        params or {},
        period_style=period_style,
        standard_period_params=standard_period_params,
    )
    filter_code = _user_skd_filter_code(filters or {})
    return f"""
// Generated by onec-mcp-universal BSP report runner.
ПараметрыЗапускаJSON = "{payload}";
ИмяОтчета = "{report_ref}";
КлючВарианта = "{variant_key}";
ИмяМакетаСКД = "{template_ref}";
МаксимумСтрок = {int(max_rows or 0)};
Предупреждения = Новый Массив;

ОтчетОбъект = Отчеты[ИмяОтчета].Создать();
Попытка
    ОтчетОбъект.ИнициализироватьОтчет();
Исключение
    ТекстОшибкиИнициализации = ОписаниеОшибки();
    Если Найти(ТекстОшибкиИнициализации, "Метод объекта не обнаружен (ИнициализироватьОтчет)") = 0 Тогда
        Предупреждения.Добавить("Report initialization skipped: " + ТекстОшибкиИнициализации);
    КонецЕсли;
КонецПопытки;
ПараметрыФормирования = ВариантыОтчетов.ПараметрыФормированияОтчета();
ПараметрыФормирования.Объект = ОтчетОбъект;
ПараметрыФормирования.ПолноеИмя = "Отчет.{report_ref}";
ПараметрыФормирования.КлючВарианта = КлючВарианта;
Попытка
    СсылкаОтчета = ОбщегоНазначения.ИдентификаторОбъектаМетаданных(Метаданные.Отчеты[ИмяОтчета]);
    Если ЗначениеЗаполнено(СсылкаОтчета) Тогда
        ПараметрыФормирования.СсылкаОтчета = СсылкаОтчета;
        СсылкаВарианта = Неопределено;
        Если ПустаяСтрока(КлючВарианта) Тогда
            ЗапросВарианта = Новый Запрос;
            ЗапросВарианта.Текст =
                "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1
                |   ВариантыОтчетов.Ссылка КАК СсылкаВарианта,
                |   ВариантыОтчетов.КлючВарианта КАК КлючВарианта
                |ИЗ
                |   Справочник.ВариантыОтчетов КАК ВариантыОтчетов
                |ГДЕ
                |   ВариантыОтчетов.Отчет = &Отчет
                |
                |УПОРЯДОЧИТЬ ПО
                |   ВариантыОтчетов.ПометкаУдаления";
            ЗапросВарианта.УстановитьПараметр("Отчет", СсылкаОтчета);
            ВыборкаВарианта = ЗапросВарианта.Выполнить().Выбрать();
            Если ВыборкаВарианта.Следующий() Тогда
                СсылкаВарианта = ВыборкаВарианта.СсылкаВарианта;
                КлючВарианта = ВыборкаВарианта.КлючВарианта;
                ПараметрыФормирования.КлючВарианта = КлючВарианта;
            КонецЕсли;
        Иначе
            СсылкаВарианта = ВариантыОтчетов.ВариантОтчета(СсылкаОтчета, КлючВарианта);
            Если СсылкаВарианта = Неопределено Тогда
                ЗапросВарианта = Новый Запрос;
                ЗапросВарианта.Текст =
                    "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1
                    |   ВариантыОтчетов.Ссылка КАК СсылкаВарианта
                    |ИЗ
                    |   Справочник.ВариантыОтчетов КАК ВариантыОтчетов
                    |ГДЕ
                    |   ВариантыОтчетов.Отчет = &Отчет
                    |   И ВариантыОтчетов.КлючВарианта = &КлючВарианта
                    |
                    |УПОРЯДОЧИТЬ ПО
                    |   ВариантыОтчетов.ПометкаУдаления";
                ЗапросВарианта.УстановитьПараметр("Отчет", СсылкаОтчета);
                ЗапросВарианта.УстановитьПараметр("КлючВарианта", КлючВарианта);
                ВыборкаВарианта = ЗапросВарианта.Выполнить().Выбрать();
                Если ВыборкаВарианта.Следующий() Тогда
                    СсылкаВарианта = ВыборкаВарианта.СсылкаВарианта;
                КонецЕсли;
            КонецЕсли;
        КонецЕсли;
        Если СсылкаВарианта <> Неопределено Тогда
            ПараметрыФормирования.СсылкаВарианта = СсылкаВарианта;
        КонецЕсли;
    КонецЕсли;
Исключение
    Предупреждения.Добавить("BSP report variant reference not resolved: " + ОписаниеОшибки());
КонецПопытки;

Подключение = ВариантыОтчетов.ПодключитьОтчетИЗагрузитьНастройки(ПараметрыФормирования);
Если Не Подключение.Успех Тогда
    ВызватьИсключение Подключение.ТекстОшибки;
КонецЕсли;
ПараметрыФормирования.Подключение = Подключение;

Настройки = Подключение.НастройкиКД;
ПользовательскиеНастройки = Подключение.ПользовательскиеНастройкиКД;
Попытка
    Настройки = ОтчетОбъект.КомпоновщикНастроек.ПолучитьНастройки();
Исключение
КонецПопытки;
Попытка
    Если ОтчетОбъект.КомпоновщикНастроек.ПользовательскиеНастройки <> Неопределено Тогда
        ПользовательскиеНастройки = ОтчетОбъект.КомпоновщикНастроек.ПользовательскиеНастройки;
    КонецЕсли;
Исключение
КонецПопытки;
{parameter_code}
{filter_code}
Попытка
    ОтчетОбъект.КомпоновщикНастроек.ЗагрузитьНастройки(Настройки);
Исключение
    Предупреждения.Добавить("BSP settings reload skipped: " + ОписаниеОшибки());
КонецПопытки;
Попытка
    Если ПользовательскиеНастройки <> Неопределено Тогда
        ОтчетОбъект.КомпоновщикНастроек.ЗагрузитьПользовательскиеНастройки(ПользовательскиеНастройки);
    КонецЕсли;
Исключение
    Предупреждения.Добавить("BSP user settings reload skipped: " + ОписаниеОшибки());
КонецПопытки;
Подключение.НастройкиКД = Настройки;
Если ПользовательскиеНастройки <> Неопределено Тогда
    Подключение.ПользовательскиеНастройкиКД = ПользовательскиеНастройки;
КонецЕсли;

Формирование = ВариантыОтчетов.СформироватьОтчет(ПараметрыФормирования, Ложь, Истина);
Если Не Формирование.Успех Тогда
    ВызватьИсключение Формирование.ТекстОшибки;
КонецЕсли;

ДокументРезультат = Формирование.ТабличныйДокумент;
Колонки = Новый Массив;
Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
    Колонки.Добавить("C" + Строка(НомерКолонки));
КонецЦикла;

Строки = Новый Массив;
ВсегоСтрок = ДокументРезультат.ВысотаТаблицы;
Если МаксимумСтрок > 0 И ВсегоСтрок > МаксимумСтрок Тогда
    ВсегоСтрок = МаксимумСтрок;
    Предупреждения.Добавить("Result truncated by max_rows.");
КонецЕсли;

Для НомерСтроки = 1 По ВсегоСтрок Цикл
    СтрокаРезультата = Новый Структура;
    ЕстьДанные = Ложь;
    Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
        ИмяКолонки = "C" + Строка(НомерКолонки);
        ТекстЯчейки = "";
        Попытка
            ТекстЯчейки = СокрЛП(Строка(ДокументРезультат.Область(НомерСтроки, НомерКолонки).Текст));
        Исключение
            ТекстЯчейки = "";
        КонецПопытки;
        Если Не ПустаяСтрока(ТекстЯчейки) Тогда
            ЕстьДанные = Истина;
        КонецЕсли;
        СтрокаРезультата.Вставить(ИмяКолонки, ТекстЯчейки);
    КонецЦикла;
    Если ЕстьДанные Тогда
        Строки.Добавить(СтрокаРезультата);
    КонецЕсли;
КонецЦикла;

КоличествоРисунков = 0;
Попытка
    КоличествоРисунков = ДокументРезультат.Рисунки.Количество();
Исключение
КонецПопытки;
МетаданныеРезультата = Новый Структура;
МетаданныеРезультата.Вставить("report", ИмяОтчета);
МетаданныеРезультата.Вставить("variant", КлючВарианта);
МетаданныеРезультата.Вставить("template", ИмяМакетаСКД);
МетаданныеРезультата.Вставить("source", "bsp_variant_report_runner");
МетаданныеРезультата.Вставить("drawing_count", КоличествоРисунков);
МетаданныеРезультата.Вставить("tabular_height", ДокументРезультат.ВысотаТаблицы);
МетаданныеРезультата.Вставить("tabular_width", ДокументРезультат.ШиринаТаблицы);
МетаданныеРезультата.Вставить("params_json", ПараметрыЗапускаJSON);

Результат = Новый Структура("columns, rows, totals, metadata, warnings, output_type, artifacts, preview",
    Колонки, Строки, Новый Структура, МетаданныеРезультата, Предупреждения, "rows", Новый Массив, Новый Структура);
""".strip()


def _manager_no_arg_function_code(report_name: str, entrypoint: str, max_rows: int) -> str:
    report_ident = _bsl_identifier(report_name)
    entrypoint_ident = _bsl_identifier(entrypoint)
    if not report_ident or not entrypoint_ident:
        return 'ВызватьИсключение "Invalid manager function report strategy";'
    return f"""
// Generated by onec-mcp-universal manager no-arg function runner.
МаксимумСтрок = {int(max_rows or 0)};
Предупреждения = Новый Массив;
РезультатВызова = Отчеты.{report_ident}.{entrypoint_ident}();

Колонки = Новый Массив;
Строки = Новый Массив;

Если ТипЗнч(РезультатВызова) = Тип("ТаблицаЗначений") Тогда
    Для Каждого КолонкаРезультата Из РезультатВызова.Колонки Цикл
        Колонки.Добавить(КолонкаРезультата.Имя);
    КонецЦикла;
    НомерСтроки = 0;
    Для Каждого СтрокаТаблицы Из РезультатВызова Цикл
        НомерСтроки = НомерСтроки + 1;
        Если МаксимумСтрок > 0 И НомерСтроки > МаксимумСтрок Тогда
            Предупреждения.Добавить("Result truncated by max_rows.");
            Прервать;
        КонецЕсли;
        СтрокаРезультата = Новый Структура;
        Для Каждого ИмяКолонки Из Колонки Цикл
            СтрокаРезультата.Вставить(ИмяКолонки, Строка(СтрокаТаблицы[ИмяКолонки]));
        КонецЦикла;
        Строки.Добавить(СтрокаРезультата);
    КонецЦикла;
ИначеЕсли ТипЗнч(РезультатВызова) = Тип("ТабличныйДокумент") Тогда
    Для НомерКолонки = 1 По РезультатВызова.ШиринаТаблицы Цикл
        Колонки.Добавить("C" + Строка(НомерКолонки));
    КонецЦикла;
    ВсегоСтрок = РезультатВызова.ВысотаТаблицы;
    Если МаксимумСтрок > 0 И ВсегоСтрок > МаксимумСтрок Тогда
        ВсегоСтрок = МаксимумСтрок;
        Предупреждения.Добавить("Result truncated by max_rows.");
    КонецЕсли;
    Для НомерСтроки = 1 По ВсегоСтрок Цикл
        СтрокаРезультата = Новый Структура;
        ЕстьДанные = Ложь;
        Для НомерКолонки = 1 По РезультатВызова.ШиринаТаблицы Цикл
            ИмяКолонки = "C" + Строка(НомерКолонки);
            ТекстЯчейки = "";
            Попытка
                ТекстЯчейки = СокрЛП(Строка(РезультатВызова.Область(НомерСтроки, НомерКолонки).Текст));
            Исключение
                ТекстЯчейки = "";
            КонецПопытки;
            Если Не ПустаяСтрока(ТекстЯчейки) Тогда
                ЕстьДанные = Истина;
            КонецЕсли;
            СтрокаРезультата.Вставить(ИмяКолонки, ТекстЯчейки);
        КонецЦикла;
        Если ЕстьДанные Тогда
            Строки.Добавить(СтрокаРезультата);
        КонецЕсли;
    КонецЦикла;
Иначе
    Колонки.Добавить("value");
    СтрокаРезультата = Новый Структура;
    СтрокаРезультата.Вставить("value", Строка(РезультатВызова));
    Строки.Добавить(СтрокаРезультата);
КонецЕсли;

МетаданныеРезультата = Новый Структура;
МетаданныеРезультата.Вставить("report", "{_bsl_string(report_name)}");
МетаданныеРезультата.Вставить("entrypoint", "{_bsl_string(entrypoint)}");
МетаданныеРезультата.Вставить("source", "manager_no_arg_function_runner");

Результат = Новый Структура("columns, rows, totals, metadata, warnings, output_type, artifacts, preview",
    Колонки, Строки, Новый Структура, МетаданныеРезультата, Предупреждения, "rows", Новый Массив, Новый Структура);
""".strip()


def _form_artifact_code(report_name: str, variant: str, context: dict, max_rows: int) -> str:
    report_ref = _bsl_string(report_name)
    variant_key = _bsl_string(variant)
    object_ref = _bsl_string((context.get("object_description") or {}).get("_objectRef") or context.get("object_link") or "")
    return f"""
// Generated by onec-mcp-universal form artifact runner.
ИмяОтчета = "{report_ref}";
КлючВарианта = "{variant_key}";
СсылкаОбъектаСтрокой = "{object_ref}";
МаксимумСтрок = {int(max_rows or 0)};

Артефакты = Новый Массив;
Артефакты.Добавить(Новый Структура("kind, ref", "object_ref", СсылкаОбъектаСтрокой));
МетаданныеРезультата = Новый Структура;
МетаданныеРезультата.Вставить("report", ИмяОтчета);
МетаданныеРезультата.Вставить("variant", КлючВарианта);
МетаданныеРезультата.Вставить("source", "form_artifact_runner");
МетаданныеРезультата.Вставить("object_ref", СсылкаОбъектаСтрокой);
Предпросмотр = Новый Структура("text", "Form artifact runner requires a concrete form adapter for this report.");

Результат = Новый Структура("columns, rows, totals, metadata, warnings, output_type, artifacts, preview",
    Новый Массив, Новый Массив, Новый Структура, МетаданныеРезультата, Новый Массив, "artifact", Артефакты, Предпросмотр);
""".strip()


def _structured_execution_error(executed: dict, run_id: str) -> dict | None:
    return classify_report_failure(str(executed.get("error") or ""), run_id=run_id)


def _should_retry_with_standard_period(executed: dict) -> bool:
    error = str(executed.get("error") or "")
    lowered = error.lower()
    if "период.дата" in lowered:
        return True
    if "значение не является значением объектного типа" in lowered and (
        "датаначала" in lowered or "датаокончания" in lowered
    ):
        return True
    return False


def _raw_skd_code(
    report_name: str,
    variant: str,
    template_name: str,
    period: dict,
    filters: dict,
    params: dict,
    max_rows: int,
    *,
    period_style: str = "date",
    standard_period_params: list[str] | None = None,
) -> str:
    report_ref = _bsl_string(report_name)
    variant_key = _bsl_string(variant)
    template_ref = _bsl_string(template_name or "ОсновнаяСхемаКомпоновкиДанных")
    payload = _bsl_string(json.dumps({"period": period, "filters": filters, "params": params, "max_rows": max_rows}, ensure_ascii=False))
    parameter_code = _raw_skd_parameter_code(
        period or {},
        params or {},
        period_style=period_style,
        standard_period_params=standard_period_params,
    )
    filter_code = _user_skd_filter_code(filters or {})
    return f"""
// Generated by onec-mcp-universal raw SKD runner.
ПараметрыЗапускаJSON = "{payload}";
ИмяОтчета = "{report_ref}";
КлючВарианта = "{variant_key}";
ИмяМакетаСКД = "{template_ref}";
МаксимумСтрок = {int(max_rows or 0)};

Предупреждения = Новый Массив;
Если Не ПустаяСтрока(КлючВарианта) Тогда
    Предупреждения.Добавить("Raw SKD runner uses default settings in v1; variant key is stored in metadata.");
КонецЕсли;

СхемаКомпоновкиДанных = Отчеты[ИмяОтчета].ПолучитьМакет(ИмяМакетаСКД);
Настройки = СхемаКомпоновкиДанных.НастройкиПоУмолчанию;
ПользовательскиеНастройки = Неопределено;
Если Не ПустаяСтрока(КлючВарианта) Тогда
    Попытка
        ВариантНастроекСКД = СхемаКомпоновкиДанных.ВариантыНастроек.Найти(КлючВарианта);
        Если ВариантНастроекСКД <> Неопределено Тогда
            Настройки = ВариантНастроекСКД.Настройки;
        КонецЕсли;
    Исключение
        Предупреждения.Добавить("SKD variant settings not applied: " + ОписаниеОшибки());
    КонецПопытки;
КонецЕсли;
{parameter_code}
{filter_code}

КомпоновщикМакета = Новый КомпоновщикМакетаКомпоновкиДанных;
МакетКомпоновки = КомпоновщикМакета.Выполнить(СхемаКомпоновкиДанных, Настройки);

ПроцессорКомпоновкиДанных = Новый ПроцессорКомпоновкиДанных;
ПроцессорКомпоновкиДанных.Инициализировать(МакетКомпоновки);

ДокументРезультат = Новый ТабличныйДокумент;
ПроцессорВывода = Новый ПроцессорВыводаРезультатаКомпоновкиДанныхВТабличныйДокумент;
ПроцессорВывода.УстановитьДокумент(ДокументРезультат);
ПроцессорВывода.Вывести(ПроцессорКомпоновкиДанных);

Колонки = Новый Массив;
Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
    Колонки.Добавить("C" + Строка(НомерКолонки));
КонецЦикла;

Строки = Новый Массив;
ВсегоСтрок = ДокументРезультат.ВысотаТаблицы;
Если МаксимумСтрок > 0 И ВсегоСтрок > МаксимумСтрок Тогда
    ВсегоСтрок = МаксимумСтрок;
    Предупреждения.Добавить("Result truncated by max_rows.");
КонецЕсли;

Для НомерСтроки = 1 По ВсегоСтрок Цикл
    СтрокаРезультата = Новый Структура;
    ЕстьДанные = Ложь;
    Для НомерКолонки = 1 По ДокументРезультат.ШиринаТаблицы Цикл
        ИмяКолонки = "C" + Строка(НомерКолонки);
        ТекстЯчейки = "";
        Попытка
            ТекстЯчейки = СокрЛП(Строка(ДокументРезультат.Область(НомерСтроки, НомерКолонки).Текст));
        Исключение
            ТекстЯчейки = "";
        КонецПопытки;
        Если Не ПустаяСтрока(ТекстЯчейки) Тогда
            ЕстьДанные = Истина;
        КонецЕсли;
        СтрокаРезультата.Вставить(ИмяКолонки, ТекстЯчейки);
    КонецЦикла;
    Если ЕстьДанные Тогда
        Строки.Добавить(СтрокаРезультата);
    КонецЕсли;
КонецЦикла;

КоличествоРисунков = 0;
Попытка
    КоличествоРисунков = ДокументРезультат.Рисунки.Количество();
Исключение
КонецПопытки;
МетаданныеРезультата = Новый Структура;
МетаданныеРезультата.Вставить("report", ИмяОтчета);
МетаданныеРезультата.Вставить("variant", КлючВарианта);
МетаданныеРезультата.Вставить("template", ИмяМакетаСКД);
МетаданныеРезультата.Вставить("source", "raw_skd_runner");
МетаданныеРезультата.Вставить("drawing_count", КоличествоРисунков);
МетаданныеРезультата.Вставить("tabular_height", ДокументРезультат.ВысотаТаблицы);
МетаданныеРезультата.Вставить("tabular_width", ДокументРезультат.ШиринаТаблицы);
МетаданныеРезультата.Вставить("params_json", ПараметрыЗапускаJSON);

Результат = Новый Структура("columns, rows, totals, metadata, warnings", Колонки, Строки, Новый Структура, МетаданныеРезультата, Предупреждения);
""".strip()


def _raw_skd_dataset_query_code(
    report_name: str,
    variant: str,
    template_name: str,
    query_text: str,
    selected_fields: list[str],
    field_titles: dict[str, str],
    period: dict,
    filters: dict,
    params: dict,
    max_rows: int,
    *,
    period_style: str = "date",
    standard_period_params: list[str] | None = None,
) -> str:
    report_ref = _bsl_string(report_name)
    variant_key = _bsl_string(variant)
    template_ref = _bsl_string(template_name or "ОсновнаяСхемаКомпоновкиДанных")
    safe_query = _bsl_query_text_literal(query_text)
    payload = _bsl_string(json.dumps({"period": period, "filters": filters, "params": params, "max_rows": max_rows}, ensure_ascii=False))
    parameter_code = _query_parameter_code(
        period or {},
        filters or {},
        params or {},
        period_style=period_style,
        standard_period_params=standard_period_params,
    )
    runtime_filter_code = _dataset_query_runtime_filter_code(filters or {}, start_index=len(params or {}))
    columns_code = "\n".join(
        f'Колонки.Добавить("{_bsl_string(field_titles.get(field, field))}");'
        for field in selected_fields
    )
    row_code = "\n".join(
        _dataset_query_row_field_block(field, str(field_titles.get(field, field) or field), field, index)
        for index, field in enumerate(selected_fields)
        if _bsl_identifier(field)
    )
    return f"""
// Generated by onec-mcp-universal direct SKD dataset query runner.
ПараметрыЗапускаJSON = "{payload}";
ИмяОтчета = "{report_ref}";
КлючВарианта = "{variant_key}";
ИмяМакетаСКД = "{template_ref}";
МаксимумСтрок = {int(max_rows or 0)};

Предупреждения = Новый Массив;
Запрос = Новый Запрос;
Запрос.Текст = "{safe_query}";
{parameter_code}

ИсходнаяТаблица = Новый ТаблицаЗначений;
Попытка
    ИсходнаяТаблица = Запрос.Выполнить().Выгрузить();
Исключение
    Предупреждения.Добавить("Direct dataset query execution failed: " + ОписаниеОшибки());
    ВызватьИсключение ОписаниеОшибки();
КонецПопытки;

Колонки = Новый Массив;
{columns_code}

Строки = Новый Массив;
ВсегоПодходящихСтрок = 0;
РезультатОбрезан = Ложь;
Для Каждого СтрокаТаблицы Из ИсходнаяТаблица Цикл
{runtime_filter_code}
    ВсегоПодходящихСтрок = ВсегоПодходящихСтрок + 1;
    Если МаксимумСтрок > 0 И ВсегоПодходящихСтрок > МаксимумСтрок Тогда
        РезультатОбрезан = Истина;
        Продолжить;
    КонецЕсли;
    СтрокаРезультата = Новый Структура;
{row_code}
    Строки.Добавить(СтрокаРезультата);
КонецЦикла;
Если РезультатОбрезан Тогда
    Предупреждения.Добавить("Result truncated by max_rows.");
КонецЕсли;

МетаданныеРезультата = Новый Структура;
МетаданныеРезультата.Вставить("report", ИмяОтчета);
МетаданныеРезультата.Вставить("variant", КлючВарианта);
МетаданныеРезультата.Вставить("template", ИмяМакетаСКД);
МетаданныеРезультата.Вставить("source", "raw_skd_dataset_query_runner");
МетаданныеРезультата.Вставить("dataset_mode", "direct_query");
МетаданныеРезультата.Вставить("rowset_count", ИсходнаяТаблица.Количество());
МетаданныеРезультата.Вставить("filtered_rowset_count", ВсегоПодходящихСтрок);
МетаданныеРезультата.Вставить("params_json", ПараметрыЗапускаJSON);

Результат = Новый Структура("columns, rows, totals, metadata, warnings", Колонки, Строки, Новый Структура, МетаданныеРезультата, Предупреждения);
""".strip()


def _raw_skd_parameter_code(
    period: dict,
    params: dict | None = None,
    *,
    period_style: str = "date",
    standard_period_params: list[str] | None = None,
) -> str:
    date_from = _bsl_date_literal(period.get("from") or period.get("start"), "0001-01-01")
    date_to = _bsl_date_literal(period.get("to") or period.get("end") or period.get("from") or period.get("start"), "0001-01-01")
    period_value = "СтандартныйПериодСКД" if period_style == "standard_period" else "ДатаОкончанияПериода"
    date_params = {
        "НачалоПериода": "ДатаНачалаПериода",
        "Дата": "ДатаОкончанияПериода",
        "ТекущаяДата": "ДатаОкончанияПериода",
        "ДатаНачала": "ДатаНачалаПериода",
        "ДатаС": "ДатаНачалаПериода",
        "ДатаОстатков": "ДатаОкончанияПериода",
        "ПериодНачало": "ДатаНачалаПериода",
        "КонецПериода": "ДатаОкончанияПериода",
        "ДатаОкончания": "ДатаОкончанияПериода",
        "ДатаПо": "ДатаОкончанияПериода",
        "ПериодОкончание": "ДатаОкончанияПериода",
        "Период": period_value,
        "ПериодОтчета": "СтандартныйПериодСКД",
        "СтандартныйПериод": "СтандартныйПериодСКД",
        "День": "ДатаОкончанияПериода",
    }
    for name in standard_period_params or []:
        clean_name = str(name or "").strip()
        if clean_name:
            date_params.setdefault(clean_name, "СтандартныйПериодСКД")
    blocks = [
        f"ДатаНачалаПериода = {date_from};",
        f"ДатаОкончанияПериода = {date_to};",
        "СтандартныйПериодСКД = ДатаОкончанияПериода;",
        "Попытка",
        "    СтандартныйПериодСКД = Новый СтандартныйПериод(ДатаНачалаПериода, ДатаОкончанияПериода);",
        "Исключение",
        "    СтандартныйПериодСКД = ДатаОкончанияПериода;",
        "КонецПопытки;",
        "ТекущийПользовательСКД = Неопределено;",
        "ТекущиеПользователиСКД = Новый Массив;",
        "Попытка",
        "    ТекущийПользовательСКД = Пользователи.ТекущийПользователь();",
        "    Если ТекущийПользовательСКД <> Неопределено Тогда",
        "        ТекущиеПользователиСКД.Добавить(ТекущийПользовательСКД);",
        "    КонецЕсли;",
        "Исключение",
        "    Предупреждения.Добавить(\"Current user lookup failed: \" + ОписаниеОшибки());",
        "КонецПопытки;",
    ]
    for name, value in date_params.items():
        blocks.append(_set_skd_parameter_block(name, value))
    blocks.append(
        f"""
Если ТекущийПользовательСКД <> Неопределено Тогда
    Попытка
        ПараметрСКД = Настройки.ПараметрыДанных.Элементы.Найти(Новый ПараметрКомпоновкиДанных("Пользователь"));
        Если ПараметрСКД <> Неопределено Тогда
            ПараметрСКД.Значение = ТекущийПользовательСКД;
            ПараметрСКД.Использование = Истина;
        КонецЕсли;
    Исключение
        Предупреждения.Добавить("SKD parameter Пользователь not set: " + ОписаниеОшибки());
    КонецПопытки;
КонецЕсли;
""".strip()
    )
    blocks.append(
        f"""
Попытка
    Для Каждого ЭлементПараметраСКД Из Настройки.ПараметрыДанных.Элементы Цикл
        ИмяПараметраСКД = НРег(Строка(ЭлементПараметраСКД.Параметр));
        ТипПараметраСКД = Неопределено;
        ЭтоСтандартныйПериодСКД = Ложь;
        Попытка
            ТипПараметраСКД = ТипЗнч(ЭлементПараметраСКД.Значение);
            Если ТипПараметраСКД = Тип("СтандартныйПериод") Тогда
                ЭтоСтандартныйПериодСКД = Истина;
            КонецЕсли;
        Исключение
        КонецПопытки;
        Если (ИмяПараметраСКД = "пользователь" Или Найти(ИмяПараметраСКД, ".пользователь") > 0) И ТекущийПользовательСКД <> Неопределено Тогда
            ЭлементПараметраСКД.Значение = ТекущийПользовательСКД;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли ЭтоСтандартныйПериодСКД
            И (ИмяПараметраСКД = "период"
                Или Найти(ИмяПараметраСКД, ".период") > 0
                Или Найти(ИмяПараметраСКД, "период") > 0) Тогда
            ЭлементПараметраСКД.Значение = СтандартныйПериодСКД;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли Найти(ИмяПараметраСКД, "начал") > 0 Тогда
            ЭлементПараметраСКД.Значение = ДатаНачалаПериода;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли Найти(ИмяПараметраСКД, "конец") > 0 Или Найти(ИмяПараметраСКД, "оконч") > 0 Тогда
            ЭлементПараметраСКД.Значение = ДатаОкончанияПериода;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли ИмяПараметраСКД = "день" Или Найти(ИмяПараметраСКД, ".день") > 0 Тогда
            ЭлементПараметраСКД.Значение = ДатаОкончанияПериода;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли Найти(ИмяПараметраСКД, "дата") > 0 Тогда
            ЭлементПараметраСКД.Значение = ДатаОкончанияПериода;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли Найти(ИмяПараметраСКД, "стандарт") > 0 И Найти(ИмяПараметраСКД, "период") > 0 Тогда
            ЭлементПараметраСКД.Значение = СтандартныйПериодСКД;
            ЭлементПараметраСКД.Использование = Истина;
        ИначеЕсли ИмяПараметраСКД = "период" Или Найти(ИмяПараметраСКД, ".период") > 0 Или Найти(ИмяПараметраСКД, "период") > 0 Тогда
            ЭлементПараметраСКД.Значение = {period_value};
            ЭлементПараметраСКД.Использование = Истина;
        КонецЕсли;
    КонецЦикла;
Исключение
    Предупреждения.Добавить("SKD parameter scan failed: " + ОписаниеОшибки());
КонецПопытки;
""".strip()
    )
    user_parameter_code = _user_skd_parameter_code(params or {})
    if user_parameter_code:
        blocks.append(user_parameter_code)
    return "\n".join(blocks)


def _set_skd_parameter_block(name: str, value_expr: str) -> str:
    safe_name = _bsl_string(name)
    return f"""
Попытка
    Настройки.УстановитьЗначениеПараметра("{safe_name}", {value_expr});
Исключение
КонецПопытки;
Попытка
    ПараметрСКД = Настройки.ПараметрыДанных.Элементы.Найти("{safe_name}");
    Если ПараметрСКД = Неопределено Тогда
        ПараметрСКД = Настройки.ПараметрыДанных.Элементы.Найти(Новый ПараметрКомпоновкиДанных("{safe_name}"));
    КонецЕсли;
    Если ПараметрСКД <> Неопределено Тогда
        ПараметрСКД.Значение = {value_expr};
        ПараметрСКД.Использование = Истина;
    КонецЕсли;
    Исключение
        Предупреждения.Добавить("SKD parameter {safe_name} not set: " + ОписаниеОшибки());
КонецПопытки;
Попытка
    Если ПользовательскиеНастройки <> Неопределено Тогда
        ЗначениеПараметраСКД = Настройки.ПараметрыДанных.НайтиЗначениеПараметра(Новый ПараметрКомпоновкиДанных("{safe_name}"));
        Если ЗначениеПараметраСКД <> Неопределено
            И ЗначениеЗаполнено(ЗначениеПараметраСКД.ИдентификаторПользовательскойНастройки) Тогда
            ПользовательскийПараметрСКД = ПользовательскиеНастройки.Элементы.Найти(ЗначениеПараметраСКД.ИдентификаторПользовательскойНастройки);
            Если ПользовательскийПараметрСКД <> Неопределено Тогда
                ПользовательскийПараметрСКД.Значение = {value_expr};
                ПользовательскийПараметрСКД.Использование = Истина;
            КонецЕсли;
        КонецЕсли;
    КонецЕсли;
Исключение
    Предупреждения.Добавить("SKD user parameter {safe_name} not set: " + ОписаниеОшибки());
КонецПопытки;
""".strip()

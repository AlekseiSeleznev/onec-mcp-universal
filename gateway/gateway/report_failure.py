"""Classification helpers for persisted 1C report run failures."""

from __future__ import annotations

import re


_REQUIRED_PARAMETER_RE = re.compile(r'Не установлено значение параметра "([^"]+)"', re.IGNORECASE)
_PARAMETER_NOT_FOUND_RE = re.compile(r'Параметр не найден "([^"]+)"', re.IGNORECASE)
_VALUE_PARAMETER_RE = re.compile(r'Не (?:задано|заполнено) значение параметра "([^"]+)"', re.IGNORECASE)
_MISSING_ARGUMENTS_RE = re.compile(r'не указаны значения параметров "([^"]+)"', re.IGNORECASE)
_DOCUMENT_CONTEXT_RE = re.compile(
    r"(?:возможно открыть из формы документа|предназначен только для открытия в документе|значение должно быть ссылкой|"
    r"откройте карточку пользователя|отчет может быть вызван только|предназначен для использования из вида бюджета|"
    r"формирование отчета предусмотрено только для документов)",
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
_TIMEOUT_RE = re.compile(r"Report execution timed out after \d+(?:\.\d+)? seconds", re.IGNORECASE)


def status_from_error_code(error_code: str) -> str | None:
    code = str(error_code or "").strip()
    if code in {"parameter_request", "required_context"}:
        return "needs_input"
    if code in {"unsupported_runtime", "report_timeout"}:
        return "unsupported"
    return None


def classify_report_failure(error: str, *, run_id: str = "") -> dict | None:
    text = str(error or "")
    if _TIMEOUT_RE.search(text):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "report_timeout",
                "message": "Выполнение отчета превысило лимит времени текущего runner'а.",
                "unsupported_reason": "report_timeout",
                "error": text,
            },
            run_id,
        )
    missing = []
    for regex in (_REQUIRED_PARAMETER_RE, _PARAMETER_NOT_FOUND_RE, _VALUE_PARAMETER_RE):
        for match in regex.finditer(text):
            name = match.group(1).strip()
            if name and name not in {item["name"] for item in missing}:
                missing.append({"name": name, "type": "", "source": "1c_error"})
    for match in _MISSING_ARGUMENTS_RE.finditer(text):
        for raw_name in match.group(1).split(","):
            name = raw_name.strip()
            if name and name not in {item["name"] for item in missing}:
                missing.append({"name": name, "type": "", "source": "1c_error"})
    for pattern, names in _BUSINESS_PARAMETER_PATTERNS:
        if pattern.search(text):
            for name in names:
                if name and name not in {item["name"] for item in missing}:
                    missing.append({"name": name, "type": "", "source": "1c_error"})
    if missing:
        return _with_run_id(
            {
                "ok": False,
                "error_code": "parameter_request",
                "message": "Для запуска отчета нужно уточнить параметры: " + ", ".join(item["name"] for item in missing),
                "missing": missing,
                "error": text,
            },
            run_id,
        )
    if _EXTERNAL_DATASET_CONTEXT_RE.search(text):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "required_context",
                "message": "Для запуска отчета нужен внешний набор данных или контекст расшифровки.",
                "required_context": [
                    {
                        "name": "external_dataset_context",
                        "type": "external_dataset_context",
                        "message": "Передайте внешний набор данных, параметры формы или контекст расшифровки, из которого запускается этот вариант.",
                    }
                ],
                "error": text,
            },
            run_id,
        )
    if _DOCUMENT_CONTEXT_RE.search(text):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "required_context",
                "message": "Для запуска отчета нужен существующий объект 1С.",
                "required_context": [
                    {
                        "name": "object_description",
                        "type": "_objectRef",
                        "message": "Передайте существующий объект 1С, из формы которого должен запускаться отчет.",
                    }
                ],
                "error": text,
            },
            run_id,
        )
    if _FORM_CONTEXT_RE.search(text):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "required_context",
                "message": "Для запуска отчета нужен контекст формы 1С.",
                "required_context": [
                    {
                        "name": "form_context",
                        "type": "form_context",
                        "message": "Этот вариант обращается к элементам формы и не может быть выполнен только в серверном контексте.",
                    }
                ],
                "error": text,
            },
            run_id,
        )
    for pattern, reason in _UNSUPPORTED_RUNTIME_PATTERNS:
        if pattern.search(text):
            return _with_run_id(
                {
                    "ok": False,
                    "error_code": "unsupported_runtime",
                    "message": "Вариант отчета распознан, но текущий headless runner не может сформировать его корректно.",
                    "unsupported_reason": reason,
                    "error": text,
                },
                run_id,
            )
    if re.search(r"Несоответствие типов \(Параметр номер", text, re.IGNORECASE):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "unsupported_runtime",
                "message": "Вариант отчета требует runtime-типов, которые текущий headless runner не подбирает автоматически.",
                "unsupported_reason": "runtime_type_mismatch",
                "error": text,
            },
            run_id,
        )
    if re.search(r"Неверные параметры в операции сравнения", text, re.IGNORECASE):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "unsupported_runtime",
                "message": "Вариант отчета использует сравнение типов, которое текущий headless runner не воспроизводит корректно.",
                "unsupported_reason": "query_compare_type_mismatch",
                "error": text,
            },
            run_id,
        )
    if re.search(r'Неверные параметры "ДобавитьКДате"', text, re.IGNORECASE):
        return _with_run_id(
            {
                "ok": False,
                "error_code": "unsupported_runtime",
                "message": "Вариант отчета использует date-выражение, которое текущий headless runner не формирует корректно.",
                "unsupported_reason": "date_function_parameter_type",
                "error": text,
            },
            run_id,
        )
    return None


def effective_report_run_status(status: str, diagnostics: dict | None, error: str, *, run_id: str = "") -> tuple[str, dict]:
    raw_status = str(status or "").strip()
    stored_diagnostics = dict(diagnostics or {})
    if raw_status in {"done", "needs_input", "unsupported"}:
        return raw_status, stored_diagnostics

    error_code = str(stored_diagnostics.get("error_code") or "").strip()
    mapped = status_from_error_code(error_code)
    if mapped:
        return mapped, stored_diagnostics

    if raw_status == "error":
        structured = classify_report_failure(error, run_id=run_id)
        if structured:
            derived = status_from_error_code(str(structured.get("error_code") or ""))
            if derived:
                merged = dict(stored_diagnostics)
                for key, value in structured.items():
                    if key in {"ok", "run_id"}:
                        continue
                    if value in (None, "", [], {}):
                        continue
                    merged[key] = value
                return derived, merged
    return "error", stored_diagnostics


def _with_run_id(payload: dict, run_id: str) -> dict:
    if run_id:
        payload["run_id"] = run_id
    return payload

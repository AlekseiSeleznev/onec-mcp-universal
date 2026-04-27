"""Fixture discovery and parameter planning for bulk report validation."""

from __future__ import annotations

import re
from typing import Any

from .report_catalog import normalize_report_query

VALIDATION_WIDE_PERIOD = {"from": "2000-01-01", "to": "2026-12-31"}


class ReportFixtureProvider:
    def __init__(self, transport):
        self.transport = transport

    async def build_fixture_pack(self, database: str) -> dict[str, Any]:
        fallback = {
            "period": dict(VALIDATION_WIDE_PERIOD),
            "candidate_periods": [dict(VALIDATION_WIDE_PERIOD)],
            "samples": {},
            "context": {},
            "diagnostics": {"source": "fallback"},
        }
        executed = await self.transport.execute_code(database, _fixture_pack_code())
        if not executed.get("ok"):
            fallback["diagnostics"]["error"] = executed.get("error", "")
            return fallback
        payload = executed.get("data")
        if not isinstance(payload, dict):
            return fallback
        samples = payload.get("samples") if isinstance(payload.get("samples"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        detected_period = payload.get("period") if isinstance(payload.get("period"), dict) else {}
        candidate_periods = payload.get("candidate_periods") if isinstance(payload.get("candidate_periods"), list) else fallback["candidate_periods"]
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {"source": "probe"}
        if detected_period:
            diagnostics = dict(diagnostics)
            diagnostics["detected_period"] = {
                "from": str(detected_period.get("from") or ""),
                "to": str(detected_period.get("to") or detected_period.get("from") or ""),
            }
        return {
            "period": dict(VALIDATION_WIDE_PERIOD),
            "candidate_periods": self._normalize_period_candidates(
                [dict(VALIDATION_WIDE_PERIOD), detected_period] + list(candidate_periods or []),
                fallback["candidate_periods"],
            ),
            "samples": samples,
            "context": context,
            "diagnostics": diagnostics,
        }

    def plan_inputs(self, described: dict, fixture_pack: dict[str, Any], *, period_override: dict | None = None) -> dict[str, Any]:
        report = described.get("report") or {}
        params = described.get("params") or []
        chosen_period = (
            period_override
            or self._period_hint_from_variant_metadata(described)
            or self._period_hint_from_report_title(str(report.get("title") or report.get("report") or ""))
            or fixture_pack.get("period")
            or dict(VALIDATION_WIDE_PERIOD)
        )
        samples = fixture_pack.get("samples") if isinstance(fixture_pack.get("samples"), dict) else {}
        context_samples = fixture_pack.get("context") if isinstance(fixture_pack.get("context"), dict) else {}
        filter_hints = self._strategy_filter_hints(described)
        filter_names = self._strategy_filter_names(described)
        planned_params: dict[str, Any] = {}
        planned_filters: dict[str, Any] = {}
        planned_context: dict[str, Any] = {}
        missing: list[dict[str, str]] = []

        if context_samples.get("object_description"):
            planned_context["object_description"] = context_samples["object_description"]

        for item in params:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            value = self._resolve_planned_value(item, chosen_period, samples)
            if value is None:
                if item.get("required"):
                    missing.append({"name": name, "type": str(item.get("type_name") or "")})
                continue
            planned_params[name] = value

        report_title = normalize_report_query(str(report.get("title") or report.get("report") or ""))
        report_name = normalize_report_query(str(report.get("report") or ""))
        variant_name = normalize_report_query(str(report.get("variant") or ""))
        has_organization_scope = "organization" in filter_names or "организац" in report_title
        prefers_single_employee = self._report_prefers_single_employee_filter(report_title)
        prefers_user_param = "пользовател" in report_title
        if self._is_payroll_sheet_report(report_name, report_title, variant_name):
            payroll_employee = samples.get("payroll_employee") or samples.get("employee")
            payroll_organization = samples.get("payroll_organization") or samples.get("organization")
            if payroll_employee:
                planned_params["Сотрудник"] = payroll_employee
                planned_filters["Сотрудник"] = payroll_employee
            if payroll_organization:
                planned_params["Организация"] = payroll_organization
                planned_filters[filter_names.get("organization") or "Организация"] = payroll_organization
        for name, value in samples.items():
            if name == "organization":
                if has_organization_scope and "Организация" not in planned_params:
                    planned_filters[filter_names.get("organization") or "Организация"] = value
            elif name == "employee":
                if prefers_single_employee and not has_organization_scope and "Сотрудник" not in planned_params:
                    planned_filters["Сотрудник"] = value
            elif name == "user":
                if prefers_user_param and "Пользователь" not in planned_params:
                    planned_params["Пользователь"] = value
            elif name == "counterparty":
                if "контрагент" in report_title and "Контрагент" not in planned_params:
                    planned_filters["Контрагент"] = value
            elif name == "item":
                if (
                    any(token in report_title for token in ("номенклат", "материал", "продукц"))
                ) and "Номенклатура" not in planned_params:
                    planned_filters["Номенклатура"] = value

        return {
            "period": chosen_period,
            "params": planned_params,
            "filters": planned_filters,
            "context": planned_context,
            "missing": missing,
        }

    def candidate_periods(self, fixture_pack: dict[str, Any], chosen_period: dict[str, Any] | None) -> list[dict[str, str]]:
        raw_candidates = fixture_pack.get("candidate_periods") if isinstance(fixture_pack.get("candidate_periods"), list) else []
        fallback = [chosen_period or fixture_pack.get("period") or dict(VALIDATION_WIDE_PERIOD)]
        return self._normalize_period_candidates(fallback + raw_candidates, fallback)

    def candidate_filter_values(self, fixture_pack: dict[str, Any], filter_name: str, current_value: Any) -> list[Any]:
        samples = fixture_pack.get("samples") if isinstance(fixture_pack.get("samples"), dict) else {}
        normalized = normalize_report_query(filter_name)
        if normalized not in {normalize_report_query("Организация"), "organization"}:
            return []
        raw_candidates = samples.get("organization_candidates")
        if not isinstance(raw_candidates, list):
            return []
        current_text = str(current_value or "").strip()
        result: list[Any] = []
        seen: set[str] = set()
        for candidate in raw_candidates:
            candidate_text = str(candidate or "").strip()
            if not candidate_text or candidate_text == current_text or candidate_text in seen:
                continue
            seen.add(candidate_text)
            result.append(candidate_text)
        return result

    def resolve_missing(self, missing_items: list[dict], required_context: list[dict], fixture_pack: dict[str, Any]) -> dict[str, Any]:
        samples = fixture_pack.get("samples") if isinstance(fixture_pack.get("samples"), dict) else {}
        context_samples = fixture_pack.get("context") if isinstance(fixture_pack.get("context"), dict) else {}
        chosen_period = fixture_pack.get("period") if isinstance(fixture_pack.get("period"), dict) else dict(VALIDATION_WIDE_PERIOD)
        params: dict[str, Any] = {}
        context: dict[str, Any] = {}
        unresolved: list[dict] = []
        for item in missing_items:
            name = str(item.get("name") or "").strip()
            value = self._resolve_value(name, str(item.get("type") or ""), samples, chosen_period)
            if value is None:
                unresolved.append(item)
            else:
                params[name] = value
        for item in required_context:
            name = str(item.get("name") or "").strip()
            if name == "object_description" and context_samples.get("object_description"):
                context["object_description"] = context_samples["object_description"]
            else:
                unresolved.append(item)
        return {"params": params, "context": context, "unresolved": unresolved}

    def _resolve_planned_value(self, item: dict[str, Any], chosen_period: dict[str, Any], samples: dict[str, Any]) -> Any:
        name = str(item.get("name") or "").strip()
        type_name = str(item.get("type_name") or "")
        value = self._resolve_value(name, type_name, samples, chosen_period)
        if value is not None:
            return value
        if (
            not item.get("required")
            and isinstance(item.get("default"), bool)
            and item.get("default") is False
            and self._is_optional_display_toggle(name, type_name)
        ):
            return None
        return self._safe_default_value(type_name, item.get("default"))

    def _resolve_value(self, name: str, type_name: str, samples: dict[str, Any], chosen_period: dict[str, Any] | None = None) -> Any:
        normalized = normalize_report_query(name)
        type_norm = normalize_report_query(type_name)
        period_from = str((chosen_period or {}).get("from") or (chosen_period or {}).get("start") or "").strip()
        period_to = str((chosen_period or {}).get("to") or (chosen_period or {}).get("end") or period_from).strip()
        if normalized in {"период день", "периоддень"} or ("период" in normalized and "день" in normalized):
            return period_to or period_from or None
        if normalized in {"дата", "день"}:
            return period_to or period_from or None
        if normalized in {"начало периода", "дата с", "период начало"} or ("дата" in normalized and "начал" in normalized):
            return period_from or None
        if normalized in {"конец периода", "дата окончания", "дата по", "период окончание"} or ("дата" in normalized and ("конец" in normalized or "оконч" in normalized)):
            return period_to or period_from or None
        if "организац" in normalized or "организац" in type_norm:
            return samples.get("organization")
        if "сотруд" in normalized or "физлиц" in normalized or "сотрудник" in type_norm:
            return samples.get("employee")
        if "контрагент" in normalized or "контрагент" in type_norm:
            return samples.get("counterparty")
        if any(token in normalized for token in ("номенклат", "товар", "материал", "продукц")) or "номенклат" in type_norm:
            return samples.get("item")
        if "склад" in normalized or "склад" in type_norm:
            return samples.get("warehouse")
        if "валют" in normalized or "валют" in type_norm:
            return samples.get("currency")
        if "соглаш" in normalized:
            return samples.get("agreement")
        if "договор" in normalized:
            return samples.get("contract")
        if "сценар" in normalized:
            return samples.get("scenario")
        if "подраздел" in normalized:
            return samples.get("department")
        if "пользоват" in normalized:
            if not type_norm or self._is_reference_type(type_norm):
                return samples.get("user") if type_norm else None
            return samples.get("user")
        return None

    @staticmethod
    def _safe_default_value(type_name: str, default: Any) -> Any:
        if default is None or isinstance(default, dict):
            return None
        if isinstance(default, bool):
            return default
        if isinstance(default, (int, float)):
            return default
        if isinstance(default, str):
            cleaned = default.strip()
            if not cleaned:
                return None
            type_norm = normalize_report_query(type_name)
            if ReportFixtureProvider._is_reference_type(type_norm) or any(
                token in type_norm for token in ("standardperiod", "date", "datetime", "дата", "период")
            ):
                return None
            if cleaned in {"0001-01-01T00:00:00", "0001-01-01"}:
                return None
            if "ПустаяСсылка" in cleaned or "." in cleaned or ":" in cleaned:
                return None
            if cleaned.isascii() and any(char.isupper() for char in cleaned):
                return None
            return cleaned
        return None

    @staticmethod
    def _is_reference_type(type_norm: str) -> bool:
        return any(token in type_norm for token in ("справочник", "catalogref", "catalog ref", "document ref", "documentref"))

    @staticmethod
    def _is_optional_display_toggle(name: str, type_name: str) -> bool:
        normalized = normalize_report_query(name)
        type_norm = normalize_report_query(type_name)
        if "bool" not in type_norm and "булево" not in type_norm and "boolean" not in type_norm:
            return False
        return any(token in normalized for token in ("вывод", "отображ", "показ", "детализ"))

    def _strategy_filter_hints(self, described: dict) -> set[str]:
        hints: set[str] = set()
        for strategy in described.get("strategies") or []:
            details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
            for field in list(details.get("filter_fields") or []):
                normalized = normalize_report_query(str(field or ""))
                if normalized:
                    hints.add(normalized)
            for title in dict(details.get("filter_titles") or {}).values():
                normalized = normalize_report_query(str(title or ""))
                if normalized:
                    hints.add(normalized)
        return hints

    def _strategy_filter_names(self, described: dict) -> dict[str, str]:
        names: dict[str, str] = {}
        for strategy in described.get("strategies") or []:
            details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
            filter_fields = list(details.get("filter_fields") or [])
            filter_titles = dict(details.get("filter_titles") or {})
            for field in filter_fields:
                candidate = str(field or "").strip()
                normalized = normalize_report_query(candidate)
                if normalized == normalize_report_query("Организация") and "organization" not in names:
                    names["organization"] = candidate
        return names

    @staticmethod
    def _normalize_period_candidates(raw_candidates: list[Any], fallback: list[dict[str, str]]) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in raw_candidates or fallback:
            if not isinstance(item, dict):
                continue
            date_from = str(item.get("from") or item.get("start") or "").strip()
            date_to = str(item.get("to") or item.get("end") or date_from).strip()
            if not date_from or not date_to:
                continue
            key = (date_from, date_to)
            if key in seen:
                continue
            seen.add(key)
            result.append({"from": date_from, "to": date_to})
        if result:
            return result
        return [dict(VALIDATION_WIDE_PERIOD)]

    @staticmethod
    def _period_hint_from_report_title(report_title: str) -> dict[str, str] | None:
        return ReportFixtureProvider._period_hint_from_text(report_title)

    @staticmethod
    def _period_hint_from_variant_metadata(described: dict[str, Any]) -> dict[str, str] | None:
        report = described.get("report") if isinstance(described.get("report"), dict) else {}
        variant_key = str(report.get("variant") or "").strip()
        if not variant_key:
            return None
        for variant in described.get("variants") or []:
            if str(variant.get("key") or "").strip() != variant_key:
                continue
            details = variant.get("details") if isinstance(variant.get("details"), dict) else {}
            description = str(details.get("description") or "").strip()
            if description:
                return ReportFixtureProvider._period_hint_from_text(description)
        return None

    @staticmethod
    def _period_hint_from_text(text: str) -> dict[str, str] | None:
        normalized = normalize_report_query(text)
        until_year_match = re.search(r"\bдо\s+20(\d{2})\s+г", normalized)
        if until_year_match:
            until_year = int("20" + until_year_match.group(1))
            target_year = until_year - 1
            if 2000 <= target_year <= 2099:
                return {"from": f"{target_year:04d}-01-01", "to": f"{target_year:04d}-12-31"}
        obsolete_since_match = re.search(r"\bутратил[аи]?\s+актуальност[ьи]\s+с\s+20(\d{2})\s+г", normalized)
        if obsolete_since_match:
            obsolete_since_year = int("20" + obsolete_since_match.group(1))
            target_year = obsolete_since_year - 1
            if 2000 <= target_year <= 2099:
                return {"from": f"{target_year:04d}-01-01", "to": f"{target_year:04d}-12-31"}
        available_until_match = re.search(r"\bпо\s+20(\d{2})\s+год\b", normalized)
        if available_until_match and "включительно" in normalized:
            target_year = int("20" + available_until_match.group(1))
            if 2000 <= target_year <= 2099:
                return {"from": f"{target_year:04d}-01-01", "to": f"{target_year:04d}-12-31"}
        return None

    @staticmethod
    def _is_payroll_sheet_report(report_name: str, report_title: str, variant_name: str) -> bool:
        if report_name != normalize_report_query("АнализНачисленийИУдержаний"):
            return False
        return "расчетный листок" in report_title or "расчетный листок" in variant_name

    @staticmethod
    def _report_prefers_single_employee_filter(report_title: str) -> bool:
        return bool(
            re.search(r"\bсотрудника\b", report_title)
            or re.search(r"\bфизлица\b", report_title)
            or re.search(r"\bфизического лица\b", report_title)
        )


def _fixture_pack_code() -> str:
    sample_blocks = [
        _fixture_sample_block(
            "employee",
            "Сотрудники",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Сотрудники.Наименование КАК Значение ИЗ Справочник.Сотрудники КАК Сотрудники ГДЕ НЕ Сотрудники.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "item",
            "Номенклатура",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Номенклатура.Наименование КАК Значение ИЗ Справочник.Номенклатура КАК Номенклатура ГДЕ НЕ Номенклатура.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "warehouse",
            "Склады",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Склады.Наименование КАК Значение ИЗ Справочник.Склады КАК Склады ГДЕ НЕ Склады.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "counterparty",
            "Контрагенты",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Контрагенты.Наименование КАК Значение ИЗ Справочник.Контрагенты КАК Контрагенты ГДЕ НЕ Контрагенты.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "currency",
            "Валюты",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Валюты.Наименование КАК Значение ИЗ Справочник.Валюты КАК Валюты ГДЕ НЕ Валюты.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "agreement",
            "СоглашенияСКлиентами",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 СоглашенияСКлиентами.Наименование КАК Значение ИЗ Справочник.СоглашенияСКлиентами КАК СоглашенияСКлиентами ГДЕ НЕ СоглашенияСКлиентами.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "contract",
            "ДоговорыКонтрагентов",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 ДоговорыКонтрагентов.Наименование КАК Значение ИЗ Справочник.ДоговорыКонтрагентов КАК ДоговорыКонтрагентов ГДЕ НЕ ДоговорыКонтрагентов.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "scenario",
            "СценарииТоварногоПланирования",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 СценарииТоварногоПланирования.Наименование КАК Значение ИЗ Справочник.СценарииТоварногоПланирования КАК СценарииТоварногоПланирования ГДЕ НЕ СценарииТоварногоПланирования.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "department",
            "ПодразделенияОрганизаций",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 ПодразделенияОрганизаций.Наименование КАК Значение ИЗ Справочник.ПодразделенияОрганизаций КАК ПодразделенияОрганизаций ГДЕ НЕ ПодразделенияОрганизаций.ПометкаУдаления",
            "Значение",
        ),
        _fixture_sample_block(
            "user",
            "Пользователи",
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 1 Пользователи.Наименование КАК Значение ИЗ Справочник.Пользователи КАК Пользователи ГДЕ НЕ Пользователи.ПометкаУдаления",
            "Значение",
        ),
    ]
    return f"""
Результат = Новый Структура;
Диагностика = Новый Структура;
Диагностика.Вставить("source", "execute_code_probe");
Образцы = Новый Структура;
Контекст = Новый Структура;
Период = Новый Структура("from, to", "2024-01-01", "2024-12-31");
КандидатПериоды = Новый Массив;
КлючиПериодов = Новый Соответствие;
ЛучшаяДата = '00010101';
{chr(10).join(sample_blocks)}

Попытка
    Если Метаданные.Справочники.Найти("Организации") <> Неопределено Тогда
        КандидатыОрганизаций = Новый Массив;
        ЗапросОрганизаций = Новый Запрос;
        ЗапросОрганизаций.Текст =
            "ВЫБРАТЬ РАЗРЕШЕННЫЕ ПЕРВЫЕ 12
            |   Организации.Наименование КАК Значение
            |ИЗ
            |   Справочник.Организации КАК Организации
            |ГДЕ
            |   НЕ Организации.ПометкаУдаления
            |УПОРЯДОЧИТЬ ПО
            |   Организации.Наименование";
        ВыборкаОрганизаций = ЗапросОрганизаций.Выполнить().Выбрать();
        Пока ВыборкаОрганизаций.Следующий() Цикл
            ИмяОрганизацииОбразца = Строка(ВыборкаОрганизаций.Значение);
            Если ПустаяСтрока(ИмяОрганизацииОбразца) Тогда
                Продолжить;
            КонецЕсли;
            КандидатыОрганизаций.Добавить(ИмяОрганизацииОбразца);
            ТекущееЗначениеОрганизации = "";
            Если Не Образцы.Свойство("organization", ТекущееЗначениеОрганизации) Или ПустаяСтрока(Строка(ТекущееЗначениеОрганизации)) Тогда
                Образцы.Вставить("organization", ИмяОрганизацииОбразца);
            КонецЕсли;
        КонецЦикла;
        Если КандидатыОрганизаций.Количество() > 0 Тогда
            Образцы.Вставить("organization_candidates", КандидатыОрганизаций);
        КонецЕсли;
    КонецЕсли;
Исключение
КонецПопытки;

Для Каждого МетаДокумент Из Метаданные.Документы Цикл
    Попытка
        ИмяДокумента = МетаДокумент.Имя;
        ЗапросДок = Новый Запрос;
        ЗапросДок.Текст =
            "ВЫБРАТЬ ПЕРВЫЕ 3
            |   Док.Ссылка КАК Ссылка,
            |   Док.Дата КАК Дата
            |ИЗ
            |   Документ." + ИмяДокумента + " КАК Док
            |УПОРЯДОЧИТЬ ПО
            |   Док.Дата УБЫВ";
        ВыборкаДок = ЗапросДок.Выполнить().Выбрать();
        Пока ВыборкаДок.Следующий() Цикл
            ДатаДняСтрокой = Формат(НачалоДня(ВыборкаДок.Дата), "ДФ=yyyy-MM-dd");
            НачалоПериодаСтрокой = Формат(НачалоМесяца(ВыборкаДок.Дата), "ДФ=yyyy-MM-dd");
            КонецПериодаСтрокой = Формат(КонецМесяца(ВыборкаДок.Дата), "ДФ=yyyy-MM-dd");
            КлючДня = ДатаДняСтрокой + "|" + ДатаДняСтрокой;
            Если Не КлючиПериодов.Содержит(КлючДня) Тогда
                КлючиПериодов.Вставить(КлючДня, Истина);
                КандидатПериоды.Добавить(Новый Структура("from, to", ДатаДняСтрокой, ДатаДняСтрокой));
            КонецЕсли;
            КлючМесяца = НачалоПериодаСтрокой + "|" + КонецПериодаСтрокой;
            Если Не КлючиПериодов.Содержит(КлючМесяца) Тогда
                КлючиПериодов.Вставить(КлючМесяца, Истина);
                КандидатПериоды.Добавить(Новый Структура("from, to", НачалоПериодаСтрокой, КонецПериодаСтрокой));
            КонецЕсли;
            Если ВыборкаДок.Дата > ЛучшаяДата Тогда
                ЛучшаяДата = ВыборкаДок.Дата;
                Контекст.Вставить("object_description", Новый Структура("_objectRef", Строка(ВыборкаДок.Ссылка)));
                Период.Вставить("to", КонецПериодаСтрокой);
                Период.Вставить("from", НачалоПериодаСтрокой);
            КонецЕсли;
            Если КандидатПериоды.Количество() >= 12 Тогда
                Прервать;
            КонецЕсли;
        КонецЦикла;
    Исключение
    КонецПопытки;
    Если КандидатПериоды.Количество() >= 12 Тогда
        Прервать;
    КонецЕсли;
КонецЦикла;

Если КандидатПериоды.Количество() = 0 Тогда
    КандидатПериоды.Добавить(Новый Структура("from, to", Период.from, Период.to));
КонецЕсли;

Попытка
    Если Метаданные.ОбщиеМодули.Найти("ЗарплатаКадрыОтчеты") <> Неопределено Тогда
        Если СтрДлина(Период.from) >= 10 И СтрДлина(Период.to) >= 10 Тогда
            ДатаНачалаРасчета = Дата(Число(Сред(Период.from, 1, 4)), Число(Сред(Период.from, 6, 2)), Число(Сред(Период.from, 9, 2)));
            ДатаОкончанияРасчета = Дата(Число(Сред(Период.to, 1, 4)), Число(Сред(Период.to, 6, 2)), Число(Сред(Период.to, 9, 2)));
        Иначе
            ДатаНачалаРасчета = Дата(2024, 1, 1);
            ДатаОкончанияРасчета = Дата(2024, 12, 31);
        КонецЕсли;
        ЗапросРасчетныхЛистков = Новый Запрос;
        ЗапросРасчетныхЛистков.Текст =
            "ВЫБРАТЬ ПЕРВЫЕ 30
            |   Сотрудники.Наименование КАК Сотрудник,
            |   Сотрудники.ФизическоеЛицо КАК ФизическоеЛицо,
            |   Кадры.ТекущаяОрганизация КАК ТекущаяОрганизация,
            |   Кадры.ГоловнаяОрганизация КАК ГоловнаяОрганизация
            |ИЗ
            |   Справочник.Сотрудники КАК Сотрудники
            |       ЛЕВОЕ СОЕДИНЕНИЕ РегистрСведений.ТекущиеКадровыеДанныеСотрудников КАК Кадры
            |       ПО Кадры.Сотрудник = Сотрудники.Ссылка
            |ГДЕ
            |   НЕ Сотрудники.ПометкаУдаления
            |УПОРЯДОЧИТЬ ПО
            |   Сотрудники.Наименование";
        ВыборкаРасчетныхЛистков = ЗапросРасчетныхЛистков.Выполнить().Выбрать();
        Пока ВыборкаРасчетныхЛистков.Следующий() Цикл
            Если НЕ ЗначениеЗаполнено(ВыборкаРасчетныхЛистков.ФизическоеЛицо) Тогда
                Продолжить;
            КонецЕсли;
            ОрганизацияРасчета = ВыборкаРасчетныхЛистков.ТекущаяОрганизация;
            Если НЕ ЗначениеЗаполнено(ОрганизацияРасчета) Тогда
                ОрганизацияРасчета = ВыборкаРасчетныхЛистков.ГоловнаяОрганизация;
            КонецЕсли;
            Если НЕ ЗначениеЗаполнено(ОрганизацияРасчета) Тогда
                Продолжить;
            КонецЕсли;
            Попытка
                ФизЛицаРасчета = Новый Массив;
                ФизЛицаРасчета.Добавить(ВыборкаРасчетныхЛистков.ФизическоеЛицо);
                ДанныеРасчетногоЛистка = ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков(
                    ФизЛицаРасчета,
                    ОрганизацияРасчета,
                    ДатаНачалаРасчета,
                    ДатаОкончанияРасчета);
                ДокументРезультатРасчета = ДанныеРасчетногоЛистка.ДокументРезультат;
                Если ДокументРезультатРасчета <> Неопределено
                    И ДокументРезультатРасчета.ВысотаТаблицы > 0
                    И ДокументРезультатРасчета.ШиринаТаблицы > 0 Тогда
                    Образцы.Вставить("payroll_employee", Строка(ВыборкаРасчетныхЛистков.Сотрудник));
                    Образцы.Вставить("payroll_organization", Строка(ОрганизацияРасчета));
                    Прервать;
                КонецЕсли;
            Исключение
            КонецПопытки;
        КонецЦикла;
    КонецЕсли;
Исключение
КонецПопытки;

Результат.Вставить("period", Период);
Результат.Вставить("candidate_periods", КандидатПериоды);
Результат.Вставить("samples", Образцы);
Результат.Вставить("context", Контекст);
Результат.Вставить("diagnostics", Диагностика);
""".strip()


def _fixture_sample_block(sample_key: str, metadata_name: str, query_text: str, field_name: str) -> str:
    safe_sample_key = sample_key.replace('"', '""')
    safe_metadata_name = metadata_name.replace('"', '""')
    safe_query = query_text.replace('"', '""')
    safe_field_name = field_name.replace('"', '""')
    return f"""
Попытка
    Если Метаданные.Справочники.Найти("{safe_metadata_name}") <> Неопределено Тогда
        ЗапросОбразца = Новый Запрос;
        ЗапросОбразца.Текст = "{safe_query}";
        ВыборкаОбразца = ЗапросОбразца.Выполнить().Выбрать();
        Если ВыборкаОбразца.Следующий() Тогда
            Образцы.Вставить("{safe_sample_key}", Строка(ВыборкаОбразца.{safe_field_name}));
        КонецЕсли;
    КонецЕсли;
Исключение
КонецПопытки;
""".strip()

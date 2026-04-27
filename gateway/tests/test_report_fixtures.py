from __future__ import annotations

from gateway.report_fixtures import ReportFixtureProvider, _fixture_pack_code


def test_fixture_probe_code_has_no_local_procedure_definitions():
    code = _fixture_pack_code()

    assert "Процедура ДобавитьОбразец" not in code
    assert "Функция ДобавитьОбразец" not in code
    assert 'Образцы.Вставить("organization"' in code
    assert 'Образцы.Вставить("organization_candidates"' in code
    assert 'Образцы.Вставить("item"' in code
    assert 'Образцы.Вставить("payroll_employee"' in code
    assert 'Образцы.Вставить("payroll_organization"' in code


def test_fixture_provider_plans_filters_from_report_title_samples():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ себестоимости по организации"},
        "params": [],
    }
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {"organization": "Металл-Сервис", "item": "Лист 0,6 63С2А"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["period"] == {"from": "2024-04-01", "to": "2024-04-30"}
    assert plan["filters"]["Организация"] == "Металл-Сервис"
    assert "Номенклатура" not in plan["filters"]


def test_fixture_provider_uses_strategy_filter_hints_and_candidate_periods():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ взносов в фонды по организации"},
        "params": [],
        "strategies": [
            {
                "details": {
                    "filter_fields": ["Организация", "ФизическоеЛицо"],
                    "filter_titles": {"Организация": "Организация", "ФизическоеЛицо": "Сотрудники"},
                }
            }
        ],
    }
    fixture_pack = {
        "period": {"from": "2025-05-01", "to": "2025-05-31"},
        "candidate_periods": [
            {"from": "2025-05-01", "to": "2025-05-31"},
            {"from": "2024-04-01", "to": "2024-04-30"},
        ],
        "samples": {"organization": "Металл-Сервис", "employee": "Иванов И.И."},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)
    candidates = provider.candidate_periods(fixture_pack, plan["period"])

    assert plan["filters"]["Организация"] == "Металл-Сервис"
    assert "Сотрудник" not in plan["filters"]
    assert "Сотрудники" not in plan["filters"]
    assert candidates == [
        {"from": "2025-05-01", "to": "2025-05-31"},
        {"from": "2024-04-01", "to": "2024-04-30"},
    ]


def test_fixture_provider_prefers_legacy_period_for_historical_report_title():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ уплаты НДФЛ (до 2016 года)"},
        "params": [],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "candidate_periods": [{"from": "2024-01-01", "to": "2024-12-31"}],
        "samples": {},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)
    candidates = provider.candidate_periods(fixture_pack, plan["period"])

    assert plan["period"] == {"from": "2015-01-01", "to": "2015-12-31"}
    assert candidates[0] == {"from": "2015-01-01", "to": "2015-12-31"}


def test_fixture_provider_prefers_legacy_period_from_variant_description():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {
            "report": "АнализОбязательствПоНДФЛ",
            "title": "Контроль уплаты НДФЛ по источникам финансирования",
            "variant": "КонтрольСроковУплатыПоИсточникам",
        },
        "variants": [
            {
                "key": "КонтрольСроковУплатыПоИсточникам",
                "presentation": "Контроль уплаты НДФЛ по источникам финансирования",
                "details": {
                    "description": "(Утратил актуальность с 2024 года) Сроки уплаты НДФЛ. Данные показываются по 2023 год включительно."
                },
            }
        ],
        "params": [],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "candidate_periods": [{"from": "2024-01-01", "to": "2024-12-31"}],
        "samples": {},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["period"] == {"from": "2023-01-01", "to": "2023-12-31"}


def test_fixture_provider_uses_exact_organization_filter_field_even_when_title_omits_it():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Контроль уплаты НДФЛ по источникам финансирования"},
        "params": [],
        "strategies": [
            {
                "details": {
                    "filter_fields": ["Организация", "РегистрацияВНалоговомОргане"],
                    "filter_titles": {"Организация": "Организация", "РегистрацияВНалоговомОргане": "Налог. орган"},
                }
            }
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {"organization": "Андромеда Плюс"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["filters"]["Организация"] == "Андромеда Плюс"


def test_fixture_provider_returns_candidate_organization_values_without_current_duplicate():
    provider = ReportFixtureProvider(transport=None)
    fixture_pack = {
        "samples": {
            "organization": "Андромеда Плюс",
            "organization_candidates": ["Андромеда Плюс", "Андромеда Сервис", "Андромеда Сервис", ""],
        }
    }

    candidates = provider.candidate_filter_values(fixture_pack, "Организация", "Андромеда Плюс")

    assert candidates == ["Андромеда Сервис"]


def test_fixture_provider_does_not_force_organization_filter_from_strategy_hint_only():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ НДФЛ по датам получения доходов"},
        "params": [],
        "strategies": [
            {
                "details": {
                    "filter_fields": ["ГоловнаяОрганизация", "ФизическоеЛицо"],
                    "filter_titles": {"ГоловнаяОрганизация": "Организация", "ФизическоеЛицо": "Сотрудники"},
                }
            }
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {"organization": "Андромеда Плюс", "employee": "Иванов И.И."},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert "Организация" not in plan["filters"]


def test_fixture_provider_uses_payroll_samples_for_payroll_sheet_report():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {
            "report": "АнализНачисленийИУдержаний",
            "title": "Расчетный листок",
            "variant": "РасчетныйЛисток",
        },
        "params": [],
        "strategies": [{"strategy": "adapter_entrypoint", "details": {"adapter": "payroll_sheet"}}],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {
            "employee": "Кузнецов Петр Васильевич",
            "organization": "Металл-Сервис",
            "payroll_employee": "Белкина Вероника Геннадиевна",
            "payroll_organization": "Андромеда Плюс",
        },
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["params"]["Сотрудник"] == "Белкина Вероника Геннадиевна"
    assert plan["params"]["Организация"] == "Андромеда Плюс"
    assert plan["filters"]["Сотрудник"] == "Белкина Вероника Геннадиевна"
    assert plan["filters"]["Организация"] == "Андромеда Плюс"


def test_fixture_provider_does_not_force_single_employee_filter_for_plural_staff_report():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ изменений личных данных сотрудников"},
        "params": [],
        "strategies": [
            {
                "details": {
                    "filter_fields": ["Организация", "Сотрудник"],
                    "filter_titles": {"Организация": "Организация", "Сотрудник": "Сотрудники"},
                }
            }
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {"organization": "Металл-Сервис", "employee": "Иванов И.И."},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["filters"]["Организация"] == "Металл-Сервис"
    assert "Сотрудник" not in plan["filters"]
    assert "Сотрудники" not in plan["filters"]


def test_fixture_provider_does_not_treat_plural_employee_title_as_single_employee_scope():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ зарплаты по сотрудникам (за первую половину месяца)"},
        "params": [],
        "strategies": [{"details": {"filter_fields": ["Сотрудник"], "filter_titles": {"Сотрудник": "Сотрудник"}}}],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {"employee": "Кузнецов Петр Васильевич"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert "Сотрудник" not in plan["filters"]


def test_fixture_provider_does_not_force_item_filter_for_generic_goods_report_title():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Недостаточно товаров организаций"},
        "params": [],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {"item": "Тара", "organization": "Андромеда Плюс"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["filters"]["Организация"] == "Андромеда Плюс"
    assert "Номенклатура" not in plan["filters"]


def test_fixture_provider_maps_user_activity_title_to_user_param_not_employee_filter():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Активность пользователя"},
        "params": [],
        "strategies": [{"details": {"filter_fields": ["ВидОбъекта"], "filter_titles": {"ВидОбъекта": "Вид объекта"}}}],
    }
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {"employee": "Иванов И.И.", "user": "Бот 1С-ЭДО"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["params"]["Пользователь"] == "Бот 1С-ЭДО"
    assert "Сотрудник" not in plan["filters"]
    assert "Сотрудники" not in plan["filters"]


def test_fixture_provider_maps_variant_date_params_and_uses_scalar_defaults():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Продолжительность работы регламентных заданий"},
        "params": [
            {"name": "ПериодДень", "type_name": "StandardBeginningDate", "required": False, "default": {"kind": "standard_beginning_date", "value": "BeginningOfThisDay"}},
            {"name": "ОтображатьФоновыеЗадания", "type_name": "Булево", "required": False, "default": False},
            {"name": "МинимальнаяПродолжительностьСеансовРегламентныхЗаданий", "type_name": "Число", "required": False, "default": 1},
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert plan["params"]["ПериодДень"] == "2024-04-30"
    assert "ОтображатьФоновыеЗадания" not in plan["params"]
    assert plan["params"]["МинимальнаяПродолжительностьСеансовРегламентныхЗаданий"] == 1


def test_fixture_provider_skips_optional_false_display_toggles():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Анализ НДФЛ по датам получения доходов"},
        "params": [
            {"name": "ВыводитьВыплаченныеДоходы", "type_name": "boolean", "required": False, "default": False},
            {"name": "ВыводитьСуммыДоСПревышения", "type_name": "boolean", "required": False, "default": False},
            {"name": "ПериодНалоговый", "type_name": "StandardPeriod", "required": False, "default": "ThisYear"},
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-01-01", "to": "2024-12-31"},
        "samples": {},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert "ВыводитьВыплаченныеДоходы" not in plan["params"]
    assert "ВыводитьСуммыДоСПревышения" not in plan["params"]


def test_fixture_provider_skips_unsafe_defaults_for_period_and_reference_types():
    provider = ReportFixtureProvider(transport=None)
    described = {
        "report": {"title": "Активность пользователя"},
        "params": [
            {"name": "Период", "type_name": "StandardPeriod", "required": False, "default": "ThisMonth"},
            {"name": "Пользователь", "type_name": "CatalogRef.Пользователи", "required": False, "default": "Справочник.Пользователи.ПустаяСсылка"},
            {"name": "НачалоВыборки", "type_name": "dateTime", "required": False, "default": "0001-01-01T00:00:00"},
            {"name": "ОтображатьДокументы", "type_name": "boolean", "required": False, "default": True},
        ],
    }
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {"user": "Бот 1С-ЭДО"},
        "context": {},
    }

    plan = provider.plan_inputs(described, fixture_pack)

    assert "Период" not in plan["params"]
    assert plan["params"]["Пользователь"] == "Бот 1С-ЭДО"
    assert "НачалоВыборки" not in plan["params"]
    assert plan["params"]["ОтображатьДокументы"] is True


def test_fixture_provider_does_not_guess_user_when_missing_type_is_unknown():
    provider = ReportFixtureProvider(transport=None)
    fixture_pack = {
        "period": {"from": "2024-04-01", "to": "2024-04-30"},
        "samples": {"user": "Бот 1С-ЭДО"},
        "context": {},
    }

    resolved = provider.resolve_missing(
        [{"name": "Пользователь", "type": "", "source": "1c_error"}],
        [],
        fixture_pack,
    )

    assert resolved["params"] == {}
    assert resolved["unresolved"] == [{"name": "Пользователь", "type": "", "source": "1c_error"}]

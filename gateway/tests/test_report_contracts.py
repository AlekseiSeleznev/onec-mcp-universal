from __future__ import annotations

from gateway.report_contracts import (
    build_declared_output_contract,
    build_observed_signature,
    build_verified_output_contract,
    compare_output_contract,
)


def test_observed_signature_detects_detail_rows_and_totals():
    signature = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3"],
            "rows": [
                {"C1": "Себестоимость выпущенной продукции", "C2": "", "C3": ""},
                {"C1": "Статья калькуляции", "C2": "Материал", "C3": "Стоимость затрат"},
                {"C1": "Лист 0,6 63С2А", "C2": "100", "C3": "5000"},
                {"C1": "Итого", "C2": "", "C3": "5000"},
            ],
            "metadata": {"source": "bsp_variant_report_runner"},
            "warnings": [],
        }
    )

    assert signature["output_type"] == "rows"
    assert signature["detail_rows_count"] == 1
    assert signature["has_totals"] is True
    assert "лист 0 6 63 с2 а" in signature["observed_tokens_norm"]


def test_compare_output_contract_marks_header_only_when_detail_rows_are_missing():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2"],
            "rows": [
                {"C1": "Себестоимость выпущенной продукции", "C2": ""},
                {"C1": "Организация", "C2": "Металл-Сервис"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": ["Материал", "Стоимость затрат"],
            "confidence": "high",
            "confidence_score": 0.9,
        },
        observed,
    )

    assert comparison["matched"] is False
    assert comparison["mismatch_code"] == "header_only"


def test_compare_output_contract_accepts_weak_declared_contract_for_verified_promotion():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2"],
            "rows": [
                {"C1": "Материал", "C2": "Сумма"},
                {"C1": "Лист 0,6 63С2А", "C2": "5000"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": ["Колонка, которую статический анализ не смог доказать"],
            "confidence": "low",
            "confidence_score": 0.35,
        },
        observed,
    )

    assert comparison["matched"] is False
    assert comparison["mismatch_code"] == "weak_declared_contract"
    assert comparison["acceptable_with_verified"] is True


def test_verified_output_contract_uses_column_header_not_first_data_row():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3"],
            "rows": [
                {"C1": "Параметры:", "C2": "Период:", "C3": ""},
                {"C1": "Материал", "C2": "Количество затрат", "C3": "Стоимость затрат"},
                {"C1": "Доска сосновая", "C2": "15,000", "C3": "240 000,00"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    contract = build_verified_output_contract(observed, strategy_name="bsp_variant_report_runner")

    assert contract["expected_columns"] == ["Материал", "Количество затрат", "Стоимость затрат"]


def test_verified_output_contract_uses_extracted_columns_before_data_sample():
    observed = {
        "output_type": "rows",
        "columns": ["Статья калькуляции", "Затрата", "Количество затрат", "Стоимость затрат"],
        "header_rows": ["Себестоимость выпущенной продукции"],
        "detail_rows_count": 2,
        "detail_column_count": 4,
        "detail_sample": [
            {
                "Статья калькуляции": "Услуги переработчика",
                "Затрата": "Переработка давальческих материалов",
                "Количество затрат": "50,000",
                "Стоимость затрат": "15 000,00",
            }
        ],
        "has_hierarchy": False,
        "has_totals": True,
        "artifacts_count": 0,
    }

    contract = build_verified_output_contract(observed, strategy_name="ui_xlsx_runner")

    assert contract["expected_columns"] == ["Статья калькуляции", "Затрата", "Количество затрат", "Стоимость затрат"]
    assert "Услуги переработчика" not in contract["expected_columns"]


def test_compare_output_contract_accepts_empty_result_when_explicit_columns_match():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["Тип объекта", "Количество", "Размер данных (Мб)"],
            "rows": [],
            "metadata": {"source": "raw_skd_dataset_query_runner"},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": ["Тип объекта", "Количество", "Размер данных (Мб)"],
            "confidence": "high",
            "confidence_score": 0.9,
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["empty_result"] is True


def test_compare_output_contract_accepts_empty_visual_variant_when_markers_and_drawings_match():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3"],
            "rows": [
                {"C1": "Продолжительность работы регламентных заданий", "C2": "", "C3": ""},
                {"C1": "За период с 30.04.2024 0:00:00 по 30.04.2024 23:59:59", "C2": "", "C3": ""},
                {"C1": "Отключено отображение интервалов с нулевой продолжительностью", "C2": "", "C3": ""},
            ],
            "metadata": {"drawing_count": 1},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "mixed",
            "expects_detail_rows": True,
            "allows_empty_result": True,
            "expects_visual_components": True,
            "expected_columns": [],
            "expected_markers": [
                "Продолжительность работы регламентных заданий",
                "Отключено отображение интервалов с нулевой продолжительностью",
            ],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["empty_result"] is True


def test_compare_output_contract_accepts_visual_report_with_chart_headers_only():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3", "C4", "C5"],
            "rows": [
                {"C1": "Структура возникновения претензий клиентов", "C2": "", "C3": "", "C4": "", "C5": ""},
                {"C1": "Параметры:", "C2": "Период:", "C3": "", "C4": "", "C5": ""},
                {"C1": "Причины возникновения", "C2": "", "C3": "", "C4": "", "C5": ""},
                {"C1": "Подразделения", "C2": "", "C3": "", "C4": "", "C5": ""},
                {"C1": "Сотрудники", "C2": "", "C3": "", "C4": "", "C5": ""},
            ],
            "metadata": {"drawing_count": 3},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "mixed",
            "expects_detail_rows": False,
            "expects_visual_components": True,
            "expected_markers": [
                "Анализ претензий клиентов",
                "Структура возникновения претензий клиентов",
            ],
            "expected_columns": [
                "Количество претензий по причинам возникновения",
                "Количество",
                "Количество возникших претензий по вине сотрудников",
            ],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["visual_result"] is True


def test_compare_output_contract_accepts_blank_visual_report_when_contract_allows_blank_output():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": [],
            "rows": [],
            "metadata": {"drawing_count": 0},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "mixed",
            "expects_detail_rows": False,
            "accepts_blank_output": True,
            "expects_visual_components": True,
            "expected_columns": ["Количество партнеров", "Клиент"],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["blank_output"] is True


def test_compare_output_contract_accepts_header_only_empty_result_when_contract_allows_empty():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1"],
            "rows": [
                {"C1": "Анализ изменений личных данных сотрудников"},
                {"C1": "Организация"},
            ],
            "metadata": {"source": "bsp_variant_report_runner"},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "allows_empty_result": True,
            "expected_markers": ["Анализ изменений личных данных сотрудников", "Сотрудник", "Дата", "Было", "Стало"],
            "expected_columns": ["Дата", "Сотрудник", "Было", "Стало"],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["empty_result"] is True
    assert comparison["header_only_empty"] is True


def test_declared_output_contract_marks_object_module_empty_hook_as_allows_empty():
    contract = build_declared_output_contract(
        report_name="АнализИзмененийЛичныхДанныхСотрудников",
        report_title="Анализ изменений личных данных сотрудников",
        variant_key="Основной",
        variant_title="Основной",
        kind="runtime_probe_required",
        strategies=[{"strategy": "bsp_variant_report_runner", "details": {"selected_fields": ["Период", "Сотрудник"]}}],
        template_texts=["Анализ изменений личных данных сотрудников", "Сотрудник", "Было", "Стало"],
        manager_text="",
        object_text="ДопСвойства.Вставить(\"ОтчетПустой\", ОтчетыСервер.ОтчетПустой(ЭтотОбъект, ПроцессорКомпоновки));",
    )

    assert contract["allows_empty_result"] is True


def test_compare_output_contract_downgrades_runtime_folder_placeholders_to_analyzer_gap():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3", "C4"],
            "rows": [
                {"C1": "Артикул", "C2": "Номенклатура, Характеристика", "C3": "Количество", "C4": "Стоимость  (RUB)"},
                {"C1": "Арт-1", "C2": "Тара", "C3": "10,000", "C4": "705,24"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": [
                "Запас.Стоимость",
                "Запас.Количество",
                "%1%",
                "Номенклатура.Артикул",
            ],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["matched"] is False
    assert comparison["mismatch_code"] == "weak_declared_contract"
    assert comparison["acceptable_with_verified"] is True


def test_compare_output_contract_downgrades_technical_skd_column_contract_to_analyzer_gap():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3"],
            "rows": [
                {"C1": "Статья калькуляции", "C2": "Стоимость затрат", "C3": "Количество затрат"},
                {"C1": "Лист 0,6 63С2А", "C2": "5000", "C3": "100"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": ["ИсточникДанных1", "СегментНоменклатуры", "АналитикаПродукции"],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["mismatch_code"] == "weak_declared_contract"
    assert comparison["acceptable_with_verified"] is True


def test_compare_output_contract_downgrades_single_generic_resource_column_when_markers_match():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3"],
            "rows": [
                {"C1": "Анализ зарплаты по сотрудникам (помесячно)", "C2": "", "C3": ""},
                {"C1": "Организация", "C2": "Андромеда Плюс", "C3": ""},
                {"C1": "Месяц", "C2": "Январь 2024", "C3": ""},
                {"C1": "Подразделение", "C2": "Сальдо на начало месяца", "C3": "Сальдо на конец месяца"},
                {"C1": "Коммерческая служба", "C2": "111,00", "C3": "111,00"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "expected_columns": ["Сумма"],
            "expected_markers": ["Анализ зарплаты по сотрудникам (помесячно)"],
            "confidence": "high",
            "confidence_score": 0.82,
        },
        observed,
    )

    assert comparison["mismatch_code"] == "weak_declared_contract"
    assert comparison["acceptable_with_verified"] is True


def test_compare_output_contract_accepts_partial_semantic_column_overlap():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3", "C4"],
            "rows": [
                {"C1": "Выполнение маршрутных листов с задержками", "C2": "", "C3": "", "C4": ""},
                {"C1": "Буфер", "C2": "Номенклатура, Характеристика", "C3": "С задержкой", "C4": "Доля задержек, %"},
                {"C1": "Причина задержки", "C2": "Выполнено маршрутных листов", "C3": "Всего", "C4": ""},
            ],
        }
    )
    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "confidence": "high",
            "confidence_score": 0.82,
            "expected_columns": [
                "Номенклатура",
                "С задержкой",
                "Доля задержек по этапу",
                "Причина задержки",
                "Выполнено маршрутных листов",
            ],
        },
        observed,
    )

    assert comparison["matched"] is True
    assert comparison["mismatch_code"] == ""
    assert comparison["score"] >= 0.6


def test_compare_output_contract_downgrades_noisy_high_confidence_hierarchical_contract():
    observed = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2", "C3", "C4", "C5", "C6"],
            "rows": [
                {"C1": "Параметры:", "C2": "Период:", "C3": "", "C4": "", "C5": "", "C6": ""},
                {"C1": "Организация", "C2": "Склад", "C3": "Итого", "C4": "Итого", "C5": "Итого", "C6": "Итого"},
                {"C1": "Номенклатура, Характеристика, Серия, Ед.изм.", "C2": "Назначение", "C3": "Итого", "C4": "Итого", "C5": "Итого", "C6": "Итого"},
                {"C1": "Вид запасов", "C2": "Номер ГТД", "C3": "Начальный остаток", "C4": "Приход", "C5": "Расход", "C6": "Конечный остаток"},
                {"C1": "Торговый дом \"Комплексный\"", "C2": "Склад бытовой техники", "C3": "", "C4": "20,000", "C5": "20,000", "C6": ""},
                {"C1": "Кондиционер FIRMSTAR 12М", "C2": "", "C3": "", "C4": "20,000", "C5": "20,000", "C6": ""},
            ],
        }
    )

    comparison = compare_output_contract(
        {
            "output_type": "rows",
            "expects_detail_rows": True,
            "hierarchy_expected": True,
            "confidence": "high",
            "confidence_score": 0.82,
            "expected_columns": [
                "Количество в наличии",
                "Количество к оформлению",
                "Количество",
                "Недостаточно товаров организаций",
                "Используется отбор по сегменту номенклатуры",
                "Требуется передача товаров между организациями",
                "Сегмент номенклатуры",
                "Аналитика учета номенклатуры",
                "Номенклатура",
                "Номер ГТД",
                "Вид запасов",
                "Конец периода",
            ],
        },
        observed,
    )

    assert comparison["mismatch_code"] == "weak_declared_contract"
    assert comparison["acceptable_with_verified"] is True


def test_declared_contract_prioritizes_human_visible_columns_over_technical_skd_tokens():
    contract = build_declared_output_contract(
        report_name="АнализСебестоимостиВыпущеннойПродукции",
        report_title="Анализ себестоимости выпущенной продукции по организации",
        variant_key="Основной",
        variant_title="Анализ себестоимости выпущенной продукции по организации",
        kind="runtime_probe_required",
        strategies=[{"strategy": "bsp_variant_report_runner"}],
        template_texts=[
            "ИсточникДанных1",
            "СегментНоменклатуры",
            "Статья калькуляции",
            "Затрата",
            "Стоимость затрат",
            "Количество затрат",
            "Ед. изм.",
        ],
        manager_text="Функция Получить() Экспорт\nКонецФункции",
        object_text="Процедура ПриКомпоновкеРезультата() Экспорт\nКонецПроцедуры",
    )

    assert contract["expected_columns"][0] == "Статья калькуляции"
    assert {"Затрата", "Стоимость затрат", "Количество затрат"}.issubset(set(contract["expected_columns"][:5]))


def test_observed_signature_treats_text_rows_after_column_header_as_detail_rows():
    signature = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2"],
            "rows": [
                {"C1": "ABC/XYZ - распределение клиентов", "C2": ""},
                {"C1": "Партнер", "C2": "Значение параметра классификации"},
                {"C1": "Kikinda (Сербия)", "C2": "-"},
                {"C1": "Альтаир", "C2": "-"},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    assert signature["detail_rows_count"] == 2


def test_observed_signature_does_not_treat_parameter_and_filter_rows_as_detail_rows():
    signature = build_observed_signature(
        {
            "output_type": "rows",
            "columns": ["C1", "C2"],
            "rows": [
                {"C1": "Параметры:", "C2": "Период:"},
                {"C1": "", "C2": "Только отрицательные остатки: Нет"},
                {"C1": "Отбор:", "C2": "Количество к оформлению Не равно \"0\""},
            ],
            "metadata": {},
            "warnings": [],
        }
    )

    assert signature["detail_rows_count"] == 0
    assert signature["header_rows"] == [
        "Параметры: | Период:",
        "Только отрицательные остатки: Нет",
        "Отбор: | Количество к оформлению Не равно \"0\"",
    ]

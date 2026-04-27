from __future__ import annotations

from pathlib import Path

from gateway.report_analyzer import ReportAnalyzer
from gateway.report_catalog import ReportCatalog


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_project(root: Path) -> None:
    _write(
        root / "Reports/АнализНачисленийИУдержаний/Templates/ПФ_MXL_РасчетныйЛисток.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<doc xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <v8:content>Расчетный листок</v8:content>
</doc>
""",
    )
    _write(
        root / "Reports/АнализНачисленийИУдержаний/Ext/ManagerModule.bsl",
        """Процедура ПриКомпоновкеРезультата() Экспорт
    ВариантыОтчетов.ОписаниеВарианта(ЭтотОбъект, "РасчетныйЛисток");
КонецПроцедуры
""",
    )
    _write(
        root / "CommonModules/ЗарплатаКадрыОтчеты/Ext/Module.bsl",
        """Функция ДанныеРасчетныхЛистков(ФизЛицо, Организация, ДатаНачала, ДатаОкончания) Экспорт
    Возврат Новый ТаблицаЗначений;
КонецФункции
""",
    )
    for i in range(1, 11):
        report_name = f"ТестовыйОтчет{i}"
        marker = "ВнешниеНаборыДанных" if i == 2 else ""
        form_marker = "РегламентированныйОтчет" if i == 3 else ""
        _write(
            root / f"Reports/{report_name}/Templates/ОсновнаяСхемаКомпоновкиДанных.xml",
            f"<root><name>{report_name}</name><TemplateType>DataCompositionSchema</TemplateType>{marker}{form_marker}</root>",
        )


def test_analyzer_extracts_aliases_variants_and_adapter_strategy(tmp_path):
    _build_project(tmp_path)
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    analyzer = ReportAnalyzer(catalog)

    summary = analyzer.analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", title="Расчетный листок")

    assert summary["database"] == "Z01"
    assert summary["reports"] == 11
    assert described["ok"] is True
    assert described["report"]["report"] == "АнализНачисленийИУдержаний"
    assert described["report"]["variant"] == "РасчетныйЛисток"
    assert described["strategies"][0]["entrypoint"] == "ЗарплатаКадрыОтчеты.ДанныеРасчетныхЛистков"
    assert described["strategies"][0]["details"]["source"] == "static"


def test_analyzer_builds_declared_output_contract_per_variant(tmp_path):
    _write(
        tmp_path / "Reports/Себестоимость/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Анализ себестоимости</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
  <v8:item><v8:content>Материал</v8:content></v8:item>
  <v8:item><v8:content>Стоимость затрат</v8:content></v8:item>
  <v8:item><v8:content>Количество затрат</v8:content></v8:item>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", title="Анализ себестоимости")

    assert described["ok"] is True
    assert described["output_contract"]["source"] == "declared"
    assert described["output_contract"]["output_type"] == "rows"
    assert described["output_contract"]["expects_detail_rows"] is True
    assert "Материал" in described["output_contract"]["expected_columns"]
    assert described["output_contract"]["preferred_strategy"] == "raw_skd_runner"


def test_analyzer_reads_skd_variant_presentations_and_filters_service_aliases(tmp_path):
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ОсновнаяСхемаКомпоновкиДанных.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <Template>
    <Properties>
      <Name>ОсновнаяСхемаКомпоновкиДанных</Name>
      <Synonym><v8:item><v8:content>Основная схема компоновки данных</v8:content></v8:item></Synonym>
      <TemplateType>DataCompositionSchema</TemplateType>
    </Properties>
  </Template>
</MetaDataObject>
""",
    )
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">РасчетныйЛисток</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>Расчетный листок</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>
""",
    )
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Ext/ManagerModule.bsl",
        """ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "АнализЗарплатыПоСотрудникам");
ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "РасчетныйЛисток");""",
    )
    _write(
        tmp_path / "CommonModules/ЗарплатаКадрыОтчеты/Ext/Module.bsl",
        "Функция ДанныеРасчетныхЛистков() Экспорт\nКонецФункции",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    analyzer = ReportAnalyzer(catalog)

    analyzer.analyze_database("Z01", tmp_path)

    described = catalog.describe_report("Z01", title="Расчетный листок")
    service_lookup = catalog.describe_report("Z01", title="DataCompositionSchema")
    reports = catalog.list_reports("Z01", limit=10)

    assert described["ok"] is True
    assert described["report"]["variant"] == "РасчетныйЛисток"
    assert described["strategies"][0]["strategy"] == "adapter_entrypoint"
    assert service_lookup["ok"] is False
    assert all(row["title"] != "DataCompositionSchema" for row in reports)


def test_analyzer_uses_payroll_specific_contract_for_payroll_sheet_variant(tmp_path):
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ОсновнаяСхемаКомпоновкиДанных.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <Template>
    <Properties>
      <Name>ОсновнаяСхемаКомпоновкиДанных</Name>
      <TemplateType>DataCompositionSchema</TemplateType>
    </Properties>
  </Template>
</MetaDataObject>
""",
    )
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <settingsVariant>
    <dcsset:name>РасчетныйЛисток</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Расчетный листок</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:item xsi:type="dcsset:StructureItemGroup">
        <dcsset:selection>
          <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>СтатьяРасходов</dcsset:field></dcsset:item>
          <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПоОрганизациям</dcsset:field></dcsset:item>
        </dcsset:selection>
      </dcsset:item>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ПФ_MXL_РасчетныйЛисток.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <Template>
    <Properties>
      <Name>ПФ_MXL_РасчетныйЛисток</Name>
      <Synonym><v8:item><v8:content>Расчетный листок</v8:content></v8:item></Synonym>
      <TemplateType>SpreadsheetDocument</TemplateType>
    </Properties>
  </Template>
</MetaDataObject>
""",
    )
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Ext/ManagerModule.bsl",
        """ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "РасчетныйЛисток");""",
    )
    _write(
        tmp_path / "CommonModules/ЗарплатаКадрыОтчеты/Ext/Module.bsl",
        "Функция ДанныеРасчетныхЛистков() Экспорт\nКонецФункции",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализНачисленийИУдержаний", variant="РасчетныйЛисток")

    assert described["output_contract"]["report_title"] == "Расчетный листок"
    assert described["output_contract"]["expected_columns"] == []
    assert "Расчетный листок" in described["output_contract"]["expected_markers"]
    assert "СтатьяРасходов" not in described["output_contract"]["expected_markers"]


def test_analyzer_reads_variant_description_from_manager_module(tmp_path):
    _write(
        tmp_path / "Reports/АнализОбязательствПоНДФЛ/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">КонтрольСроковУплатыПоИсточникам</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Контроль уплаты НДФЛ по источникам финансирования</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    _write(
        tmp_path / "Reports/АнализОбязательствПоНДФЛ/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    НастройкиВарианта = ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "КонтрольСроковУплатыПоИсточникам");
    НастройкиВарианта.Описание = НСтр("ru = '(Утратил актуальность с 2024 года) Сроки уплаты НДФЛ.
                                    |Данные о перечисленном налоге показываются по 2023 год включительно.';
                                    |en = 'deprecated'");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализОбязательствПоНДФЛ/Ext/ObjectModule.bsl",
        "Процедура ПриКомпоновкеРезультата() Экспорт\nКонецПроцедуры",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализОбязательствПоНДФЛ", variant="КонтрольСроковУплатыПоИсточникам")
    variant = next(item for item in described["variants"] if item["key"] == "КонтрольСроковУплатыПоИсточникам")

    assert "Утратил актуальность с 2024 года" in variant["details"]["description"]
    assert "2023 год включительно" in variant["details"]["description"]


def test_analyzer_prefers_variant_named_like_report_for_synonym_and_contract(tmp_path):
    _write(
        tmp_path / "Reports/АнализВзносовВФонды/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <settingsVariant>
    <dcsset:name>НачисленоПФР</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Начислено ПФР</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
  <settingsVariant>
    <dcsset:name>АнализВзносовВФонды</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ взносов в фонды</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:filter>
        <dcsset:item xsi:type="dcsset:FilterItemComparison">
          <dcsset:left xsi:type="dcscor:Field">Организация</dcsset:left>
        </dcsset:item>
      </dcsset:filter>
      <dcsset:item xsi:type="dcsset:StructureItemGroup">
        <dcsset:selection>
          <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Организация</dcsset:field></dcsset:item>
        </dcsset:selection>
        <dcsset:item xsi:type="dcsset:StructureItemNestedObject">
          <dcsset:settings>
            <dcsset:selection>
              <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ВидРасчета</dcsset:field></dcsset:item>
              <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>НачисленоВсегоПФР</dcsset:field></dcsset:item>
            </dcsset:selection>
          </dcsset:settings>
        </dcsset:item>
      </dcsset:item>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализВзносовВФонды/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "АнализВзносовВФонды");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализВзносовВФонды/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата() Экспорт
КонецПроцедуры
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализВзносовВФонды", variant="АнализВзносовВФонды")
    nested_only = catalog.describe_report("ERP", report="АнализВзносовВФонды", variant="НачисленоПФР")
    nested_variant = next(item for item in nested_only["variants"] if item["key"] == "НачисленоПФР")

    assert described["report"]["title"] == "Анализ взносов в фонды"
    assert described["output_contract"]["report_title"] == "Анализ взносов в фонды"
    assert described["output_contract"]["variant_title"] == "Анализ взносов в фонды"
    assert "ВидРасчета" in described["strategies"][0]["details"]["selected_fields"]
    assert "Организация" in described["strategies"][0]["details"]["filter_fields"]
    assert nested_variant["details"]["launchable"] is False
    assert nested_only["strategies"] == []


def test_analyzer_reads_nested_settings_variant_selection_and_params(tmp_path):
    _write(
        tmp_path / "Reports/АнализКорреспонденций/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField">
    <dataPath>Регистратор</dataPath>
    <field>Регистратор</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Регистратор</v8:content></v8:item></title>
  </field>
  <field xsi:type="DataSetFieldField">
    <dataPath>СуммаУпрДт</dataPath>
    <field>СуммаУпрДт</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Сумма упр. Дт</v8:content></v8:item></title>
  </field>
  <field xsi:type="DataSetFieldField">
    <dataPath>СуммаУпрКт</dataPath>
    <field>СуммаУпрКт</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Сумма упр. Кт</v8:content></v8:item></title>
  </field>
  <container>
    <settingsVariant>
      <dcsset:name>АнализПоДокументам</dcsset:name>
      <dcsset:presentation xsi:type="v8:LocalStringType"><v8:item><v8:content>Анализ по документам</v8:content></v8:item></dcsset:presentation>
      <dcsset:settings>
        <dcsset:selection>
          <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Регистратор</dcsset:field></dcsset:item>
          <dcsset:item xsi:type="dcsset:SelectedItemFolder">
            <dcsset:lwsTitle><v8:item><v8:content>Сумма упр.</v8:content></v8:item></dcsset:lwsTitle>
            <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>СуммаУпрДт</dcsset:field></dcsset:item>
            <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>СуммаУпрКт</dcsset:field></dcsset:item>
          </dcsset:item>
        </dcsset:selection>
        <dcsset:dataParameters>
          <dcscor:item xsi:type="dcsset:SettingsParameterValue">
            <dcscor:parameter>ПериодОтчета</dcscor:parameter>
            <dcscor:value xsi:type="v8:StandardPeriod">
              <v8:variant xsi:type="v8:StandardPeriodVariant">LastMonth</v8:variant>
            </dcscor:value>
          </dcscor:item>
        </dcsset:dataParameters>
      </dcsset:settings>
    </settingsVariant>
  </container>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализКорреспонденций/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "АнализПоДокументам");
КонецПроцедуры
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", report="АнализКорреспонденций", variant="АнализПоДокументам")

    assert described["ok"] is True
    assert described["strategies"][0]["details"]["selected_fields"] == ["Регистратор", "СуммаУпрДт", "СуммаУпрКт"]
    assert described["strategies"][0]["details"]["field_titles"] == {
        "Регистратор": "Регистратор",
        "СуммаУпрДт": "Сумма упр. Дт",
        "СуммаУпрКт": "Сумма упр. Кт",
    }
    assert [item["name"] for item in described["params"]] == ["ПериодОтчета"]
    assert described["output_contract"]["expected_columns"][:3] == [
        "Регистратор",
        "Сумма упр. Дт",
        "Сумма упр. Кт",
    ]


def test_analyzer_uses_calculated_field_titles_in_variant_contract(tmp_path):
    _write(
        tmp_path / "Reports/АнализРасписания/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField">
    <dataPath>ЭтапОкончание</dataPath>
    <field>ЭтапОкончание</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Этап окончание</v8:content></v8:item></title>
  </field>
  <calculatedField>
    <dataPath>Отклонение</dataPath>
    <expression>1</expression>
    <title xsi:type="v8:LocalStringType">
      <v8:item><v8:lang>ru</v8:lang><v8:content>Отклонение от графика, дней</v8:content></v8:item>
      <v8:item><v8:lang>en</v8:lang><v8:content>Schedule variance, days</v8:content></v8:item>
    </title>
  </calculatedField>
  <settingsVariant>
    <dcsset:name>Основной</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ расписаний</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemFolder">
          <dcsset:lwsTitle><v8:item><v8:content>Плановая дата завершения</v8:content></v8:item></dcsset:lwsTitle>
          <dcsset:item xsi:type="dcsset:SelectedItemField">
            <dcsset:field>ЭтапОкончание</dcsset:field>
            <dcsset:lwsTitle><v8:item><v8:content>По графику</v8:content></v8:item></dcsset:lwsTitle>
          </dcsset:item>
        </dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Отклонение</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализРасписания/Ext/ObjectModule.bsl",
        "Процедура ПриКомпоновкеРезультата() Экспорт\n    ТекущаяДатаСеанса();\nКонецПроцедуры",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", report="АнализРасписания", variant="Основной")

    assert described["ok"] is True
    assert described["strategies"][0]["details"]["field_titles"]["Отклонение"] == "Отклонение от графика, дней"
    assert described["strategies"][0]["details"]["selected_presentations"] == [
        "По графику",
        "Отклонение от графика, дней",
    ]
    assert "Плановая дата завершения" in described["output_contract"]["expected_markers"]
    assert described["output_contract"]["expected_columns"] == [
        "По графику",
        "Отклонение от графика, дней",
    ]


def test_analyzer_marks_help_prerequisite_reports_as_allowing_empty_result(tmp_path):
    _write(
        tmp_path / "Reports/АнализЛояльности/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField">
    <dataPath>ПартнерКоличество</dataPath>
    <field>ПартнерКоличество</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Партнер количество</v8:content></v8:item></title>
  </field>
  <settingsVariant>
    <dcsset:name>Основной</dcsset:name>
    <dcsset:presentation xsi:type="v8:LocalStringType"><v8:item><v8:content>Анализ лояльности клиентов (XYZ)</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПартнерКоличество</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализЛояльности/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "Основной");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализЛояльности/Ext/Help/ru.html",
        """<h1>Лояльность клиентов (XYZ)</h1>
<p>Отчет предназначен для анализа на основании предварительно проведенной XYZ-классификации.</p>
<p>Согласно настроенному расписанию при помощи регламентного задания XYZ-классификация клиентов.</p>
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", report="АнализЛояльности", variant="Основной")

    assert described["ok"] is True
    assert described["output_contract"]["allows_empty_result"] is True
    assert described["output_contract"]["accepts_blank_output"] is True


def test_analyzer_classifies_multiple_report_shapes(tmp_path):
    _build_project(tmp_path)
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    analyzer = ReportAnalyzer(catalog)
    analyzer.analyze_database("ERP_DEMO", tmp_path)

    reports = {row["report"]: row for row in catalog.list_reports("ERP_DEMO", limit=50)}

    assert reports["ТестовыйОтчет1"]["kind"] == "raw_skd_runner"
    assert reports["ТестовыйОтчет2"]["kind"] == "external_datasets_required"
    assert reports["ТестовыйОтчет3"]["kind"] == "form_or_regulated"
    assert len(reports) == 11


def test_analyzer_creates_raw_strategy_for_each_skd_variant(tmp_path):
    _write(
        tmp_path / "Reports/МногоВариантов/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Первый</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Первый вариант</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Второй</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Второй вариант</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)

    first = catalog.describe_report("Z01", report="МногоВариантов", variant="Первый")
    second = catalog.describe_report("Z01", report="МногоВариантов", variant="Второй")

    assert first["strategies"][0]["strategy"] == "raw_skd_runner"
    assert first["report"]["status"] == "supported"
    assert second["strategies"][0]["strategy"] == "raw_skd_runner"
    assert second["report"]["status"] == "supported"


def test_analyzer_prefers_direct_dataset_query_runner_for_simple_local_query_schema(tmp_path):
    _write(
        tmp_path / "Reports/АнализВерсийОбъектов/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dataSource>
    <name>ИсточникДанных1</name>
    <dataSourceType>Local</dataSourceType>
  </dataSource>
  <dataSet xsi:type="DataSetQuery">
    <name>НаборДанных1</name>
    <field xsi:type="DataSetFieldField">
      <dataPath>ТипОбъекта</dataPath>
      <field>ТипОбъекта</field>
      <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Тип объекта</v8:content></v8:item></title>
    </field>
    <field xsi:type="DataSetFieldField">
      <dataPath>Количество</dataPath>
      <field>Количество</field>
      <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Количество</v8:content></v8:item></title>
    </field>
    <field xsi:type="DataSetFieldField">
      <dataPath>РазмерДанных</dataPath>
      <field>РазмерДанных</field>
      <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Размер данных (Мб)</v8:content></v8:item></title>
    </field>
    <dataSource>ИсточникДанных1</dataSource>
    <query>ВЫБРАТЬ
    ТИПЗНАЧЕНИЯ(ВерсииОбъектов.Объект) КАК ТипОбъекта,
    КОЛИЧЕСТВО(1) КАК Количество,
    СУММА(ВерсииОбъектов.РазмерДанных / 1024 / 1024) КАК РазмерДанных
ИЗ
    РегистрСведений.ВерсииОбъектов КАК ВерсииОбъектов
ГДЕ
    ВерсииОбъектов.РазмерДанных &gt; 0</query>
  </dataSet>
  <settingsVariant>
    <dcsset:name>Основной</dcsset:name>
    <dcsset:presentation xsi:type="v8:LocalStringType"><v8:item><v8:content>Количество и объем хранимых версий объектов</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ТипОбъекта</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Количество</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>РазмерДанных</dcsset:field></dcsset:item>
      </dcsset:selection>
      <dcsset:item xsi:type="dcsset:StructureItemGroup">
        <dcsset:selection><dcsset:item xsi:type="dcsset:SelectedItemAuto"/></dcsset:selection>
      </dcsset:item>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", title="Количество и объем хранимых версий объектов")

    assert described["ok"] is True
    assert described["strategies"][0]["strategy"] == "raw_skd_dataset_query_runner"
    assert described["strategies"][0]["details"]["selected_fields"] == ["ТипОбъекта", "Количество", "РазмерДанных"]
    assert described["strategies"][0]["details"]["field_titles"] == {
        "ТипОбъекта": "Тип объекта",
        "Количество": "Количество",
        "РазмерДанных": "Размер данных (Мб)",
    }
    assert described["output_contract"]["expected_columns"][:3] == [
        "Тип объекта",
        "Количество",
        "Размер данных (Мб)",
    ]


def test_analyzer_blocks_raw_skd_when_template_uses_runtime_session_function(tmp_path):
    _write(
        tmp_path / "Reports/МаршрутныеЛисты/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field><dataPath>Маршрут</dataPath><title><v8:item><v8:content>Маршрут</v8:content></v8:item></title></field>
  <field><dataPath>Количество</dataPath><title><v8:item><v8:content>Количество</v8:content></v8:item></title></field>
  <expression>ТекущаяДатаСеанса()</expression>
  <settingsVariant>
    <dcsset:name>СЗадержками</dcsset:name>
    <dcsset:presentation>
      <v8:item><v8:content>С задержками</v8:content></v8:item>
    </dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Маршрут</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Количество</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report("ERP_DEMO", title="С задержками")

    assert described["ok"] is True
    assert described["report"]["kind"] == "runtime_probe_required"
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"
    assert described["strategies"][0]["requires_runtime_probe"] is True
    assert described["output_contract"]["expected_columns"][:2] == ["Маршрут", "Количество"]


def test_analyzer_blocks_raw_skd_when_required_parameter_has_no_runner_value(tmp_path):
    _write(
        tmp_path / "Reports/СравнениеМотиваторов/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <query>ВЫБРАТЬ 1 ГДЕ Кандидаты.Вакансия = &amp;Вакансия</query>
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>Мотивация</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)

    described = catalog.describe_report("Z01", title="Мотивация")

    assert described["ok"] is True
    assert described["report"]["kind"] == "runtime_probe_required"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"
    assert described["strategies"][0]["requires_runtime_probe"] is True


def test_analyzer_detects_external_dataset_from_object_module(tmp_path):
    _write(
        tmp_path / "Reports/СПАРК/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>Надежность дебиторов</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    _write(
        tmp_path / "Reports/СПАРК/Ext/ObjectModule.bsl",
        'ВнешниеНаборыДанных.Вставить("ДанныеОтчета", РезультатЗапроса.Выгрузить());',
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report("ERP_DEMO", title="Надежность дебиторов")

    assert described["ok"] is True
    assert described["report"]["kind"] == "external_datasets_required"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"


def test_analyzer_prefers_bsp_runner_for_report_object_composition_handlers(tmp_path):
    _write(
        tmp_path / "Reports/АнализПравДоступа/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">АнализПравДоступа</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Анализ прав доступа</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    _write(
        tmp_path / "Reports/АнализПравДоступа/Ext/ObjectModule.bsl",
        """Процедура ОпределитьНастройкиФормы(Форма, КлючВарианта, Настройки) Экспорт
    Настройки.События.ПриСозданииНаСервере = Истина;
КонецПроцедуры

Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровки, СтандартнаяОбработка)
    ВнешниеНаборыДанных = Новый Структура;
    ВнешниеНаборыДанных.Вставить("ПраваПользователей", Новый ТаблицаЗначений);
КонецПроцедуры""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", title="Анализ прав доступа")

    assert described["ok"] is True
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"
    assert described["strategies"][0]["details"]["object_events"] == [
        "ОпределитьНастройкиФормы",
        "ПриКомпоновкеРезультата",
    ]


def test_analyzer_marks_bsp_command_context_reports_as_requiring_object_ref(tmp_path):
    _write(
        tmp_path / "Reports/КонтекстныйОтчет/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x"><v8:item><v8:content>Контекстный отчет</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    _write(
        tmp_path / "Reports/КонтекстныйОтчет/Ext/ObjectModule.bsl",
        """Процедура ОпределитьНастройкиФормы(Форма, КлючВарианта, Настройки) Экспорт
    Настройки.События.ПриСозданииНаСервере = Истина;
КонецПроцедуры

Процедура ПриСозданииНаСервере(ЭтаФорма, Отказ, СтандартнаяОбработка) Экспорт
    Если ЭтаФорма.Параметры.Свойство("ПараметрКоманды") Тогда
        ЭтаФорма.ФормаПараметры.Отбор.Вставить("Регистратор", ЭтаФорма.Параметры.ПараметрКоманды);
    Иначе
        ВызватьИсключение "Отчет предназначен только для открытия в документе.";
    КонецЕсли;
КонецПроцедуры""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report("ERP_DEMO", title="Контекстный отчет")

    assert described["ok"] is True
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"
    assert described["strategies"][0]["details"]["requires_object_ref"] is True


def test_analyzer_creates_form_artifact_strategy_for_regulated_forms(tmp_path):
    _write(
        tmp_path / "Reports/РегламентированноеУведомление/Forms/ФормаОтчета/Ext/Form.xml",
        "<Form><AutoCommandBar name=\"ФормаКоманднаяПанель\" /></Form>",
    )
    _write(
        tmp_path / "Reports/РегламентированноеУведомление/Ext/ObjectModule.bsl",
        "РегламентированныйОтчет = Истина;",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", report="РегламентированноеУведомление")

    assert described["ok"] is True
    assert described["report"]["kind"] == "form_or_regulated"
    assert described["strategies"][0]["strategy"] == "form_artifact_runner"
    assert described["strategies"][0]["output_type"] == "artifact"
    assert described["strategies"][0]["details"]["requires_object_ref"] is True


def test_analyzer_creates_form_artifact_strategy_for_form_only_regulated_name(tmp_path):
    _write(
        tmp_path / "Reports/РегламентированноеУведомлениеБанковскиеГарантии/Forms/ФормаОтзыв501/Ext/Form.xml",
        "<Form><Button name=\"ФормаСформироватьXML\" /></Form>",
    )
    _write(
        tmp_path / "Reports/РегламентированноеУведомлениеБанковскиеГарантии/Templates/Печать_ФормаОтзыв501.xml",
        "<root><TemplateType>SpreadsheetDocument</TemplateType></root>",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", report="РегламентированноеУведомлениеБанковскиеГарантии")

    assert described["ok"] is True
    assert described["strategies"][0]["strategy"] == "form_artifact_runner"
    assert described["report"]["status"] == "supported"


def test_analyzer_uses_bsp_runner_for_form_regulated_reports_with_object_events(tmp_path):
    _write(
        tmp_path / "Reports/СтатистикаПерсонала/Templates/СхемаКомпоновкиДанныхЗарплата.xml",
        """<MetaDataObject>
  <Template><Properties>
    <Name>СхемаКомпоновкиДанныхЗарплата</Name>
    <Synonym><v8:item xmlns:v8="x"><v8:content>Схема компоновки данных зарплата</v8:content></v8:item></Synonym>
    <TemplateType>DataCompositionSchema</TemplateType>
  </Properties></Template>
</MetaDataObject>""",
    )
    _write(
        tmp_path / "Reports/СтатистикаПерсонала/Ext/ManagerModule.bsl",
        'Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт\n'
        '    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "СреднесписочнаяЧисленность");\n'
        "КонецПроцедуры",
    )
    _write(
        tmp_path / "Reports/СтатистикаПерсонала/Ext/ObjectModule.bsl",
        """РегламентированныйОтчет = Истина;
Процедура ОпределитьНастройкиФормы(Форма, КлючВарианта, Настройки) Экспорт
КонецПроцедуры
Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровки, СтандартнаяОбработка)
КонецПроцедуры""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", report="СтатистикаПерсонала")

    assert described["ok"] is True
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"
    assert described["report"]["variant"] == "СреднесписочнаяЧисленность"


def test_analyzer_creates_bsp_runner_for_empty_key_variant_report(tmp_path):
    _write(
        tmp_path / "Reports/ИспользуемыеВнешниеРесурсы/Templates/ПредставленияРазрешений.xml",
        "<MetaDataObject><Template><Properties><TemplateType>SpreadsheetDocument</TemplateType></Properties></Template></MetaDataObject>",
    )
    _write(
        tmp_path / "Reports/ИспользуемыеВнешниеРесурсы/Ext/ManagerModule.bsl",
        'Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт\n'
        '    ВариантыОтчетов.ОписаниеВарианта(Настройки, Метаданные.Отчеты.ИспользуемыеВнешниеРесурсы, "");\n'
        "КонецПроцедуры",
    )
    _write(
        tmp_path / "Reports/ИспользуемыеВнешниеРесурсы/Ext/ObjectModule.bsl",
        """Процедура ОпределитьНастройкиФормы(Форма, КлючВарианта, Настройки) Экспорт
КонецПроцедуры
Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровки, СтандартнаяОбработка)
КонецПроцедуры""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", report="ИспользуемыеВнешниеРесурсы")

    assert described["ok"] is True
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"
    assert described["report"]["variant"] == ""


def test_analyzer_creates_no_arg_manager_function_strategy(tmp_path):
    _write(
        tmp_path / "Reports/ВизуализацияУстаревшихУведомлений/Templates/ИнформацияДляПечати.xml",
        "<MetaDataObject><Template><Properties><TemplateType>SpreadsheetDocument</TemplateType></Properties></Template></MetaDataObject>",
    )
    _write(
        tmp_path / "Reports/ВизуализацияУстаревшихУведомлений/Ext/ManagerModule.bsl",
        """Функция ИнформацияДляПечати() Экспорт
    Возврат Новый ТаблицаЗначений;
КонецФункции

Функция ИнформацияДляПечатиУведомления(Ссылка) Экспорт
КонецФункции""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)
    described = catalog.describe_report("Z01", report="ВизуализацияУстаревшихУведомлений")

    assert described["ok"] is True
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "manager_no_arg_function_runner"
    assert described["strategies"][0]["entrypoint"] == "ИнформацияДляПечати"


def test_analyzer_detects_external_dataset_object_from_skd_xml(tmp_path):
    _write(
        tmp_path / "Reports/ПоискКонтрагентов/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <dataSet xsi:type="DataSetObject">
    <name>РезультатПоиска</name>
    <objectName>ДанныеПоиска</objectName>
  </dataSet>
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>Поиск контрагентов</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report("ERP_DEMO", title="Поиск контрагентов")

    assert described["ok"] is True
    assert described["report"]["kind"] == "external_datasets_required"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"


def test_analyzer_blocks_raw_skd_when_query_uses_prepared_temp_table(tmp_path):
    _write(
        tmp_path / "Reports/Справка/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <query>ВЫБРАТЬ ОбщиеДанные.ФИО ИЗ
    ВТОбщиеДанныеСправок КАК ОбщиеДанные</query>
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">Основной</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>Справка сотруднику</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("Z01", tmp_path)

    described = catalog.describe_report("Z01", title="Справка сотруднику")

    assert described["ok"] is True
    assert described["report"]["kind"] == "runtime_probe_required"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"


def test_analyzer_offers_dataset_query_before_probe_for_runtime_probe_report_with_local_query(tmp_path):
    _write(
        tmp_path / "Reports/АнализОбязательствПоНДФЛ/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dataSource>
    <name>ИсточникДанных1</name>
    <dataSourceType>Local</dataSourceType>
  </dataSource>
  <dataSet xsi:type="DataSetQuery">
    <name>НаборДанныхНДФЛ</name>
    <field xsi:type="DataSetFieldField">
      <dataPath>Удержано</dataPath>
      <field>Удержано</field>
      <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Удержано</v8:content></v8:item></title>
    </field>
    <field xsi:type="DataSetFieldField">
      <dataPath>Перечислено</dataPath>
      <field>Перечислено</field>
      <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Уплачено</v8:content></v8:item></title>
    </field>
    <dataSource>ИсточникДанных1</dataSource>
    <query>ВЫБРАТЬ
    100 КАК Удержано,
    25 КАК Перечислено</query>
  </dataSet>
  <settingsVariant>
    <dcsset:name>КонтрольСроковУплатыПоИсточникам</dcsset:name>
    <dcsset:presentation xsi:type="v8:LocalStringType"><v8:item><v8:content>Контроль уплаты НДФЛ по источникам финансирования</v8:content></v8:item></dcsset:presentation>
        <dcsset:settings>
          <dcsset:selection>
            <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Удержано</dcsset:field></dcsset:item>
            <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Перечислено</dcsset:field></dcsset:item>
            <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПериодКонтрольОстатков</dcsset:field></dcsset:item>
          </dcsset:selection>
        </dcsset:settings>
      </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализОбязательствПоНДФЛ/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата() Экспорт
    СхемаКомпоновкиДанных.НаборыДанных.НаборДанныхНДФЛ.Поля.Найти("Удержано");
КонецПроцедуры""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализОбязательствПоНДФЛ", variant="КонтрольСроковУплатыПоИсточникам")

    assert described["report"]["kind"] == "runtime_probe_required"
    assert described["strategies"][0]["strategy"] == "bsp_variant_report_runner"
    assert described["strategies"][1]["strategy"] == "raw_skd_dataset_query_runner"
    assert described["strategies"][2]["strategy"] == "raw_skd_probe_runner"
    assert described["strategies"][1]["details"]["selected_fields"] == ["Удержано", "Перечислено"]
    assert "ПериодКонтрольОстатков" not in described["strategies"][1]["details"]["selected_fields"]


def test_analyzer_fallbacks_and_helper_branches(tmp_path):
    _write(
        tmp_path / "Reports/БезXML/Templates/Пустой.xml",
        "<root><TemplateType>DataCompositionSchema</TemplateType><a /></root>",
    )
    _write(tmp_path / "Reports/БитыйXML/Templates/Синоним.xml", "<root>Печатная форма</broken")
    _write(
        tmp_path / "Reports/Табличный/Templates/Макет.xml",
        "<root><TemplateType>SpreadsheetDocument</TemplateType><name>Макет</name></root>",
    )
    _write(
        tmp_path / "Reports/БезИмениВарианта/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant><presentation><v8:item><v8:content>Вариант без имени</v8:content></v8:item></presentation></settingsVariant>
  <settingsVariant><name>Технический</name><presentation><v8:item><v8:content>DataCompositionSchema</v8:content></v8:item></presentation></settingsVariant>
</root>""",
    )
    _write(
        tmp_path / "Reports/Экспортный/Ext/ManagerModule.bsl",
        "Функция Построить() Экспорт\nКонецФункции",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    analyzer = ReportAnalyzer(catalog)
    analyzer.analyze_database("Z01", tmp_path)

    no_xml = catalog.describe_report("Z01", title="Пустой")
    broken_xml = catalog.describe_report("Z01", title="Печатная форма")
    spreadsheet = catalog.describe_report("Z01", title="Макет")
    exported = catalog.describe_report("Z01", report="Экспортный")

    assert no_xml["ok"] is True
    assert no_xml["variants"][0]["template"] == "Пустой"
    assert no_xml["strategies"][0]["details"]["template"] == "Пустой"
    assert broken_xml["ok"] is True
    assert broken_xml["variants"] == []
    assert spreadsheet["ok"] is True
    assert spreadsheet["strategies"] == []
    assert spreadsheet["report"]["kind"] == "unsupported"
    assert exported["report"]["kind"] == "exported_entrypoint_probe"
    assert analyzer._variant_for_alias("x", []) == ""
    assert analyzer._variant_for_alias("x", [{"key": "fallback", "presentation": "y"}]) == "fallback"
    assert analyzer._classify("", False, False) == "unsupported"
    assert analyzer._read_text(tmp_path / "missing.bsl") == ""
    assert analyzer._unique_nonempty([" A ", "A", "", "B"]) == ["A", "B"]
    assert analyzer._template_aliases(tmp_path / "Reports/БитыйXML") == ["Печатная форма"]
    assert analyzer._manager_variant_keys('ОписаниеВарианта(Настройки); ОписаниеВарианта("bad-key!");') == []
    assert analyzer._skd_variant_presentations(tmp_path / "Reports/БезИмениВарианта") == {}
    assert analyzer._first_user_content("<root><content>DataCompositionSchema</content></root>") == ""
    assert analyzer._needs_runtime_probe("схемакомпоновкиданных.наборыданных", "") is True
    assert analyzer._needs_runtime_probe("", "<expression>ОбщийМодуль.Функция()</expression>") is True
    assert analyzer._preferred_payroll_variant([{"key": "РасчетныйЛистокДругой", "presentation": ""}]) == "РасчетныйЛистокДругой"
    assert analyzer._preferred_payroll_variant([{"key": "Расчетный листок", "presentation": ""}]) == "Расчетный листок"
    assert analyzer._preferred_payroll_variant([{"key": "", "presentation": "Расчетный листок"}]) == ""
    assert analyzer._preferred_payroll_variant([]) == ""
    assert analyzer._unique_entries(
        [
            {"alias": ""},
            {"alias": " Дубль ", "variant": "A"},
            {"alias": "Дубль", "variant": "A"},
            {"alias": "Дубль", "variant": "B"},
        ]
    ) == [
        {"alias": "Дубль", "variant": "A"},
        {"alias": "Дубль", "variant": "B"},
    ]
    assert analyzer._variant_aliases([{"key": "РасчетныйЛисток", "presentation": ""}])[0]["alias"] == "Расчетный Листок"
    assert analyzer._known_aliases("АнализНачисленийИУдержаний", [])[0]["variant"] == ""
    assert analyzer._is_user_alias("https://its.1c.ru/db/example") is False
    assert analyzer._is_user_alias("LatinIdentifier") is False


def test_analyzer_uses_graph_hints_for_known_adapter_when_static_module_missing(tmp_path):
    _write(
        tmp_path / "Reports/АнализНачисленийИУдержаний/Templates/ПФ_MXL_РасчетныйЛисток.xml",
        "<root>Расчетный листок</root>",
    )
    graph_hints = {
        "available": True,
        "nodes": [
            {
                "id": "Z01:CommonModules:ЗарплатаКадрыОтчеты",
                "type": "commonModule",
                "properties": {"name": "ЗарплатаКадрыОтчеты", "db": "Z01"},
            },
            {
                "id": "Z01:Reports:АнализНачисленийИУдержаний",
                "type": "report",
                "properties": {"name": "АнализНачисленийИУдержаний", "db": "Z01"},
            },
        ],
        "edges": [
            {
                "sourceId": "Z01:Reports:АнализНачисленийИУдержаний",
                "targetId": "Z01:CommonModules:ЗарплатаКадрыОтчеты",
                "type": "references",
            }
        ],
    }
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog, graph_hints=graph_hints).analyze_database("Z01", tmp_path)

    described = catalog.describe_report("Z01", title="Расчетный листок")

    assert described["ok"] is True
    assert described["strategies"][0]["strategy"] == "adapter_entrypoint"
    assert described["strategies"][0]["details"]["source"] == "graph"
    assert described["report"]["report"] == "АнализНачисленийИУдержаний"


def test_analyzer_graph_summary_ignores_malformed_graph_items(tmp_path):
    analyzer = ReportAnalyzer(
        ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results"),
        graph_hints={
            "available": True,
            "nodes": [None, {"id": "Z01:Reports:Отчет", "properties": "bad"}],
            "edges": [None, {"sourceId": "missing", "targetId": "other"}],
        },
    )

    summary = analyzer._graph_summary("Отчет")

    assert summary["available"] is True
    assert summary["node_ids"] == ["Z01:Reports:Отчет"]
    assert summary["related_edge_count"] == 0
    assert analyzer._payroll_adapter_source(tmp_path, summary) == ""


def test_analyzer_keeps_declared_contract_variant_specific_for_context_view(tmp_path):
    _write(
        tmp_path / "Reports/АнализВыполненияМаршрутныхЛистов/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <settingsVariant>
    <dcsset:name>ВыполнениеМаршрутныхЛистовСЗадержками</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Выполнение маршрутных листов с задержками</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Номенклатура</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>СЗадержкой</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ДоляЗадержек</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
  <settingsVariant>
    <dcsset:name>СведенияОВыполненииМаршрутныхЛистовКонтекст</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Сведения о выполнении маршрутных листов</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>МаршрутныйЛист</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Буфер</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПричинаЗадержки</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ЗатраченоВремени</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
  <field><dataPath>Номенклатура</dataPath><title><v8:item><v8:content>Номенклатура</v8:content></v8:item></title></field>
  <field><dataPath>СЗадержкой</dataPath><title><v8:item><v8:content>С задержкой</v8:content></v8:item></title></field>
  <field><dataPath>ДоляЗадержек</dataPath><title><v8:item><v8:content>Доля задержек, %</v8:content></v8:item></title></field>
  <field><dataPath>МаршрутныйЛист</dataPath><title><v8:item><v8:content>Маршрутный лист</v8:content></v8:item></title></field>
  <field><dataPath>Буфер</dataPath><title><v8:item><v8:content>Буфер</v8:content></v8:item></title></field>
  <field><dataPath>ПричинаЗадержки</dataPath><title><v8:item><v8:content>Причина задержки</v8:content></v8:item></title></field>
  <field><dataPath>ЗатраченоВремени</dataPath><title><v8:item><v8:content>Затрачено времени, %</v8:content></v8:item></title></field>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализВыполненияМаршрутныхЛистов/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "ВыполнениеМаршрутныхЛистовСЗадержками");
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "СведенияОВыполненииМаршрутныхЛистовКонтекст");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализВыполненияМаршрутныхЛистов/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата() Экспорт
КонецПроцедуры
""",
    )

    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report(
        "ERP_DEMO",
        report="АнализВыполненияМаршрутныхЛистов",
        variant="СведенияОВыполненииМаршрутныхЛистовКонтекст",
    )

    assert described["output_contract"]["expected_columns"] == [
        "Маршрутный лист",
        "Буфер",
        "Причина задержки",
        "Затрачено времени, %",
    ]
    assert "Номенклатура" not in described["output_contract"]["expected_columns"]


def test_analyzer_uses_variant_specific_layout_contract_for_custom_control_report(tmp_path):
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field><dataPath>Пользователь</dataPath><title><v8:item><v8:content>Пользователь</v8:content></v8:item></title></field>
  <field><dataPath>КоличествоПользователей</dataPath><title><v8:item><v8:content>Количество пользователей</v8:content></v8:item></title></field>
  <settingsVariant>
    <dcsset:name>АнализАктивностиПользователей</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ активности пользователей</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Пользователь</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>КоличествоПользователей</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
  <settingsVariant>
    <dcsset:name>КонтрольЖурналаРегистрации</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Контроль журнала регистрации</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:dataParameters>
        <dcscor:item xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core" xsi:type="dcsset:SettingsParameterValue">
          <dcscor:parameter>ВариантОтчета</dcscor:parameter>
          <dcscor:value xsi:type="xs:string" xmlns:xs="http://www.w3.org/2001/XMLSchema">КонтрольЖурналаРегистрации</dcscor:value>
        </dcscor:item>
      </dcsset:dataParameters>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Templates/МакетОтчетаПоОшибкамВЖурналеРегистрации/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<doc xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <v8:content>Ошибки и предупреждения в журнале регистрации</v8:content>
  <v8:content>Ошибки ([ЧислоОшибок])</v8:content>
  <v8:content>Предупреждения ([ЧислоПредупреждений])</v8:content>
</doc>
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "АнализАктивностиПользователей");
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "КонтрольЖурналаРегистрации");
КонецПроцедуры

Функция СформироватьОтчетКонтрольЖурналаРегистрации() Экспорт
    Макет = ПолучитьМакет("МакетОтчетаПоОшибкамВЖурналеРегистрации");
    Если РезультатКомпоновкиТЧ.Итог > 0 Тогда
        Возврат Макет;
    КонецЕсли;
    Возврат Неопределено;
КонецФункции
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровкиОбъект, СтандартнаяОбработка, АдресХранилища) Экспорт
    Если ВариантОтчета = "КонтрольЖурналаРегистрации" Тогда
        РезультатФормированияОтчета = Отчеты.АнализЖурналаРегистрации.
            СформироватьОтчетКонтрольЖурналаРегистрации();
    КонецЕсли;
КонецПроцедуры
""",
    )

    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report(
        "ERP_DEMO",
        report="АнализЖурналаРегистрации",
        variant="КонтрольЖурналаРегистрации",
    )

    assert described["output_contract"]["expects_detail_rows"] is False
    assert described["output_contract"]["expected_markers"][:3] == [
        "Анализ Журнала Регистрации",
        "Контроль журнала регистрации",
        "Ошибки и предупреждения в журнале регистрации",
    ]
    assert "Количество пользователей" not in described["output_contract"]["expected_columns"]


def test_analyzer_extracts_variant_data_parameters_and_defaults(tmp_path):
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:dcscor="http://v8.1c.ru/8.1/data-composition-system/core"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <parameter>
    <name>ВариантОтчета</name>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Вариант отчета</v8:content></v8:item></title>
    <valueType><v8:Type>xs:string</v8:Type></valueType>
  </parameter>
  <parameter>
    <name>ПериодДень</name>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Период день</v8:content></v8:item></title>
    <valueType><v8:Type>v8:StandardBeginningDate</v8:Type></valueType>
  </parameter>
  <parameter>
    <name>ОтображатьФоновыеЗадания</name>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Отображать фоновые задания</v8:content></v8:item></title>
    <valueType><v8:Type>xs:boolean</v8:Type></valueType>
  </parameter>
  <parameter>
    <name>МинимальнаяПродолжительностьСеансовРегламентныхЗаданий</name>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Минимальная продолжительность</v8:content></v8:item></title>
    <valueType><v8:Type>xs:decimal</v8:Type></valueType>
  </parameter>
  <settingsVariant>
    <dcsset:name>ПродолжительностьРаботыРегламентныхЗаданий</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Продолжительность работы регламентных заданий</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:dataParameters>
        <dcscor:item xsi:type="dcsset:SettingsParameterValue">
          <dcscor:parameter>ВариантОтчета</dcscor:parameter>
          <dcscor:value xsi:type="xs:string">ПродолжительностьРаботыРегламентныхЗаданий</dcscor:value>
        </dcscor:item>
        <dcscor:item xsi:type="dcsset:SettingsParameterValue">
          <dcscor:parameter>ПериодДень</dcscor:parameter>
          <dcscor:value xsi:type="v8:StandardBeginningDate"><v8:variant xsi:type="v8:StandardBeginningDateVariant">BeginningOfThisDay</v8:variant></dcscor:value>
        </dcscor:item>
        <dcscor:item xsi:type="dcsset:SettingsParameterValue">
          <dcscor:parameter>ОтображатьФоновыеЗадания</dcscor:parameter>
          <dcscor:value xsi:type="xs:boolean">false</dcscor:value>
        </dcscor:item>
        <dcscor:item xsi:type="dcsset:SettingsParameterValue">
          <dcscor:parameter>МинимальнаяПродолжительностьСеансовРегламентныхЗаданий</dcscor:parameter>
          <dcscor:value xsi:type="xs:decimal">1</dcscor:value>
        </dcscor:item>
      </dcsset:dataParameters>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "ПродолжительностьРаботыРегламентныхЗаданий");
КонецПроцедуры
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report(
        "ERP_DEMO",
        report="АнализЖурналаРегистрации",
        variant="ПродолжительностьРаботыРегламентныхЗаданий",
    )
    params = {item["name"]: item for item in described["params"]}

    assert "ВариантОтчета" not in params
    assert params["ПериодДень"]["source"] == "skd_variant_data_parameter"
    assert params["ПериодДень"]["default"] == {"kind": "standard_beginning_date", "value": "BeginningOfThisDay"}
    assert params["ОтображатьФоновыеЗадания"]["default"] is False
    assert params["МинимальнаяПродолжительностьСеансовРегламентныхЗаданий"]["default"] == 1


def test_analyzer_detects_visual_local_layout_contract_for_runtime_variant(tmp_path):
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name>ПродолжительностьРаботыРегламентныхЗаданий</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Продолжительность работы регламентных заданий</v8:content></v8:item></dcsset:presentation>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Templates/ПродолжительностьРаботыРегламентныхЗаданий/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<doc xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <v8:content>Продолжительность работы регламентных заданий</v8:content>
  <v8:content>Отключено отображение интервалов с нулевой продолжительностью</v8:content>
  <v8:content>Диаграмма</v8:content>
</doc>
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "ПродолжительностьРаботыРегламентныхЗаданий");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализЖурналаРегистрации/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровкиОбъект, СтандартнаяОбработка, АдресХранилища) Экспорт
    Если ВариантОтчета = "ПродолжительностьРаботыРегламентныхЗаданий" Тогда
        ПродолжительностьРаботыРегламентныхЗаданий(НастройкиОтчета, ДокументРезультат, КомпоновщикНастроек);
    КонецЕсли;
КонецПроцедуры

Процедура ПродолжительностьРаботыРегламентныхЗаданий(НастройкиОтчета, ДокументРезультат, КомпоновщикНастроек)
    Макет = ПолучитьМакет("ПродолжительностьРаботыРегламентныхЗаданий");
    Если ЗначениеЗаполнено(ОдновременноСессий) Тогда
        ДокументРезультат.Вывести(ОписаниеОбластиМакета(Макет, "ШапкаТаблицы"));
    КонецЕсли;
    Область = ОписаниеОбластиМакета(Макет, "Диаграмма");
    ДиаграммаГанта = Область.Рисунки.ДиаграммаГанта.Объект;
КонецПроцедуры
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)
    described = catalog.describe_report(
        "ERP_DEMO",
        report="АнализЖурналаРегистрации",
        variant="ПродолжительностьРаботыРегламентныхЗаданий",
    )

    assert described["output_contract"]["output_type"] == "mixed"
    assert described["output_contract"]["allows_empty_result"] is True
    assert described["output_contract"]["expects_visual_components"] is True
    assert described["output_contract"]["expected_markers"][:3] == [
        "Анализ Журнала Регистрации",
        "Продолжительность работы регламентных заданий",
        "Отключено отображение интервалов с нулевой продолжительностью",
    ]


def test_analyzer_marks_chart_variant_with_prerequisite_help_as_blank_visual_contract(tmp_path):
    _write(
        tmp_path / "Reports/АнализЗависимостиОтКлиентовABC/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField">
    <dataPath>ПартнерКоличество</dataPath>
    <field>ПартнерКоличество</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Количество партнеров</v8:content></v8:item></title>
  </field>
  <field xsi:type="DataSetFieldField">
    <dataPath>Партнер</dataPath>
    <field>Партнер</field>
    <title xsi:type="v8:LocalStringType"><v8:item><v8:content>Клиент</v8:content></v8:item></title>
  </field>
  <settingsVariant>
    <dcsset:name>Основной</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ зависимости от клиентов (ABC)</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПартнерКоличество</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Партнер</dcsset:field></dcsset:item>
      </dcsset:selection>
      <dcsset:item xsi:type="dcsset:StructureItemChart">
        <dcsset:series>
          <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПартнерКоличество</dcsset:field></dcsset:item>
        </dcsset:series>
      </dcsset:item>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализЗависимостиОтКлиентовABC/Ext/Help/ru.html",
        """<html><body>
<p>Отчет предназначен для визуального анализа на основании данных о предварительно проведенной АВС-классификации клиентов.</p>
<p>Предварительная АВС-классификация клиентов может быть осуществлена согласно настроенному расписанию при помощи регламентного задания.</p>
</body></html>
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализЗависимостиОтКлиентовABC", variant="Основной")

    assert described["output_contract"]["output_type"] == "mixed"
    assert described["output_contract"]["expects_detail_rows"] is False
    assert described["output_contract"]["expects_visual_components"] is True
    assert described["output_contract"]["accepts_blank_output"] is True
    assert "Количество партнеров" in described["output_contract"]["expected_columns"]


def test_analyzer_marks_report_with_empty_hook_as_allows_empty_result(tmp_path):
    _write(
        tmp_path / "Reports/АнализИзмененийЛичныхДанныхСотрудников/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField"><dataPath>Период</dataPath><field>Период</field><title xsi:type="v8:LocalStringType"><v8:item><v8:content>Дата</v8:content></v8:item></title></field>
  <field xsi:type="DataSetFieldField"><dataPath>Сотрудник</dataPath><field>Сотрудник</field></field>
  <field xsi:type="DataSetFieldField"><dataPath>ПрежнееЗначение</dataPath><field>ПрежнееЗначение</field><title xsi:type="v8:LocalStringType"><v8:item><v8:content>Было</v8:content></v8:item></title></field>
  <field xsi:type="DataSetFieldField"><dataPath>УстановленноеЗначение</dataPath><field>УстановленноеЗначение</field><title xsi:type="v8:LocalStringType"><v8:item><v8:content>Стало</v8:content></v8:item></title></field>
  <settingsVariant>
    <dcsset:name>АнализИзмененийЛичныхДанныхСотрудников</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ изменений личных данных сотрудников</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Период</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>Сотрудник</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ПрежнееЗначение</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>УстановленноеЗначение</dcsset:field></dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    _write(
        tmp_path / "Reports/АнализИзмененийЛичныхДанныхСотрудников/Ext/ManagerModule.bsl",
        """Процедура НастроитьВариантыОтчета(Настройки, НастройкиОтчета) Экспорт
    НастройкиОтчета.ОпределитьНастройкиФормы = Истина;
    НастройкиВарианта = ВариантыОтчетов.ОписаниеВарианта(Настройки, НастройкиОтчета, "АнализИзмененийЛичныхДанныхСотрудников");
КонецПроцедуры
""",
    )
    _write(
        tmp_path / "Reports/АнализИзмененийЛичныхДанныхСотрудников/Ext/ObjectModule.bsl",
        """Процедура ПриКомпоновкеРезультата(ДокументРезультат, ДанныеРасшифровки, СтандартнаяОбработка)
    СтандартнаяОбработка = Ложь;
    ДопСвойства = КомпоновщикНастроек.ПользовательскиеНастройки.ДополнительныеСвойства;
    ДопСвойства.Вставить("ОтчетПустой", ОтчетыСервер.ОтчетПустой(ЭтотОбъект, Неопределено));
КонецПроцедуры
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report(
        "ERP",
        report="АнализИзмененийЛичныхДанныхСотрудников",
        variant="АнализИзмененийЛичныхДанныхСотрудников",
    )

    assert described["output_contract"]["allows_empty_result"] is True


def test_analyzer_uses_selected_folder_titles_for_matrix_variant_contract(tmp_path):
    _write(
        tmp_path / "Reports/АнализНДФЛ/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <field xsi:type="DataSetFieldField"><dataPath>ФизическоеЛицо</dataPath><field>ФизическоеЛицо</field><title xsi:type="v8:LocalStringType"><v8:item><v8:content>Сотрудник</v8:content></v8:item></title></field>
  <field xsi:type="DataSetFieldField"><dataPath>Доход</dataPath><field>Доход</field></field>
  <field xsi:type="DataSetFieldField"><dataPath>ДоходМатпомощь</dataPath><field>ДоходМатпомощь</field></field>
  <field xsi:type="DataSetFieldField"><dataPath>СтандартныйВычет</dataPath><field>СтандартныйВычет</field></field>
  <field xsi:type="DataSetFieldField"><dataPath>ИмущественныйВычет</dataPath><field>ИмущественныйВычет</field></field>
  <settingsVariant>
    <dcsset:name>АнализНДФЛПоМесяцам</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ НДФЛ по месяцам</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings>
      <dcsset:selection>
        <dcsset:item xsi:type="dcsset:SelectedItemField"><dcsset:field>ФизическоеЛицо</dcsset:field></dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemFolder">
          <dcsset:lwsTitle><v8:item><v8:content>Начислено</v8:content></v8:item></dcsset:lwsTitle>
          <dcsset:item xsi:type="dcsset:SelectedItemField">
            <dcsset:field>Доход</dcsset:field>
            <dcsset:lwsTitle><v8:item><v8:content>Всего</v8:content></v8:item></dcsset:lwsTitle>
          </dcsset:item>
          <dcsset:item xsi:type="dcsset:SelectedItemField">
            <dcsset:field>ДоходМатпомощь</dcsset:field>
            <dcsset:lwsTitle><v8:item><v8:content>в т.ч. матпомощь</v8:content></v8:item></dcsset:lwsTitle>
          </dcsset:item>
        </dcsset:item>
        <dcsset:item xsi:type="dcsset:SelectedItemFolder">
          <dcsset:lwsTitle><v8:item><v8:content>Станд. и имущ. вычеты</v8:content></v8:item></dcsset:lwsTitle>
          <dcsset:item xsi:type="dcsset:SelectedItemField">
            <dcsset:field>СтандартныйВычет</dcsset:field>
            <dcsset:lwsTitle><v8:item><v8:content>Стандартн.</v8:content></v8:item></dcsset:lwsTitle>
          </dcsset:item>
          <dcsset:item xsi:type="dcsset:SelectedItemField">
            <dcsset:field>ИмущественныйВычет</dcsset:field>
            <dcsset:lwsTitle><v8:item><v8:content>Имуществ.</v8:content></v8:item></dcsset:lwsTitle>
          </dcsset:item>
        </dcsset:item>
      </dcsset:selection>
    </dcsset:settings>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализНДФЛ", variant="АнализНДФЛПоМесяцам")

    assert described["output_contract"]["expected_columns"][:5] == [
        "Сотрудник",
        "Всего",
        "в т.ч. матпомощь",
        "Стандартн.",
        "Имуществ.",
    ]
    assert "Начислено" in described["output_contract"]["expected_markers"]
    assert "Станд. и имущ. вычеты" in described["output_contract"]["expected_markers"]


def test_analyzer_marks_historical_variant_as_allowing_empty_result(tmp_path):
    _write(
        tmp_path / "Reports/АнализНДФЛ/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema"
  xmlns:dcsset="http://v8.1c.ru/8.1/data-composition-system/settings"
  xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <settingsVariant>
    <dcsset:name>АнализУплатыНДФЛ</dcsset:name>
    <dcsset:presentation><v8:item><v8:content>Анализ уплаты НДФЛ (до 2016 года)</v8:content></v8:item></dcsset:presentation>
    <dcsset:settings/>
  </settingsVariant>
</DataCompositionSchema>
""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")

    ReportAnalyzer(catalog).analyze_database("ERP", tmp_path)
    described = catalog.describe_report("ERP", report="АнализНДФЛ", variant="АнализУплатыНДФЛ")

    assert described["output_contract"]["allows_empty_result"] is True
    assert described["output_contract"]["accepts_blank_output"] is True

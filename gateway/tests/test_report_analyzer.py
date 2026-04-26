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


def test_analyzer_blocks_raw_skd_when_template_uses_runtime_session_function(tmp_path):
    _write(
        tmp_path / "Reports/МаршрутныеЛисты/Templates/ОсновнаяСхемаКомпоновкиДанных/Ext/Template.xml",
        """<root xmlns:v8="http://v8.1c.ru/8.1/data/core">
  <expression>ТекущаяДатаСеанса()</expression>
  <settingsVariant>
    <dcsset:name xmlns:dcsset="x">СЗадержками</dcsset:name>
    <dcsset:presentation xmlns:dcsset="x">
      <v8:item><v8:content>С задержками</v8:content></v8:item>
    </dcsset:presentation>
  </settingsVariant>
</root>""",
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    ReportAnalyzer(catalog).analyze_database("ERP_DEMO", tmp_path)

    described = catalog.describe_report("ERP_DEMO", title="С задержками")

    assert described["ok"] is True
    assert described["report"]["kind"] == "runtime_probe_required"
    assert described["report"]["status"] == "supported"
    assert described["strategies"][0]["strategy"] == "raw_skd_probe_runner"
    assert described["strategies"][0]["requires_runtime_probe"] is True


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

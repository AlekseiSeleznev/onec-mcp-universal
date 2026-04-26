from __future__ import annotations

from gateway.report_catalog import ReportCatalog
from gateway.report_resolver import ReportResolver


def test_resolver_returns_not_found_with_nearest_candidates(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {
                    "name": "АнализНачисленийИУдержаний",
                    "aliases": [{"alias": "Расчетный листок", "source": "template", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "priority": 20, "confidence": 0.7}],
                }
            ]
        },
    )
    result = ReportResolver(catalog).resolve("Z01", title="Расчетка")

    assert result["ok"] is False
    assert result["error_code"] == "report_not_found"
    assert result["candidates"][0]["title"] == "Расчетный листок"


def test_resolver_detects_ambiguous_user_facing_name(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "Z01",
        "/projects/Z01",
        {
            "reports": [
                {"name": "Отчет1", "aliases": [{"alias": "Продажи", "source": "synonym", "confidence": 0.9}]},
                {"name": "Отчет2", "aliases": [{"alias": "Продажи", "source": "synonym", "confidence": 0.9}]},
            ]
        },
    )
    result = ReportResolver(catalog).resolve("Z01", title="Продажи")

    assert result["ok"] is False
    assert result["error_code"] == "ambiguous_report"
    assert {row["report"] for row in result["candidates"]} == {"Отчет1", "Отчет2"}


def test_resolver_detects_ambiguous_variants_with_same_user_facing_name(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "ABCXYZАнализНоменклатуры",
                    "aliases": [
                        {"alias": "ABC/XYZ-анализ номенклатуры", "variant": "ЗапасыПоСкладам", "confidence": 0.99},
                        {"alias": "ABC/XYZ-анализ номенклатуры", "variant": "ПоНоменклатуреКонтекст", "confidence": 0.99},
                    ],
                    "variants": [
                        {"key": "ЗапасыПоСкладам", "presentation": "ABC/XYZ-анализ номенклатуры"},
                        {"key": "ПоНоменклатуреКонтекст", "presentation": "ABC/XYZ-анализ номенклатуры"},
                    ],
                }
            ]
        },
    )

    result = ReportResolver(catalog).resolve("ERP_DEMO", title="ABC XYZ анализ номенклатуры")

    assert result["ok"] is False
    assert result["error_code"] == "ambiguous_report"
    assert {row["variant"] for row in result["candidates"]} == {"ЗапасыПоСкладам", "ПоНоменклатуреКонтекст"}


def test_resolver_prefers_variant_over_duplicate_report_synonym(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "СПАРК",
                    "synonym": "Надежность дебиторов",
                    "aliases": [{"alias": "Надежность дебиторов", "variant": "Основной", "confidence": 0.99}],
                    "variants": [{"key": "Основной", "presentation": "Надежность дебиторов"}],
                }
            ]
        },
    )

    result = ReportResolver(catalog).resolve("ERP_DEMO", title="Надежность дебиторов")

    assert result["ok"] is True
    assert result["report"]["variant"] == "Основной"


def test_resolver_accepts_explicit_technical_report(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis("Z01", "/projects/Z01", {"reports": [{"name": "ТехническийОтчет"}]})

    result = ReportResolver(catalog).resolve("Z01", report="ТехническийОтчет")

    assert result["ok"] is True
    assert result["report"]["report"] == "ТехническийОтчет"

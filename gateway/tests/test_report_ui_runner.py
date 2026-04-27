from __future__ import annotations

from pathlib import Path

import pytest

from gateway.report_catalog import ReportCatalog
from gateway.report_ui_runner import ReportUiRunner
from gateway.tests.test_report_result_extractor import _write_xlsx


class FakeUiClient:
    def __init__(self, artifact_path: Path):
        self.artifact_path = artifact_path
        self.calls = []

    async def export_report(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "artifact_path": str(self.artifact_path), "diagnostics": {"mode": "fake"}}


@pytest.mark.asyncio
async def test_ui_runner_exports_parses_persists_and_removes_temp_file(tmp_path):
    artifact = tmp_path / "ui" / "report.xlsx"
    artifact.parent.mkdir()
    _write_xlsx(
        artifact,
        [
            ["Себестоимость выпущенной продукции"],
            ["Материал", "Стоимость затрат"],
            ["Лист 0,6 63C2A", "5 000,00"],
        ],
    )
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "synonym": "Анализ себестоимости",
                    "aliases": [{"alias": "Анализ себестоимости", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "output_type": "rows"}],
                    "output_contracts": [
                        {
                            "source": "declared",
                            "contract": {
                                "output_type": "rows",
                                "expects_detail_rows": True,
                                "expected_columns": ["Материал", "Стоимость затрат"],
                                "expected_markers": ["Себестоимость"],
                            },
                        }
                    ],
                }
            ]
        },
    )

    result = await ReportUiRunner(
        catalog=catalog,
        client=FakeUiClient(artifact),
        artifacts_dir=tmp_path / "artifacts",
    ).run_report(
        database="ERP_DEMO",
        title="Анализ себестоимости",
        report="АнализСебестоимости",
        variant="",
        period={"start": "2024-04-01", "end": "2024-04-30"},
        filters={"Организация": "Металл-Сервис"},
        params={},
        max_rows=100,
    )

    assert result["ok"] is True
    assert result["runner_used"] == "ui"
    assert result["extractor_used"] == "xlsx_export"
    assert result["rows"] == [{"Материал": "Лист 0,6 63C2A", "Стоимость затрат": "5 000,00"}]
    assert result["contract_validation"]["matched"] is True
    assert not artifact.exists()
    stored = catalog.get_report_result("ERP_DEMO", result["run_id"])
    assert stored["rows"][0]["Материал"] == "Лист 0,6 63C2A"


@pytest.mark.asyncio
async def test_ui_runner_passes_saved_ui_strategy_to_client(tmp_path):
    artifact = tmp_path / "ui" / "report.xlsx"
    artifact.parent.mkdir()
    _write_xlsx(artifact, [["Заголовок"], ["Материал", "Стоимость затрат"], ["Лист", "5000"]])
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "synonym": "Анализ себестоимости",
                    "aliases": [{"alias": "Анализ себестоимости", "confidence": 1.0}],
                    "strategies": [{"strategy": "raw_skd_runner", "output_type": "rows"}],
                }
            ]
        },
    )
    catalog.upsert_report_ui_strategy(
        "ERP_DEMO",
        "АнализСебестоимости",
        "",
        {
            "open": {"mode": "metadata_link", "metadata_path": "Отчет.АнализСебестоимости"},
            "parameter_map": {"Организация": "Организация"},
            "export": {"format": "xlsx"},
        },
        source="declared",
    )
    client = FakeUiClient(artifact)

    await ReportUiRunner(catalog=catalog, client=client, artifacts_dir=tmp_path / "artifacts").run_report(
        database="ERP_DEMO",
        title="",
        report="АнализСебестоимости",
        variant="",
        period=None,
        filters={"Организация": "Металл-Сервис"},
        params={},
    )

    assert client.calls[0]["ui_strategy"]["open"]["metadata_path"] == "Отчет.АнализСебестоимости"
    assert client.calls[0]["ui_strategy"]["parameter_map"]["Организация"] == "Организация"

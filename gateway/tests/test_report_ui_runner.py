from __future__ import annotations

from pathlib import Path

import pytest

from gateway.report_catalog import ReportCatalog
from gateway.report_ui_runner import WebTestHttpReportClient, ReportUiRunner, _ui_fields
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


def test_ui_fields_format_dates_and_skip_implicit_combined_period():
    fields = _ui_fields(
        {"start": "2024-04-01", "end": "2024-04-30"},
        {"Организация": "Металл-Сервис"},
        {},
        {
            "parameter_map": {
                "start": "Период1ДатаНачала",
                "end": "Период1ДатаОкончания",
                "Организация": "КомпоновщикНастроекПользовательскиеНастройкиЭлемент7Значение",
            }
        },
    )

    assert fields == {
        "Период1ДатаНачала": "01.04.2024",
        "Период1ДатаОкончания": "30.04.2024",
        "КомпоновщикНастроекПользовательскиеНастройкиЭлемент7Значение": "Металл-Сервис",
    }
    assert "Период" not in fields


def test_ui_fields_use_explicit_combined_period_mapping_only():
    fields = _ui_fields(
        {"start": "2024-04-01", "end": "2024-04-30"},
        {},
        {},
        {"parameter_map": {"period": "Период"}},
    )

    assert fields["Период"] == "01.04.2024 - 30.04.2024"


@pytest.mark.asyncio
async def test_ui_runner_persists_successful_strategy_as_verified(tmp_path):
    catalog = ReportCatalog(tmp_path / "catalog.sqlite", tmp_path / "results")
    catalog.replace_analysis(
        "ERP_DEMO",
        "/projects/ERP_DEMO",
        {
            "reports": [
                {
                    "name": "АнализСебестоимости",
                    "aliases": [{"alias": "Анализ себестоимости"}],
                }
            ]
        },
    )
    source_xlsx = tmp_path / "source.xlsx"
    _write_xlsx(source_xlsx, [["Материал", "Стоимость затрат"], ["Лист", 5000]])

    class FakeClient:
        async def export_report(self, **kwargs):
            Path(kwargs["artifact_path"]).write_bytes(source_xlsx.read_bytes())
            return {"ok": True, "artifact_path": kwargs["artifact_path"], "artifact_format": "xlsx"}

    result = await ReportUiRunner(catalog=catalog, client=FakeClient(), artifacts_dir=tmp_path / "tmp").run_report(
        database="ERP_DEMO",
        title="Анализ себестоимости",
        period={"start": "2024-04-01", "end": "2024-04-30"},
        filters={"Организация": "Металл-Сервис"},
        export_format="xlsx",
    )
    strategy = catalog.get_report_ui_strategy("ERP_DEMO", "АнализСебестоимости", "")

    assert result["ok"] is True
    assert strategy["source"] == "verified"
    assert strategy["strategy"]["open"]["metadata_path"] == "Отчет.АнализСебестоимости"
    assert strategy["strategy"]["parameter_map"]["Организация"] == "Организация"


@pytest.mark.asyncio
async def test_http_ui_client_writes_returned_artifact_base64(tmp_path, monkeypatch):
    import base64
    import json

    payload = b"artifact-bytes"

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "ok": True,
                "output": "REPORT_UI_EXPORT_JSON=" + json.dumps(
                    {
                        "artifact_format": "xlsx",
                        "artifact_base64": base64.b64encode(payload).decode("ascii"),
                    }
                )
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, content, headers):
            assert url == "http://127.0.0.1:40785/exec"
            assert "returnArtifactBase64" in content
            return FakeResponse()

    monkeypatch.setattr("gateway.report_ui_runner.httpx.AsyncClient", FakeAsyncClient)
    target = tmp_path / "report.xlsx"

    result = await WebTestHttpReportClient("http://127.0.0.1:40785").export_report(
        database="ERP_DEMO",
        report="Отчет",
        artifact_path=str(target),
        export_format="xlsx",
        ui_strategy={},
    )

    assert result["ok"] is True
    assert result["artifact_path"] == str(target)
    assert target.read_bytes() == payload
    assert "artifact_base64" not in result

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from gateway.report_result_extractor import ReportResultExtractor


def _cell_ref(row: int, col: int) -> str:
    name = ""
    col_num = col
    while col_num:
        col_num, rem = divmod(col_num - 1, 26)
        name = chr(65 + rem) + name
    return f"{name}{row}"


def _write_xlsx(path: Path, rows: list[list[object]], merges: list[str] | None = None) -> None:
    merges = merges or []
    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = _cell_ref(row_idx, col_idx)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    merge_xml = ""
    if merges:
        merge_xml = f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{ref}"/>' for ref in merges) + "</mergeCells>"
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>{merge_xml}</worksheet>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet)


def test_extract_xlsx_builds_structured_rows_and_removes_temp_file(tmp_path):
    xlsx = tmp_path / "run" / "report.xlsx"
    xlsx.parent.mkdir()
    _write_xlsx(
        xlsx,
        [
            ["Себестоимость выпущенной продукции"],
            ["Параметры:", "Период: 01.04.2024 - 30.04.2024"],
            ["Материал", "Стоимость затрат"],
            ["Лист 0,6 63C2A", "5 000,00"],
            ["Итого", "20 000,00"],
        ],
    )

    result = ReportResultExtractor().extract(xlsx, artifact_format="xlsx", cleanup=True)

    assert result["ok"] is True
    assert result["extractor_used"] == "xlsx_export"
    assert result["columns"] == ["Материал", "Стоимость затрат"]
    assert result["rows"] == [{"Материал": "Лист 0,6 63C2A", "Стоимость затрат": "5 000,00"}]
    assert result["totals"]["Стоимость затрат"] == "20 000,00"
    assert result["observed_signature"]["detail_rows_count"] == 1
    assert result["artifact_hash"]
    assert result["cleanup_status"] == "deleted"
    assert not xlsx.exists()


def test_extract_xlsx_preserves_merged_group_headers(tmp_path):
    xlsx = tmp_path / "report.xlsx"
    _write_xlsx(
        xlsx,
        [
            ["Остатки товаров"],
            ["Материал", "Показатели", ""],
            ["", "Стоимость затрат", "Количество"],
            ["Лист 0,6 63C2A", "5 000,00", "100,000"],
        ],
        merges=["B2:C2"],
    )

    result = ReportResultExtractor().extract(xlsx, artifact_format="xlsx", cleanup=False)

    assert result["columns"] == ["Материал", "Показатели / Стоимость затрат", "Показатели / Количество"]
    assert result["rows"][0]["Материал"] == "Лист 0,6 63C2A"
    assert result["rows"][0]["Показатели / Стоимость затрат"] == "5 000,00"
    assert xlsx.exists()


def test_extract_xlsx_does_not_duplicate_merged_data_cells(tmp_path):
    xlsx = tmp_path / "cost.xlsx"
    _write_xlsx(
        xlsx,
        [
            ["Себестоимость выпущенной продукции"],
            ["Параметры:", "", "Период: 01.04.2024 - 30.04.2024"],
            ["Статья калькуляции", "", "", "", "", "", "", "", "", "Количество затрат", "Стоимость затрат"],
            ["Затрата", "", "", "", "Характеристика", "Серия", "Ед. изм."],
            ["Итого", "", "", "", "", "", "", "", "", "", "20000"],
            ["Материалы основные", "", "", "", "", "", "", "", "", "", "5000"],
            ["Лист 0,6 63C2A", "", "", "", "", "", "кг", "", "", "100", "5000"],
        ],
        merges=[
            "A3:I3",
            "A4:D4",
            "G4:I4",
            "A5:I5",
            "A6:I6",
            "A7:D7",
            "G7:I7",
        ],
    )

    result = ReportResultExtractor().extract(xlsx, artifact_format="xlsx", cleanup=False)

    assert "Статья калькуляции / Затрата 2" not in result["columns"]
    material = next(row for row in result["rows"] if row.get("Статья калькуляции / Затрата") == "Лист 0,6 63C2A")
    assert material["Статья калькуляции / Ед. изм."] == "кг"
    assert material["Стоимость затрат"] == "5000"
    assert "затрата" in result["observed_signature"]["observed_tokens_norm"]


def test_extract_invalid_file_keeps_artifact_for_diagnostics(tmp_path):
    broken = tmp_path / "broken.xlsx"
    broken.write_text("not a zip", encoding="utf-8")

    with pytest.raises(ValueError):
        ReportResultExtractor(keep_error_artifacts=True).extract(broken, artifact_format="xlsx", cleanup=True)

    assert broken.exists()


def test_extract_dom_json_fallback_builds_rows_and_removes_file(tmp_path):
    artifact = tmp_path / "dom.json"
    artifact.write_text(
        """{
          "title": "Себестоимость",
          "headers": ["Материал", "Стоимость затрат"],
          "data": [{"Материал": "Лист", "Стоимость затрат": "5000"}],
          "totals": {"Стоимость затрат": "5000"}
        }""",
        encoding="utf-8",
    )

    result = ReportResultExtractor().extract(artifact, artifact_format="json", cleanup=True)

    assert result["ok"] is True
    assert result["extractor_used"] == "dom_spreadsheet"
    assert result["columns"] == ["Материал", "Стоимость затрат"]
    assert result["rows"] == [{"Материал": "Лист", "Стоимость затрат": "5000"}]
    assert result["cleanup_status"] == "deleted"
    assert not artifact.exists()

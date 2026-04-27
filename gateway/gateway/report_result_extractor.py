"""Extract structured report data from UI-exported 1C report artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .report_contracts import build_observed_signature
from .report_catalog import normalize_report_query


_XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELL_RE = re.compile(r"^([A-Z]+)(\d+)$")
_NUMBER_RE = re.compile(r"^-?\d[\d\s\u00a0]*(?:[,.]\d+)?$")


class ReportResultExtractor:
    """Parse temporary report export files and remove them after successful use."""

    def __init__(self, *, keep_error_artifacts: bool = False):
        self.keep_error_artifacts = bool(keep_error_artifacts)

    def extract(self, artifact_path: str | Path, *, artifact_format: str = "xlsx", cleanup: bool = True) -> dict:
        path = Path(artifact_path)
        artifact_hash = _file_hash(path)
        normalized_format = (artifact_format or path.suffix.lstrip(".") or "xlsx").lower()
        try:
            if normalized_format == "xlsx":
                result = self._extract_xlsx(path)
                extractor_used = "xlsx_export"
            elif normalized_format == "html":
                result = self._extract_html(path)
                extractor_used = "html_export"
            elif normalized_format in {"json", "dom_json"}:
                result = self._extract_dom_json(path)
                extractor_used = "dom_spreadsheet"
            else:
                raise ValueError(f"Unsupported report artifact format: {normalized_format}")
        except Exception as exc:
            if cleanup and not self.keep_error_artifacts:
                _cleanup_file(path)
            raise ValueError(f"Cannot extract report artifact '{path}': {exc}") from exc

        observed_signature = build_observed_signature(result)
        cleanup_status = "kept"
        if cleanup:
            cleanup_status = _cleanup_file(path)
        return {
            "ok": True,
            "artifact_format": normalized_format,
            "artifact_hash": artifact_hash,
            "extractor_used": extractor_used,
            "cleanup_status": cleanup_status,
            "observed_signature": observed_signature,
            **result,
        }

    def _extract_xlsx(self, path: Path) -> dict:
        matrix = _read_xlsx_matrix(path)
        return _matrix_to_result(matrix)

    def _extract_html(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8", errors="replace")
        rows: list[list[str]] = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, flags=re.IGNORECASE | re.DOTALL):
            cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.IGNORECASE | re.DOTALL)
            row = [re.sub(r"<[^>]+>", " ", cell).strip() for cell in cells]
            if any(row):
                rows.append(row)
        if not rows:
            raise ValueError("HTML artifact has no table rows")
        return _matrix_to_result(rows)

    def _extract_dom_json(self, path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload.get("data"), list) and (not payload["data"] or isinstance(payload["data"][0], dict)):
            rows = [dict(item) for item in payload.get("data") or []]
            columns = list(payload.get("headers") or (list(rows[0].keys()) if rows else []))
            return {
                "columns": columns,
                "rows": rows,
                "totals": dict(payload.get("totals") or {}),
                "metadata": {"title": str(payload.get("title") or ""), "source": "dom_spreadsheet"},
                "output_type": "rows",
            }
        raw_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        if raw_rows and isinstance(raw_rows[0], list):
            return _matrix_to_result(raw_rows)
        raise ValueError("DOM JSON artifact has no spreadsheet data")


def _read_xlsx_matrix(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in zf.namelist():
            sheet_name = next((name for name in zf.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")), "")
        if not sheet_name:
            raise ValueError("XLSX workbook has no worksheets")
        root = ET.fromstring(zf.read(sheet_name))
    cells: dict[tuple[int, int], str] = {}
    max_col = 0
    for row_el in root.findall(".//x:sheetData/x:row", _XML_NS):
        row_idx = int(row_el.attrib.get("r") or 0)
        if row_idx <= 0:
            continue
        sequential_col = 0
        for cell_el in row_el.findall("x:c", _XML_NS):
            sequential_col += 1
            ref = cell_el.attrib.get("r", "")
            match = _CELL_RE.match(ref)
            col_idx = _column_index(match.group(1)) if match else sequential_col
            value = _cell_value(cell_el, shared_strings)
            if value:
                cells[(row_idx, col_idx)] = value
                max_col = max(max_col, col_idx)

    row_numbers = sorted({row for row, _ in cells})
    return [[cells.get((row_idx, col_idx), "") for col_idx in range(1, max_col + 1)] for row_idx in row_numbers]


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(".//x:si", _XML_NS):
        strings.append("".join(t.text or "" for t in item.findall(".//x:t", _XML_NS)).strip())
    return strings


def _cell_value(cell_el: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell_el.attrib.get("t", "")
    if cell_type == "inlineStr":
        return " ".join((t.text or "").strip() for t in cell_el.findall(".//x:t", _XML_NS)).strip()
    value_el = cell_el.find("x:v", _XML_NS)
    value = (value_el.text or "").strip() if value_el is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError):
            return value
    return value


def _matrix_to_result(matrix: list[list[str]]) -> dict:
    rows = [_trim_row(row) for row in matrix if any(str(cell).strip() for cell in row)]
    if not rows:
        return {"columns": [], "rows": [], "totals": {}, "metadata": {"raw_row_count": 0}, "output_type": "rows"}
    max_col = max(len(row) for row in rows)
    rows = [row + [""] * (max_col - len(row)) for row in rows]
    first_data_idx = _first_data_row_index(rows)
    detail_idx = _detail_header_index(rows, first_data_idx)
    if detail_idx < 0:
        return {
            "columns": [],
            "rows": [{"value": " | ".join(cell for cell in row if cell)} for row in rows],
            "totals": {},
            "metadata": {"raw_row_count": len(rows), "title": _first_text(rows), "header_detection": "failed"},
            "output_type": "rows",
        }
    group_idx = _group_header_index(rows, detail_idx)
    columns = _build_columns(rows[detail_idx], rows[group_idx] if group_idx >= 0 else None)
    data_rows: list[dict] = []
    totals: dict[str, str] = {}
    for row in rows[first_data_idx:]:
        if _non_empty_count(row) == 0:
            continue
        obj = _row_to_object(row, columns)
        first = normalize_report_query(next((cell for cell in row if cell), ""))
        if first in {"итого", "всего"}:
            totals.update(obj)
            continue
        if obj:
            data_rows.append(obj)
    visible_columns = _prune_unused_columns(columns, data_rows, totals)
    return {
        "columns": visible_columns,
        "rows": data_rows,
        "totals": totals,
        "metadata": {
            "raw_row_count": len(rows),
            "title": _first_text(rows),
            "header_row_index": detail_idx,
            "group_header_row_index": group_idx,
        },
        "output_type": "rows",
    }


def _build_columns(detail_row: list[str], group_row: list[str] | None) -> list[str]:
    group_filled = [""] * len(detail_row)
    if group_row:
        current = ""
        for idx, value in enumerate(group_row[: len(detail_row)]):
            if value:
                current = value
            group_filled[idx] = current
    columns = []
    for idx, detail in enumerate(detail_row):
        group = group_filled[idx] if idx < len(group_filled) else ""
        if detail and group and group != detail:
            columns.append(f"{group} / {detail}")
        elif detail:
            columns.append(detail)
        elif group:
            columns.append(group)
        else:
            columns.append("")
    return _dedupe_columns(columns)


def _row_to_object(row: list[str], columns: list[str]) -> dict[str, str]:
    result = {}
    for idx, column in enumerate(columns):
        if not column or idx >= len(row):
            continue
        value = str(row[idx] or "").strip()
        if value:
            result[column] = value
    return result


def _prune_unused_columns(columns: list[str], rows: list[dict[str, str]], totals: dict[str, str]) -> list[str]:
    visible = [name for name in columns if name]
    if not visible or (not rows and not totals):
        return visible
    used = set()
    for row in rows:
        used.update(key for key, value in row.items() if str(value).strip())
    used.update(key for key, value in totals.items() if str(value).strip())
    return [name for name in visible if name in used]


def _first_data_row_index(rows: list[list[str]]) -> int:
    for idx, row in enumerate(rows):
        if _has_number(row) and not _is_service_row(row):
            return idx
    return len(rows)


def _detail_header_index(rows: list[list[str]], first_data_idx: int) -> int:
    for idx in range(first_data_idx - 1, -1, -1):
        row = rows[idx]
        if _non_empty_count(row) >= 2 and not _has_number(row) and not _is_service_row(row):
            return idx
    return -1


def _group_header_index(rows: list[list[str]], detail_idx: int) -> int:
    if detail_idx <= 0:
        return -1
    candidate = rows[detail_idx - 1]
    if _non_empty_count(candidate) >= 2 and not _has_number(candidate) and not _is_service_row(candidate):
        return detail_idx - 1
    return -1


def _is_service_row(row: list[str]) -> bool:
    joined = normalize_report_query(" ".join(cell for cell in row if cell))
    return bool(joined) and (
        joined.startswith("параметры")
        or joined.startswith("отбор")
        or joined.startswith("период")
        or "период " in joined
    )


def _has_number(row: list[str]) -> bool:
    return any(_NUMBER_RE.match(str(cell).strip()) for cell in row if str(cell).strip())


def _non_empty_count(row: list[str]) -> int:
    return sum(1 for cell in row if str(cell).strip())


def _trim_row(row: list[object]) -> list[str]:
    return [str(cell if cell is not None else "").strip() for cell in row]


def _first_text(rows: list[list[str]]) -> str:
    for row in rows:
        for cell in row:
            if str(cell).strip():
                return str(cell).strip()
    return ""


def _dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for column in columns:
        if not column:
            result.append("")
            continue
        count = seen.get(column, 0) + 1
        seen[column] = count
        result.append(column if count == 1 else f"{column} {count}")
    return result


def _column_index(name: str) -> int:
    value = 0
    for char in name:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


def _parse_range(value: str) -> tuple[int, int, int, int] | None:
    if ":" not in value:
        return None
    left, right = value.split(":", 1)
    left_match = _CELL_RE.match(left)
    right_match = _CELL_RE.match(right)
    if not left_match or not right_match:
        return None
    return (
        int(left_match.group(2)),
        _column_index(left_match.group(1)),
        int(right_match.group(2)),
        _column_index(right_match.group(1)),
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cleanup_file(path: Path) -> str:
    try:
        path.unlink(missing_ok=True)
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return "deleted"
    except OSError as exc:
        return f"cleanup_failed:{exc}"

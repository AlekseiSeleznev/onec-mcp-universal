"""Expected/observed structure contracts for 1C report results."""

from __future__ import annotations

import re
from typing import Any

from .report_catalog import normalize_report_query


_NUMERIC_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_SERVICE_TOKENS = {
    "параметры",
    "период",
    "организация",
    "отбор",
    "по",
    "для",
}
_GENERIC_EXPECTED_TOKENS = {
    "сумма",
    "количество",
    "остаток",
    "итого",
    "процент",
    "значение",
}


def build_declared_output_contract(
    *,
    report_name: str,
    report_title: str,
    variant_key: str,
    variant_title: str,
    kind: str,
    strategies: list[dict],
    template_texts: list[str],
    manager_text: str,
    object_text: str,
    expected_columns_override: list[str] | None = None,
    expected_markers_override: list[str] | None = None,
    expects_detail_rows: bool | None = None,
    output_type_override: str | None = None,
    allows_empty_result: bool = False,
    expects_visual_components: bool = False,
    accepts_blank_output: bool = False,
) -> dict:
    output_type = output_type_override or ("artifact" if kind == "form_or_regulated" else "rows")
    preferred_strategy = str(strategies[0].get("strategy") or "") if strategies else ""
    expected_columns = (
        _unique_nonempty(expected_columns_override or [])
        if expected_columns_override is not None
        else _strategy_expected_columns(strategies) or _extract_expected_columns(template_texts, report_title, variant_title)
    )
    expected_markers = (
        _unique_nonempty(expected_markers_override or [])
        if expected_markers_override is not None
        else _unique_nonempty([report_title, variant_title, *expected_columns[:6]])
    )
    allows_empty_result = bool(allows_empty_result or _supports_empty_report_output(object_text))
    field_roles = [_field_role(field) for field in expected_columns[:12]]
    confidence_score = 0.35
    if output_type == "artifact":
        confidence_score = 0.55
    elif expected_columns:
        confidence_score = 0.82
    elif expected_markers:
        confidence_score = 0.62
    confidence = "low"
    if confidence_score >= 0.75:
        confidence = "high"
    elif confidence_score >= 0.55:
        confidence = "medium"
    return {
        "source": "declared",
        "report_name": report_name,
        "report_title": report_title,
        "variant_key": variant_key,
        "variant_title": variant_title,
        "output_type": output_type,
        "expects_detail_rows": output_type == "rows" if expects_detail_rows is None else bool(expects_detail_rows),
        "expects_artifact": output_type in {"artifact", "mixed"},
        "allows_empty_result": bool(allows_empty_result),
        "expects_visual_components": bool(expects_visual_components),
        "accepts_blank_output": bool(accepts_blank_output),
        "expected_markers": expected_markers,
        "expected_columns": expected_columns,
        "field_roles": field_roles,
        "hierarchy_expected": _looks_hierarchical("\n".join(template_texts) + "\n" + object_text),
        "totals_expected": bool(expected_columns) or "итого" in normalize_report_query("\n".join(template_texts)),
        "preferred_strategy": preferred_strategy,
        "confidence": confidence,
        "confidence_score": round(confidence_score, 3),
        "evidence": {
            "kind": kind,
            "strategy_count": len(strategies),
            "template_text_count": len(template_texts),
            "object_handlers": _present_events(object_text),
            "manager_export_count": manager_text.lower().count("экспорт"),
        },
    }


def build_observed_signature(result: dict[str, Any]) -> dict[str, Any]:
    rows = list(result.get("rows") or [])
    columns = list(result.get("columns") or [])
    output_type = str(result.get("output_type") or "rows")
    artifacts = list(result.get("artifacts") or [])
    header_rows: list[str] = []
    detail_rows: list[dict[str, Any]] = []
    observed_tokens: list[str] = []
    for value in columns:
        cleaned = str(value).strip()
        if not cleaned:
            continue
        observed_tokens.append(cleaned)
        if " / " in cleaned:
            observed_tokens.append(cleaned.rsplit(" / ", 1)[-1].strip())
    max_nonempty = 0
    has_totals = False
    has_hierarchy = False
    column_header_seen = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        values = [str(value).strip() for value in row.values() if str(value).strip()]
        if not values:
            continue
        observed_tokens.extend(values)
        max_nonempty = max(max_nonempty, len(values))
        joined = " | ".join(values)
        is_total = _looks_like_total(values)
        if is_total:
            has_totals = True
        if _looks_hierarchical(joined):
            has_hierarchy = True
        if _is_service_row(values):
            if len(header_rows) < 8:
                header_rows.append(joined)
        elif is_total:
            header_rows.append(joined)
        elif _looks_like_column_header(values):
            if column_header_seen:
                detail_rows.append(row)
            else:
                header_rows.append(joined)
                column_header_seen = True
        elif _is_detail_row(values):
            detail_rows.append(row)
        elif len(header_rows) < 8:
            header_rows.append(joined)
    return {
        "output_type": output_type,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "header_rows": header_rows,
        "detail_rows_count": len(detail_rows),
        "detail_sample": detail_rows[:5],
        "detail_column_count": max((_nonempty_values_count(row) for row in detail_rows), default=0),
        "max_nonempty_cells": max_nonempty,
        "has_totals": has_totals,
        "has_hierarchy": has_hierarchy,
        "artifacts_count": len(artifacts),
        "warnings": list(result.get("warnings") or []),
        "observed_tokens": _unique_nonempty(observed_tokens[:80]),
        "observed_tokens_norm": [normalize_report_query(item) for item in _unique_nonempty(observed_tokens[:80])],
        "metadata": dict(result.get("metadata") or {}),
    }


def build_verified_output_contract(observed: dict[str, Any], *, strategy_name: str = "") -> dict[str, Any]:
    expected_columns: list[str] = []
    header_rows = [str(row or "") for row in observed.get("header_rows") or []]
    for header_row in header_rows:
        if " | " not in header_row:
            continue
        parts = [part.strip() for part in header_row.split(" | ") if part.strip()]
        if len(parts) < 2:
            continue
        normalized = [normalize_report_query(part) for part in parts]
        if normalized[0] in {"параметры", "отбор"}:
            continue
        if any("итого" in part for part in normalized):
            continue
        if any(_NUMERIC_RE.match(part.replace(" ", "").replace("\xa0", "")) for part in parts):
            continue
        expected_columns = parts
        break
    if not expected_columns:
        expected_columns = _meaningful_observed_columns(observed.get("columns") or [])
    if not expected_columns:
        detail_sample = list(observed.get("detail_sample") or [])
        if detail_sample:
            first = detail_sample[0]
            if isinstance(first, dict):
                expected_columns = [str(value).strip() for value in first.values() if str(value).strip()]
    return {
        "source": "verified",
        "output_type": str(observed.get("output_type") or "rows"),
        "expects_detail_rows": bool(observed.get("detail_rows_count")),
        "expects_artifact": str(observed.get("output_type") or "rows") in {"artifact", "mixed"},
        "expected_markers": list(observed.get("header_rows") or [])[:6],
        "expected_columns": expected_columns[:12],
        "field_roles": [_field_role(field) for field in expected_columns[:12]],
        "hierarchy_expected": bool(observed.get("has_hierarchy")),
        "totals_expected": bool(observed.get("has_totals")),
        "preferred_strategy": strategy_name,
        "confidence": "high",
        "confidence_score": 0.99,
        "evidence": {
            "detail_rows_count": int(observed.get("detail_rows_count") or 0),
            "detail_column_count": int(observed.get("detail_column_count") or 0),
            "artifacts_count": int(observed.get("artifacts_count") or 0),
        },
    }


def _meaningful_observed_columns(columns: list[Any]) -> list[str]:
    result: list[str] = []
    for value in columns:
        text = str(value or "").strip()
        normalized = normalize_report_query(text)
        if not text or not normalized:
            continue
        if re.fullmatch(r"c\d+", normalized):
            continue
        if _NUMERIC_RE.match(text.replace(" ", "").replace("\xa0", "")):
            continue
        result.append(text)
    return result if len(result) >= 2 else []


def compare_output_contract(expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    expected_output = str(expected.get("output_type") or "unknown")
    observed_output = str(observed.get("output_type") or "unknown")
    if expected_output not in {"unknown", "", observed_output, "mixed"}:
        code = "artifact_instead_of_rows" if expected_output == "rows" and observed_output == "artifact" else "wrong_output_type"
        return {"matched": False, "mismatch_code": code, "acceptable_with_verified": False, "score": 0.0}
    if (
        expected.get("accepts_blank_output")
        and int(observed.get("row_count") or 0) == 0
        and int(observed.get("column_count") or 0) == 0
        and not list(observed.get("header_rows") or [])
        and int(observed.get("artifacts_count") or 0) == 0
    ):
        return {
            "matched": True,
            "mismatch_code": "",
            "acceptable_with_verified": False,
            "score": 0.6,
            "empty_result": True,
            "blank_output": True,
        }

    expected_columns = [normalize_report_query(item) for item in expected.get("expected_columns") or [] if normalize_report_query(item)]
    observed_tokens_norm = [str(item or "") for item in observed.get("observed_tokens_norm") or [] if str(item or "")]
    observed_tokens = set(observed_tokens_norm)
    marker_coverage = _marker_coverage(expected.get("expected_markers") or [], observed_tokens_norm)
    drawing_count = int((observed.get("metadata") or {}).get("drawing_count") or 0)
    if (
        expected.get("expects_visual_components")
        and not expected.get("expects_detail_rows")
        and drawing_count > 0
    ):
        title_coverage = _marker_coverage(list(expected.get("expected_markers") or [])[:2], observed_tokens_norm)
        if title_coverage > 0:
            return {
                "matched": True,
                "mismatch_code": "",
                "acceptable_with_verified": False,
                "score": max(0.5, marker_coverage, title_coverage),
                "visual_result": True,
            }
    if expected.get("expects_detail_rows") and int(observed.get("detail_rows_count") or 0) <= 0:
        if int(observed.get("row_count") or 0) == 0 and expected_columns:
            matched_columns = [item for item in expected_columns if _column_is_observed(item, observed_tokens_norm)]
            coverage = len(matched_columns) / max(1, len(expected_columns))
            if coverage >= 0.66 and int(observed.get("column_count") or 0) > 0:
                return {
                    "matched": True,
                    "mismatch_code": "",
                    "acceptable_with_verified": False,
                    "score": coverage,
                    "matched_columns": matched_columns,
                    "empty_result": True,
                }
        if expected.get("allows_empty_result"):
            title_coverage = _marker_coverage(list(expected.get("expected_markers") or [])[:1], observed_tokens_norm)
            if (
                title_coverage > 0
                and int(observed.get("row_count") or 0) <= 4
                and int(observed.get("column_count") or 0) <= 2
                and int(observed.get("max_nonempty_cells") or 0) <= 1
            ):
                return {
                    "matched": True,
                    "mismatch_code": "",
                    "acceptable_with_verified": False,
                    "score": max(0.25, title_coverage),
                    "empty_result": True,
                    "header_only_empty": True,
                }
        if expected.get("allows_empty_result") and marker_coverage >= 0.34:
            if not expected.get("expects_visual_components") or drawing_count > 0:
                return {
                    "matched": True,
                    "mismatch_code": "",
                    "acceptable_with_verified": False,
                    "score": max(0.34, marker_coverage),
                    "empty_result": True,
                }
        code = "header_only" if int(observed.get("row_count") or 0) > 0 else "missing_detail_rows"
        return {"matched": False, "mismatch_code": code, "acceptable_with_verified": False, "score": 0.1}
    technical_ratio = _technical_expected_ratio(expected.get("expected_columns") or [])
    if expected_columns:
        matched_columns = [item for item in expected_columns if _column_is_observed(item, observed_tokens_norm)]
        coverage = len(matched_columns) / max(1, len(expected_columns))
        confidence_score = float(expected.get("confidence_score") or 0)
        generic_ratio = _generic_expected_ratio(expected.get("expected_columns") or [])
        if coverage <= 0:
            if (
                confidence_score < 0.55
                or technical_ratio >= 0.5
                or (
                    generic_ratio >= 0.5
                    and marker_coverage > 0
                    and int(observed.get("detail_rows_count") or 0) > 0
                )
            ):
                return {
                    "matched": False,
                    "mismatch_code": "weak_declared_contract",
                    "acceptable_with_verified": True,
                    "score": coverage,
                    "matched_columns": matched_columns,
                }
            return {
                "matched": False,
                "mismatch_code": "missing_expected_columns",
                "acceptable_with_verified": False,
                "score": coverage,
                "matched_columns": matched_columns,
            }
        if coverage < 0.34 and confidence_score >= 0.75:
            if (
                (expected.get("hierarchy_expected") or observed.get("has_hierarchy"))
                and int(observed.get("detail_rows_count") or 0) > 0
                and len(matched_columns) >= 2
            ):
                return {
                    "matched": False,
                    "mismatch_code": "weak_declared_contract",
                    "acceptable_with_verified": True,
                    "score": coverage,
                    "matched_columns": matched_columns,
                }
            if technical_ratio >= 0.5:
                return {
                    "matched": False,
                    "mismatch_code": "weak_declared_contract",
                    "acceptable_with_verified": True,
                    "score": coverage,
                    "matched_columns": matched_columns,
                }
            return {
                "matched": False,
                "mismatch_code": "semantic_mismatch",
                "acceptable_with_verified": False,
                "score": coverage,
                "matched_columns": matched_columns,
            }
    elif expected.get("expected_markers"):
        confidence_score = float(expected.get("confidence_score") or 0)
        if marker_coverage <= 0:
            return {
                "matched": False,
                "mismatch_code": "semantic_mismatch" if confidence_score >= 0.75 else "weak_declared_contract",
                "acceptable_with_verified": confidence_score < 0.55,
                "score": marker_coverage,
            }
        if marker_coverage < 0.34 and confidence_score >= 0.75:
            return {
                "matched": False,
                "mismatch_code": "semantic_mismatch",
                "acceptable_with_verified": False,
                "score": marker_coverage,
            }
    return {"matched": True, "mismatch_code": "", "acceptable_with_verified": False, "score": 1.0}


def _extract_expected_columns(template_texts: list[str], report_title: str, variant_title: str) -> list[str]:
    blacklist = {
        normalize_report_query(report_title),
        normalize_report_query(variant_title),
        normalize_report_query("основная схема компоновки данных"),
    }
    scored: list[tuple[int, str]] = []
    for text in template_texts:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            continue
        if len(cleaned) > 48 or len(cleaned) < 3:
            continue
        normalized = normalize_report_query(cleaned)
        if not normalized or normalized in blacklist or normalized in _SERVICE_TOKENS:
            continue
        if normalized.startswith("параметры ") or normalized.startswith("отбор "):
            continue
        scored.append((_candidate_priority(cleaned, normalized), cleaned))
    scored.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    return _unique_nonempty([item[1] for item in scored])[:12]


def _strategy_expected_columns(strategies: list[dict]) -> list[str]:
    for strategy in strategies:
        details = strategy.get("details") if isinstance(strategy.get("details"), dict) else {}
        selected_fields = list(details.get("selected_fields") or [])
        field_titles = dict(details.get("field_titles") or {})
        if not selected_fields:
            continue
        columns = [str(field_titles.get(field) or field).strip() for field in selected_fields if str(field_titles.get(field) or field).strip()]
        if columns:
            return _unique_nonempty(columns)[:12]
    return []


def _field_role(field: str) -> dict[str, str]:
    normalized = normalize_report_query(field)
    role = "group"
    if any(token in normalized for token in ("стоим", "сумм", "колич", "процент", "остаток", "себестоим")):
        role = "resource"
    elif any(token in normalized for token in ("итого", "итог")):
        role = "total"
    elif any(token in normalized for token in ("организац", "материал", "номенклат", "контрагент", "сотрудник", "склад", "подраздел")):
        role = "dimension"
    return {"name": field, "role": role, "confidence": "medium"}


def _looks_like_total(values: list[str]) -> bool:
    return any("итог" in normalize_report_query(value) for value in values)


def _is_detail_row(values: list[str]) -> bool:
    if any(_NUMERIC_RE.match(value.replace(" ", "")) for value in values):
        return True
    return False


def _is_service_row(values: list[str]) -> bool:
    normalized = [normalize_report_query(value) for value in values if str(value).strip()]
    if not normalized:
        return False
    first = normalized[0]
    if first in {"параметры", "отбор", "период"}:
        return True
    joined = " ".join(normalized)
    return joined.startswith("только ") and "остатк" in joined


def _looks_like_column_header(values: list[str]) -> bool:
    if len(values) < 2:
        return False
    if any(_NUMERIC_RE.match(value.replace(" ", "")) for value in values):
        return False
    return all(len(value) <= 40 for value in values)


def _looks_hierarchical(text: str) -> bool:
    normalized = normalize_report_query(text)
    return any(token in normalized for token in ("иерарх", "групп", "вложен", "подчин"))


def _present_events(object_text: str) -> list[str]:
    result = []
    for name in (
        "ПриКомпоновкеРезультата",
        "ПередЗагрузкойНастроекВКомпоновщик",
        "ОпределитьНастройкиФормы",
    ):
        if name.lower() in (object_text or "").lower():
            result.append(name)
    return result


def _nonempty_values_count(row: dict[str, Any]) -> int:
    return len([value for value in row.values() if str(value).strip()])


def _unique_nonempty(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if not cleaned or cleaned in seen:
            continue
        result.append(cleaned)
        seen.add(cleaned)
    return result


def _candidate_priority(raw: str, normalized: str) -> int:
    score = 0
    if " " in raw or "." in raw:
        score += 3
    if "статья" in normalized:
        score += 10
    if "затрат" in normalized or "стоим" in normalized or "колич" in normalized:
        score += 9
    if "процент" in normalized:
        score += 6
    if any(token in normalized for token in ("материал", "номенклат", "организац", "контрагент", "сотрудник")):
        score += 5
    if "ед изм" in normalized:
        score += 2
    if _looks_technical_camel(raw):
        score -= 6
    if "." in raw:
        score -= 4
    if "%" in raw:
        score -= 4
    if any(char.isdigit() for char in raw):
        score -= 3
    if normalized.startswith(("сумма ", "среднее ", "максимум ", "минимум ")):
        score -= 4
    if normalized.startswith(("источник данных", "аналитика", "сегмент", "подразделение", "заказ на производство")):
        score -= 2
    return score


def _looks_technical_camel(value: str) -> bool:
    return bool(re.search(r"(?<=[а-яёa-z])(?=[А-ЯЁA-Z])", value))


def _technical_expected_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    flagged = 0
    for value in values:
        raw = str(value or "")
        normalized = normalize_report_query(raw)
        if (
            _looks_technical_camel(raw)
            or "." in raw
            or "%" in raw
            or any(char.isdigit() for char in raw)
            or normalized.startswith(("сумма ", "среднее ", "максимум ", "минимум "))
        ):
            flagged += 1
            continue
        if normalized.startswith(("источник данных", "аналитика", "сегмент", "подразделение", "заказ на производство")):
            flagged += 1
    return flagged / max(1, len(values))


def _generic_expected_ratio(values: list[str]) -> float:
    if not values:
        return 0.0
    generic = 0
    for value in values:
        normalized = normalize_report_query(str(value or ""))
        if not normalized:
            continue
        if normalized in _GENERIC_EXPECTED_TOKENS:
            generic += 1
            continue
        if any(normalized.startswith(token + " ") for token in ("сумма", "количество", "остаток", "процент")):
            generic += 1
    return generic / max(1, len(values))


def _column_is_observed(expected: str, observed_tokens: list[str]) -> bool:
    if not expected:
        return False
    for observed in observed_tokens:
        if expected == observed:
            return True
        if len(expected) >= 8 and expected in observed:
            return True
        if len(observed) >= 8 and observed in expected:
            return True
        expected_words = {word for word in expected.split() if len(word) >= 4}
        observed_words = {word for word in observed.split() if len(word) >= 4}
        if len(expected_words) >= 2 and len(expected_words & observed_words) >= 2:
            return True
    return False


def _marker_coverage(expected_markers: list[str], observed_tokens: list[str]) -> float:
    markers = [normalize_report_query(item) for item in expected_markers or [] if normalize_report_query(item)]
    if not markers:
        return 0.0
    matched = [marker for marker in markers if _column_is_observed(marker, observed_tokens)]
    return len(matched) / max(1, len(markers))


def _supports_empty_report_output(object_text: str) -> bool:
    lowered = (object_text or "").lower()
    return "отчетпустой(" in lowered or "отчетысервер.отчетпустой(" in lowered

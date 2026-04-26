"""Documentation enrichment for cataloged 1C reports."""

from __future__ import annotations

import json
import re


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_report_doc_query(database: str, report: dict) -> str:
    title = str(report.get("title") or "")
    report_name = str(report.get("report") or "")
    variant = str(report.get("variant") or "")
    return (
        "Найди в ИТС и 1С:Напарник пользовательское описание отчета 1С для конкретной конфигурации.\n"
        "Нужно помочь бухгалтеру найти и запустить отчет по человеческому названию, а не по техническому имени.\n"
        f"База/конфигурация: {database}\n"
        f"Пользовательское название из конфигурации: {title}\n"
        f"Техническое имя: Отчет.{report_name}\n"
        f"Вариант: {variant}\n"
        "Верни JSON без пояснений: "
        '{"title":"...","aliases":["..."],"summary":"...","parameters":["..."],"source_urls":["..."],"confidence":0.0}'
    )


def parse_report_doc_response(content: str, fallback_title: str = "") -> dict:
    parsed = _parse_json_object(content)
    if parsed is None:
        return {
            "title": fallback_title,
            "aliases": _extract_alias_lines(content),
            "summary": _short_summary(content),
            "source_urls": _extract_urls(content),
            "confidence": 0.65,
        }
    aliases = parsed.get("aliases") if isinstance(parsed.get("aliases"), list) else []
    source_urls = parsed.get("source_urls") if isinstance(parsed.get("source_urls"), list) else []
    confidence = parsed.get("confidence", 0.75)
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.75
    return {
        "title": str(parsed.get("title") or fallback_title or "").strip(),
        "aliases": [str(alias).strip() for alias in aliases if str(alias).strip()],
        "summary": str(parsed.get("summary") or _short_summary(content)).strip(),
        "parameters": [str(item).strip() for item in parsed.get("parameters") or [] if str(item).strip()],
        "source_urls": [str(url).strip() for url in source_urls if str(url).strip()],
        "confidence": max(0.0, min(1.0, confidence_value)),
    }


def _parse_json_object(content: str) -> dict | None:
    match = _JSON_BLOCK_RE.search(content or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _extract_alias_lines(content: str) -> list[str]:
    aliases: list[str] = []
    for line in (content or "").splitlines():
        lowered = line.lower()
        if "синоним" not in lowered and "называ" not in lowered and "также" not in lowered:
            continue
        aliases.extend(part.strip(" -—:;,.\"'") for part in re.split(r"[,;]", line) if part.strip())
    return aliases[:8]


def _extract_urls(content: str) -> list[str]:
    return re.findall(r"https?://[^\s)>\"]+", content or "")[:8]


def _short_summary(content: str) -> str:
    text = " ".join((content or "").split())
    return text[:500]

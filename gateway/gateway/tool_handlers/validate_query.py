"""Handler for validate_query MCP tool."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Protocol

log = logging.getLogger(__name__)

_SERVER_SYNTAX_ERROR_MARKERS = (
    "синтаксическ",
    "syntax error",
    "ошибка синтакс",
    "недопустимый",
    "unexpected token",
    "parse error",
)


class ToolkitLike(Protocol):
    """Minimal toolkit shape used by server-side query validation."""

    async def call_tool(self, name: str, arguments: dict): ...


def validate_query_static(query: str) -> tuple[bool, list[str], list[str]]:
    """Run static query checks without server interaction."""
    stripped = query.strip()
    if not stripped:
        return False, ["Запрос пуст"], []

    errors: list[str] = []
    warnings: list[str] = []

    clean = re.sub(r"//[^\n]*", "", stripped)
    upper = clean.upper()

    if "ВЫБРАТЬ" not in upper:
        errors.append("В запросе отсутствует ключевое слово ВЫБРАТЬ")

    depth = 0
    i = 0
    while i < len(clean):
        char = clean[i]
        if char == '"':
            i += 1
            while i < len(clean) and clean[i] != '"':
                i += 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                errors.append("Лишняя закрывающая скобка ')'")
                depth = 0
        i += 1

    if depth > 0:
        errors.append(f"Несбалансированные скобки: {depth} незакрытых '('")

    vt_pattern = r"\.(Остатки|ОстаткиИОбороты|Обороты|СрезПоследних|СрезПервых)\s*\)"
    if re.search(vt_pattern, clean, re.IGNORECASE) and "ГДЕ" in upper:
        warnings.append(
            "Параметры виртуальной таблицы могут быть в ГДЕ вместо скобок — "
            "это снижает производительность. Фильтруйте внутри .Остатки(...)"
        )

    if re.search(r"ВЫБРАТЬ\s+(РАЗЛИЧНЫЕ\s+)?(ПЕРВЫЕ\s+\d+\s+)?\*", upper, re.DOTALL):
        warnings.append("Рекомендуется выбирать конкретные поля вместо *")

    return len(errors) == 0, errors, warnings


def add_limit_zero(query: str) -> str:
    """Insert or override TOP clause to avoid data retrieval during server validation."""
    match = re.search(r"\bВЫБРАТЬ\b", query, re.IGNORECASE)
    if not match:
        return query

    pos = match.end()
    tail = query[pos:]

    diff_match = re.match(r"(\s+РАЗЛИЧНЫЕ)\b", tail, re.IGNORECASE)
    if diff_match:
        pos += diff_match.end()
        tail = query[pos:]

    first_match = re.match(r"(\s+ПЕРВЫЕ\s+)\d+", tail, re.IGNORECASE)
    if first_match:
        return query[:pos] + first_match.group(1) + "0" + tail[first_match.end() :]
    return query[:pos] + " ПЕРВЫЕ 0" + tail


async def validate_query(
    query: str,
    get_active: Callable[[], object | None],
    get_toolkit: Callable[[], ToolkitLike | None],
) -> str:
    """Validate query statically and on server when active session/toolkit are available."""
    valid, errors, warnings = validate_query_static(query)
    result: dict = {}

    if errors:
        result["valid"] = False
        result["errors"] = errors
        if warnings:
            result["warnings"] = warnings
        return json.dumps(result, ensure_ascii=False, indent=2)

    try:
        if get_active():
            toolkit = get_toolkit()
            if toolkit:
                limited_query = add_limit_zero(query)
                call_result = await toolkit.call_tool("execute_query", {"query": limited_query})
                response_text = call_result.content[0].text if call_result.content else ""
                low = response_text.lower()

                if any(marker in low for marker in _SERVER_SYNTAX_ERROR_MARKERS):
                    result["valid"] = False
                    result["errors"] = [f"Ошибка синтаксиса от сервера 1С: {response_text[:600]}"]
                else:
                    result["valid"] = True
                    result["source"] = "server"
                    result["message"] = "Запрос проверен на сервере 1С — синтаксис корректен"

                if warnings:
                    result["warnings"] = warnings
                return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.warning(f"Server-side query validation failed: {exc}")

    result["valid"] = True
    result["source"] = "static"
    result["message"] = "Статическая проверка пройдена (база данных не подключена)"
    if warnings:
        result["warnings"] = warnings
    return json.dumps(result, ensure_ascii=False, indent=2)

from __future__ import annotations

import json

from gateway.report_docs import build_report_doc_query, parse_report_doc_response


def test_build_report_doc_query_contains_configuration_and_report_identity():
    query = build_report_doc_query(
        "Z01",
        {"title": "Расчетный листок", "report": "АнализНачисленийИУдержаний", "variant": "РасчетныйЛисток"},
    )

    assert "База/конфигурация: Z01" in query
    assert "Отчет.АнализНачисленийИУдержаний" in query
    assert "РасчетныйЛисток" in query
    assert "JSON" in query


def test_parse_report_doc_response_reads_json_and_clamps_confidence():
    parsed = parse_report_doc_response(
        "```json\n"
        + json.dumps(
            {
                "title": "Расчетный листок",
                "aliases": [" расчетка ", ""],
                "summary": "Описание",
                "parameters": ["Сотрудник", ""],
                "source_urls": ["https://its.1c.ru/db/hr"],
                "confidence": 2,
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    fallback_confidence = parse_report_doc_response('{"title":"X","confidence":"bad"}')

    assert parsed["title"] == "Расчетный листок"
    assert parsed["aliases"] == ["расчетка"]
    assert parsed["parameters"] == ["Сотрудник"]
    assert parsed["source_urls"] == ["https://its.1c.ru/db/hr"]
    assert parsed["confidence"] == 1.0
    assert fallback_confidence["confidence"] == 0.75


def test_parse_report_doc_response_falls_back_to_prose_aliases_urls_and_summary():
    content = """
    Отчет также называют: расчетка сотрудника, листок по зарплате.
    Подробности: https://its.1c.ru/db/example)
    """ + "x" * 600

    parsed = parse_report_doc_response(content, fallback_title="Расчетный листок")
    invalid_json = parse_report_doc_response("{bad json}", fallback_title="Fallback")

    assert parsed["title"] == "Расчетный листок"
    assert "расчетка сотрудника" in parsed["aliases"][0]
    assert parsed["source_urls"] == ["https://its.1c.ru/db/example"]
    assert len(parsed["summary"]) == 500
    assert invalid_json["title"] == "Fallback"

"""Tests for PII anonymizer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.anonymizer import Anonymizer


def test_disabled_by_default():
    a = Anonymizer()
    assert not a.enabled
    assert a.anonymize_text("Иванов Иван Иванович") == "Иванов Иван Иванович"


def test_enable_disable():
    a = Anonymizer()
    a.enable()
    assert a.enabled
    a.disable()
    assert not a.enabled


def test_fio_replacement():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("Сотрудник: Петров Сергей Александрович работает")
    assert "Петров" not in result
    assert "Сергей" not in result
    assert "Александрович" not in result
    assert "Сотрудник:" in result
    assert "работает" in result


def test_fio_stable_mapping():
    a = Anonymizer()
    a.enable()
    r1 = a.anonymize_text("Петров Сергей Александрович")
    r2 = a.anonymize_text("Петров Сергей Александрович")
    assert r1 == r2  # same input → same output


def test_inn_10_digits():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("ИНН: 7707083893")
    assert "7707083893" not in result
    assert "ИНН:" in result


def test_inn_12_digits():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("ИНН физлица: 550108153953")
    assert "550108153953" not in result


def test_snils():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("СНИЛС: 123-456-789 01")
    assert "123-456-789 01" not in result


def test_phone():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("Телефон: +7 (916) 123-45-67")
    assert "916" not in result
    assert "123-45-67" not in result


def test_email():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("Email: ivan@company.ru")
    assert "ivan@company.ru" not in result
    assert "@example.com" in result


def test_company_name():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text('Поставщик: ООО "Ромашка и Компания"')
    assert "Ромашка" not in result
    assert "ООО" in result


def test_json_anonymization():
    a = Anonymizer()
    a.enable()
    data = {
        "name": "Иванов Иван Иванович",
        "inn": "7707083893",
        "items": [{"contact": "test@mail.ru"}],
    }
    result = a.anonymize_json(data)
    assert "Иванов" not in result["name"]
    assert "7707083893" not in result["inn"]
    assert "test@mail.ru" not in result["items"][0]["contact"]


def test_process_tool_response_only_data_tools():
    a = Anonymizer()
    a.enable()
    # Non-data tool should not be anonymized
    text = '{"name": "Иванов Иван Иванович"}'
    assert a.process_tool_response("get_metadata", text) == text
    # Data tool should be anonymized
    result = a.process_tool_response("execute_query", text)
    assert "Иванов" not in result

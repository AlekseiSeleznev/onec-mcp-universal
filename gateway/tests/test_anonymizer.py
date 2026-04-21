"""Tests for PII anonymizer."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.anonymizer import Anonymizer, _pick


def test_disabled_by_default():
    a = Anonymizer()
    assert not a.enabled
    assert a.anonymize_text("Иванов Иван Иванович") == "Иванов Иван Иванович"


def test_enable_disable():
    a = Anonymizer()
    assert "включена" in a.enable()
    assert a.enabled
    assert "выключена" in a.disable()
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


def test_fio_replacement_never_keeps_same_components_from_pool():
    a = Anonymizer(salt="shared-salt")
    a.enable()

    result = a.anonymize_text("Иванов Иван Иванович")

    assert "Иванов" not in result
    assert " Иван " not in f" {result} "
    assert "Иванович" not in result


def test_explicit_salt_keeps_mapping_stable_across_instances():
    a1 = Anonymizer(salt="shared-salt")
    a2 = Anonymizer(salt="shared-salt")
    a1.enable()
    a2.enable()

    assert a1.anonymize_text("Петров Сергей Александрович") == a2.anonymize_text("Петров Сергей Александрович")


def test_different_explicit_salts_change_mapping():
    a1 = Anonymizer(salt="salt-one")
    a2 = Anonymizer(salt="salt-two")
    a1.enable()
    a2.enable()

    assert a1.anonymize_text("Петров Сергей Александрович") != a2.anonymize_text("Петров Сергей Александрович")


def test_default_salt_is_not_shared_between_instances():
    a1 = Anonymizer()
    a2 = Anonymizer()

    assert a1._salt != a2._salt


def test_pick_skips_forbidden_exact_match(monkeypatch):
    monkeypatch.setattr("gateway.anonymizer._stable_hash", lambda value, salt="": 0)

    result = _pick(["Иванов", "Петров"], "seed", forbidden="Иванов")

    assert result == "Петров"


def test_pick_skips_forbidden_initial(monkeypatch):
    monkeypatch.setattr("gateway.anonymizer._stable_hash", lambda value, salt="": 0)

    result = _pick(["Александр", "Борис"], "seed", forbidden_initial="А")

    assert result == "Борис"


def test_pick_falls_back_to_first_entry_when_everything_is_forbidden(monkeypatch):
    monkeypatch.setattr("gateway.anonymizer._stable_hash", lambda value, salt="": 0)

    result = _pick(["Иванов"], "seed", forbidden="Иванов")

    assert result == "Иванов"


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
    assert result == a.anonymize_text("ИНН физлица: 550108153953")


def test_snils():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("СНИЛС: 123-456-789 01")
    assert "123-456-789 01" not in result
    assert result == a.anonymize_text("СНИЛС: 123-456-789 01")


def test_phone():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("Телефон: +7 (916) 123-45-67")
    assert "916" not in result
    assert "123-45-67" not in result
    assert result == a.anonymize_text("Телефон: +7 (916) 123-45-67")


def test_email():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text("Email: ivan@company.ru")
    assert "ivan@company.ru" not in result
    assert "@example.com" in result
    assert result == a.anonymize_text("Email: ivan@company.ru")


def test_company_name():
    a = Anonymizer()
    a.enable()
    result = a.anonymize_text('Поставщик: ООО "Ромашка и Компания"')
    assert "Ромашка" not in result
    assert "ООО" in result
    assert result == a.anonymize_text('Поставщик: ООО "Ромашка и Компания"')


def test_short_fio_replacement_and_cache():
    a = Anonymizer()
    a.enable()
    text = "Ответственный: Петров С.А."
    result = a.anonymize_text(text)
    assert "Петров С.А." not in result
    assert result == a.anonymize_text(text)


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


def test_process_tool_response_non_json_falls_back_to_text():
    a = Anonymizer()
    a.enable()
    result = a.process_tool_response("execute_query", "Контакт: Иванов Иван Иванович")
    assert "Иванов Иван Иванович" not in result


def test_process_tool_response_type_error_falls_back_to_text(monkeypatch):
    a = Anonymizer()
    a.enable()

    def _raise_type_error(_text):
        raise TypeError("bad payload")

    monkeypatch.setattr(json, "loads", _raise_type_error)
    result = a.process_tool_response("execute_query", "Контакт: ivan@company.ru")
    assert "@example.com" in result


def test_anonymize_json_returns_scalars_unchanged():
    a = Anonymizer()
    a.enable()
    assert a.anonymize_json(42) == 42
    assert a.anonymize_json(None) is None


def test_anonymize_json_returns_original_when_disabled():
    a = Anonymizer()
    payload = {"name": "Иванов Иван Иванович"}
    assert a.anonymize_json(payload) is payload

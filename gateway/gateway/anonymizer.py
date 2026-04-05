"""
PII anonymization for 1C query results.
Masks personal data (FIO, INN, SNILS, phones, emails) with stable hash-based replacements.
Enabled/disabled via MCP tool at runtime.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

# --- Fake data pools for stable replacement ---

_LAST_NAMES = [
    "Иванов", "Петров", "Сидоров", "Козлов", "Новиков", "Морозов", "Волков",
    "Соколов", "Лебедев", "Кузнецов", "Попов", "Смирнов", "Васильев", "Павлов",
    "Семёнов", "Голубев", "Виноградов", "Богданов", "Воробьёв", "Фёдоров",
]
_FIRST_NAMES = [
    "Александр", "Дмитрий", "Сергей", "Андрей", "Алексей", "Михаил", "Николай",
    "Владимир", "Евгений", "Олег", "Виктор", "Игорь", "Максим", "Артём", "Павел",
    "Роман", "Илья", "Денис", "Кирилл", "Тимофей",
]
_MIDDLE_NAMES = [
    "Александрович", "Дмитриевич", "Сергеевич", "Андреевич", "Алексеевич",
    "Михайлович", "Николаевич", "Владимирович", "Евгеньевич", "Олегович",
    "Викторович", "Игоревич", "Максимович", "Артёмович", "Павлович",
    "Романович", "Ильич", "Денисович", "Кириллович", "Тимофеевич",
]
_COMPANY_PREFIXES = [
    "Альфа", "Бета", "Гамма", "Дельта", "Сигма", "Омега", "Вектор",
    "Спектр", "Импульс", "Горизонт", "Прогресс", "Квант", "Формат",
    "Стандарт", "Базис", "Модуль", "Атлас", "Орион", "Титан", "Каскад",
]


def _stable_hash(value: str, salt: str = "") -> int:
    """Deterministic hash for stable replacement mapping."""
    h = hashlib.sha256((salt + value).encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _pick(pool: list[str], value: str, salt: str = "") -> str:
    return pool[_stable_hash(value, salt) % len(pool)]


# --- Pattern matchers ---

# ИНН: 10 or 12 digits
_INN_RE = re.compile(r'\b(\d{10}|\d{12})\b')
# СНИЛС: XXX-XXX-XXX XX or 11 digits
_SNILS_RE = re.compile(r'\b(\d{3}-\d{3}-\d{3}\s?\d{2}|\d{11})\b')
# Phone: +7XXXXXXXXXX or 8XXXXXXXXXX variants
_PHONE_RE = re.compile(r'(\+7|8)[\s(-]*(\d[\s()-]*){10}')
# Email
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
# FIO-like: 2-3 capitalized Russian words in a row (Фамилия Имя Отчество)
_FIO_RE = re.compile(r'([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ][а-яё]{1,20})\s+([А-ЯЁ][а-яё]{1,30})')
# Short FIO: Фамилия И.О.
_FIO_SHORT_RE = re.compile(r'([А-ЯЁ][а-яё]{1,30})\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.')


class Anonymizer:
    """Stateful anonymizer with stable mapping per gateway session."""

    def __init__(self) -> None:
        self.enabled: bool = False
        self._salt = "onec-mcp-anon"
        self._cache: dict[str, str] = {}  # original → replacement

    def enable(self) -> str:
        self.enabled = True
        self._cache.clear()
        return "Анонимизация включена. Персональные данные в ответах будут маскироваться."

    def disable(self) -> str:
        self.enabled = False
        self._cache.clear()
        return "Анонимизация выключена. Ответы содержат реальные данные."

    def _replace_inn(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        h = _stable_hash(original, self._salt)
        if len(original) == 12:
            fake = f"{(h % 900000000000) + 100000000000:012d}"
        else:
            fake = f"{(h % 9000000000) + 1000000000:010d}"
        self._cache[original] = fake
        return fake

    def _replace_snils(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        h = _stable_hash(original, self._salt)
        digits = f"{(h % 90000000000) + 10000000000:011d}"
        fake = f"{digits[:3]}-{digits[3:6]}-{digits[6:9]} {digits[9:11]}"
        self._cache[original] = fake
        return fake

    def _replace_phone(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        h = _stable_hash(original, self._salt)
        fake = f"+7{(h % 9000000000) + 1000000000:010d}"
        self._cache[original] = fake
        return fake

    def _replace_email(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        h = _stable_hash(original, self._salt)
        fake = f"user{h % 10000}@example.com"
        self._cache[original] = fake
        return fake

    def _replace_fio(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        fake = (
            f"{_pick(_LAST_NAMES, original, 'l')} "
            f"{_pick(_FIRST_NAMES, original, 'f')} "
            f"{_pick(_MIDDLE_NAMES, original, 'm')}"
        )
        self._cache[original] = fake
        return fake

    def _replace_fio_short(self, match: re.Match) -> str:
        original = match.group(0)
        if original in self._cache:
            return self._cache[original]
        ln = _pick(_LAST_NAMES, original, 'l')
        fn = _pick(_FIRST_NAMES, original, 'f')
        mn = _pick(_MIDDLE_NAMES, original, 'm')
        fake = f"{ln} {fn[0]}.{mn[0]}."
        self._cache[original] = fake
        return fake

    def _replace_company(self, text: str) -> str:
        """Replace ООО/ЗАО/ОАО/АО/ИП company names."""
        def _repl(m: re.Match) -> str:
            original = m.group(0)
            if original in self._cache:
                return self._cache[original]
            prefix = m.group(1)
            fake = f'{prefix} "{_pick(_COMPANY_PREFIXES, original, "c")}"'
            self._cache[original] = fake
            return fake
        return re.sub(
            r'(ООО|ЗАО|ОАО|ПАО|АО|ИП)\s*"([^"]{2,60})"',
            _repl, text
        )

    def anonymize_text(self, text: str) -> str:
        """Apply all anonymization patterns to a text string."""
        if not self.enabled or not text:
            return text
        text = _FIO_RE.sub(self._replace_fio, text)
        text = _FIO_SHORT_RE.sub(self._replace_fio_short, text)
        text = self._replace_company(text)
        text = _PHONE_RE.sub(self._replace_phone, text)
        text = _EMAIL_RE.sub(self._replace_email, text)
        text = _SNILS_RE.sub(self._replace_snils, text)
        text = _INN_RE.sub(self._replace_inn, text)
        return text

    def anonymize_json(self, data: Any) -> Any:
        """Recursively anonymize string values in JSON-like structures."""
        if not self.enabled:
            return data
        if isinstance(data, str):
            return self.anonymize_text(data)
        if isinstance(data, dict):
            return {k: self.anonymize_json(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.anonymize_json(item) for item in data]
        return data

    def process_tool_response(self, tool_name: str, text: str) -> str:
        """Process a tool response text, anonymizing if needed."""
        if not self.enabled:
            return text
        # Only anonymize data-returning tools
        data_tools = {
            "execute_query", "execute_code", "get_event_log",
            "get_object_by_link", "find_references_to_object",
        }
        if tool_name not in data_tools:
            return text
        try:
            data = json.loads(text)
            anonymized = self.anonymize_json(data)
            return json.dumps(anonymized, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            return self.anonymize_text(text)


# Singleton
anonymizer = Anonymizer()

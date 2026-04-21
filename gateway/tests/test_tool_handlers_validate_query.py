"""Tests for gateway.tool_handlers.validate_query."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.validate_query import add_limit_zero, validate_query, validate_query_static


class TestValidateQueryStatic:
    def test_empty_query(self):
        valid, errors, warnings = validate_query_static("")
        assert valid is False
        assert errors
        assert warnings == []

    def test_missing_select_keyword(self):
        valid, errors, _ = validate_query_static("ИЗ Справочник.Номенклатура")
        assert valid is False
        assert any("ВЫБРАТЬ" in err for err in errors)

    def test_static_query_warning_for_star(self):
        valid, errors, warnings = validate_query_static("ВЫБРАТЬ * ИЗ Справочник.Номенклатура")
        assert valid is True
        assert errors == []
        assert warnings

    def test_invalid_query_can_return_warnings_too(self):
        valid, errors, warnings = validate_query_static(
            "РегистрНакопления.ТоварыНаСкладах.Остатки) КАК Остатки ГДЕ Остатки.Склад = &Склад"
        )
        assert valid is False
        assert errors
        assert warnings


class TestAddLimitZero:
    def test_inserts_first_clause(self):
        query = "ВЫБРАТЬ Код ИЗ Справочник.Номенклатура"
        transformed = add_limit_zero(query)
        assert transformed.startswith("ВЫБРАТЬ ПЕРВЫЕ 0")

    def test_replaces_existing_first_value(self):
        query = "ВЫБРАТЬ ПЕРВЫЕ 100 Код ИЗ Справочник.Номенклатура"
        transformed = add_limit_zero(query)
        assert "ПЕРВЫЕ 0" in transformed
        assert "ПЕРВЫЕ 100" not in transformed


class TestValidateQueryAsync:
    @pytest.mark.asyncio
    async def test_returns_static_result_without_active_db(self):
        result = await validate_query(
            query="ВЫБРАТЬ 1",
            get_active=lambda: None,
            get_toolkit=lambda: None,
        )
        payload = json.loads(result)
        assert payload["valid"] is True
        assert payload["source"] == "static"

    @pytest.mark.asyncio
    async def test_returns_static_result_when_toolkit_missing(self):
        result = await validate_query(
            query="ВЫБРАТЬ * ИЗ Справочник.Номенклатура",
            get_active=lambda: object(),
            get_toolkit=lambda: None,
        )
        payload = json.loads(result)
        assert payload["valid"] is True
        assert payload["source"] == "static"
        assert payload["warnings"]

    @pytest.mark.asyncio
    async def test_server_path_uses_execute_query_with_first_zero(self):
        toolkit = SimpleNamespace(
            call_tool=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(text='{"ok": true}')]))
        )

        result = await validate_query(
            query="ВЫБРАТЬ Код ИЗ Справочник.Номенклатура",
            get_active=lambda: object(),
            get_toolkit=lambda: toolkit,
        )
        payload = json.loads(result)
        assert payload["valid"] is True
        assert payload["source"] == "server"
        toolkit.call_tool.assert_awaited_once()
        call_args = toolkit.call_tool.await_args.args
        assert call_args[0] == "execute_query"
        assert "ПЕРВЫЕ 0" in call_args[1]["query"]

    @pytest.mark.asyncio
    async def test_server_syntax_error_detected(self):
        toolkit = SimpleNamespace(
            call_tool=AsyncMock(
                return_value=SimpleNamespace(content=[SimpleNamespace(text="Syntax error near token")])
            )
        )

        result = await validate_query(
            query="ВЫБРАТЬ Код ИЗ Справочник.Номенклатура",
            get_active=lambda: object(),
            get_toolkit=lambda: toolkit,
        )
        payload = json.loads(result)
        assert payload["valid"] is False
        assert any("Ошибка синтаксиса от сервера 1С" in err for err in payload["errors"])

    @pytest.mark.asyncio
    async def test_server_success_preserves_warnings(self):
        toolkit = SimpleNamespace(
            call_tool=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(text='{"ok": true}')]))
        )

        result = await validate_query(
            query="ВЫБРАТЬ * ИЗ Справочник.Номенклатура",
            get_active=lambda: object(),
            get_toolkit=lambda: toolkit,
        )
        payload = json.loads(result)
        assert payload["valid"] is True
        assert payload["source"] == "server"
        assert payload["warnings"]

    @pytest.mark.asyncio
    async def test_server_exception_falls_back_to_static(self):
        toolkit = SimpleNamespace(call_tool=AsyncMock(side_effect=RuntimeError("boom")))

        result = await validate_query(
            query="ВЫБРАТЬ 1",
            get_active=lambda: object(),
            get_toolkit=lambda: toolkit,
        )
        payload = json.loads(result)
        assert payload["valid"] is True
        assert payload["source"] == "static"

    @pytest.mark.asyncio
    async def test_static_error_response_preserves_warnings(self):
        result = await validate_query(
            query="РегистрНакопления.ТоварыНаСкладах.Остатки) КАК Остатки ГДЕ Остатки.Склад = &Склад",
            get_active=lambda: None,
            get_toolkit=lambda: None,
        )
        payload = json.loads(result)
        assert payload["valid"] is False
        assert payload["warnings"]

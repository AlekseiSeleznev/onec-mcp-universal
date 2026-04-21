"""Tests for gateway.tool_handlers.its."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.its import its_search


class TestItsHandler:
    @pytest.mark.asyncio
    async def test_missing_api_key_returns_explicit_error(self):
        result = await its_search("как настроить БСП?", "")

        assert "ERROR: NAPARNIK_API_KEY not configured." in result
        assert "Add to .env: NAPARNIK_API_KEY=your-key-here" in result

    @pytest.mark.asyncio
    async def test_calls_naparnik_client_with_key(self):
        with patch("gateway.tool_handlers.its.NaparnikClient") as client_cls:
            client = MagicMock()
            client.search = AsyncMock(return_value="Результат поиска")
            client_cls.return_value = client

            result = await its_search("запрос", "test-key")

        assert result == "Результат поиска"
        client_cls.assert_called_once_with("test-key")
        client.search.assert_awaited_once_with("запрос")

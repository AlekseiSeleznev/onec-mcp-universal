"""Tests for gateway.tool_handlers.graph."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.tool_handlers.graph import graph_request, try_handle_graph_tool


class TestTryHandleGraphTool:
    @pytest.mark.asyncio
    async def test_returns_none_for_non_graph_tool(self):
        requester = AsyncMock()

        result = await try_handle_graph_tool("not_graph", {}, requester)

        assert result is None
        requester.assert_not_called()

    @pytest.mark.asyncio
    async def test_graph_stats_calls_requester(self):
        requester = AsyncMock(return_value='{"ok": true}')

        result = await try_handle_graph_tool("graph_stats", {}, requester)

        assert result == '{"ok": true}'
        requester.assert_awaited_once_with("GET", "/api/graph/stats")

    @pytest.mark.asyncio
    async def test_graph_search_payload_defaults(self):
        requester = AsyncMock(return_value='{"results": []}')

        result = await try_handle_graph_tool("graph_search", {"query": "test"}, requester)

        assert result == '{"results": []}'
        requester.assert_awaited_once_with(
            "POST",
            "/api/graph/search",
            {"query": "test", "types": [], "limit": 20},
        )

    @pytest.mark.asyncio
    async def test_graph_search_filters_results_by_active_db(self):
        requester = AsyncMock(
            return_value=json.dumps(
                {
                    "results": [
                        {"db": "Z01", "id": "Z01:Catalogs:Номенклатура"},
                        {"db": "Z02", "id": "Z02:Catalogs:Номенклатура"},
                    ]
                },
                ensure_ascii=False,
            )
        )

        result = await try_handle_graph_tool(
            "graph_search",
            {"query": "Номенклатура"},
            requester,
            active_db="Z01",
        )

        parsed = json.loads(result)
        assert parsed["results"] == [{"db": "Z01", "id": "Z01:Catalogs:Номенклатура"}]
        requester.assert_awaited_once_with(
            "POST",
            "/api/graph/search",
            {"query": "Номенклатура", "types": [], "limit": 20, "dbs": ["Z01"]},
        )

    @pytest.mark.asyncio
    async def test_graph_search_filters_nodes_by_active_db_properties(self):
        requester = AsyncMock(
            return_value=json.dumps(
                {
                    "nodes": [
                        {"id": "Z01:Catalogs:Номенклатура", "properties": {"db": "Z01"}},
                        {"id": "Z02:Catalogs:Номенклатура", "properties": {"db": "Z02"}},
                    ]
                },
                ensure_ascii=False,
            )
        )

        result = await try_handle_graph_tool(
            "graph_search",
            {"query": "Номенклатура"},
            requester,
            active_db="Z02",
        )

        parsed = json.loads(result)
        assert parsed["nodes"] == [{"id": "Z02:Catalogs:Номенклатура", "properties": {"db": "Z02"}}]
        requester.assert_awaited_once_with(
            "POST",
            "/api/graph/search",
            {"query": "Номенклатура", "types": [], "limit": 20, "dbs": ["Z02"]},
        )

    @pytest.mark.asyncio
    async def test_graph_search_filters_edges_and_total_count_by_active_db(self):
        requester = AsyncMock(
            return_value=json.dumps(
                {
                    "nodes": [
                        {"id": "Z01:Catalogs:Номенклатура", "properties": {"db": "Z01"}},
                        {"id": "Z02:Catalogs:Номенклатура", "properties": {"db": "Z02"}},
                    ],
                    "edges": [
                        {
                            "sourceId": "Z01:Catalogs:Номенклатура",
                            "targetId": "Z01:file:Catalogs/Номенклатура/Ext/ObjectModule.bsl",
                        },
                        {
                            "sourceId": "Z02:Catalogs:Номенклатура",
                            "targetId": "Z02:file:Catalogs/Номенклатура/Ext/ObjectModule.bsl",
                        },
                    ],
                    "totalCount": 2,
                },
                ensure_ascii=False,
            )
        )

        result = await try_handle_graph_tool(
            "graph_search",
            {"query": "Номенклатура"},
            requester,
            active_db="Z01",
        )

        parsed = json.loads(result)
        assert parsed["nodes"] == [{"id": "Z01:Catalogs:Номенклатура", "properties": {"db": "Z01"}}]
        assert parsed["edges"] == [
            {
                "sourceId": "Z01:Catalogs:Номенклатура",
                "targetId": "Z01:file:Catalogs/Номенклатура/Ext/ObjectModule.bsl",
            }
        ]
        assert parsed["totalCount"] == 1

    @pytest.mark.asyncio
    async def test_graph_search_filter_handles_malformed_items_ids_edges_and_invalid_json(self):
        invalid_requester = AsyncMock(return_value="not-json")
        invalid = await try_handle_graph_tool(
            "graph_search",
            {"query": "Номенклатура"},
            invalid_requester,
            active_db="Z01",
        )
        requester = AsyncMock(
            return_value=json.dumps(
                {
                    "nodes": [
                        "not-a-dict",
                        {"id": "Z01:Catalogs:Номенклатура"},
                        {"id": "NO_COLON"},
                        {"properties": {"db": ""}},
                    ],
                    "edges": [
                        "not-a-dict",
                        {"sourceId": "NO_COLON", "targetId": "Z01:file:Catalogs/Номенклатура"},
                        {"sourceId": "NO_COLON", "targetId": "NO_COLON"},
                    ],
                    "totalCount": 4,
                },
                ensure_ascii=False,
            )
        )

        result = await try_handle_graph_tool(
            "graph_search",
            {"query": "Номенклатура"},
            requester,
            active_db="Z01",
        )

        parsed = json.loads(result)
        assert invalid == "not-json"
        assert parsed["nodes"] == [{"id": "Z01:Catalogs:Номенклатура"}]
        assert parsed["edges"] == [{"sourceId": "NO_COLON", "targetId": "Z01:file:Catalogs/Номенклатура"}]
        assert parsed["totalCount"] == 1

    @pytest.mark.asyncio
    async def test_graph_related_uses_depth_param(self):
        requester = AsyncMock(return_value='{"neighbors": []}')

        result = await try_handle_graph_tool(
            "graph_related",
            {"object_id": "Z01:Documents:Анкета/Ext/ObjectModule.bsl", "depth": 2},
            requester,
        )

        assert result == '{"neighbors": []}'
        requester.assert_awaited_once_with(
            "GET",
            "/api/graph/related/Z01%3ADocuments%3A%D0%90%D0%BD%D0%BA%D0%B5%D1%82%D0%B0%2FExt%2FObjectModule.bsl",
            None,
            params={"depth": 2},
        )


class TestGraphRequest:
    @pytest.mark.asyncio
    async def test_get_success_json(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"nodes": 42})
        response.text = '{"nodes": 42}'

        with patch("gateway.tool_handlers.graph.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=response)
            mock_client_cls.return_value = mock_client

            result = await graph_request("http://graph:8080", "GET", "/api/graph/stats")

        parsed = json.loads(result)
        assert parsed["nodes"] == 42

    @pytest.mark.asyncio
    async def test_post_success_json(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(return_value={"results": []})
        response.text = '{"results": []}'

        with patch("gateway.tool_handlers.graph.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=response)
            mock_client_cls.return_value = mock_client

            result = await graph_request(
                "http://graph:8080",
                "POST",
                "/api/graph/search",
                body={"query": "test"},
                params={"depth": 1},
            )

        parsed = json.loads(result)
        assert parsed["results"] == []

    @pytest.mark.asyncio
    async def test_non_json_response_falls_back_to_text(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(side_effect=ValueError("not json"))
        response.text = "plain response"

        with patch("gateway.tool_handlers.graph.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=response)
            mock_client_cls.return_value = mock_client

            result = await graph_request("http://graph:8080", "GET", "/api/graph/stats")

        assert result == "plain response"

    @pytest.mark.asyncio
    async def test_connect_error_returns_actionable_message(self):
        with patch("gateway.tool_handlers.graph.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value = mock_client

            result = await graph_request("http://graph:8080", "GET", "/api/graph/stats")

        assert "ERROR: bsl-graph service not available" in result
        assert "docker compose --profile bsl-graph up -d" in result

    @pytest.mark.asyncio
    async def test_generic_error_returns_error_text(self):
        with patch("gateway.tool_handlers.graph.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=RuntimeError("boom"))
            mock_client_cls.return_value = mock_client

            result = await graph_request("http://graph:8080", "POST", "/api/graph/search", body={})

        assert result == "ERROR: boom"

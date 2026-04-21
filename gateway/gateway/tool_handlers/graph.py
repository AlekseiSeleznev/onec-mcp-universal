"""Handlers for bsl-graph MCP tools."""

from __future__ import annotations

import json
from urllib.parse import quote

import httpx

_GRAPH_TOOLS = {"graph_stats", "graph_search", "graph_related"}


def _item_db(item: dict) -> str | None:
    if not isinstance(item, dict):
        return None
    direct = item.get("db")
    if isinstance(direct, str) and direct:
        return direct
    props = item.get("properties")
    if isinstance(props, dict):
        prop_db = props.get("db")
        if isinstance(prop_db, str) and prop_db:
            return prop_db
    item_id = item.get("id")
    if isinstance(item_id, str) and ":" in item_id:
        return item_id.split(":", 1)[0]
    return None


def _edge_db(item: dict) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in ("sourceId", "targetId"):
        value = item.get(key)
        if isinstance(value, str) and ":" in value:
            return value.split(":", 1)[0]
    return None


def _filter_graph_search_payload(payload: str, active_db: str | None) -> str:
    if not active_db:
        return payload
    try:
        data = json.loads(payload)
    except Exception:
        return payload
    filtered_count: int | None = None
    for key in ("results", "nodes"):
        items = data.get(key)
        if isinstance(items, list):
            filtered_items = [item for item in items if _item_db(item) == active_db]
            data[key] = filtered_items
            filtered_count = len(filtered_items)
    edges = data.get("edges")
    if isinstance(edges, list):
        data["edges"] = [item for item in edges if _edge_db(item) == active_db]
    if filtered_count is not None and isinstance(data.get("totalCount"), int):
        data["totalCount"] = filtered_count
    return json.dumps(data, ensure_ascii=False, indent=2)


async def graph_request(
    base_url: str,
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> str:
    """Call bsl-graph REST API and return normalized text response."""
    base = base_url.rstrip("/")
    url = base + path
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                resp = await client.get(url, params=params)
            else:
                resp = await client.post(url, json=body, params=params)
            resp.raise_for_status()
            try:
                return json.dumps(resp.json(), ensure_ascii=False, indent=2)
            except Exception:
                return resp.text
    except httpx.ConnectError:
        return (
            f"ERROR: bsl-graph service not available at {base}. "
            "Start it with: docker compose --profile bsl-graph up -d"
        )
    except Exception as exc:
        return f"ERROR: {exc}"


async def try_handle_graph_tool(
    name: str,
    arguments: dict,
    requester,
    active_db: str | None = None,
) -> str | None:
    """Handle graph tools and return response text; return None for non-graph tools.

    requester signature:
      await requester(method: str, path: str, body: dict|None = None, params: dict|None = None) -> str
    """
    if name not in _GRAPH_TOOLS:
        return None

    if name == "graph_stats":
        return await requester("GET", "/api/graph/stats")

    if name == "graph_search":
        payload = {
            "query": arguments.get("query", ""),
            "types": arguments.get("types", []),
            "limit": arguments.get("limit", 20),
        }
        if active_db:
            payload["dbs"] = [active_db]
        result = await requester("POST", "/api/graph/search", payload)
        return _filter_graph_search_payload(result, active_db)

    oid = arguments.get("object_id", "")
    encoded_oid = quote(oid, safe="")
    return await requester(
        "GET",
        f"/api/graph/related/{encoded_oid}",
        None,
        params={"depth": arguments.get("depth", 1)},
    )

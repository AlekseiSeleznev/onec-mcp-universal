from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from collections import deque


PORT = int(os.environ.get("PORT", "8888"))
WORKSPACE = Path(os.environ.get("GRAPH_WORKSPACE", "/workspace"))
HOSTFS_HOME = Path(os.environ.get("GRAPH_HOSTFS_HOME", "/hostfs-home"))
STATE_FILE = Path(os.environ.get("GRAPH_STATE_FILE", "/data/graph.json"))
REGISTRY_STATE_FILE = Path(os.environ.get("GRAPH_REGISTRY_STATE_FILE", "/data/db_state.json"))
BSL_SNAPSHOT_DIR = STATE_FILE.parent / "bsl-search-cache"
RESCAN_SECONDS = max(30, int(os.environ.get("GRAPH_RESCAN_SECONDS", "300")))

OBJECT_DIRS = {
    "AccumulationRegisters": "accumulationRegister",
    "BusinessProcesses": "businessProcess",
    "CalculationRegisters": "calculationRegister",
    "Catalogs": "catalog",
    "ChartsOfAccounts": "chartOfAccounts",
    "ChartsOfCalculationTypes": "chartOfCalculationTypes",
    "ChartsOfCharacteristicTypes": "chartOfCharacteristicTypes",
    "CommonCommands": "commonCommand",
    "CommonForms": "commonForm",
    "CommonModules": "commonModule",
    "Constants": "constant",
    "DataProcessors": "dataProcessor",
    "DefinedTypes": "definedType",
    "DocumentJournals": "documentJournal",
    "Documents": "document",
    "Enums": "enum",
    "EventSubscriptions": "eventSubscription",
    "ExchangePlans": "exchangePlan",
    "FilterCriteria": "filterCriteria",
    "HTTPServices": "httpService",
    "InformationRegisters": "informationRegister",
    "IntegrationServices": "integrationService",
    "Reports": "report",
    "Roles": "role",
    "ScheduledJobs": "scheduledJob",
    "SessionParameters": "sessionParameter",
    "SettingsStorages": "settingsStorage",
    "Subsystems": "subsystem",
    "Tasks": "task",
    "WebServices": "webService",
    "WSReferences": "wsReference",
    "XDTOPackages": "xdtoPackage",
}

IDENT_RE = re.compile(r"[A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*")


def _friendly_bsl_name(rel_path: str, type_folder: str) -> str:
    """
    Build a readable, distinguishable display name for a bsl file node.

    Raw names like "Module.bsl" or "ManagerModule.bsl" collide across hundreds
    of objects. Produce "ОбъектИмя/Форма/Module.bsl" instead.
    """
    parts = [p for p in (rel_path or "").split("/") if p and p != "Ext"]
    # Drop the top-level type folder (e.g. "InformationRegisters") so the name
    # starts with the object's own name.
    if parts and parts[0] == type_folder:
        parts = parts[1:]
    return "/".join(parts) or rel_path or ""


@dataclass
class Edge:
    source_id: str
    target_id: str
    edge_type: str
    properties: dict[str, Any]


class GraphStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[Edge] = []
        self.updated_at = ""
        self.last_error = ""
        self.load_snapshot()

    def load_snapshot(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        self.nodes = payload.get("nodes", {})
        self.edges = [Edge(**edge) for edge in payload.get("edges", [])]
        self.updated_at = payload.get("updated_at", "")
        self.last_error = payload.get("last_error", "")

    def save_snapshot(self) -> None:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "nodes": self.nodes,
            "edges": [edge.__dict__ for edge in self.edges],
            "updated_at": self.updated_at,
            "last_error": self.last_error,
        }
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _registered_roots(self) -> list[tuple[str, Path]]:
        if not REGISTRY_STATE_FILE.exists():
            return []
        try:
            payload = json.loads(REGISTRY_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

        roots: list[tuple[str, Path]] = []
        seen: set[tuple[str, str]] = set()
        for item in payload.get("databases", []):
            db_name = str(item.get("name") or item.get("slug") or "").strip()
            project_path = str(item.get("project_path") or "").strip().rstrip("/")
            if not db_name or not project_path:
                continue

            root = self._resolve_project_path(project_path, item)
            if root is None or not root.is_dir():
                continue

            key = (db_name, str(root))
            if key in seen:
                continue
            seen.add(key)
            roots.append((db_name, root))
        return roots

    def _load_cached_symbols(self, db_name: str, project_path: str) -> list[dict[str, Any]]:
        requested_name = Path((project_path or "").rstrip("/")).name or db_name
        if not BSL_SNAPSHOT_DIR.exists():
            return []

        candidates: list[tuple[float, Path]] = []
        for snapshot in BSL_SNAPSHOT_DIR.glob("*.json"):
            try:
                payload = json.loads(snapshot.read_text(encoding="utf-8"))
            except Exception:
                continue
            indexed_path = str(payload.get("indexed_path") or "").rstrip("/")
            if Path(indexed_path).name != requested_name:
                continue
            try:
                mtime = snapshot.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((mtime, snapshot))

        for _, snapshot in sorted(candidates, key=lambda item: item[0], reverse=True):
            try:
                payload = json.loads(snapshot.read_text(encoding="utf-8"))
                symbols = payload.get("symbols", [])
            except Exception:
                continue
            if symbols:
                return symbols
        return []

    def _resolve_project_path(self, project_path: str, entry: dict[str, Any]) -> Path | None:
        if project_path == "/workspace" or project_path.startswith("/workspace/"):
            rel = project_path[len("/workspace") :].lstrip("/")
            return WORKSPACE / rel if rel else WORKSPACE

        if project_path == "/hostfs-home" or project_path.startswith("/hostfs-home/"):
            rel = project_path[len("/hostfs-home") :].lstrip("/")
            return HOSTFS_HOME / rel if rel else HOSTFS_HOME

        raw = Path(project_path)
        if raw.is_dir():
            return raw

        basename = Path(project_path).name
        for candidate in (
            WORKSPACE / basename,
            HOSTFS_HOME / basename,
            WORKSPACE / str(entry.get("slug") or ""),
            WORKSPACE / str(entry.get("name") or ""),
        ):
            if str(candidate).rstrip("/") and candidate.is_dir():
                return candidate
        return None

    def rebuild(self) -> None:
        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[Edge] = []

        db_roots = self._registered_roots()
        object_name_index: dict[tuple[str, str], list[str]] = {}
        owner_by_file: dict[Path, str] = {}

        for db_name, db_root in db_roots:
            for folder_name, node_type in OBJECT_DIRS.items():
                top = db_root / folder_name
                if not top.is_dir():
                    continue
                for obj_dir in top.iterdir():
                    if not obj_dir.is_dir():
                        continue
                    object_name = obj_dir.name
                    node_id = f"{db_name}:{folder_name}:{object_name}"
                    nodes[node_id] = {
                        "id": node_id,
                        "type": node_type,
                        "properties": {
                            "db": db_name,
                            "name": object_name,
                            "folder": folder_name,
                            "path": str(obj_dir),
                        },
                    }
                    object_name_index.setdefault((db_name, object_name.lower()), []).append(node_id)

                    for bsl_file in obj_dir.rglob("*.bsl"):
                        rel = bsl_file.relative_to(db_root).as_posix()
                        file_node_id = f"{db_name}:file:{rel}"
                        nodes[file_node_id] = {
                            "id": file_node_id,
                            "type": "bslFile",
                            "properties": {
                                "db": db_name,
                                "name": _friendly_bsl_name(rel, folder_name),
                                "path": str(bsl_file),
                                "relativePath": rel,
                            },
                        }
                        owner_by_file[bsl_file] = node_id
                        edges.append(
                            Edge(
                                source_id=node_id,
                                target_id=file_node_id,
                                edge_type="containsFile",
                                properties={},
                            )
                        )

        if not nodes and REGISTRY_STATE_FILE.exists():
            try:
                registry_payload = json.loads(REGISTRY_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                registry_payload = {}
            for item in registry_payload.get("databases", []):
                db_name = str(item.get("name") or item.get("slug") or "").strip()
                project_path = str(item.get("project_path") or "").strip()
                if not db_name or not project_path:
                    continue
                symbols = self._load_cached_symbols(db_name, project_path)
                if not symbols:
                    continue
                for symbol in symbols:
                    rel = str(symbol.get("file") or "").strip().lstrip("/")
                    if not rel:
                        continue
                    parts = Path(rel).parts
                    if len(parts) < 2:
                        continue
                    folder_name = parts[0]
                    object_name = parts[1]
                    node_type = OBJECT_DIRS.get(folder_name)
                    if not node_type:
                        continue
                    node_id = f"{db_name}:{folder_name}:{object_name}"
                    nodes.setdefault(
                        node_id,
                        {
                            "id": node_id,
                            "type": node_type,
                            "properties": {
                                "db": db_name,
                                "name": object_name,
                                "folder": folder_name,
                                "path": project_path.rstrip("/") + "/" + "/".join(parts[:2]),
                            },
                        },
                    )
                    object_name_index.setdefault((db_name, object_name.lower()), []).append(node_id)
                    file_node_id = f"{db_name}:file:{rel}"
                    nodes.setdefault(
                        file_node_id,
                        {
                            "id": file_node_id,
                            "type": "bslFile",
                            "properties": {
                                "db": db_name,
                                "name": _friendly_bsl_name(rel, folder_name),
                                "path": project_path.rstrip("/") + "/" + rel,
                                "relativePath": rel,
                            },
                        },
                    )
                    owner_by_file[Path(rel)] = node_id
                    edges.append(
                        Edge(
                            source_id=node_id,
                            target_id=file_node_id,
                            edge_type="containsFile",
                            properties={"source": "snapshot"},
                        )
                    )

        known_names = {name for _, name in object_name_index.keys()}
        for bsl_file, owner_id in owner_by_file.items():
            try:
                text = bsl_file.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                continue
            identifiers = {token.lower() for token in IDENT_RE.findall(text)}
            owner_node = nodes.get(owner_id, {})
            owner_db = str(owner_node.get("properties", {}).get("db", ""))
            for name in identifiers & known_names:
                for target_id in object_name_index.get((owner_db, name), []):
                    if target_id == owner_id:
                        continue
                    edges.append(
                        Edge(
                            source_id=owner_id,
                            target_id=target_id,
                            edge_type="references",
                            properties={"via": bsl_file.name},
                        )
                    )

        dedup: dict[tuple[str, str, str], Edge] = {}
        for edge in edges:
            dedup[(edge.source_id, edge.target_id, edge.edge_type)] = edge

        with self.lock:
            self.nodes = nodes
            self.edges = list(dedup.values())
            self.updated_at = started_at
            self.last_error = ""
            self.save_snapshot()

    def stats(self) -> dict[str, Any]:
        with self.lock:
            dbs = sorted(
                {
                    node["properties"].get("db", "")
                    for node in self.nodes.values()
                    if node["properties"].get("db")
                }
            )
            by_type: dict[str, int] = {}
            by_type_by_db: dict[str, dict[str, int]] = {}
            edges_by_db: dict[str, int] = {}
            edge_types: dict[str, int] = {}
            edge_types_by_db: dict[str, dict[str, int]] = {}
            for node in self.nodes.values():
                t = str(node.get("type") or "")
                if t:
                    by_type[t] = by_type.get(t, 0) + 1
                db = str(node["properties"].get("db", ""))
                if db and t:
                    by_type_by_db.setdefault(db, {})
                    by_type_by_db[db][t] = by_type_by_db[db].get(t, 0) + 1
            for edge in self.edges:
                source = self.nodes.get(edge.source_id, {})
                target = self.nodes.get(edge.target_id, {})
                db = str(source.get("properties", {}).get("db", "") or target.get("properties", {}).get("db", ""))
                edge_type = str(edge.edge_type or "")
                if edge_type:
                    edge_types[edge_type] = edge_types.get(edge_type, 0) + 1
                if db:
                    edges_by_db[db] = edges_by_db.get(db, 0) + 1
                    if edge_type:
                        edge_types_by_db.setdefault(db, {})
                        edge_types_by_db[db][edge_type] = edge_types_by_db[db].get(edge_type, 0) + 1
            return {
                "totalNodes": len(self.nodes),
                "totalEdges": len(self.edges),
                "updatedAt": self.updated_at,
                "workspace": str(WORKSPACE),
                "indexedDatabases": dbs,
                "byType": by_type,
                "byTypeByDb": by_type_by_db,
                "edgesByDb": edges_by_db,
                "edgeTypes": edge_types,
                "edgeTypesByDb": edge_types_by_db,
                "registryStateFile": str(REGISTRY_STATE_FILE),
                "lastError": self.last_error,
            }

    @staticmethod
    def _parse_csv_values(values: list[str] | None) -> list[str]:
        out: list[str] = []
        for raw in values or []:
            for part in str(raw or "").split(","):
                value = part.strip()
                if value:
                    out.append(value)
        return out

    @staticmethod
    def _normalize_direction(direction: str | None) -> str:
        value = str(direction or "both").strip().lower()
        if value in {"in", "out", "both"}:
            return value
        return "both"

    def _node_allowed(
        self,
        node: dict[str, Any],
        include_node_types: set[str],
        exclude_node_types: set[str],
        allowed_dbs: set[str],
    ) -> bool:
        node_type = str(node.get("type") or "")
        db = str(node.get("properties", {}).get("db", ""))
        if allowed_dbs and db not in allowed_dbs:
            return False
        if include_node_types and node_type not in include_node_types:
            return False
        if exclude_node_types and node_type in exclude_node_types:
            return False
        return True

    @staticmethod
    def _serialize_edge(edge: Edge) -> dict[str, Any]:
        return {
            "sourceId": edge.source_id,
            "targetId": edge.target_id,
            "type": edge.edge_type,
            "properties": edge.properties,
        }

    def _path_neighbors(
        self,
        current: str,
        adjacency: dict[str, list[tuple[str, Edge]]],
        direction: str,
        allowed_edge_types: set[str],
        include_node_types: set[str],
        exclude_node_types: set[str],
        allowed_dbs: set[str],
    ) -> list[tuple[str, Edge]]:
        options: list[tuple[str, Edge]] = []
        for other, edge in adjacency.get(current, []):
            if allowed_edge_types and edge.edge_type not in allowed_edge_types:
                continue
            other_node = self.nodes.get(other)
            if other_node is None:
                continue
            if not self._node_allowed(
                other_node,
                include_node_types,
                exclude_node_types,
                allowed_dbs,
            ):
                continue
            if direction == "out" and edge.source_id != current:
                continue
            if direction == "in" and edge.target_id != current:
                continue
            options.append((other, edge))
        return options

    def search(
        self,
        query: str,
        types: list[str] | None,
        limit: int,
        dbs: list[str] | None = None,
    ) -> dict[str, Any]:
        # Split the query into whitespace-separated tokens. Each token must
        # appear as a substring (case-insensitive) in the node id/name/path —
        # i.e. "размеры пособий" matches "РазмерыГосударственныхПособий".
        tokens = [t.lower() for t in (query or "").split() if t.strip()]
        allowed = {t.lower() for t in (types or []) if t}
        allowed_dbs = {d for d in (dbs or []) if d}

        def matches_tokens(node: dict[str, Any]) -> bool:
            haystack = (
                node["id"]
                + " "
                + str(node["properties"].get("name", ""))
                + " "
                + str(node["properties"].get("relativePath", ""))
            ).lower()
            return all(tok in haystack for tok in tokens)

        with self.lock:
            nodes = list(self.nodes.values())
            if allowed:
                nodes = [node for node in nodes if str(node["type"]).lower() in allowed]
            if allowed_dbs:
                nodes = [
                    node
                    for node in nodes
                    if str(node["properties"].get("db", "")) in allowed_dbs
                ]
            if tokens:
                nodes = [node for node in nodes if matches_tokens(node)]
            nodes = nodes[: max(1, min(limit or 20, 200))]
            node_ids = {node["id"] for node in nodes}
            edges = [
                {
                    "sourceId": edge.source_id,
                    "targetId": edge.target_id,
                    "type": edge.edge_type,
                    "properties": edge.properties,
                }
                for edge in self.edges
                if edge.source_id in node_ids or edge.target_id in node_ids
            ]
            return {"nodes": nodes, "edges": edges, "totalCount": len(nodes)}

    def related(
        self,
        node_id: str,
        depth: int,
        *,
        direction: str = "both",
        edge_types: list[str] | None = None,
        include_node_types: list[str] | None = None,
        exclude_node_types: list[str] | None = None,
        limit_nodes: int | None = None,
        limit_edges: int | None = None,
        dbs: list[str] | None = None,
    ) -> dict[str, Any]:
        max_depth = max(1, min(depth or 1, 3))
        direction = self._normalize_direction(direction)
        allowed_edge_types = {str(v) for v in (edge_types or []) if v}
        include_types = {str(v) for v in (include_node_types or []) if v}
        exclude_types = {str(v) for v in (exclude_node_types or []) if v}
        allowed_dbs = {str(v) for v in (dbs or []) if v}
        node_limit = max(1, min(limit_nodes or 200, 200)) if limit_nodes else None
        edge_limit = max(1, min(limit_edges or 400, 400)) if limit_edges else None
        with self.lock:
            root_node = self.nodes.get(node_id)
            if root_node is None:
                return {"nodes": [], "edges": [], "totalCount": 0, "truncated": False}
            root_db = str(root_node.get("properties", {}).get("db", ""))
            if root_db:
                allowed_dbs.add(root_db)
            adjacency: dict[str, list[Edge]] = {}
            for edge in self.edges:
                if allowed_edge_types and edge.edge_type not in allowed_edge_types:
                    continue
                if direction in {"both", "out"}:
                    adjacency.setdefault(edge.source_id, []).append(edge)
                if direction in {"both", "in"}:
                    adjacency.setdefault(edge.target_id, []).append(edge)

            seen = {node_id}
            frontier = {node_id}
            collected_edges: dict[tuple[str, str, str], Edge] = {}
            truncated = False
            for _ in range(max_depth):
                next_frontier: set[str] = set()
                for current in frontier:
                    for edge in adjacency.get(current, []):
                        if direction == "out" and edge.source_id != current:
                            continue
                        if direction == "in" and edge.target_id != current:
                            continue
                        other = edge.target_id if edge.source_id == current else edge.source_id
                        other_node = self.nodes.get(other)
                        if other_node is None:
                            continue
                        if not self._node_allowed(
                            other_node,
                            include_types,
                            exclude_types,
                            allowed_dbs,
                        ):
                            continue
                        if edge_limit is not None and (edge.source_id, edge.target_id, edge.edge_type) not in collected_edges and len(collected_edges) >= edge_limit:
                            truncated = True
                            continue
                        collected_edges[(edge.source_id, edge.target_id, edge.edge_type)] = edge
                        if other not in seen:
                            related_seen = max(0, len(seen) - 1)
                            if node_limit is not None and related_seen >= node_limit:
                                truncated = True
                                continue
                            seen.add(other)
                            next_frontier.add(other)
                frontier = next_frontier

            nodes = [
                self.nodes[nid]
                for nid in seen
                if nid in self.nodes and (
                    nid == node_id
                    or self._node_allowed(self.nodes[nid], include_types, exclude_types, allowed_dbs)
                )
            ]
            edges = [self._serialize_edge(edge) for edge in collected_edges.values()]
            return {"nodes": nodes, "edges": edges, "totalCount": len(nodes), "truncated": truncated}

    def path_between(
        self,
        source_id: str,
        target_id: str,
        *,
        max_depth: int = 6,
        edge_types: list[str] | None = None,
        include_node_types: list[str] | None = None,
        exclude_node_types: list[str] | None = None,
        dbs: list[str] | None = None,
        direction: str = "both",
        max_visited: int = 1000,
    ) -> dict[str, Any]:
        depth_limit = max(1, min(max_depth or 6, 12))
        visited_limit = max(1, min(max_visited or 1000, 5000))
        direction = self._normalize_direction(direction)
        allowed_edge_types = {str(v) for v in (edge_types or []) if v}
        include_types = {str(v) for v in (include_node_types or []) if v}
        exclude_types = {str(v) for v in (exclude_node_types or []) if v}
        allowed_dbs = {str(v) for v in (dbs or []) if v}
        with self.lock:
            source = self.nodes.get(source_id)
            target = self.nodes.get(target_id)
            if source is None or target is None:
                return {
                    "nodes": [],
                    "edges": [],
                    "pathFound": False,
                    "hopCount": 0,
                    "visitedCount": 0,
                    "truncated": False,
                    "reason": "not_found",
                }

            source_db = str(source.get("properties", {}).get("db", ""))
            target_db = str(target.get("properties", {}).get("db", ""))
            if source_db and target_db and source_db != target_db:
                return {
                    "nodes": [],
                    "edges": [],
                    "pathFound": False,
                    "hopCount": 0,
                    "visitedCount": 0,
                    "truncated": False,
                    "reason": "not_found",
                }
            if source_db:
                allowed_dbs.add(source_db)

            adjacency: dict[str, list[tuple[str, Edge]]] = {}
            for edge in self.edges:
                if direction in {"both", "out"}:
                    adjacency.setdefault(edge.source_id, []).append((edge.target_id, edge))
                if direction in {"both", "in"}:
                    adjacency.setdefault(edge.target_id, []).append((edge.source_id, edge))

            queue: deque[tuple[str, int]] = deque([(source_id, 0)])
            parents: dict[str, tuple[str, Edge]] = {}
            visited = {source_id}
            visited_count = 1
            truncated = False
            reason = "not_found"

            while queue:
                current, depth = queue.popleft()
                if current == target_id:
                    break
                if depth >= depth_limit:
                    reason = "depth_limit"
                    continue
                for other, edge in self._path_neighbors(
                    current,
                    adjacency,
                    direction,
                    allowed_edge_types,
                    include_types,
                    exclude_types,
                    allowed_dbs,
                ):
                    if other in visited:
                        continue
                    if visited_count >= visited_limit:
                        truncated = True
                        reason = "search_limit"
                        queue.clear()
                        break
                    visited.add(other)
                    visited_count += 1
                    parents[other] = (current, edge)
                    queue.append((other, depth + 1))

            if target_id not in visited:
                return {
                    "nodes": [],
                    "edges": [],
                    "pathFound": False,
                    "hopCount": 0,
                    "visitedCount": visited_count,
                    "truncated": truncated,
                    "reason": reason,
                }

            node_ids = [target_id]
            path_edges: list[Edge] = []
            cursor = target_id
            while cursor != source_id:
                parent, edge = parents[cursor]
                path_edges.append(edge)
                node_ids.append(parent)
                cursor = parent
            node_ids.reverse()
            path_edges.reverse()
            return {
                "nodes": [self.nodes[nid] for nid in node_ids if nid in self.nodes],
                "edges": [self._serialize_edge(edge) for edge in path_edges],
                "pathFound": True,
                "hopCount": max(0, len(node_ids) - 1),
                "visitedCount": visited_count,
                "truncated": truncated,
                "reason": "",
            }


STORE = GraphStore()


def rebuild_loop() -> None:
    while True:
        try:
            STORE.rebuild()
        except Exception as exc:
            with STORE.lock:
                STORE.last_error = str(exc)
                STORE.save_snapshot()
        time.sleep(RESCAN_SECONDS)


STATIC_DIR = Path(__file__).parent / "static"
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "bsl-graph-lite/0.1"

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, code: int, body: bytes, mime: str, cache: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        if not cache:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, rel_path: str) -> bool:
        """Serve a static file from ./static/. Returns True if a response was sent."""
        rel = (rel_path or "").lstrip("/")
        if not rel:
            rel = "index.html"
        # Path-traversal guard — resolve and assert containment.
        try:
            full = (STATIC_DIR / rel).resolve()
            full.relative_to(STATIC_DIR.resolve())
        except (ValueError, OSError):
            return False
        if not full.is_file():
            return False
        try:
            data = full.read_bytes()
        except OSError:
            return False
        mime = _MIME.get(full.suffix.lower(), "application/octet-stream")
        self._send_bytes(200, data, mime)
        return True

    def log_message(self, fmt: str, *args: Any) -> None:
        print(fmt % args, flush=True)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok", **STORE.stats()})
            return
        if parsed.path == "/api/graph/stats":
            self._send(200, STORE.stats())
            return
        if parsed.path.startswith("/api/graph/related/"):
            node_id = unquote(parsed.path[len("/api/graph/related/") :])
            params = parse_qs(parsed.query)
            depth = int((params.get("depth") or ["1"])[0])
            self._send(
                200,
                STORE.related(
                    node_id,
                    depth,
                    direction=str((params.get("direction") or ["both"])[0]),
                    edge_types=STORE._parse_csv_values(params.get("edge_types")),
                    include_node_types=STORE._parse_csv_values(params.get("include_node_types")),
                    exclude_node_types=STORE._parse_csv_values(params.get("exclude_node_types")),
                    limit_nodes=int((params.get("limit_nodes") or ["0"])[0] or 0) or None,
                    limit_edges=int((params.get("limit_edges") or ["0"])[0] or 0) or None,
                    dbs=STORE._parse_csv_values(params.get("dbs")),
                ),
            )
            return
        # Static UI
        if parsed.path == "/" or parsed.path == "/ui" or parsed.path == "/ui/":
            if self._serve_static("index.html"):
                return
        if parsed.path.startswith("/static/"):
            if self._serve_static(parsed.path[len("/static/") :]):
                return
        self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        if parsed.path == "/api/graph/search":
            result = STORE.search(
                query=str(payload.get("query", "")),
                types=list(payload.get("types", []) or []),
                limit=int(payload.get("limit", 20) or 20),
                dbs=[str(d) for d in (payload.get("dbs", []) or []) if d],
            )
            self._send(200, result)
            return
        if parsed.path == "/api/graph/rebuild":
            try:
                STORE.rebuild()
                self._send(200, {"ok": True, **STORE.stats()})
            except Exception as exc:
                self._send(500, {"ok": False, "error": str(exc)})
            return
        if parsed.path == "/api/graph/path":
            result = STORE.path_between(
                source_id=str(payload.get("sourceId", "")),
                target_id=str(payload.get("targetId", "")),
                max_depth=int(payload.get("maxDepth", 6) or 6),
                edge_types=[str(v) for v in (payload.get("edgeTypes", []) or []) if v],
                include_node_types=[str(v) for v in (payload.get("includeNodeTypes", []) or []) if v],
                exclude_node_types=[str(v) for v in (payload.get("excludeNodeTypes", []) or []) if v],
                dbs=[str(v) for v in (payload.get("dbs", []) or []) if v],
                direction=str(payload.get("direction", "both") or "both"),
                max_visited=int(payload.get("maxVisited", 1000) or 1000),
            )
            self._send(200, result)
            return
        self._send(404, {"error": "Not found"})


if __name__ == "__main__":
    threading.Thread(target=rebuild_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

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

_DOC_STYLE = """*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;max-width:980px;margin:0 auto;line-height:1.7}
h1{color:#f8fafc;margin-bottom:8px;font-size:1.5rem}h2{color:#38bdf8;margin:28px 0 10px;font-size:1.15rem;border-bottom:1px solid #334155;padding-bottom:6px}h3{color:#94a3b8;margin:18px 0 6px;font-size:.95rem}
p,li{color:#94a3b8;font-size:.88rem;margin-bottom:8px}ul,ol{padding-left:24px;margin-bottom:12px}code{background:#334155;padding:2px 6px;border-radius:3px;font-size:.82rem;color:#e2e8f0}
pre{background:#1e293b;padding:12px 16px;border-radius:6px;overflow-x:auto;margin:10px 0;border:1px solid #334155}pre code{background:none;padding:0}
a{color:#38bdf8}.back{display:inline-block;margin-bottom:20px;font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.85rem}th,td{padding:8px 10px;border:1px solid #334155;text-align:left}th{background:#1e293b;color:#64748b}
.note{background:#1e293b;border-left:3px solid #38bdf8;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0}
.warn{background:#1e293b;border-left:3px solid #eab308;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0}"""


def render_docs(lang: str = "ru") -> str:
    use_lang = "en" if lang == "en" else "ru"
    if use_lang == "ru":
        return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Документация BSL Graph</title><style>{_DOC_STYLE}</style></head><body>
<a class="back" href="/?lang=ru">&larr; Назад к графу</a>
<h1>Документация BSL Graph</h1>
<p>BSL Graph — это отдельный viewer для анализа зависимостей между объектами конфигурации 1С и BSL-модулями. Он работает поверх уже построенного графа и предназначен не для редактирования, а для расследования влияния изменений, навигации по зависимостям и поиска коротких путей между объектами.</p>

<h2>Что показывает граф</h2>
<p>Каждый узел представляет объект конфигурации 1С или BSL-файл. Цвет заливки показывает тип объекта, цвет рамки — базу данных. Сейчас используются два основных типа связей:</p>
<ul>
<li><code>Использует</code> — объект ссылается на другой объект или символ по имени в коде.</li>
<li><code>Содержит BSL-файл</code> — объект связан со своим исходным модулем.</li>
</ul>
<div class="note"><p>Viewer всегда работает в пределах активной базы. Если база переключена, и поиск, и анализ пути, и раскрытие окрестности выполняются только по ней.</p></div>

<h2>Верхняя панель</h2>
<table>
<tr><th>Элемент</th><th>Что делает</th><th>Как связан с остальным</th></tr>
<tr><td>Поле поиска</td><td>Ищет узлы по имени. Поддерживает несколько слов через пробел.</td><td>Результаты попадают в боковую панель «Результаты поиска». Клик по результату фокусирует существующий узел или догружает его окрестность.</td></tr>
<tr><td>Список</td><td>Открывает и закрывает панель результатов поиска.</td><td>Полезно, если граф уже открыт и нужно быстро перейти к другому объекту без нового запроса.</td></tr>
<tr><td>Очистить</td><td>Очищает поле поиска, текущий canvas, список результатов и выделение узла.</td><td>Не меняет активную базу, язык и глобальные фильтры. Это «сброс рабочего вида», а не пересборка графа.</td></tr>
<tr><td>Обзор / Путь</td><td>Переключает основной режим работы viewer.</td><td>В режиме «Обзор» удобнее раскрывать окрестности. В режиме «Путь» — выбирать старт и цель и строить кратчайший путь.</td></tr>
<tr><td>↶ Назад</td><td>Возвращает к предыдущему состоянию графа.</td><td>Запоминаются переходы по кликам, раскрытия соседей, построение пути, выбор старта/цели, закрепления, переключение базы, режима и ключевых фильтров.</td></tr>
<tr><td>↷ Вперёд</td><td>Возвращает к следующему состоянию графа после шага назад.</td><td>Работает как обычная история навигации: если после шага назад сделать новое действие, «ветка вперёд» обрезается.</td></tr>
<tr><td>RU / EN</td><td>Переключает язык интерфейса и локализованные подписи типов узлов и связей.</td><td>Не меняет сами данные графа. Переключение перезагружает страницу с параметром <code>?lang=</code>.</td></tr>
<tr><td>Документация</td><td>Открывает эту страницу.</td><td>Язык документации синхронизирован с текущим языком интерфейса.</td></tr>
<tr><td>Пересобрать</td><td>Запускает пересборку графа по текущему рабочему каталогу BSL.</td><td>Нужно использовать после изменений в выгрузке BSL, если нужно обновить сам граф, а не только локальный viewer.</td></tr>
<tr><td>Имя базы</td><td>Показывает активную базу.</td><td>Все действия viewer ниже выполняются в пределах этой базы.</td></tr>
<tr><td>Количество узлов и рёбер</td><td>Показывает размер графа по активной базе.</td><td>Это не число узлов на canvas, а общий размер среза графа для выбранной БД.</td></tr>
</table>

<h2>Левая колонка</h2>
<h3>Базы</h3>
<p>Радиокнопки в блоке «Базы» переключают активную БД. После переключения canvas очищается, путь сбрасывается, а список типов и статистика пересчитываются под новую базу.</p>
<div class="note"><p>Если открыть viewer через deep link с <code>?db=...</code>, эта база выберется автоматически.</p></div>

<h3>Типы</h3>
<p>Блок «Типы» — это быстрые преднастроенные поиски. Клик по типу запускает поиск узлов соответствующей категории, например «Справочник», «Документ» или «Общий модуль».</p>

<h2>Режимы работы</h2>
<h3>Обзор</h3>
<p>Режим для исследования окрестности объекта. Основные действия:</p>
<ul>
<li>клик по узлу — показать детали и подсветить его локальную окрестность;</li>
<li>двойной клик — догрузить соседей;</li>
<li>кнопка «Развернуть соседей» — то же действие из панели узла;</li>
<li>кнопка «Оставить только текущую окрестность» — очистить canvas и построить вокруг выбранного узла свежую локальную картину.</li>
</ul>

<h3>Путь</h3>
<p>Режим для impact analysis. Здесь viewer строит кратчайший путь между двумя объектами в пределах текущей базы.</p>
<ul>
<li>первый клик по узлу обычно делает его стартом;</li>
<li>второй клик по другому узлу — целью;</li>
<li>то же можно задать кнопками «Выбрать как старт» и «Выбрать как цель» в карточке узла;</li>
<li>после этого кнопка «Построить путь» запрашивает путь на backend и показывает его на canvas и справа списком шагов.</li>
</ul>

<h2>Правая колонка</h2>
<h3>Контекст</h3>
<p>Блок «Контекст» показывает:</p>
<ul>
<li>текущий режим анализа;</li>
<li>активную базу;</li>
<li>количество узлов и рёбер именно на canvas;</li>
<li>активные фильтры;</li>
<li>предупреждения о том, что результат усечён лимитами или путь не найден.</li>
</ul>

<h3>Узел</h3>
<p>Карточка узла показывает имя, тип, базу и доступные действия:</p>
<table>
<tr><th>Кнопка</th><th>Что делает</th><th>Когда использовать</th></tr>
<tr><td>Развернуть соседей</td><td>Догружает окрестность выбранного узла с учётом фильтров анализа.</td><td>Когда нужно увидеть, с чем узел связан напрямую или на глубину 2-3.</td></tr>
<tr><td>Закрепить узел / Снять закрепление</td><td>Помечает узел как важный и сохраняет его при очистке незакреплённых.</td><td>Когда собираете «рабочую сцену» вокруг нескольких ключевых объектов.</td></tr>
<tr><td>Выбрать как старт</td><td>Назначает узел стартом для поиска пути.</td><td>Используйте в режиме «Путь» либо заранее перед переключением режима.</td></tr>
<tr><td>Выбрать как цель</td><td>Назначает узел целью для поиска пути.</td><td>Используйте вместе со стартом перед построением пути.</td></tr>
</table>

<h3>Анализ</h3>
<p>Этот блок управляет тем, какие связи viewer будет раскрывать и учитывать при поиске пути.</p>
<table>
<tr><th>Настройка</th><th>Что делает</th><th>Как влияет на другие действия</th></tr>
<tr><td>Направление</td><td>Ограничивает раскрытие окрестности входящими, исходящими или обоими типами связей.</td><td>Влияет на «Развернуть соседей» и «Оставить только текущую окрестность». Для пути направление тоже передаётся на backend.</td></tr>
<tr><td>Скрыть BSL-файлы</td><td>Исключает узлы типа <code>bslFile</code> из анализа.</td><td>Уменьшает шум и действует и на окрестность, и на построение пути.</td></tr>
<tr><td>Типы связей</td><td>Оставляет только выбранные типы рёбер.</td><td>Если выбрать только «Использует», путь и окрестность будут строиться только по таким рёбрам.</td></tr>
<tr><td>Типы узлов</td><td>Оставляет только выбранные категории узлов.</td><td>Полезно, если нужен путь, например, только через метаданные без файлов или только через определённые типы объектов.</td></tr>
<tr><td>Оставить только текущую окрестность</td><td>Очищает canvas и строит вокруг выбранного узла свежую локальную подгрузку.</td><td>Сбрасывает шум прошлых раскрытий, но сохраняет активные фильтры и базу.</td></tr>
<tr><td>Очистить всё кроме закреплённых</td><td>Удаляет с canvas всё, что не закреплено.</td><td>Нужно, когда на графе уже накопилось слишком много переходов, но есть набор узлов, который надо сохранить.</td></tr>
</table>
<div class="warn"><p>Если фильтры слишком жёсткие, путь может не найтись даже при существующей связи в полном графе. В таких случаях сначала снимите часть фильтров и попробуйте снова.</p></div>

<h3>Путь</h3>
<table>
<tr><th>Элемент</th><th>Что делает</th></tr>
<tr><td>Старт</td><td>Показывает выбранный исходный узел.</td></tr>
<tr><td>Цель</td><td>Показывает выбранный конечный узел.</td></tr>
<tr><td>Макс. глубина</td><td>Ограничивает глубину BFS-поиска пути. Меньшее значение быстрее, большее — полнее, но тяжелее.</td></tr>
<tr><td>Построить путь</td><td>Запускает поиск кратчайшего пути на backend с текущими фильтрами.</td></tr>
<tr><td>Очистить путь</td><td>Сбрасывает текущий path result, но не стирает сам canvas.</td></tr>
<tr><td>Статус пути</td><td>Показывает, выбран ли старт, цель, найден ли путь и не сработали ли лимиты.</td></tr>
<tr><td>Шаги пути</td><td>Пошагово перечисляет найденную цепочку вида «узел → связь → узел».</td></tr>
</table>

<h2>Результаты поиска</h2>
<p>Панель результатов показывает узлы, найденные по строке поиска или по блоку «Типы». Клик по элементу:</p>
<ul>
<li>если узел уже есть на canvas — просто фокусирует его;</li>
<li>если узла ещё нет — подгружает его окрестность и затем фокусирует.</li>
</ul>

<h2>История навигации</h2>
<p>Кнопки ↶ и ↷ запоминают не текст запросов, а именно состояния viewer. В историю входят:</p>
<ul>
<li>поиск и переход по результату;</li>
<li>клики по узлам и снятие выделения;</li>
<li>раскрытие окрестности;</li>
<li>выбор старта и цели;</li>
<li>построение и очистка пути;</li>
<li>закрепление и очистка узлов;</li>
<li>смена режима, базы и ключевых фильтров.</li>
</ul>

<h2>Deep links</h2>
<p>Viewer можно открыть сразу в нужном контексте через параметры URL:</p>
<pre><code>?lang=ru|en
?db=Z01
?q=Номенклатура
?nodeId=Z01:Catalogs:Номенклатура
?mode=overview|path</code></pre>
<p>Типовые сценарии:</p>
<ul>
<li><code>?db=Z01&amp;q=Номенклатура</code> — сразу открыть базу и выполнить поиск;</li>
<li><code>?db=Z01&amp;nodeId=Z01:Catalogs:Номенклатура</code> — сразу загрузить окрестность конкретного узла;</li>
<li><code>?db=Z01&amp;mode=path</code> — открыть viewer сразу в режиме поиска пути.</li>
</ul>

<h2>Ограничения и предупреждения</h2>
<ul>
<li>Viewer анализирует только активную базу.</li>
<li>Если backend вернул <code>truncated=true</code>, значит результат подрезан лимитами узлов, рёбер или поиска пути.</li>
<li>Если путь не найден, это не всегда означает отсутствие зависимости — возможно, её скрывают текущие фильтры или ограничение <code>Макс. глубина</code>.</li>
<li>«Пересобрать» обновляет сам граф из BSL workspace, а не только текущее представление на экране.</li>
</ul>

<h2>Быстрые рабочие сценарии</h2>
<ol>
<li><b>Что изменится, если я меняю объект:</b> выберите объект как старт, зависимый объект как цель и постройте путь.</li>
<li><b>Кто использует этот объект:</b> в режиме «Обзор» переключите направление на «Входящие» и разверните окрестность.</li>
<li><b>Как очистить шум:</b> включите «Скрыть BSL-файлы», закрепите важные узлы и нажмите «Очистить всё кроме закреплённых».</li>
<li><b>Как вернуться к прошлому состоянию:</b> используйте ↶ и ↷ вместо ручного повторения поиска и раскрытий.</li>
</ol>
</body></html>"""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BSL Graph Documentation</title><style>{_DOC_STYLE}</style></head><body>
<a class="back" href="/?lang=en">&larr; Back to graph</a>
<h1>BSL Graph Documentation</h1>
<p>BSL Graph is a dedicated viewer for dependency analysis between 1C configuration objects and BSL modules. It works on top of a prebuilt graph and is meant for investigation, impact analysis, and path tracing rather than editing.</p>

<h2>What the graph shows</h2>
<p>Each node represents either a configuration object or a BSL file. Fill color reflects node type, border color reflects the database. The main edge types are:</p>
<ul>
<li><code>Uses</code> — one object references another object or symbol in code.</li>
<li><code>Contains BSL file</code> — an object is linked to its source module.</li>
</ul>
<div class="note"><p>The viewer always works inside the active database. Search, neighborhood expansion, and path analysis are all scoped to that DB.</p></div>

<h2>Top bar</h2>
<table>
<tr><th>Element</th><th>What it does</th><th>How it relates to other controls</th></tr>
<tr><td>Search field</td><td>Searches nodes by name. Multiple words are supported.</td><td>Results appear in the search results panel. Clicking a result focuses an existing node or loads its neighborhood.</td></tr>
<tr><td>List</td><td>Opens and closes the search results panel.</td><td>Useful when the graph is already populated and you want to jump to another object without a new query.</td></tr>
<tr><td>Clear</td><td>Clears the search field, canvas, search results, and current selection.</td><td>Does not change the active DB, language, or global filters. It resets the current view, not the underlying graph.</td></tr>
<tr><td>Overview / Path</td><td>Switches the main viewer mode.</td><td>Overview is for neighborhood exploration. Path is for shortest-path impact analysis.</td></tr>
<tr><td>↶ Back</td><td>Moves to the previous graph state.</td><td>The history tracks actual canvas states: clicks, expansions, path building, source/target selection, pinning, DB switch, mode switch, and key filters.</td></tr>
<tr><td>↷ Forward</td><td>Moves to the next graph state after a back step.</td><td>Works like browser history: once you go back and perform a new action, the forward branch is discarded.</td></tr>
<tr><td>RU / EN</td><td>Switches UI language and localized node/edge labels.</td><td>Data stays the same; the page reloads with a different <code>?lang=</code> parameter.</td></tr>
<tr><td>Docs</td><td>Opens this documentation page.</td><td>The documentation language follows the current UI language.</td></tr>
<tr><td>Rebuild</td><td>Triggers a full graph rebuild from the current BSL workspace.</td><td>Use this after BSL workspace changes when the underlying graph needs to be refreshed.</td></tr>
<tr><td>Database name</td><td>Shows the active database.</td><td>All analysis below is scoped to this database.</td></tr>
<tr><td>Node / edge counters</td><td>Show the total graph size for the active DB.</td><td>This is not the same as the number of currently visible canvas elements.</td></tr>
</table>

<h2>Left column</h2>
<h3>Databases</h3>
<p>The “Databases” block switches the active DB. When you switch databases, the canvas is cleared, the current path is reset, and the type list and stats are recalculated for the new DB.</p>
<div class="note"><p>If the viewer is opened via a deep link with <code>?db=...</code>, that database is selected automatically.</p></div>

<h3>Types</h3>
<p>The “Types” block is a quick entry point for category-based searches. Clicking a type runs a search for nodes of that metadata category, such as Catalog, Document, or Common module.</p>

<h2>Modes</h2>
<h3>Overview</h3>
<p>This mode is for neighborhood exploration. Core actions:</p>
<ul>
<li>single click — show details and highlight the local neighborhood;</li>
<li>double click — load and expand neighbors;</li>
<li>“Expand neighbours” — the same action from the node card;</li>
<li>“Keep only current neighborhood” — clear the canvas and rebuild a fresh local view around the selected node.</li>
</ul>

<h3>Path</h3>
<p>This mode is for impact analysis. The viewer builds the shortest path between two objects inside the current database.</p>
<ul>
<li>the first click usually sets the source node;</li>
<li>the second click on a different node sets the target;</li>
<li>the same can be done through “Set as source” and “Set as target” in the node card;</li>
<li>“Build path” sends the request to the backend and renders the path both on the canvas and in the step list.</li>
</ul>

<h2>Right column</h2>
<h3>Context</h3>
<p>The “Context” block shows:</p>
<ul>
<li>current analysis mode;</li>
<li>active database;</li>
<li>node and edge counts currently present on the canvas;</li>
<li>active filters;</li>
<li>warnings when results are truncated or a path was not found.</li>
</ul>

<h3>Node</h3>
<p>The node card shows the node name, type, DB, and actions:</p>
<table>
<tr><th>Button</th><th>What it does</th><th>When to use it</th></tr>
<tr><td>Expand neighbours</td><td>Loads the neighborhood of the selected node with current analysis filters applied.</td><td>Use it to inspect direct or depth-limited dependencies around the object.</td></tr>
<tr><td>Pin node / Unpin node</td><td>Marks the node as important and preserves it when non-pinned nodes are cleared.</td><td>Use it to build a stable working scene around several key objects.</td></tr>
<tr><td>Set as source</td><td>Assigns the node as the source for path analysis.</td><td>Use it in Path mode or prepare it before switching modes.</td></tr>
<tr><td>Set as target</td><td>Assigns the node as the target for path analysis.</td><td>Use it together with the source before building a path.</td></tr>
</table>

<h3>Analysis</h3>
<p>This block controls what kind of relationships the viewer will expand and consider for path search.</p>
<table>
<tr><th>Setting</th><th>What it does</th><th>How it affects other actions</th></tr>
<tr><td>Direction</td><td>Limits neighborhood expansion to incoming, outgoing, or both directions.</td><td>Affects “Expand neighbours” and “Keep only current neighborhood”. The same direction is also passed into path analysis.</td></tr>
<tr><td>Hide BSL files</td><td>Excludes <code>bslFile</code> nodes from analysis.</td><td>Reduces noise and affects both neighborhood expansion and shortest-path search.</td></tr>
<tr><td>Edge types</td><td>Keeps only selected relation kinds.</td><td>If only “Uses” is selected, both path and neighborhood will follow only those edges.</td></tr>
<tr><td>Node types</td><td>Keeps only selected node categories.</td><td>Useful when the path should pass only through specific kinds of metadata objects.</td></tr>
<tr><td>Keep only current neighborhood</td><td>Clears the canvas and rebuilds a fresh local view around the selected node.</td><td>Removes noise from previous exploration while preserving the current filters and DB.</td></tr>
<tr><td>Clear all except pinned</td><td>Removes every node from the canvas except pinned ones.</td><td>Use it when the graph becomes crowded but you need to keep a curated working set.</td></tr>
</table>
<div class="warn"><p>If filters are too restrictive, a valid path may not be found even though it exists in the full graph. In that case relax the filters and try again.</p></div>

<h3>Path</h3>
<table>
<tr><th>Element</th><th>What it does</th></tr>
<tr><td>Source</td><td>Shows the current source node.</td></tr>
<tr><td>Target</td><td>Shows the current target node.</td></tr>
<tr><td>Max depth</td><td>Limits BFS path search depth. Lower values are faster; larger values are broader but heavier.</td></tr>
<tr><td>Build path</td><td>Runs shortest-path search on the backend with the current filters.</td></tr>
<tr><td>Clear path</td><td>Clears the current path result but keeps the canvas.</td></tr>
<tr><td>Path status</td><td>Shows whether source and target are selected and whether the path was found or limited.</td></tr>
<tr><td>Path steps</td><td>Lists the resulting chain in the form “node → edge → node”.</td></tr>
</table>

<h2>Search results</h2>
<p>The search results panel shows nodes found by the search field or by the “Types” block. Clicking an item:</p>
<ul>
<li>focuses the node directly if it is already on the canvas;</li>
<li>loads its neighborhood first and then focuses it if it is not on the canvas yet.</li>
</ul>

<h2>Navigation history</h2>
<p>The ↶ and ↷ buttons remember actual viewer states rather than raw text queries. The tracked history includes:</p>
<ul>
<li>search and result selection;</li>
<li>node clicks and deselection;</li>
<li>neighborhood expansion;</li>
<li>source/target selection;</li>
<li>path build and path clear;</li>
<li>pinning and canvas cleanup;</li>
<li>mode, database, and key filter changes.</li>
</ul>

<h2>Deep links</h2>
<p>The viewer can be opened directly in a prepared context via URL parameters:</p>
<pre><code>?lang=ru|en
?db=Z01
?q=Номенклатура
?nodeId=Z01:Catalogs:Номенклатура
?mode=overview|path</code></pre>
<p>Typical scenarios:</p>
<ul>
<li><code>?db=Z01&amp;q=Номенклатура</code> — open the DB and immediately run a search;</li>
<li><code>?db=Z01&amp;nodeId=Z01:Catalogs:Номенклатура</code> — immediately load the neighborhood of a specific node;</li>
<li><code>?db=Z01&amp;mode=path</code> — open directly in path mode.</li>
</ul>

<h2>Limits and warnings</h2>
<ul>
<li>The viewer analyzes only the active database.</li>
<li>If the backend returns <code>truncated=true</code>, the result was cut by node, edge, or path search limits.</li>
<li>If a path is not found, it may still exist in the full graph but be hidden by current filters or the <code>Max depth</code> limit.</li>
<li>“Rebuild” refreshes the underlying graph from the BSL workspace; it does not merely redraw the current canvas.</li>
</ul>

<h2>Quick workflows</h2>
<ol>
<li><b>What changes if I modify this object:</b> set the object as source, a dependent object as target, and build the path.</li>
<li><b>Who uses this object:</b> switch Direction to Incoming in Overview mode and expand the neighborhood.</li>
<li><b>How to reduce noise:</b> enable “Hide BSL files”, pin important nodes, and use “Clear all except pinned”.</li>
<li><b>How to return to a previous state:</b> use ↶ and ↷ instead of manually repeating search and expansion steps.</li>
</ol>
</body></html>"""


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
        if parsed.path == "/docs" or parsed.path == "/ui/docs":
            lang = str((parse_qs(parsed.query).get("lang") or ["ru"])[0]).lower()
            body = render_docs("en" if lang == "en" else "ru").encode("utf-8")
            self._send_bytes(200, body, "text/html; charset=utf-8")
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

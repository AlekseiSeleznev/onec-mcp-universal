from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def _load_module(tmp_path: Path):
    workspace = tmp_path / "workspace"
    hostfs_home = tmp_path / "hostfs-home"
    data_dir = tmp_path / "data"
    workspace.mkdir()
    hostfs_home.mkdir()
    data_dir.mkdir()

    module_path = Path(__file__).resolve().parents[2] / "bsl-graph-lite" / "server.py"
    name = f"bsl_graph_lite_test_{tmp_path.name}"
    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)

    old_env = dict(os.environ)
    os.environ["GRAPH_WORKSPACE"] = str(workspace)
    os.environ["GRAPH_HOSTFS_HOME"] = str(hostfs_home)
    os.environ["GRAPH_STATE_FILE"] = str(data_dir / "graph.json")
    os.environ["GRAPH_REGISTRY_STATE_FILE"] = str(data_dir / "db_state.json")
    try:
        assert spec and spec.loader
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    return module, workspace, hostfs_home, data_dir


def test_rebuild_indexes_only_registered_databases(tmp_path):
    module, workspace, hostfs_home, data_dir = _load_module(tmp_path)

    registered_root = hostfs_home / "as" / "Z" / "Z01" / "CommonModules" / "ОбщийМодуль1" / "Ext"
    registered_root.mkdir(parents=True)
    (registered_root / "Module.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    orphan_root = workspace / "ORPHAN" / "CommonModules" / "ЛишнийМодуль" / "Ext"
    orphan_root.mkdir(parents=True)
    (orphan_root / "Module.bsl").write_text("Функция Лишняя() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    stats = module.STORE.stats()
    assert stats["totalNodes"] > 0
    assert stats["indexedDatabases"] == ["Z01"]

    results = module.STORE.search("Лишняя", None, 20)
    assert results["totalCount"] == 0


def test_search_and_related_work_for_registered_database(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    common_dir = hostfs_home / "as" / "Z" / "Z01" / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
    common_dir.mkdir(parents=True)
    (common_dir / "Module.bsl").write_text(
        "Функция НайтиНоменклатуру() Экспорт\n"
        "    Возврат Номенклатура;\n"
        "КонецФункции\n",
        encoding="utf-8",
    )

    catalog_dir = hostfs_home / "as" / "Z" / "Z01" / "Catalogs" / "Номенклатура" / "Ext"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    found = module.STORE.search("Номенклатура", ["catalog"], 20)
    assert found["totalCount"] == 1
    object_id = found["nodes"][0]["id"]

    related = module.STORE.related(object_id, 2)
    edge_types = {edge["type"] for edge in related["edges"]}
    assert related["totalCount"] >= 1
    assert "references" in edge_types or "containsFile" in edge_types


def test_http_related_decodes_url_encoded_node_ids(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    common_dir = hostfs_home / "as" / "Z" / "Z01" / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
    common_dir.mkdir(parents=True)
    (common_dir / "Module.bsl").write_text(
        "Функция НайтиНоменклатуру() Экспорт\n"
        "    Возврат Номенклатура;\n"
        "КонецФункции\n",
        encoding="utf-8",
    )

    catalog_dir = hostfs_home / "as" / "Z" / "Z01" / "Catalogs" / "Номенклатура" / "Ext"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    encoded = "/api/graph/related/Z01%3ACatalogs%3A%D0%9D%D0%BE%D0%BC%D0%B5%D0%BD%D0%BA%D0%BB%D0%B0%D1%82%D1%83%D1%80%D0%B0?depth=2"
    handler = module.Handler.__new__(module.Handler)
    handler.path = encoded
    payload: dict = {}
    handler._send = lambda code, body: payload.update({"code": code, "body": body})

    module.Handler.do_GET(handler)

    assert payload["code"] == 200
    assert payload["body"]["totalCount"] >= 1
    assert any(edge["type"] in {"references", "containsFile"} for edge in payload["body"]["edges"])


def test_rebuild_falls_back_to_bsl_search_snapshot_when_filesystem_tree_missing(tmp_path):
    module, _workspace, _hostfs_home, data_dir = _load_module(tmp_path)

    snapshot_dir = data_dir / "bsl-search-cache"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "snapshot.json").write_text(
        json.dumps(
            {
                "indexed_path": "/hostfs-home/as/Z/Z01",
                "symbols": [
                    {
                        "name": "Тест",
                        "kind": "Функция",
                        "params": "",
                        "export": True,
                        "file": "Catalogs/Номенклатура/Ext/ManagerModule.bsl",
                        "module": "Справочник.Номенклатура",
                        "line": 1,
                        "comment": "",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    stats = module.STORE.stats()
    assert stats["totalNodes"] >= 2
    assert stats["indexedDatabases"] == ["Z01"]

    found = module.STORE.search("Номенклатура", ["catalog"], 20)
    assert found["totalCount"] == 1


def test_stats_include_edge_counts_per_database(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    for db in ("Z01", "Z02"):
        common_dir = hostfs_home / "as" / "Z" / db / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
        common_dir.mkdir(parents=True)
        (common_dir / "Module.bsl").write_text(
            "Функция НайтиНоменклатуру() Экспорт\n"
            "    Возврат Номенклатура;\n"
            "КонецФункции\n",
            encoding="utf-8",
        )

        catalog_dir = hostfs_home / "as" / "Z" / db / "Catalogs" / "Номенклатура" / "Ext"
        catalog_dir.mkdir(parents=True)
        (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    },
                    {
                        "name": "Z02",
                        "slug": "Z02",
                        "connection": "Srvr=localhost;Ref=Z02;",
                        "project_path": "/hostfs-home/as/Z/Z02",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    stats = module.STORE.stats()
    assert stats["indexedDatabases"] == ["Z01", "Z02"]
    assert stats["edgesByDb"]["Z01"] > 0
    assert stats["edgesByDb"]["Z02"] > 0
    assert sum(stats["edgesByDb"].values()) == stats["totalEdges"]


def test_related_does_not_cross_database_boundaries_for_same_object_names(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    for db in ("Z01", "Z02"):
        common_dir = hostfs_home / "as" / "Z" / db / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
        common_dir.mkdir(parents=True)
        (common_dir / "Module.bsl").write_text(
            "Функция НайтиНоменклатуру() Экспорт\n"
            "    Возврат Номенклатура;\n"
            "КонецФункции\n",
            encoding="utf-8",
        )

        catalog_dir = hostfs_home / "as" / "Z" / db / "Catalogs" / "Номенклатура" / "Ext"
        catalog_dir.mkdir(parents=True)
        (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    },
                    {
                        "name": "Z02",
                        "slug": "Z02",
                        "connection": "Srvr=localhost;Ref=Z02;",
                        "project_path": "/hostfs-home/as/Z/Z02",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    related = module.STORE.related("Z01:Catalogs:Номенклатура", 1)
    dbs = {node["properties"].get("db", "") for node in related["nodes"]}

    assert dbs == {"Z01"}


def test_related_supports_direction_type_filters_and_truncation(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    common_dir = hostfs_home / "as" / "Z" / "Z01" / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
    common_dir.mkdir(parents=True)
    (common_dir / "Module.bsl").write_text(
        "Функция НайтиНоменклатуру() Экспорт\n"
        "    Возврат Номенклатура;\n"
        "КонецФункции\n",
        encoding="utf-8",
    )

    catalog_dir = hostfs_home / "as" / "Z" / "Z01" / "Catalogs" / "Номенклатура" / "Ext"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    incoming = module.STORE.related(
        "Z01:Catalogs:Номенклатура",
        2,
        direction="in",
        edge_types=["references"],
    )
    assert incoming["truncated"] is False
    assert all(edge["type"] == "references" for edge in incoming["edges"])
    assert any(node["id"] == "Z01:CommonModules:РаботаСНоменклатурой" for node in incoming["nodes"])

    limited = module.STORE.related(
        "Z01:Catalogs:Номенклатура",
        1,
        limit_nodes=1,
    )
    assert limited["truncated"] is True

    files_only = module.STORE.related(
        "Z01:Catalogs:Номенклатура",
        2,
        include_node_types=["bslFile"],
        limit_nodes=1,
    )
    assert files_only["truncated"] is False
    assert len(files_only["nodes"]) == 2
    assert any(node["type"] == "bslFile" for node in files_only["nodes"])


def test_http_related_parses_analysis_query_params(tmp_path):
    module, _workspace, hostfs_home, data_dir = _load_module(tmp_path)

    common_dir = hostfs_home / "as" / "Z" / "Z01" / "CommonModules" / "РаботаСНоменклатурой" / "Ext"
    common_dir.mkdir(parents=True)
    (common_dir / "Module.bsl").write_text(
        "Функция НайтиНоменклатуру() Экспорт\n"
        "    Возврат Номенклатура;\n"
        "КонецФункции\n",
        encoding="utf-8",
    )

    catalog_dir = hostfs_home / "as" / "Z" / "Z01" / "Catalogs" / "Номенклатура" / "Ext"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "ManagerModule.bsl").write_text("Функция Тест() Экспорт\nКонецФункции\n", encoding="utf-8")

    (data_dir / "db_state.json").write_text(
        json.dumps(
            {
                "active": "Z01",
                "databases": [
                    {
                        "name": "Z01",
                        "slug": "Z01",
                        "connection": "Srvr=localhost;Ref=Z01;",
                        "project_path": "/hostfs-home/as/Z/Z01",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    module.STORE.rebuild()

    handler = module.Handler.__new__(module.Handler)
    handler.path = (
        "/api/graph/related/Z01%3ACatalogs%3A%D0%9D%D0%BE%D0%BC%D0%B5%D0%BD%D0%BA%D0%BB%D0%B0%D1%82%D1%83%D1%80%D0%B0"
        "?depth=2&direction=in&edge_types=references&exclude_node_types=bslFile&limit_nodes=5"
    )
    payload: dict = {}
    handler._send = lambda code, body: payload.update({"code": code, "body": body})

    module.Handler.do_GET(handler)

    assert payload["code"] == 200
    assert all(edge["type"] == "references" for edge in payload["body"]["edges"])
    assert all(node["type"] != "bslFile" for node in payload["body"]["nodes"])


def test_path_finds_shortest_chain_with_filters(tmp_path):
    module, _workspace, _hostfs_home, _data_dir = _load_module(tmp_path)

    nodes = {
        "Z01:Catalogs:Номенклатура": {
            "id": "Z01:Catalogs:Номенклатура",
            "type": "catalog",
            "properties": {"db": "Z01", "name": "Номенклатура"},
        },
        "Z01:CommonModules:РаботаСНоменклатурой": {
            "id": "Z01:CommonModules:РаботаСНоменклатурой",
            "type": "commonModule",
            "properties": {"db": "Z01", "name": "РаботаСНоменклатурой"},
        },
        "Z01:Documents:ЗаказПокупателя": {
            "id": "Z01:Documents:ЗаказПокупателя",
            "type": "document",
            "properties": {"db": "Z01", "name": "ЗаказПокупателя"},
        },
        "Z01:file:CommonModules/РаботаСНоменклатурой/Ext/Module.bsl": {
            "id": "Z01:file:CommonModules/РаботаСНоменклатурой/Ext/Module.bsl",
            "type": "bslFile",
            "properties": {"db": "Z01", "name": "РаботаСНоменклатурой/Module.bsl"},
        },
    }
    edges = [
        module.Edge(
            "Z01:Documents:ЗаказПокупателя",
            "Z01:CommonModules:РаботаСНоменклатурой",
            "references",
            {},
        ),
        module.Edge(
            "Z01:CommonModules:РаботаСНоменклатурой",
            "Z01:Catalogs:Номенклатура",
            "references",
            {},
        ),
        module.Edge(
            "Z01:CommonModules:РаботаСНоменклатурой",
            "Z01:file:CommonModules/РаботаСНоменклатурой/Ext/Module.bsl",
            "containsFile",
            {},
        ),
    ]

    with module.STORE.lock:
        module.STORE.nodes = nodes
        module.STORE.edges = edges

    path = module.STORE.path_between(
        "Z01:Documents:ЗаказПокупателя",
        "Z01:Catalogs:Номенклатура",
        max_depth=4,
        edge_types=["references"],
        exclude_node_types=["bslFile"],
        max_visited=20,
    )

    assert path["pathFound"] is True
    assert path["hopCount"] == 2
    assert path["truncated"] is False
    assert [node["id"] for node in path["nodes"]] == [
        "Z01:Documents:ЗаказПокупателя",
        "Z01:CommonModules:РаботаСНоменклатурой",
        "Z01:Catalogs:Номенклатура",
    ]
    assert all(edge["type"] == "references" for edge in path["edges"])


def test_path_reports_reason_when_not_found_or_limited(tmp_path):
    module, _workspace, _hostfs_home, _data_dir = _load_module(tmp_path)

    with module.STORE.lock:
        module.STORE.nodes = {
            "Z01:A": {"id": "Z01:A", "type": "catalog", "properties": {"db": "Z01"}},
            "Z01:M": {"id": "Z01:M", "type": "commonModule", "properties": {"db": "Z01"}},
            "Z01:B": {"id": "Z01:B", "type": "document", "properties": {"db": "Z01"}},
            "Z02:B": {"id": "Z02:B", "type": "document", "properties": {"db": "Z02"}},
        }
        module.STORE.edges = [
            module.Edge("Z01:A", "Z01:M", "references", {}),
            module.Edge("Z01:M", "Z01:B", "references", {}),
        ]

    missing = module.STORE.path_between("Z01:A", "Z02:B", max_depth=3, max_visited=10)
    assert missing["pathFound"] is False
    assert missing["reason"] == "not_found"

    limited = module.STORE.path_between("Z01:A", "Z01:B", max_depth=3, max_visited=1)
    assert limited["pathFound"] is False
    assert limited["reason"] == "search_limit"
    assert limited["truncated"] is True


def test_http_path_endpoint_returns_payload(tmp_path):
    module, _workspace, _hostfs_home, _data_dir = _load_module(tmp_path)

    with module.STORE.lock:
        module.STORE.nodes = {
            "Z01:A": {"id": "Z01:A", "type": "catalog", "properties": {"db": "Z01"}},
            "Z01:B": {"id": "Z01:B", "type": "document", "properties": {"db": "Z01"}},
        }
        module.STORE.edges = [module.Edge("Z01:A", "Z01:B", "references", {})]

    handler = module.Handler.__new__(module.Handler)
    handler.path = "/api/graph/path"
    handler.headers = {"Content-Length": "91"}
    handler.rfile = __import__("io").BytesIO(
        json.dumps(
            {"sourceId": "Z01:A", "targetId": "Z01:B", "maxDepth": 3, "edgeTypes": ["references"]},
            ensure_ascii=False,
        ).encode("utf-8")
    )
    payload: dict = {}
    handler._send = lambda code, body: payload.update({"code": code, "body": body})

    module.Handler.do_POST(handler)

    assert payload["code"] == 200
    assert payload["body"]["pathFound"] is True
    assert payload["body"]["hopCount"] == 1


def test_docs_route_renders_localized_graph_dashboard_help(tmp_path):
    module, _workspace, _hostfs_home, _data_dir = _load_module(tmp_path)

    handler = module.Handler.__new__(module.Handler)
    handler.path = "/docs?lang=ru"
    payload: dict = {}
    handler._send_bytes = lambda code, body, mime, cache=False: payload.update(
        {"code": code, "body": body.decode("utf-8"), "mime": mime}
    )

    module.Handler.do_GET(handler)

    assert payload["code"] == 200
    assert payload["mime"].startswith("text/html")
    assert "Документация BSL Graph" in payload["body"]
    assert "Пересобрать" in payload["body"]
    assert "RU / EN" in payload["body"]
    assert "История навигации" in payload["body"]
    assert "Очистить всё кроме закреплённых" in payload["body"]
    assert "↶ Назад" in payload["body"]
    assert "Путь влияния" in payload["body"]
    assert "Что зависит от узла" in payload["body"]
    assert "Группировать BSL-файлы" in payload["body"]
    assert "Сцены" in payload["body"]
    assert "Пояснение связей" in payload["body"]
    assert "Показать BSL-файлы" in payload["body"]
    assert "Экспорт" in payload["body"]

    handler_en = module.Handler.__new__(module.Handler)
    handler_en.path = "/docs?lang=en"
    payload_en: dict = {}
    handler_en._send_bytes = lambda code, body, mime, cache=False: payload_en.update(
        {"code": code, "body": body.decode("utf-8"), "mime": mime}
    )

    module.Handler.do_GET(handler_en)

    assert payload_en["code"] == 200
    assert "BSL Graph Documentation" in payload_en["body"]
    assert "Rebuild" in payload_en["body"]
    assert "RU / EN" in payload_en["body"]
    assert "Navigation history" in payload_en["body"]
    assert "Clear all except pinned" in payload_en["body"]
    assert "↶ Back" in payload_en["body"]
    assert "Impact path" in payload_en["body"]
    assert "Reverse impact" in payload_en["body"]
    assert "Group BSL files" in payload_en["body"]
    assert "Scenes" in payload_en["body"]
    assert "Edge explanations" in payload_en["body"]
    assert "Show BSL files" in payload_en["body"]
    assert "Export" in payload_en["body"]

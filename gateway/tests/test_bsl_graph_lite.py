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

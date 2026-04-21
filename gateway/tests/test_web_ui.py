"""Tests for web_ui.py — HTML dashboard rendering."""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.web_ui import render_dashboard, _esc, _esc_js


# ---------------------------------------------------------------------------
# HTML escaping
# ---------------------------------------------------------------------------


class TestEscaping:
    def test_esc_html_entities(self):
        assert _esc('<script>alert("xss")</script>') == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'

    def test_esc_quotes(self):
        assert _esc("it's a \"test\"") == "it&#x27;s a &quot;test&quot;"

    def test_esc_empty(self):
        assert _esc("") == ""

    def test_esc_js_single_quotes(self):
        assert _esc_js("it's") == "it\\'s"

    def test_esc_js_backslash(self):
        assert _esc_js("path\\to") == "path\\\\to"

    def test_esc_js_newline(self):
        assert _esc_js("line1\nline2") == "line1\\nline2"


# ---------------------------------------------------------------------------
# Dashboard rendering
# ---------------------------------------------------------------------------


class TestRenderDashboard:
    def _render(self, lang="ru", **kwargs):
        defaults = {
            "backends_status": {"onec-toolkit": {"ok": True, "tools": 5}},
            "databases": [],
            "profiling_stats": {"total_queries": 0, "message": "No queries"},
            "cache_stats": {"entries": 0, "hits": 0, "misses": 0, "hit_rate": "0%", "ttl_seconds": 600},
            "anon_enabled": False,
            "config_items": [("PORT", "8080")],
            "container_info": [],
            "docker_system": {},
            "lang": lang,
        }
        defaults.update(kwargs)
        return render_dashboard(**defaults)

    def test_returns_html_string(self):
        html = self._render()
        assert isinstance(html, str)
        assert "<html" in html
        assert "</html>" in html

    def test_contains_title(self):
        html = self._render()
        assert "onec-mcp-universal" in html

    def test_russian_locale(self):
        html = self._render(lang="ru")
        assert "Статус" in html or "Информация" in html

    def test_english_locale(self):
        html = self._render(lang="en")
        assert "Status" in html or "Info" in html

    def test_database_listed(self):
        html = self._render(databases=[{
            "name": "TestDB",
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "http://localhost:6100/mcp",
            "lsp_container": "mcp-lsp-test",
            "epf_connected": True,
            "active": True,
            "backend_connected": True,
        }])
        assert "TestDB" in html
        assert 'data-epf-name="TestDB"' in html

    def test_xss_in_database_name(self):
        html = self._render(databases=[{
            "name": '<img src=x onerror=alert(1)>',
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "",
            "lsp_container": "",
            "epf_connected": False,
            "active": False,
            "backend_connected": False,
        }])
        assert "<img" not in html  # Should be escaped
        assert "&lt;img" in html

    def test_contains_version(self):
        from gateway.config import VERSION
        html = self._render()
        assert f"v{VERSION}" in html

    def test_contains_refresh_button(self):
        html = self._render()
        assert "reload()" in html or "Refresh" in html or "Обновить" in html
        assert "refreshDockerStats()" in html
        assert "Обновить статистику" in html or "Refresh stats" in html
        assert "function findByDataAttr(attr,value)" in html
        assert "findByDataAttr('data-container-memory', name)" in html

    def test_remove_warning_translated_ru(self):
        html = self._render(lang="ru")
        assert "без возможности восстановления" in html or "remove_warning" not in html

    def test_remove_warning_translated_en(self):
        html = self._render(lang="en")
        assert "permanently removed" in html or "remove_warning" not in html

    def test_showtoast_handles_error_objects(self):
        html = self._render()
        # showToast should use String() conversion for Error objects
        assert "msg.message" in html or "String(msg" in html

    def test_api_fetch_injects_bearer_token_for_dashboard_actions(self):
        html = self._render()
        assert "function apiFetch(" in html
        assert "sessionStorage.getItem('gateway_api_token')" in html
        assert "headers['Authorization']='Bearer '+_apiToken" in html
        assert "apiFetch('/api/action/connect-db'" in html
        assert "fetch('/api/action/connect-db'" not in html

    def test_epf_poll_refreshes_layout_on_backend_state_change(self):
        html = self._render(databases=[{
            "name": "TestDB",
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "http://localhost:6100/mcp",
            "lsp_container": "mcp-lsp-test",
            "epf_connected": True,
            "active": True,
            "backend_connected": False,
        }])
        assert "data-backend-connected=" in html
        assert "reloadNeeded" in html
        assert "if(reloadNeeded){setTimeout(reload,100);}" in html

    def test_action_progress_router_present(self):
        html = self._render()
        assert "function progressMessageForAction(u)" in html
        assert "showActionProgress(u)" in html
        assert "/api/action/disconnect" in html

    def test_progress_messages_present_for_non_act_buttons(self):
        html = self._render(lang="ru")
        assert "Подключаем базу..." in html
        assert "Сохраняем параметры базы..." in html
        assert "Сохраняем конфигурацию шлюза..." in html
        assert "Сохраняем папку выгрузки BSL..." in html

    def test_optional_services_section_renders_items(self):
        html = self._render(
            optional_services=[
                {"name": "bsl-lsp-bridge", "state": "err", "details": "image missing"},
                {"name": "bsl-graph", "state": "warn", "details": "optional profile is not running"},
            ]
        )
        assert "Опциональные сервисы" in html
        assert "bsl-lsp-bridge" in html
        assert "image missing" in html

    def test_optional_services_invalid_state_falls_back_to_warn(self):
        html = self._render(
            optional_services=[
                {"name": "custom", "state": "unexpected", "details": "details"}
            ]
        )
        assert 'class="dot warn"' in html

    def test_optional_services_without_details_render_name_only(self):
        html = self._render(
            optional_services=[
                {"name": "custom", "state": "ok", "details": ""}
            ]
        )
        assert "custom" in html

    def test_container_table_uses_container_status_header(self):
        html = self._render(
            container_info=[
                {
                    "name": "onec-mcp-gw",
                    "image": "onec-mcp-universal-gateway:latest",
                    "status": "running",
                    "running": True,
                    "memory_usage_bytes": 123,
                    "image_size_bytes": 456,
                }
            ]
        )
        assert "Статус контейнера" in html
        assert "<th>EPF</th>" not in html

    def test_optional_services_escape_html(self):
        html = self._render(
            optional_services=[
                {"name": "<script>alert(1)</script>", "state": "warn", "details": "<b>unsafe</b>"}
            ]
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "&lt;b&gt;unsafe&lt;/b&gt;" in html

    def test_container_table_shows_memory_and_disk_columns(self):
        html = self._render(
            container_info=[
                {
                    "name": "mcp-lsp-ERPPur_Local",
                    "image": "mcp-lsp-bridge-bsl:latest",
                    "status": "running",
                    "running": True,
                    "memory_usage_bytes": 2684354560,
                    "image_size_bytes": 2147483648,
                }
            ]
        )
        assert "RAM сейчас" in html
        assert "Образ на диске" in html
        assert "2.50 GB" in html
        assert "2.00 GB" in html

    def test_container_table_shows_na_for_missing_metrics(self):
        html = self._render(
            container_info=[
                {
                    "name": "onec-mcp-gw",
                    "image": "onec-mcp-universal-gateway:latest",
                    "status": "running",
                    "running": True,
                    "memory_usage_bytes": None,
                    "image_size_bytes": None,
                }
            ]
        )
        assert "н/д" in html

    def test_docker_summary_renders_placeholders_until_stats_loaded(self):
        html = self._render(docker_system={})
        assert 'id="docker-version"' in html
        assert 'id="docker-images-size"' in html
        assert "Статистика не загружена" in html or "Stats not loaded" in html

    def test_profiling_summary_renders_stats_when_queries_exist(self):
        html = self._render(profiling_stats={"total_queries": 3, "avg_ms": 12, "max_ms": 30, "slow_queries_over_5s": 1})
        assert ">3<" in html
        assert "12ms" in html
        assert "30ms" in html

    def test_docker_summary_renders_error_placeholder(self):
        html = self._render(docker_system={"error": "no docker"})
        assert "Статистика не загружена" in html or "Stats not loaded" in html

    def test_docker_summary_renders_loaded_volume_size(self):
        html = self._render(docker_system={"version": "24", "cpus": 4, "memory_gb": 8, "images_size_gb": 2, "volumes_size_gb": 1.5})
        assert "1.5 GB" in html

    def test_backend_connected_with_epf_disconnected_is_not_struck_and_has_disconnect_action(self):
        html = self._render(databases=[{
            "name": "TestDB",
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "http://localhost:6100/mcp",
            "lsp_container": "mcp-lsp-test",
            "epf_connected": False,
            "active": True,
            "backend_connected": True,
        }])
        assert "text-decoration:line-through" not in html
        assert "confirmDisconnect('TestDB')" in html
        assert "/api/action/reconnect?name=TestDB" not in html

    def test_backend_disconnected_with_epf_connected_is_struck_and_has_reconnect_action(self):
        html = self._render(databases=[{
            "name": "TestDB",
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "http://localhost:6100/mcp",
            "lsp_container": "mcp-lsp-test",
            "epf_connected": True,
            "active": False,
            "backend_connected": False,
        }])
        assert "text-decoration:line-through" in html
        assert "/api/action/reconnect?name=TestDB" in html

    def test_non_default_connected_database_shows_switch_button(self):
        html = self._render(databases=[{
            "name": "TestDB",
            "connection": "Srvr=srv;Ref=db;",
            "project_path": "/projects/test",
            "toolkit_url": "http://localhost:6100/mcp",
            "lsp_container": "mcp-lsp-test",
            "epf_connected": False,
            "active": False,
            "backend_connected": True,
        }])
        assert "/api/action/switch?name=TestDB" in html


def test_translation_dict_has_no_duplicate_keys_in_source():
    """Guard against silent overwrites in _T literal due duplicate keys."""
    source = Path(__file__).resolve().parents[1] / "gateway" / "web_ui.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    t_dict = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_T":
                    t_dict = node.value
                    break
        if t_dict is not None:
            break

    assert isinstance(t_dict, ast.Dict), "_T must be a dict literal"

    for lang_key, lang_val in zip(t_dict.keys, t_dict.values):
        if not (isinstance(lang_key, ast.Constant) and isinstance(lang_key.value, str)):
            continue
        if not isinstance(lang_val, ast.Dict):
            continue
        keys = [
            k.value for k in lang_val.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        assert not dupes, f"Duplicate translation keys for '{lang_key.value}': {dupes}"

"""
Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard. Supports Russian (default) and English.
Two tabs: Info (monitoring) and Settings (configuration).
"""
from __future__ import annotations

VERSION = "v0.4"
GITHUB_URL = "https://github.com/AlekseiSeleznev/onec-mcp-universal"

# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

_T = {
    "ru": {
        "title": "onec-mcp-universal",
        "subtitle": "MCP-шлюз для 1С:Предприятие",
        "tab_info": "Информация",
        "tab_settings": "Настройки",
        "btn_docs": "Документация",
        "btn_refresh": "Обновить",
        "h_backends": "Бэкенды",
        "h_databases": "Базы данных",
        "h_profiling": "Профилирование запросов",
        "h_cache": "Кеш метаданных",
        "h_anon": "Анонимизация",
        "h_system": "Система",
        "h_containers": "Docker-контейнеры",
        "h_config": "Конфигурация шлюза",
        "h_db_mgmt": "Управление базами",
        "h_actions": "Действия",
        "tools": "инструментов",
        "active": "активная",
        "enabled": "Включена",
        "disabled": "Выключена",
        "queries": "Запросов",
        "avg": "Среднее",
        "max": "Макс",
        "slow": "Медленных (>5с)",
        "entries": "Записей",
        "hit_rate": "Попадания",
        "ttl": "TTL",
        "no_backends": "Нет бэкендов",
        "no_databases": "Нет подключённых баз",
        "no_queries": "Запросы ещё не выполнялись",
        "epf_connected": "EPF подключена",
        "epf_waiting": "Ожидание EPF",
        "name": "Имя",
        "connection": "Подключение",
        "status": "Статус",
        "setting": "Параметр",
        "value": "Значение",
        "configured": "настроен",
        "not_configured": "не настроен",
        "license": "Лицензия",
        "project": "Проект на GitHub",
        "connect_db": "Подключить базу",
        "disconnect_db": "Отключить базу",
        "clear_cache": "Очистить кеш",
        "toggle_anon": "Вкл/выкл анонимизацию",
        "restart_hint": "Для применения изменений перезапустите шлюз",
        "doc_title": "Документация дашборда",
        "doc_info_title": "Вкладка «Информация»",
        "doc_info_text": "Показывает текущее состояние шлюза в реальном времени: статус бэкендов (зелёный — OK, красный — недоступен), подключённые базы данных 1С, статистику производительности запросов (среднее/максимальное время, количество медленных запросов), состояние кеша метаданных (количество записей, процент попаданий) и статус анонимизации персональных данных.",
        "doc_settings_title": "Вкладка «Настройки»",
        "doc_settings_text": "Управление базами данных (подключение/отключение через MCP-инструменты connect_database/disconnect_database), очистка кеша метаданных и включение/выключение анонимизации. Параметры конфигурации (.env) показаны для справки — для их изменения отредактируйте файл .env и перезапустите шлюз командой: docker compose restart gateway",
        "doc_api_title": "API эндпоинты",
        "doc_api_text": "/health — JSON-статус бэкендов, /mcp — MCP Streamable HTTP, /dashboard — этот дашборд, /api/export-bsl — REST для выгрузки BSL, /api/register — REST для регистрации EPF",
    },
    "en": {
        "title": "onec-mcp-universal",
        "subtitle": "MCP Gateway for 1C:Enterprise",
        "tab_info": "Information",
        "tab_settings": "Settings",
        "btn_docs": "Documentation",
        "btn_refresh": "Refresh",
        "h_backends": "Backends",
        "h_databases": "Databases",
        "h_profiling": "Query Profiling",
        "h_cache": "Metadata Cache",
        "h_anon": "Anonymization",
        "h_system": "System",
        "h_containers": "Docker Containers",
        "h_config": "Gateway Configuration",
        "h_db_mgmt": "Database Management",
        "h_actions": "Actions",
        "tools": "tools",
        "active": "active",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "queries": "Queries",
        "avg": "Average",
        "max": "Max",
        "slow": "Slow (>5s)",
        "entries": "Entries",
        "hit_rate": "Hit Rate",
        "ttl": "TTL",
        "no_backends": "No backends",
        "no_databases": "No databases connected",
        "no_queries": "No queries recorded yet",
        "epf_connected": "EPF connected",
        "epf_waiting": "Waiting for EPF",
        "name": "Name",
        "connection": "Connection",
        "status": "Status",
        "setting": "Setting",
        "value": "Value",
        "configured": "configured",
        "not_configured": "not configured",
        "license": "License",
        "project": "GitHub Project",
        "connect_db": "Connect Database",
        "disconnect_db": "Disconnect Database",
        "clear_cache": "Clear Cache",
        "toggle_anon": "Toggle Anonymization",
        "restart_hint": "Restart gateway to apply changes",
        "doc_title": "Dashboard Documentation",
        "doc_info_title": "Information Tab",
        "doc_info_text": "Shows real-time gateway state: backend status (green=OK, red=unavailable), connected 1C databases, query performance stats (avg/max time, slow query count), metadata cache state (entries, hit rate), and PII anonymization status.",
        "doc_settings_title": "Settings Tab",
        "doc_settings_text": "Manage databases (connect/disconnect via MCP tools connect_database/disconnect_database), clear metadata cache, and toggle anonymization. Config parameters (.env) are shown for reference — edit .env and restart: docker compose restart gateway",
        "doc_api_title": "API Endpoints",
        "doc_api_text": "/health — JSON backend status, /mcp — MCP Streamable HTTP, /dashboard — this dashboard, /api/export-bsl — BSL export REST, /api/register — EPF registration REST",
    },
}

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="{{lang}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>onec-mcp-universal dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}

/* Header */
.header{background:#1e293b;border-bottom:1px solid #334155;padding:16px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.header-left{display:flex;align-items:center;gap:16px}
.header h1{font-size:1.25rem;color:#f8fafc;white-space:nowrap}
.header .subtitle{color:#64748b;font-size:.85rem}
.header-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.lang-sw{display:flex;gap:0;border:1px solid #475569;border-radius:6px;overflow:hidden}
.lang-sw a{padding:4px 10px;font-size:.75rem;color:#94a3b8;border:none;display:block}
.lang-sw a.active{background:#334155;color:#f8fafc}
.btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:6px;font-size:.8rem;cursor:pointer;border:1px solid #475569;background:#1e293b;color:#94a3b8;text-decoration:none}
.btn:hover{background:#334155;color:#f8fafc;text-decoration:none}
.btn-primary{background:#0369a1;border-color:#0369a1;color:#fff}.btn-primary:hover{background:#0284c7}

/* Tabs */
.tabs{display:flex;gap:0;background:#1e293b;border-bottom:1px solid #334155;padding:0 24px}
.tab{padding:12px 20px;font-size:.85rem;color:#64748b;cursor:pointer;border-bottom:2px solid transparent;transition:all .15s}
.tab:hover{color:#94a3b8}
.tab.active{color:#38bdf8;border-bottom-color:#38bdf8}
.tab-content{display:none;padding:24px}.tab-content.active{display:block}

/* Grid & Cards */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;margin-bottom:20px}
.card{background:#1e293b;border-radius:10px;padding:20px;border:1px solid #334155}
.card h2{font-size:.7rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px;font-weight:600}
.status-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:.9rem}
.dot{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#22c55e}.dot.err{background:#ef4444}.dot.warn{background:#eab308}
.sname{font-weight:600;color:#f1f5f9}.stools{color:#64748b;font-size:.8rem}
.badge{display:inline-block;background:#164e63;color:#22d3ee;padding:1px 7px;border-radius:4px;font-size:.7rem;margin-left:6px}
.stat-value{font-size:1.6rem;font-weight:700;color:#f8fafc;line-height:1.2}
.stat-label{color:#64748b;font-size:.7rem;margin-top:2px}
.stats-row{display:flex;gap:28px;flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;color:#64748b;padding:8px 10px;border-bottom:1px solid #334155;font-weight:500;font-size:.75rem}
td{padding:8px 10px;border-bottom:1px solid #1e293b;color:#cbd5e1}
tr:hover td{background:#1e293b80}

/* Modal */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;justify-content:center;align-items:flex-start;padding-top:60px}
.modal-overlay.open{display:flex}
.modal{background:#1e293b;border:1px solid #334155;border-radius:12px;max-width:720px;width:90%;max-height:80vh;overflow-y:auto;padding:28px}
.modal h2{font-size:1.1rem;color:#f8fafc;margin-bottom:16px}
.modal h3{font-size:.9rem;color:#38bdf8;margin:16px 0 8px}
.modal p{color:#94a3b8;font-size:.85rem;line-height:1.6;margin-bottom:8px}
.modal code{background:#334155;padding:2px 6px;border-radius:4px;font-size:.8rem;color:#e2e8f0}
.modal-close{float:right;cursor:pointer;color:#64748b;font-size:1.2rem;background:none;border:none;padding:4px}
.modal-close:hover{color:#f8fafc}

/* Footer */
.footer{padding:16px 24px;text-align:center;color:#475569;font-size:.75rem;border-top:1px solid #1e293b}
.footer a{color:#64748b}.footer a:hover{color:#94a3b8}

/* Actions group */
.action-group{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.hint{color:#64748b;font-size:.75rem;margin-top:12px;font-style:italic}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
<div class="header-left">
<h1>{{title}}</h1>
<span class="subtitle">{{subtitle}}</span>
</div>
<div class="header-right">
<div class="lang-sw">
<a href="/dashboard?lang=ru" class="{{ru_active}}">RU</a>
<a href="/dashboard?lang=en" class="{{en_active}}">EN</a>
</div>
<button class="btn" onclick="openDocs()">{{btn_docs}}</button>
<button class="btn" onclick="location.reload()">{{btn_refresh}}</button>
</div>
</div>

<!-- Tabs -->
<div class="tabs">
<div class="tab active" onclick="switchTab('info')">{{tab_info}}</div>
<div class="tab" onclick="switchTab('settings')">{{tab_settings}}</div>
</div>

<!-- Tab: Info -->
<div class="tab-content active" id="tab-info">
<div class="grid">

<div class="card">
<h2>{{h_backends}}</h2>
{{backends_html}}
</div>

<div class="card">
<h2>{{h_databases}}</h2>
{{databases_html}}
</div>

<div class="card">
<h2>{{h_profiling}}</h2>
{{profiling_html}}
</div>

<div class="card">
<h2>{{h_cache}}</h2>
{{cache_html}}
</div>

<div class="card">
<h2>{{h_anon}}</h2>
<div class="status-row">
<div class="dot {{anon_dot}}"></div>
<span class="sname">{{anon_status}}</span>
</div>
</div>

<div class="card">
<h2>{{h_system}}</h2>
{{system_html}}
</div>

</div>
</div>

<!-- Tab: Settings -->
<div class="tab-content" id="tab-settings">
<div class="grid">

<div class="card">
<h2>{{h_config}}</h2>
<table>
<tr><th>{{setting}}</th><th>{{value}}</th></tr>
{{config_html}}
</table>
<p class="hint">{{restart_hint}}</p>
</div>

<div class="card">
<h2>{{h_actions}}</h2>
<div class="action-group">
<button class="btn btn-primary" onclick="apiAction('/api/action/clear-cache')">{{clear_cache}}</button>
<button class="btn" onclick="apiAction('/api/action/toggle-anon')">{{toggle_anon}}</button>
</div>
<h2 style="margin-top:20px">{{h_db_mgmt}}</h2>
{{db_mgmt_html}}
</div>

</div>
</div>

<!-- Docs Modal -->
<div class="modal-overlay" id="docs-modal">
<div class="modal">
<button class="modal-close" onclick="closeDocs()">&times;</button>
<h2>{{doc_title}}</h2>
<h3>{{doc_info_title}}</h3>
<p>{{doc_info_text}}</p>
<h3>{{doc_settings_title}}</h3>
<p>{{doc_settings_text}}</p>
<h3>{{doc_api_title}}</h3>
<p>{{doc_api_text}}</p>
</div>
</div>

<!-- Footer -->
<div class="footer">
{{title}} {{version}} &mdash;
<a href="{{github_url}}">{{project}}</a> &mdash;
<a href="{{github_url}}/blob/main/LICENSE">{{license}}: MIT</a> &mdash;
<a href="/health">API Health</a> &mdash;
<a href="/mcp">MCP</a>
</div>

<script>
function switchTab(id){
document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
document.getElementById('tab-'+id).classList.add('active');
event.target.classList.add('active');
}
function openDocs(){document.getElementById('docs-modal').classList.add('open')}
function closeDocs(){document.getElementById('docs-modal').classList.remove('open')}
document.getElementById('docs-modal').addEventListener('click',function(e){
if(e.target===this)closeDocs();
});
function apiAction(url){
fetch(url,{method:'POST'}).then(r=>r.json()).then(d=>{
alert(d.message||d.error||JSON.stringify(d));
location.reload();
}).catch(e=>alert('Error: '+e));
}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Render function
# ---------------------------------------------------------------------------

def render_dashboard(
    backends_status: dict,
    databases: list[dict],
    profiling_stats: dict,
    cache_stats: dict,
    anon_enabled: bool,
    config_items: list[tuple[str, str]],
    container_info: list[dict] | None = None,
    lang: str = "ru",
) -> str:
    t = _T.get(lang, _T["ru"])

    # Backends
    b_lines = []
    for name, info in backends_status.items():
        ok = info.get("ok", False)
        tools = info.get("tools", 0)
        is_active = info.get("active", False)
        badge = f'<span class="badge">{t["active"]}</span>' if is_active else ""
        dot = "ok" if ok else "err"
        b_lines.append(
            f'<div class="status-row"><div class="dot {dot}"></div>'
            f'<span class="sname">{name}</span>'
            f'<span class="stools">{tools} {t["tools"]}</span>{badge}</div>'
        )
    backends_html = "\n".join(b_lines) if b_lines else f'<span class="stools">{t["no_backends"]}</span>'

    # Databases
    if databases:
        rows = [f'<table><tr><th>{t["name"]}</th><th>{t["connection"]}</th><th>{t["status"]}</th></tr>']
        for db in databases:
            badge = f'<span class="badge">{t["active"]}</span>' if db.get("active") else ""
            epf = t["epf_connected"] if db.get("epf_connected") else t["epf_waiting"]
            conn = db.get("connection", "")[:45]
            rows.append(f'<tr><td>{db["name"]} {badge}</td><td><code>{conn}</code></td><td>{epf}</td></tr>')
        rows.append("</table>")
        databases_html = "\n".join(rows)
    else:
        databases_html = f'<span class="stools">{t["no_databases"]}</span>'

    # Profiling
    ps = profiling_stats
    if ps.get("total_queries", 0) > 0:
        profiling_html = f"""<div class="stats-row">
<div><div class="stat-value">{ps['total_queries']}</div><div class="stat-label">{t['queries']}</div></div>
<div><div class="stat-value">{ps['avg_ms']}ms</div><div class="stat-label">{t['avg']}</div></div>
<div><div class="stat-value">{ps['max_ms']}ms</div><div class="stat-label">{t['max']}</div></div>
<div><div class="stat-value">{ps.get('slow_queries_over_5s',0)}</div><div class="stat-label">{t['slow']}</div></div>
</div>"""
    else:
        profiling_html = f'<span class="stools">{t["no_queries"]}</span>'

    # Cache
    cs = cache_stats
    cache_html = f"""<div class="stats-row">
<div><div class="stat-value">{cs.get('entries',0)}</div><div class="stat-label">{t['entries']}</div></div>
<div><div class="stat-value">{cs.get('hit_rate','0%')}</div><div class="stat-label">{t['hit_rate']}</div></div>
<div><div class="stat-value">{cs.get('ttl_seconds',0)}s</div><div class="stat-label">{t['ttl']}</div></div>
</div>"""

    # Anonymization
    anon_dot = "ok" if anon_enabled else "warn"
    anon_status = t["enabled"] if anon_enabled else t["disabled"]

    # System info
    system_html = _render_system_info(container_info, t)

    # Config table
    config_rows = [f"<tr><td>{k}</td><td><code>{v}</code></td></tr>" for k, v in config_items]
    config_html = "\n".join(config_rows)

    # DB management
    if databases:
        db_lines = []
        for db in databases:
            db_lines.append(
                f'<div class="status-row"><span class="sname">{db["name"]}</span>'
                f'<button class="btn" style="margin-left:auto;font-size:.75rem" '
                f'onclick="apiAction(\'/api/action/disconnect?name={db["name"]}\')">'
                f'{t["disconnect_db"]}</button></div>'
            )
        db_mgmt_html = "\n".join(db_lines)
    else:
        db_mgmt_html = f'<span class="stools">{t["no_databases"]}</span>'

    # Fill template
    html = HTML_TEMPLATE
    for key, val in t.items():
        html = html.replace("{{" + key + "}}", val)
    html = html.replace("{{backends_html}}", backends_html)
    html = html.replace("{{databases_html}}", databases_html)
    html = html.replace("{{profiling_html}}", profiling_html)
    html = html.replace("{{cache_html}}", cache_html)
    html = html.replace("{{anon_dot}}", anon_dot)
    html = html.replace("{{anon_status}}", anon_status)
    html = html.replace("{{system_html}}", system_html)
    html = html.replace("{{config_html}}", config_html)
    html = html.replace("{{db_mgmt_html}}", db_mgmt_html)
    html = html.replace("{{version}}", VERSION)
    html = html.replace("{{github_url}}", GITHUB_URL)
    html = html.replace("{{lang}}", lang)
    html = html.replace("{{ru_active}}", "active" if lang == "ru" else "")
    html = html.replace("{{en_active}}", "active" if lang == "en" else "")
    return html


def _render_system_info(container_info: list[dict] | None, t: dict) -> str:
    if not container_info:
        return '<span class="stools">Docker info unavailable</span>'
    rows = ['<table><tr><th>Container</th><th>Image</th><th>Status</th><th>Size</th></tr>']
    for c in container_info:
        status_dot = "ok" if c.get("running") else "err"
        rows.append(
            f'<tr><td><div class="status-row" style="margin:0"><div class="dot {status_dot}"></div>'
            f'{c.get("name","")}</div></td>'
            f'<td><code>{c.get("image","")[:35]}</code></td>'
            f'<td>{c.get("status","")}</td>'
            f'<td>{c.get("size","")}</td></tr>'
        )
    rows.append("</table>")
    return "\n".join(rows)

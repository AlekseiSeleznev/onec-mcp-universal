"""
Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard. Supports Russian (default) and English.
Two tabs: Info + Settings. Documentation opens in /dashboard/docs.
"""
from __future__ import annotations

VERSION = "v0.4"
GITHUB_URL = "https://github.com/AlekseiSeleznev/onec-mcp-universal"

# SVG logo: stylized 1C cube + MCP connector
LOGO_SVG = (
    '<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">'
    '<rect x="2" y="6" width="20" height="20" rx="3" fill="#0ea5e9" opacity=".85"/>'
    '<text x="7" y="21" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="#fff">1C</text>'
    '<circle cx="26" cy="10" r="5" fill="#22c55e"/>'
    '<circle cx="26" cy="22" r="5" fill="#a855f7"/>'
    '<line x1="22" y1="16" x2="26" y2="10" stroke="#64748b" stroke-width="1.5"/>'
    '<line x1="22" y1="16" x2="26" y2="22" stroke="#64748b" stroke-width="1.5"/>'
    '<circle cx="22" cy="16" r="2" fill="#f8fafc"/>'
    '</svg>'
)

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
        "h_profiling": "Профилирование",
        "h_cache": "Кеш метаданных",
        "h_anon": "Анонимизация",
        "h_system": "Docker-контейнеры",
        "h_config": "Конфигурация шлюза",
        "h_db_mgmt": "Управление базами данных",
        "h_actions": "Действия",
        "tools": "инстр.",
        "active": "активная",
        "enabled": "Включена",
        "disabled": "Выключена",
        "queries": "Запросов",
        "avg": "Среднее",
        "max_label": "Макс",
        "slow": "Медл. (>5с)",
        "entries": "Записей",
        "hit_rate": "Попадания",
        "ttl": "TTL",
        "no_backends": "Нет бэкендов",
        "no_databases": "Нет подключённых баз",
        "no_queries": "Нет запросов",
        "epf_ok": "EPF OK",
        "epf_wait": "Ожид. EPF",
        "name": "Имя",
        "connection": "Подключение",
        "status": "Статус",
        "setting": "Параметр",
        "value": "Значение",
        "license": "Лицензия",
        "project": "GitHub",
        "connect_db": "Подключить базу",
        "disconnect_db": "Отключить",
        "clear_cache": "Очистить кеш",
        "toggle_anon": "Анонимизация вкл/выкл",
        "restart_hint": "Изменения .env применяются после: docker compose restart gateway",
        "add_db_name": "Имя базы",
        "add_db_conn": "Строка подключения",
        "add_db_path": "Путь к проекту",
        "add_db_btn": "Подключить",
        "container": "Контейнер",
        "image": "Образ",
        "no_containers": "Нет контейнеров",
    },
    "en": {
        "title": "onec-mcp-universal",
        "subtitle": "MCP Gateway for 1C:Enterprise",
        "tab_info": "Information",
        "tab_settings": "Settings",
        "btn_docs": "Docs",
        "btn_refresh": "Refresh",
        "h_backends": "Backends",
        "h_databases": "Databases",
        "h_profiling": "Profiling",
        "h_cache": "Metadata Cache",
        "h_anon": "Anonymization",
        "h_system": "Docker Containers",
        "h_config": "Gateway Configuration",
        "h_db_mgmt": "Database Management",
        "h_actions": "Actions",
        "tools": "tools",
        "active": "active",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "queries": "Queries",
        "avg": "Avg",
        "max_label": "Max",
        "slow": "Slow (>5s)",
        "entries": "Entries",
        "hit_rate": "Hit Rate",
        "ttl": "TTL",
        "no_backends": "No backends",
        "no_databases": "No databases",
        "no_queries": "No queries yet",
        "epf_ok": "EPF OK",
        "epf_wait": "EPF waiting",
        "name": "Name",
        "connection": "Connection",
        "status": "Status",
        "setting": "Setting",
        "value": "Value",
        "license": "License",
        "project": "GitHub",
        "connect_db": "Connect DB",
        "disconnect_db": "Disconnect",
        "clear_cache": "Clear Cache",
        "toggle_anon": "Toggle Anonymization",
        "restart_hint": "Changes to .env require: docker compose restart gateway",
        "add_db_name": "DB name",
        "add_db_conn": "Connection string",
        "add_db_path": "Project path",
        "add_db_btn": "Connect",
        "container": "Container",
        "image": "Image",
        "no_containers": "No containers",
    },
}

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="{{lang}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>onec-mcp-universal</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}
.header{background:#1e293b;border-bottom:1px solid #334155;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.header-left{display:flex;align-items:center;gap:12px}
.header h1{font-size:1.15rem;color:#f8fafc}
.header .sub{color:#64748b;font-size:.8rem}
.header-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.lang-sw{display:flex;border:1px solid #475569;border-radius:5px;overflow:hidden}
.lang-sw a{padding:3px 8px;font-size:.7rem;color:#94a3b8;display:block}
.lang-sw a.on{background:#334155;color:#f8fafc}
.btn{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:5px;font-size:.78rem;cursor:pointer;border:1px solid #475569;background:#1e293b;color:#94a3b8;text-decoration:none}
.btn:hover{background:#334155;color:#f8fafc;text-decoration:none}
.btn-p{background:#0369a1;border-color:#0369a1;color:#fff}.btn-p:hover{background:#0284c7}
.btn-d{background:#991b1b;border-color:#991b1b;color:#fff;font-size:.7rem;padding:3px 8px}.btn-d:hover{background:#b91c1c}
.tabs{display:flex;background:#1e293b;border-bottom:1px solid #334155;padding:0 24px}
.tab{padding:10px 18px;font-size:.82rem;color:#64748b;cursor:pointer;border-bottom:2px solid transparent}
.tab:hover{color:#94a3b8}.tab.on{color:#38bdf8;border-bottom-color:#38bdf8}
.tc{display:none;padding:20px 24px}.tc.on{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px;margin-bottom:16px}
.card{background:#1e293b;border-radius:8px;padding:16px;border:1px solid #334155;overflow:hidden}
.card h2{font-size:.68rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;font-weight:600}
.sr{display:flex;align-items:center;gap:7px;margin-bottom:6px;font-size:.85rem}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#22c55e}.dot.err{background:#ef4444}.dot.warn{background:#eab308}
.sn{font-weight:600;color:#f1f5f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
.st{color:#64748b;font-size:.78rem;white-space:nowrap}
.badge{display:inline-block;background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.65rem;margin-left:4px;white-space:nowrap}
.sv{font-size:1.4rem;font-weight:700;color:#f8fafc;line-height:1.2}
.sl{color:#64748b;font-size:.68rem;margin-top:1px}
.srow{display:flex;gap:24px;flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:.8rem;table-layout:fixed}
th{text-align:left;color:#64748b;padding:6px 8px;border-bottom:1px solid #334155;font-weight:500;font-size:.72rem;overflow:hidden;text-overflow:ellipsis}
td{padding:6px 8px;border-bottom:1px solid #1e293b;color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;word-break:break-all}
.footer{padding:12px 24px;text-align:center;color:#475569;font-size:.72rem;border-top:1px solid #1e293b}
.footer a{color:#64748b}.footer a:hover{color:#94a3b8}
.ag{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.hint{color:#64748b;font-size:.72rem;margin-top:10px;font-style:italic}
.form-row{display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap}
.form-row label{font-size:.75rem;color:#94a3b8;min-width:100px}
.form-row input{flex:1;min-width:150px;padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem}
.form-row input:focus{outline:none;border-color:#38bdf8}
</style>
</head>
<body>
<div class="header">
<div class="header-left">
{{logo}}
<div><h1>{{title}}</h1><span class="sub">{{subtitle}}</span></div>
</div>
<div class="header-right">
<div class="lang-sw">
<a href="/dashboard?lang=ru" class="{{ru_on}}">RU</a>
<a href="/dashboard?lang=en" class="{{en_on}}">EN</a>
</div>
<a class="btn" href="/dashboard/docs?lang={{lang}}" target="_blank">{{btn_docs}}</a>
<button class="btn" onclick="location.reload()">{{btn_refresh}}</button>
</div>
</div>
<div class="tabs">
<div class="tab on" onclick="stab(this,'info')">{{tab_info}}</div>
<div class="tab" onclick="stab(this,'settings')">{{tab_settings}}</div>
</div>
<div class="tc on" id="t-info">
<div class="grid">
<div class="card"><h2>{{h_backends}}</h2>{{backends_html}}</div>
<div class="card"><h2>{{h_databases}}</h2>{{databases_html}}</div>
<div class="card"><h2>{{h_profiling}}</h2>{{profiling_html}}</div>
<div class="card"><h2>{{h_cache}}</h2>{{cache_html}}</div>
<div class="card"><h2>{{h_anon}}</h2><div class="sr"><div class="dot {{anon_dot}}"></div><span class="sn">{{anon_status}}</span></div></div>
<div class="card"><h2>{{h_system}}</h2>{{system_html}}</div>
</div>
</div>
<div class="tc" id="t-settings">
<div class="grid">
<div class="card">
<h2>{{h_db_mgmt}}</h2>
{{db_mgmt_html}}
<h2 style="margin-top:16px">{{connect_db}}</h2>
<div class="form-row"><label>{{add_db_name}}</label><input id="db-name" placeholder="ERP_DEMO"></div>
<div class="form-row"><label>{{add_db_conn}}</label><input id="db-conn" placeholder="Srvr=localhost;Ref=ERP;"></div>
<div class="form-row"><label>{{add_db_path}}</label><input id="db-path" placeholder="/home/user/projects"></div>
<div class="ag"><button class="btn btn-p" onclick="connectDb()">{{add_db_btn}}</button></div>
</div>
<div class="card">
<h2>{{h_config}}</h2>
<table><tr><th style="width:40%">{{setting}}</th><th>{{value}}</th></tr>{{config_html}}</table>
<p class="hint">{{restart_hint}}</p>
</div>
<div class="card">
<h2>{{h_actions}}</h2>
<div class="ag">
<button class="btn btn-p" onclick="act('/api/action/clear-cache')">{{clear_cache}}</button>
<button class="btn" onclick="act('/api/action/toggle-anon')">{{toggle_anon}}</button>
</div>
</div>
</div>
</div>
<div class="footer">
{{logo}} {{title}} {{version}} &mdash;
<a href="{{github_url}}">{{project}}</a> &mdash;
<a href="{{github_url}}/blob/main/LICENSE">{{license}}: MIT</a> &mdash;
<a href="/health">Health</a> &mdash; <a href="/mcp">MCP</a>
</div>
<script>
function stab(el,id){
document.querySelectorAll('.tc').forEach(e=>e.classList.remove('on'));
document.querySelectorAll('.tab').forEach(e=>e.classList.remove('on'));
document.getElementById('t-'+id).classList.add('on');
el.classList.add('on');
}
function act(u){fetch(u,{method:'POST'}).then(r=>r.json()).then(d=>{alert(d.message||d.error||JSON.stringify(d));location.reload()}).catch(e=>alert(e))}
function connectDb(){
var n=document.getElementById('db-name').value.trim();
var c=document.getElementById('db-conn').value.trim();
var p=document.getElementById('db-path').value.trim();
if(!n||!c||!p){alert('Fill all fields');return}
fetch('/api/action/connect-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,connection:c,project_path:p})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error||JSON.stringify(d));if(d.ok)location.reload()}).catch(e=>alert(e))
}
</script>
</body></html>"""


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
        b_lines.append(
            f'<div class="sr"><div class="dot {"ok" if ok else "err"}"></div>'
            f'<span class="sn">{name}</span>'
            f'<span class="st">{tools} {t["tools"]}</span>{badge}</div>'
        )
    backends_html = "\n".join(b_lines) or f'<span class="st">{t["no_backends"]}</span>'

    # Databases — fixed table layout
    if databases:
        rows = [f'<table><colgroup><col style="width:25%"><col style="width:45%"><col style="width:30%"></colgroup>'
                f'<tr><th>{t["name"]}</th><th>{t["connection"]}</th><th>{t["status"]}</th></tr>']
        for db in databases:
            badge = f' <span class="badge">{t["active"]}</span>' if db.get("active") else ""
            epf = t["epf_ok"] if db.get("epf_connected") else t["epf_wait"]
            conn = db.get("connection", "")[:40]
            rows.append(f'<tr><td>{db["name"]}{badge}</td><td><code style="font-size:.72rem">{conn}</code></td><td>{epf}</td></tr>')
        rows.append("</table>")
        databases_html = "\n".join(rows)
    else:
        databases_html = f'<span class="st">{t["no_databases"]}</span>'

    # Profiling
    ps = profiling_stats
    if ps.get("total_queries", 0) > 0:
        profiling_html = f'<div class="srow"><div><div class="sv">{ps["total_queries"]}</div><div class="sl">{t["queries"]}</div></div><div><div class="sv">{ps["avg_ms"]}ms</div><div class="sl">{t["avg"]}</div></div><div><div class="sv">{ps["max_ms"]}ms</div><div class="sl">{t["max_label"]}</div></div><div><div class="sv">{ps.get("slow_queries_over_5s",0)}</div><div class="sl">{t["slow"]}</div></div></div>'
    else:
        profiling_html = f'<span class="st">{t["no_queries"]}</span>'

    # Cache
    cs = cache_stats
    cache_html = f'<div class="srow"><div><div class="sv">{cs.get("entries",0)}</div><div class="sl">{t["entries"]}</div></div><div><div class="sv">{cs.get("hit_rate","0%")}</div><div class="sl">{t["hit_rate"]}</div></div><div><div class="sv">{cs.get("ttl_seconds",0)}s</div><div class="sl">{t["ttl"]}</div></div></div>'

    anon_dot = "ok" if anon_enabled else "warn"
    anon_status = t["enabled"] if anon_enabled else t["disabled"]

    # System / containers
    if container_info:
        c_rows = [f'<table><colgroup><col style="width:35%"><col style="width:40%"><col style="width:25%"></colgroup>'
                  f'<tr><th>{t["container"]}</th><th>{t["image"]}</th><th>{t["status"]}</th></tr>']
        for c in container_info:
            dot = "ok" if c.get("running") else "err"
            img = c.get("image", "")[:30]
            c_rows.append(f'<tr><td><span class="sr" style="margin:0;gap:5px"><span class="dot {dot}"></span>{c["name"]}</span></td><td style="font-size:.72rem">{img}</td><td>{c.get("status","")}</td></tr>')
        c_rows.append("</table>")
        system_html = "\n".join(c_rows)
    else:
        system_html = f'<span class="st">{t["no_containers"]}</span>'

    # Config
    config_html = "\n".join(f"<tr><td>{k}</td><td><code>{v}</code></td></tr>" for k, v in config_items)

    # DB management
    if databases:
        db_lines = []
        for db in databases:
            db_lines.append(
                f'<div class="sr"><span class="sn">{db["name"]}</span>'
                f'<button class="btn-d" style="margin-left:auto" '
                f'onclick="act(\'/api/action/disconnect?name={db["name"]}\')">'
                f'{t["disconnect_db"]}</button></div>'
            )
        db_mgmt_html = "\n".join(db_lines)
    else:
        db_mgmt_html = f'<span class="st">{t["no_databases"]}</span>'

    html = HTML_TEMPLATE
    for key, val in t.items():
        html = html.replace("{{" + key + "}}", val)
    replacements = {
        "backends_html": backends_html, "databases_html": databases_html,
        "profiling_html": profiling_html, "cache_html": cache_html,
        "anon_dot": anon_dot, "anon_status": anon_status,
        "system_html": system_html, "config_html": config_html,
        "db_mgmt_html": db_mgmt_html, "version": VERSION,
        "github_url": GITHUB_URL, "lang": lang,
        "ru_on": "on" if lang == "ru" else "",
        "en_on": "on" if lang == "en" else "",
        "logo": LOGO_SVG,
    }
    for k, v in replacements.items():
        html = html.replace("{{" + k + "}}", v)
    return html


# --- Documentation page (separate URL) ---

DOCS_HTML = {
    "ru": r"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Документация — onec-mcp-universal</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;max-width:860px;margin:0 auto;line-height:1.7}
h1{color:#f8fafc;margin-bottom:8px;font-size:1.4rem}h2{color:#38bdf8;margin:24px 0 8px;font-size:1.1rem}h3{color:#94a3b8;margin:16px 0 6px;font-size:.95rem}
p,li{color:#94a3b8;font-size:.88rem;margin-bottom:6px}ul{padding-left:20px}code{background:#334155;padding:2px 6px;border-radius:3px;font-size:.82rem;color:#e2e8f0}
a{color:#38bdf8}.back{display:inline-block;margin-bottom:20px;font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.85rem}th,td{padding:6px 10px;border:1px solid #334155;text-align:left}th{background:#1e293b;color:#64748b}
</style></head><body>
<a class="back" href="/dashboard?lang=ru">&larr; Назад к дашборду</a>
<h1>Документация onec-mcp-universal</h1>
<p>Версия: """ + VERSION + """</p>

<h2>Вкладка «Информация»</h2>
<p>Показывает текущее состояние шлюза в реальном времени.</p>
<h3>Бэкенды</h3>
<p>Статус каждого MCP-бэкенда: <span style="color:#22c55e">зелёный</span> — работает, <span style="color:#ef4444">красный</span> — недоступен. Указано количество инструментов. Для per-database бэкендов показан признак «активная» — через какую базу маршрутизируются запросы.</p>
<h3>Базы данных</h3>
<p>Подключённые информационные базы 1С. Статус EPF — подключена ли обработка MCPToolkit в клиенте 1С.</p>
<h3>Профилирование</h3>
<p>Статистика execute_query: количество выполненных запросов, среднее и максимальное время, количество медленных (&gt;5 секунд).</p>
<h3>Кеш метаданных</h3>
<p>TTL-кеш для get_metadata. Количество записей, процент попаданий. Очистка — кнопка в настройках.</p>
<h3>Анонимизация</h3>
<p>Маскировка ПД (ФИО, ИНН, СНИЛС, телефоны, email) в ответах execute_query. Включается/выключается из настроек или через MCP-инструмент <code>enable_anonymization</code>.</p>
<h3>Docker-контейнеры</h3>
<p>Все контейнеры проекта с их статусом: onec-mcp-gw, onec-mcp-toolkit, onec-mcp-platform, onec-toolkit-{db}, mcp-lsp-{db}.</p>

<h2>Вкладка «Настройки»</h2>
<h3>Управление базами данных</h3>
<p>Список подключённых баз с кнопкой «Отключить». Форма подключения новой базы — укажите имя (латиница), строку подключения 1С (<code>Srvr=сервер;Ref=база;</code>) и путь к каталогу проекта на хосте.</p>
<h3>Конфигурация шлюза</h3>
<p>Текущие значения переменных окружения. Для изменения:</p>
<ul>
<li>Отредактируйте файл <code>.env</code> в корне проекта</li>
<li>Перезапустите шлюз: <code>docker compose restart gateway</code></li>
</ul>
<h3>Действия</h3>
<ul>
<li><b>Очистить кеш</b> — удаляет все закешированные результаты get_metadata</li>
<li><b>Анонимизация вкл/выкл</b> — переключает маскировку ПД в ответах</li>
</ul>

<h2>API-эндпоинты</h2>
<table>
<tr><th>Путь</th><th>Метод</th><th>Описание</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP — основной вход для AI-ассистентов</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>JSON-статус бэкендов</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI дашборд (этот интерфейс)</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>Документация (эта страница)</td></tr>
<tr><td><code>/api/export-bsl</code></td><td>POST</td><td>REST для выгрузки BSL (вызывается EPF)</td></tr>
<tr><td><code>/api/register</code></td><td>POST</td><td>REST для регистрации EPF</td></tr>
<tr><td><code>/api/action/{action}</code></td><td>POST</td><td>Действия дашборда (clear-cache, toggle-anon, disconnect, connect-db)</td></tr>
</table>

<h2>Переменные окружения (.env)</h2>
<table>
<tr><th>Переменная</th><th>По умолч.</th><th>Описание</th></tr>
<tr><td><code>GW_PORT</code></td><td>8080</td><td>Порт шлюза</td></tr>
<tr><td><code>LOG_LEVEL</code></td><td>INFO</td><td>Уровень логирования</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Включённые бэкенды</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>Ключ API 1С:Напарник (code.1c.ai)</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>TTL кеша метаданных (сек)</td></tr>
<tr><td><code>EXPORT_HOST_URL</code></td><td>http://localhost:8082</td><td>URL сервиса выгрузки BSL</td></tr>
<tr><td><code>PLATFORM_PATH</code></td><td>/opt/1cv8/...</td><td>Путь к платформе 1С</td></tr>
</table>
</body></html>""",

    "en": r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Documentation — onec-mcp-universal</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;max-width:860px;margin:0 auto;line-height:1.7}
h1{color:#f8fafc;margin-bottom:8px;font-size:1.4rem}h2{color:#38bdf8;margin:24px 0 8px;font-size:1.1rem}h3{color:#94a3b8;margin:16px 0 6px;font-size:.95rem}
p,li{color:#94a3b8;font-size:.88rem;margin-bottom:6px}ul{padding-left:20px}code{background:#334155;padding:2px 6px;border-radius:3px;font-size:.82rem;color:#e2e8f0}
a{color:#38bdf8}.back{display:inline-block;margin-bottom:20px;font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.85rem}th,td{padding:6px 10px;border:1px solid #334155;text-align:left}th{background:#1e293b;color:#64748b}
</style></head><body>
<a class="back" href="/dashboard?lang=en">&larr; Back to dashboard</a>
<h1>onec-mcp-universal Documentation</h1>
<p>Version: """ + VERSION + """</p>

<h2>Information Tab</h2>
<p>Real-time gateway monitoring.</p>
<h3>Backends</h3><p>MCP backend status: <span style="color:#22c55e">green</span>=OK, <span style="color:#ef4444">red</span>=down. Tool count shown. Per-DB backends show "active" badge.</p>
<h3>Databases</h3><p>Connected 1C databases. EPF status — whether MCPToolkit EPF is running in the 1C client.</p>
<h3>Profiling</h3><p>execute_query stats: count, avg/max duration, slow queries (&gt;5s).</p>
<h3>Metadata Cache</h3><p>TTL cache for get_metadata. Clear via Settings tab.</p>
<h3>Anonymization</h3><p>PII masking (FIO, INN, SNILS, phones, emails). Toggle in Settings or via <code>enable_anonymization</code> tool.</p>

<h2>Settings Tab</h2>
<h3>Database Management</h3><p>Connect/disconnect databases. Provide name (latin), connection string, and host project path.</p>
<h3>Configuration</h3><p>Current .env values. To change: edit <code>.env</code>, then <code>docker compose restart gateway</code>.</p>

<h2>API Endpoints</h2>
<table>
<tr><th>Path</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP endpoint</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>Backend health JSON</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>This dashboard</td></tr>
<tr><td><code>/api/action/{action}</code></td><td>POST</td><td>Dashboard actions</td></tr>
</table>

<h2>Environment Variables (.env)</h2>
<table>
<tr><th>Variable</th><th>Default</th><th>Description</th></tr>
<tr><td><code>GW_PORT</code></td><td>8080</td><td>Gateway port</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Enabled backends</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>1C:Naparnik API key</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>Metadata cache TTL (sec)</td></tr>
</table>
</body></html>""",
}


def render_docs(lang: str = "ru") -> str:
    return DOCS_HTML.get(lang, DOCS_HTML["ru"])

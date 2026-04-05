"""
Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard. Supports Russian (default) and English.
Two tabs: Info + Settings. Documentation opens in /dashboard/docs.
"""
from __future__ import annotations

VERSION = "v0.4"
GITHUB_URL = "https://github.com/AlekseiSeleznev/onec-mcp-universal"

# Simple text-based logo
LOGO_SVG = (
    '<svg width="36" height="24" viewBox="0 0 36 24" xmlns="http://www.w3.org/2000/svg">'
    '<rect width="36" height="24" rx="4" fill="#0ea5e9"/>'
    '<text x="18" y="17" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" '
    'font-size="13" font-weight="700" fill="#fff">1C</text>'
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
        "epf_ok": "Обработка подключена",
        "epf_wait": "Ожидание обработки",
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
        "edit_config": "Редактировать",
        "save_config": "Сохранить",
        "cancel": "Отмена",
        "config_edit_hint": "Перезапуск шлюза произойдёт автоматически.",
        "docker_version": "Docker",
        "docker_os": "ОС",
        "docker_cpus": "CPU",
        "docker_mem": "RAM",
        "docker_imgs": "Образы",
        "docker_imgs_size": "Размер образов",
        "docker_vols_size": "Размер томов",
        "running": "запущен",
        "stopped": "остановлен",
        "configure": "По умолч.",
        "add_db": "Добавить базу",
        "edit_db": "Изменить",
        "confirm_disconnect": "Отключить базу",
        "default_badge": "по умолч.",
        "edit_db_title": "Редактирование базы",
        "save": "Сохранить",
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
        "epf_ok": "Connected",
        "epf_wait": "Waiting for EPF",
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
        "edit_config": "Edit",
        "save_config": "Save",
        "cancel": "Cancel",
        "config_edit_hint": "Edit .env and click Save. Gateway restart required.",
        "docker_version": "Docker",
        "docker_os": "OS",
        "docker_cpus": "CPUs",
        "docker_mem": "RAM",
        "docker_imgs": "Images",
        "docker_imgs_size": "Images size",
        "docker_vols_size": "Volumes size",
        "running": "running",
        "stopped": "stopped",
        "configure": "Default",
        "add_db": "Add Database",
        "edit_db": "Edit",
        "confirm_disconnect": "Disconnect database",
        "default_badge": "default",
        "edit_db_title": "Edit Database",
        "save": "Save",
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
<div class="card"><h2>{{h_system}}</h2>{{docker_info_html}}{{system_html}}</div>
</div>
</div>
<div class="tc" id="t-settings">
<div class="grid">
<div class="card">
<h2>{{h_db_mgmt}}</h2>
{{db_mgmt_html}}
<div style="margin-top:12px;padding-top:12px;border-top:1px solid #334155">
<h2>{{add_db}}</h2>
<div class="form-row"><label>{{add_db_name}}</label><input id="db-name" placeholder="ERP_DEMO"></div>
<div class="form-row"><label>{{add_db_conn}}</label><input id="db-conn" placeholder="Srvr=localhost;Ref=ERP;"></div>
<div class="form-row"><label>{{add_db_path}}</label><input id="db-path" placeholder="/home/user/projects"></div>
<div class="ag"><button class="btn btn-p" onclick="connectDb()">{{add_db_btn}}</button></div>
</div>
</div>
<div class="card">
<h2>{{h_config}} <button class="btn" style="float:right;font-size:.7rem" onclick="editEnv()">{{edit_config}}</button></h2>
<div id="config-view">
<table><tr><th style="width:40%">{{setting}}</th><th>{{value}}</th></tr>{{config_html}}</table>
</div>
<div id="config-edit" style="display:none">
<textarea id="env-editor" style="width:100%;height:250px;background:#0f172a;color:#e2e8f0;border:1px solid #475569;border-radius:4px;padding:8px;font-family:monospace;font-size:.8rem;resize:vertical"></textarea>
<div class="ag">
<button class="btn btn-p" onclick="saveEnv()">{{save_config}}</button>
<button class="btn" onclick="cancelEnv()">{{cancel}}</button>
</div>
<p class="hint">{{config_edit_hint}}</p>
</div>
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
{{title}} {{version}} &mdash;
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
location.hash=id;
}
// Restore tab from hash on load
(function(){var h=location.hash.replace('#','');if(h){
var tab=document.querySelector('.tab');
document.querySelectorAll('.tc').forEach(e=>e.classList.remove('on'));
document.querySelectorAll('.tab').forEach(e=>e.classList.remove('on'));
var el=document.getElementById('t-'+h);if(el){el.classList.add('on');
document.querySelectorAll('.tab').forEach(t=>{if(t.textContent&&t.onclick&&t.onclick.toString().includes(h))t.classList.add('on')})
}else{document.querySelector('.tc').classList.add('on');document.querySelector('.tab').classList.add('on')}
}})();
function act(u){fetch(u,{method:'POST'}).then(r=>r.json()).then(d=>{alert(d.message||d.error||JSON.stringify(d));location.hash=location.hash;location.reload()}).catch(e=>alert(e))}
function connectDb(){
var n=document.getElementById('db-name').value.trim();
var c=document.getElementById('db-conn').value.trim();
var p=document.getElementById('db-path').value.trim();
if(!n||!c||!p){alert('Fill all fields');return}
fetch('/api/action/connect-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,connection:c,project_path:p})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error||JSON.stringify(d));if(d.ok)location.reload()}).catch(e=>alert(e))
}
function editDb(name,conn,path){
var nc=prompt('{{add_db_conn}}:',conn);if(!nc)return;
var np=prompt('{{add_db_path}}:',path);if(!np)return;
fetch('/api/action/edit-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,connection:nc,project_path:np})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error);location.hash='settings';location.reload()}).catch(e=>alert(e))
}
function editEnv(){
fetch('/api/action/get-env',{method:'POST'}).then(r=>r.json()).then(d=>{
document.getElementById('env-editor').value=d.env||'';
document.getElementById('config-view').style.display='none';
document.getElementById('config-edit').style.display='block';
}).catch(e=>alert(e))
}
function saveEnv(){
var c=document.getElementById('env-editor').value;
fetch('/api/action/save-env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error);cancelEnv()}).catch(e=>alert(e))
}
function cancelEnv(){
document.getElementById('config-view').style.display='block';
document.getElementById('config-edit').style.display='none';
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
    docker_system: dict | None = None,
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
            badge = f' <span class="badge">{t["default_badge"]}</span>' if db.get("active") else ""
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

    # System / containers — translate status
    status_map = {"running": t["running"], "exited": t["stopped"], "created": t["stopped"]}
    if container_info:
        c_rows = [f'<table><colgroup><col style="width:35%"><col style="width:40%"><col style="width:25%"></colgroup>'
                  f'<tr><th>{t["container"]}</th><th>{t["image"]}</th><th>{t["status"]}</th></tr>']
        for c in container_info:
            dot = "ok" if c.get("running") else "err"
            img = c.get("image", "")[:30]
            st = status_map.get(c.get("status", ""), c.get("status", ""))
            c_rows.append(f'<tr><td><span class="sr" style="margin:0;gap:5px"><span class="dot {dot}"></span>{c["name"]}</span></td><td style="font-size:.72rem">{img}</td><td>{st}</td></tr>')
        c_rows.append("</table>")
        system_html = "\n".join(c_rows)
    else:
        system_html = f'<span class="st">{t["no_containers"]}</span>'

    # Docker system info
    if docker_system and not docker_system.get("error"):
        ds = docker_system
        vol_size = ds.get("volumes_size_gb", 0)
        vol_str = f"{vol_size} GB" if vol_size >= 0.01 else "<1 MB"
        docker_info_html = (
            f'<div class="srow" style="margin-bottom:12px">'
            f'<div><div class="sv" style="font-size:1rem">{ds.get("version","?")}</div><div class="sl">{t["docker_version"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{ds.get("cpus",0)}</div><div class="sl">{t["docker_cpus"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{ds.get("memory_gb",0)} GB</div><div class="sl">{t["docker_mem"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{ds.get("images_size_gb",0)} GB</div><div class="sl">{t["docker_imgs_size"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{vol_str}</div><div class="sl">{t["docker_vols_size"]}</div></div>'
            f'</div>'
        )
    else:
        docker_info_html = ""

    # Config
    config_html = "\n".join(f"<tr><td>{k}</td><td><code>{v}</code></td></tr>" for k, v in config_items)

    # DB management — with Configure + Disconnect buttons
    if databases:
        db_lines = []
        for db in databases:
            is_default = db.get("active", False)
            badge = f' <span class="badge">{t["default_badge"]}</span>' if is_default else ""
            epf_st = t["epf_ok"] if db.get("epf_connected") else t["epf_wait"]
            conn = db.get("connection", "")
            proj = db.get("project_path", "")
            conn_short = conn[:40]
            # Buttons
            default_btn = ""
            if not is_default:
                default_btn = (
                    f'<button class="btn" style="font-size:.68rem;padding:2px 8px" '
                    f'onclick="act(\'/api/action/switch?name={db["name"]}\')">{t["configure"]}</button>'
                )
            edit_btn = (
                f'<button class="btn" style="font-size:.68rem;padding:2px 8px" '
                f'onclick="editDb(\'{db["name"]}\',\'{conn}\',\'{proj}\')">{t["edit_db"]}</button>'
            )
            disc_btn = (
                f'<button class="btn-d" '
                f'onclick="if(confirm(\'{t["confirm_disconnect"]} {db["name"]}?\'))act(\'/api/action/disconnect?name={db["name"]}\')">'
                f'{t["disconnect_db"]}</button>'
            )
            db_lines.append(
                f'<div class="sr" style="gap:6px;flex-wrap:wrap">'
                f'<span class="sn">{db["name"]}{badge}</span>'
                f'<span class="st">{conn_short} — {epf_st}</span>'
                f'<span style="margin-left:auto;display:flex;gap:4px">'
                f'{edit_btn}{default_btn}{disc_btn}'
                f'</span></div>'
            )
        db_mgmt_html = "\n".join(db_lines)
    else:
        db_mgmt_html = f'<span class="st">{t["no_databases"]}</span>'

    html = HTML_TEMPLATE
    for key, val in t.items():
        html = html.replace("{{" + key + "}}", val)
    replacements = {
        "backends_html": backends_html, "databases_html": databases_html, "docker_info_html": docker_info_html,
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

_DOC_STYLE = """*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:32px;max-width:900px;margin:0 auto;line-height:1.7}
h1{color:#f8fafc;margin-bottom:8px;font-size:1.5rem}h2{color:#38bdf8;margin:28px 0 10px;font-size:1.15rem;border-bottom:1px solid #334155;padding-bottom:6px}h3{color:#94a3b8;margin:18px 0 6px;font-size:.95rem}
p,li{color:#94a3b8;font-size:.88rem;margin-bottom:8px}ul,ol{padding-left:24px;margin-bottom:12px}code{background:#334155;padding:2px 6px;border-radius:3px;font-size:.82rem;color:#e2e8f0}
pre{background:#1e293b;padding:12px 16px;border-radius:6px;overflow-x:auto;margin:10px 0;border:1px solid #334155}pre code{background:none;padding:0}
a{color:#38bdf8}.back{display:inline-block;margin-bottom:20px;font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:.85rem}th,td{padding:8px 10px;border:1px solid #334155;text-align:left}th{background:#1e293b;color:#64748b}
.note{background:#1e293b;border-left:3px solid #38bdf8;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0}
.warn{background:#1e293b;border-left:3px solid #eab308;padding:10px 14px;margin:12px 0;border-radius:0 4px 4px 0}"""

DOCS_HTML = {
    "ru": r"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Документация — onec-mcp-universal</title>
<style>""" + _DOC_STYLE + """</style></head><body>
<a class="back" href="/dashboard?lang=ru">&larr; Назад к дашборду</a>
<h1>Документация onec-mcp-universal</h1>
<p>Версия: """ + VERSION + """ | <a href="https://github.com/AlekseiSeleznev/onec-mcp-universal">GitHub</a> | Лицензия: MIT</p>

<h2>Обзор</h2>
<p>onec-mcp-universal — единый MCP-шлюз для работы с 1С:Предприятие из AI-ассистентов (Claude Code, Cursor, Windsurf). Шлюз объединяет несколько бэкендов в один MCP-сервер по адресу <code>http://localhost:8080/mcp</code>.</p>
<div class="note"><p><b>Как это работает:</b> AI-ассистент отправляет запросы на шлюз → шлюз маршрутизирует их к нужному бэкенду (данные 1С, навигация по коду, документация платформы) → результат возвращается AI.</p></div>

<h2>Вкладка «Информация»</h2>

<h3>Бэкенды</h3>
<p>Каждый бэкенд — отдельный MCP-сервер, который предоставляет набор инструментов:</p>
<ul>
<li><b>onec-toolkit</b> (8 инструментов) — запросы к БД, выполнение кода, метаданные, журнал регистрации, права доступа. Работает через обработку MCPToolkit.epf в клиенте 1С.</li>
<li><b>platform-context</b> (5 инструментов) — документация API платформы 1С: поиск методов, описания типов, конструкторы.</li>
<li><b>bsl-lsp-bridge</b> (14 инструментов) — навигация по BSL-коду: поиск символов, определения, граф вызовов, диагностика, переименование.</li>
</ul>
<p>Статус: <span style="color:#22c55e">зелёный</span> = работает, <span style="color:#ef4444">красный</span> = недоступен. При подключении базы создаются дополнительные per-database бэкенды (onec-toolkit-{db} + mcp-lsp-{db}).</p>

<h3>Базы данных</h3>
<p>Список подключённых информационных баз 1С. Каждая база имеет:</p>
<ul>
<li><b>Имя</b> — идентификатор (латиница, используется в именах контейнеров)</li>
<li><b>Подключение</b> — строка подключения 1С (<code>Srvr=сервер;Ref=база;</code>)</li>
<li><b>Статус EPF</b> — подключена ли обработка MCPToolkit в клиенте 1С. «Ожид. EPF» означает, что обработку нужно открыть и нажать «Подключить к прокси».</li>
</ul>
<p>База с меткой <span style="background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.75rem">активная</span> — через неё маршрутизируются все запросы (execute_query, symbol_explore и т.д.).</p>

<h3>Профилирование запросов</h3>
<p>Автоматический замер времени каждого <code>execute_query</code>:</p>
<ul>
<li><b>Запросов</b> — общее количество выполненных запросов с момента запуска шлюза</li>
<li><b>Среднее</b> — среднее время выполнения в миллисекундах</li>
<li><b>Макс</b> — максимальное время выполнения</li>
<li><b>Медленных (&gt;5с)</b> — количество запросов, выполнявшихся более 5 секунд</li>
</ul>
<p>Каждый ответ execute_query автоматически получает поле <code>_profiling</code> с длительностью и подсказками по оптимизации (SELECT *, отсутствие WHERE, много JOIN и т.д.).</p>

<h3>Кеш метаданных</h3>
<p>Результаты <code>get_metadata</code> кешируются на 10 минут (настраивается через <code>METADATA_CACHE_TTL</code>). Повторный запрос тех же метаданных возвращается мгновенно. Очистить кеш можно кнопкой в настройках или через MCP-инструмент <code>invalidate_metadata_cache</code>.</p>

<h3>Анонимизация</h3>
<p>Маскировка персональных данных в ответах execute_query, execute_code, get_object_by_link, get_event_log:</p>
<ul>
<li>ФИО (Иванов Иван Иванович → Петров Сергей Александрович)</li>
<li>ИНН (10 и 12 цифр)</li>
<li>СНИЛС (XXX-XXX-XXX XX)</li>
<li>Телефоны (+7 ...)</li>
<li>Email</li>
<li>Названия компаний (ООО "Ромашка" → ООО "Альфа")</li>
</ul>
<p>Маппинг стабильный: одно и то же значение всегда заменяется одним и тем же фейком. Включается кнопкой в настройках или через MCP-инструмент <code>enable_anonymization</code>.</p>

<h3>Docker-контейнеры</h3>
<p>Информация о Docker-демоне (версия, CPU, RAM, размер образов/томов) и список контейнеров проекта:</p>
<ul>
<li><b>onec-mcp-gw</b> — MCP-шлюз (этот сервер)</li>
<li><b>onec-mcp-toolkit</b> — статический бэкенд данных (порт 6003)</li>
<li><b>onec-mcp-platform</b> — документация платформы (порт 8081)</li>
<li><b>onec-toolkit-{db}</b> — динамический бэкенд данных для каждой базы</li>
<li><b>mcp-lsp-{db}</b> — BSL Language Server для каждой базы</li>
</ul>

<h2>Вкладка «Настройки»</h2>

<h3>Управление базами данных</h3>
<p>Список подключённых баз с кнопками:</p>
<ul>
<li><b>Настроить</b> — переключение активной базы (через MCP-инструмент <code>switch_database</code>)</li>
<li><b>Отключить</b> — остановка и удаление Docker-контейнеров базы. Данные базы 1С и BSL-исходники не затрагиваются.</li>
</ul>
<p><b>Добавить базу</b> — форма подключения новой базы:</p>
<ul>
<li><b>Имя базы</b> — уникальный идентификатор (латиница, цифры, дефис, подчёркивание). Примеры: ERP, ZUP_TEST, buh-main</li>
<li><b>Строка подключения</b> — формат 1С: <code>Srvr=имя_сервера;Ref=имя_базы;</code> или <code>File=/путь/к/базе</code></li>
<li><b>Путь к проекту</b> — абсолютный путь на хосте, куда будут выгружены BSL-исходники</li>
</ul>
<div class="warn"><p><b>После подключения базы:</b> откройте обработку <code>1c/MCPToolkit.epf</code> в клиенте 1С и нажмите «Подключить к прокси». Для навигации по коду также нажмите «Выгрузить BSL».</p></div>

<h3>Конфигурация шлюза</h3>
<p>Текущие значения переменных окружения из файла <code>.env</code>. Нажмите <b>«Редактировать»</b> для изменения:</p>
<ol>
<li>Откроется текстовый редактор с содержимым .env</li>
<li>Внесите изменения (формат: <code>ПЕРЕМЕННАЯ=значение</code>, по одной на строку)</li>
<li>Нажмите «Сохранить»</li>
<li>Перезапустите шлюз: <code>docker compose restart gateway</code></li>
</ol>
<div class="note"><p>На Linux файл .env монтируется в контейнер. На Windows используйте <code>docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d</code>.</p></div>

<h3>Действия</h3>
<ul>
<li><b>Очистить кеш</b> — удаляет все закешированные результаты get_metadata. Используйте после изменения структуры конфигурации 1С.</li>
<li><b>Анонимизация вкл/выкл</b> — переключает маскировку персональных данных в ответах. Не требует перезапуска.</li>
</ul>

<h2>Обработка MCPToolkit.epf</h2>
<p>Внешняя обработка для клиента 1С:Предприятие. Является посредником между шлюзом и информационной базой.</p>
<h3>Элементы интерфейса</h3>
<ul>
<li><b>Адрес сервера</b> — URL toolkit-бэкенда (заполняется автоматически при подключении к прокси)</li>
<li><b>Подключиться / Отключиться</b> — управление long-polling соединением с toolkit</li>
<li><b>Определить базу</b> — автоопределение параметров текущей базы (сервер, имя)</li>
<li><b>Подключить к прокси</b> — регистрация в шлюзе (отправляет /api/register, получает toolkit_poll_url)</li>
<li><b>Выгрузить BSL</b> — выгрузка исходников конфигурации для навигации по коду</li>
<li><b>Журнал событий</b> — лог операций, ошибок, статусов подключения</li>
</ul>
<h3>Вкладка «Анонимизация»</h3>
<p>Настройка правил точной анонимизации (regex-паттерны, словари замен). Работает на стороне EPF независимо от серверной анонимизации шлюза.</p>

<h2>MCP-инструменты (полный список)</h2>
<table>
<tr><th>Инструмент</th><th>Описание</th></tr>
<tr><td><code>execute_query</code></td><td>Запрос к БД на языке 1С с параметрами и лимитами</td></tr>
<tr><td><code>execute_code</code></td><td>Выполнение произвольного кода 1С (сервер или клиент)</td></tr>
<tr><td><code>get_metadata</code></td><td>Структура конфигурации: реквизиты, типы, табличные части</td></tr>
<tr><td><code>get_event_log</code></td><td>Чтение журнала регистрации с фильтрацией</td></tr>
<tr><td><code>get_object_by_link</code></td><td>Получение объекта по навигационной ссылке</td></tr>
<tr><td><code>get_link_of_object</code></td><td>Генерация ссылки из результатов запроса</td></tr>
<tr><td><code>find_references_to_object</code></td><td>Поиск использований объекта в документах и регистрах</td></tr>
<tr><td><code>get_access_rights</code></td><td>Анализ ролей и прав на объекты метаданных</td></tr>
<tr><td><code>symbol_explore</code></td><td>Семантический поиск символов в BSL-коде</td></tr>
<tr><td><code>definition</code></td><td>Переход к определению символа</td></tr>
<tr><td><code>hover</code></td><td>Информация о символе (тип, параметры)</td></tr>
<tr><td><code>call_hierarchy</code></td><td>Дерево вызовов (кто вызывает / что вызывает)</td></tr>
<tr><td><code>call_graph</code></td><td>Граф вызовов с определением точек входа</td></tr>
<tr><td><code>document_diagnostics</code></td><td>Ошибки и предупреждения в BSL-файле</td></tr>
<tr><td><code>project_analysis</code></td><td>Анализ проекта: символы, связи, структура</td></tr>
<tr><td><code>validate_query</code></td><td>Проверка синтаксиса запроса (статика + сервер)</td></tr>
<tr><td><code>its_search</code></td><td>Поиск по ИТС через API 1С:Напарник</td></tr>
<tr><td><code>bsl_index</code></td><td>Построение индекса BSL-функций</td></tr>
<tr><td><code>bsl_search_tool</code></td><td>Поиск функций в индексе BSL</td></tr>
<tr><td><code>write_bsl</code></td><td>Запись BSL-модуля в проект</td></tr>
<tr><td><code>enable_anonymization</code></td><td>Включить маскировку ПД</td></tr>
<tr><td><code>disable_anonymization</code></td><td>Выключить маскировку ПД</td></tr>
<tr><td><code>query_stats</code></td><td>Статистика производительности запросов</td></tr>
<tr><td><code>invalidate_metadata_cache</code></td><td>Очистить кеш метаданных</td></tr>
<tr><td><code>reindex_bsl</code></td><td>Принудительная переиндексация BSL</td></tr>
<tr><td><code>connect_database</code></td><td>Подключить базу 1С</td></tr>
<tr><td><code>disconnect_database</code></td><td>Отключить базу 1С</td></tr>
<tr><td><code>switch_database</code></td><td>Переключить активную базу</td></tr>
<tr><td><code>list_databases</code></td><td>Список подключённых баз</td></tr>
<tr><td><code>get_server_status</code></td><td>Статус бэкендов</td></tr>
</table>

<h2>API-эндпоинты</h2>
<table>
<tr><th>Путь</th><th>Метод</th><th>Описание</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP — основной вход для AI-ассистентов</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>JSON-статус всех бэкендов</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI дашборд</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>Эта страница документации</td></tr>
<tr><td><code>/api/export-bsl</code></td><td>POST</td><td>REST для выгрузки BSL (вызывается EPF)</td></tr>
<tr><td><code>/api/register</code></td><td>POST</td><td>REST для регистрации EPF в шлюзе</td></tr>
<tr><td><code>/api/action/connect-db</code></td><td>POST</td><td>Подключить базу данных</td></tr>
<tr><td><code>/api/action/disconnect</code></td><td>POST</td><td>Отключить базу данных</td></tr>
<tr><td><code>/api/action/clear-cache</code></td><td>POST</td><td>Очистить кеш метаданных</td></tr>
<tr><td><code>/api/action/toggle-anon</code></td><td>POST</td><td>Включить/выключить анонимизацию</td></tr>
<tr><td><code>/api/action/get-env</code></td><td>POST</td><td>Прочитать содержимое .env</td></tr>
<tr><td><code>/api/action/save-env</code></td><td>POST</td><td>Сохранить содержимое .env</td></tr>
</table>

<h2>Переменные окружения (.env)</h2>
<table>
<tr><th>Переменная</th><th>По умолч.</th><th>Описание</th></tr>
<tr><td><code>GW_PORT</code></td><td>8080</td><td>Порт шлюза</td></tr>
<tr><td><code>LOG_LEVEL</code></td><td>INFO</td><td>Уровень логирования (DEBUG, INFO, WARNING, ERROR)</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Включённые бэкенды (через запятую). Добавьте test-runner для тестов YaXUnit.</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>Ключ API 1С:Напарник. Получить: <a href="https://code.1c.ai">code.1c.ai</a> → Профиль → API-токен.</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>TTL кеша метаданных в секундах (0 = отключить)</td></tr>
<tr><td><code>EXPORT_HOST_URL</code></td><td>http://localhost:8082</td><td>URL сервиса выгрузки BSL. На Windows: <code>http://host.docker.internal:8082</code></td></tr>
<tr><td><code>PLATFORM_PATH</code></td><td>/opt/1cv8/x86_64/8.3.27.2074</td><td>Путь к каталогу платформы 1С</td></tr>
<tr><td><code>HOST_PLATFORM_PATH</code></td><td>/opt/1cv8</td><td>Корневой путь к платформе на хосте (монтируется в platform-context)</td></tr>
<tr><td><code>ONEC_TIMEOUT</code></td><td>180</td><td>Таймаут выполнения команд в 1С (секунды)</td></tr>
</table>

<h2>Устранение неполадок</h2>
<h3>Бэкенд показывает красный статус</h3>
<p>Проверьте логи контейнера: <code>docker logs onec-mcp-gw -f</code>. Убедитесь, что все контейнеры запущены: <code>docker compose ps</code>.</p>
<h3>EPF не подключается</h3>
<p>Проверьте, что шлюз запущен (<code>curl http://localhost:8080/health</code>). Убедитесь, что обработка открыта в клиенте 1С и нажата кнопка «Подключить к прокси».</p>
<h3>BSL-навигация не работает</h3>
<p>Нажмите «Выгрузить BSL» в обработке. Дождитесь завершения индексации (3-5 минут для ERP). Проверьте статус: инструмент <code>lsp_status</code>.</p>
<h3>Ошибка .env при редактировании в дашборде</h3>
<p>Файл .env монтируется с хоста (<code>./.env:/data/.env:rw</code>). Убедитесь, что файл .env существует в корне проекта. Создайте: <code>cp .env.example .env</code>.</p>
</body></html>""",

    "en": r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Documentation — onec-mcp-universal</title>
<style>""" + _DOC_STYLE + """</style></head><body>
<a class="back" href="/dashboard?lang=en">&larr; Back to dashboard</a>
<h1>onec-mcp-universal Documentation</h1>
<p>Version: """ + VERSION + """ | <a href="https://github.com/AlekseiSeleznev/onec-mcp-universal">GitHub</a> | License: MIT</p>

<h2>Overview</h2>
<p>onec-mcp-universal is a unified MCP gateway for 1C:Enterprise integration with AI assistants (Claude Code, Cursor, Windsurf). Single endpoint <code>http://localhost:8080/mcp</code> routes requests to multiple backends.</p>
<div class="note"><p><b>Per-session routing:</b> Each AI assistant session works with its own active database independently. All databases remain connected simultaneously.</p></div>

<h2>Information Tab</h2>
<h3>Backends</h3>
<p>MCP backend status: <span style="color:#22c55e">green</span>=OK, <span style="color:#ef4444">red</span>=unavailable. Tool count shown.</p>
<ul>
<li><b>onec-toolkit</b> (8 tools) — DB queries, code execution, metadata, event log, access rights</li>
<li><b>platform-context</b> (5 tools) — 1C platform API documentation</li>
<li><b>bsl-lsp-bridge</b> (14 tools) — BSL code navigation, diagnostics, call graphs</li>
</ul>

<h3>Databases</h3>
<p>Connected 1C databases. EPF status shows whether MCPToolkit EPF is running in the 1C client. Database marked "default" is used for new AI sessions.</p>

<h3>Profiling</h3>
<p>Automatic <code>execute_query</code> timing: count, avg/max duration, slow queries (&gt;5s). Each response includes <code>_profiling</code> field with optimization hints.</p>

<h3>Metadata Cache</h3>
<p>TTL cache for <code>get_metadata</code> (default: 10 min). Shows entries count, hit rate. Clear via Settings.</p>

<h3>Anonymization</h3>
<p>PII masking in query results: FIO, INN, SNILS, phones, emails, company names. Stable hash mapping (same input = same fake). Toggle in Settings or via <code>enable_anonymization</code> tool.</p>

<h3>Docker Containers</h3>
<p>Docker daemon info (version, CPU, RAM, disk usage) and project container list with status.</p>

<h2>Settings Tab</h2>
<h3>Database Management</h3>
<p>Connected databases with buttons:</p>
<ul>
<li><b>Edit</b> — change connection string or project path</li>
<li><b>Default</b> — set as default for new AI sessions</li>
<li><b>Disconnect</b> — stop and remove containers (data untouched)</li>
</ul>
<p><b>Add Database</b> — name (latin), connection string (<code>Srvr=server;Ref=db;</code>), host project path.</p>
<div class="warn"><p><b>After connecting:</b> open <code>1c/MCPToolkit.epf</code> in 1C client, click "Connect to proxy", then "Export BSL".</p></div>

<h3>Gateway Configuration</h3>
<p>Current .env values. Click <b>"Edit"</b> to modify:</p>
<ol>
<li>Edit values in the text editor</li>
<li>Click "Save"</li>
<li>Restart: <code>docker compose restart gateway</code></li>
</ol>
<div class="note"><p>On Linux, .env is mounted into the container. On Windows, use <code>docker compose -f docker-compose.yml -f docker-compose.windows.yml up -d</code>.</p></div>

<h3>Actions</h3>
<ul>
<li><b>Clear Cache</b> — remove all cached get_metadata results</li>
<li><b>Toggle Anonymization</b> — enable/disable PII masking (no restart needed)</li>
</ul>

<h2>MCPToolkit EPF</h2>
<p>External data processor for 1C:Enterprise client. Acts as a bridge between the gateway and the 1C database.</p>
<ul>
<li><b>Connect / Disconnect</b> — manage long-polling connection to toolkit</li>
<li><b>Detect DB</b> — auto-detect current database parameters</li>
<li><b>Connect to proxy</b> — register with gateway (sends /api/register)</li>
<li><b>Export BSL</b> — export configuration sources for code navigation</li>
<li><b>Event log</b> — operation log, errors, connection status</li>
</ul>

<h2>MCP Tools (complete list)</h2>
<table>
<tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>execute_query</code></td><td>1C query language with parameters and limits</td></tr>
<tr><td><code>execute_code</code></td><td>Execute arbitrary 1C code (server or client)</td></tr>
<tr><td><code>get_metadata</code></td><td>Configuration structure: attributes, types, tabular sections</td></tr>
<tr><td><code>get_event_log</code></td><td>Read event log with filtering</td></tr>
<tr><td><code>get_object_by_link</code></td><td>Get object by navigation link</td></tr>
<tr><td><code>get_link_of_object</code></td><td>Generate link from query results</td></tr>
<tr><td><code>find_references_to_object</code></td><td>Find object usage in documents and registers</td></tr>
<tr><td><code>get_access_rights</code></td><td>Analyze roles and permissions</td></tr>
<tr><td><code>symbol_explore</code></td><td>Semantic BSL symbol search</td></tr>
<tr><td><code>definition</code></td><td>Go to symbol definition</td></tr>
<tr><td><code>hover</code></td><td>Symbol info (type, parameters)</td></tr>
<tr><td><code>call_hierarchy</code></td><td>Call tree (callers / callees)</td></tr>
<tr><td><code>call_graph</code></td><td>Call graph with entry point detection</td></tr>
<tr><td><code>document_diagnostics</code></td><td>Errors and warnings in BSL file</td></tr>
<tr><td><code>project_analysis</code></td><td>Project analysis: symbols, relationships</td></tr>
<tr><td><code>validate_query</code></td><td>Query syntax validation (static + server)</td></tr>
<tr><td><code>its_search</code></td><td>ITS search via 1C:Naparnik API</td></tr>
<tr><td><code>bsl_index</code></td><td>Build BSL function index</td></tr>
<tr><td><code>bsl_search_tool</code></td><td>Search BSL function index</td></tr>
<tr><td><code>write_bsl</code></td><td>Write BSL module to project</td></tr>
<tr><td><code>enable_anonymization</code></td><td>Enable PII masking</td></tr>
<tr><td><code>disable_anonymization</code></td><td>Disable PII masking</td></tr>
<tr><td><code>query_stats</code></td><td>Query performance statistics</td></tr>
<tr><td><code>invalidate_metadata_cache</code></td><td>Clear metadata cache</td></tr>
<tr><td><code>reindex_bsl</code></td><td>Force BSL re-indexing</td></tr>
<tr><td><code>connect_database</code></td><td>Connect 1C database</td></tr>
<tr><td><code>disconnect_database</code></td><td>Disconnect 1C database</td></tr>
<tr><td><code>switch_database</code></td><td>Switch active database (per-session)</td></tr>
<tr><td><code>list_databases</code></td><td>List connected databases</td></tr>
<tr><td><code>get_server_status</code></td><td>Backend health status</td></tr>
</table>

<h2>API Endpoints</h2>
<table>
<tr><th>Path</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP — main entry for AI assistants</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>Backend health JSON</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI dashboard</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>This documentation page</td></tr>
<tr><td><code>/api/export-bsl</code></td><td>POST</td><td>BSL export REST (called by EPF)</td></tr>
<tr><td><code>/api/register</code></td><td>POST</td><td>EPF registration REST</td></tr>
<tr><td><code>/api/action/connect-db</code></td><td>POST</td><td>Connect database</td></tr>
<tr><td><code>/api/action/disconnect</code></td><td>POST</td><td>Disconnect database</td></tr>
<tr><td><code>/api/action/edit-db</code></td><td>POST</td><td>Edit database parameters</td></tr>
<tr><td><code>/api/action/switch</code></td><td>POST</td><td>Set default database</td></tr>
<tr><td><code>/api/action/clear-cache</code></td><td>POST</td><td>Clear metadata cache</td></tr>
<tr><td><code>/api/action/toggle-anon</code></td><td>POST</td><td>Toggle anonymization</td></tr>
<tr><td><code>/api/action/get-env</code></td><td>POST</td><td>Read .env file</td></tr>
<tr><td><code>/api/action/save-env</code></td><td>POST</td><td>Save .env file</td></tr>
</table>

<h2>Environment Variables (.env)</h2>
<table>
<tr><th>Variable</th><th>Default</th><th>Description</th></tr>
<tr><td><code>GW_PORT</code></td><td>8080</td><td>Gateway port</td></tr>
<tr><td><code>LOG_LEVEL</code></td><td>INFO</td><td>Log level (DEBUG, INFO, WARNING, ERROR)</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Enabled backends (comma-separated)</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>1C:Naparnik API key (<a href="https://code.1c.ai">code.1c.ai</a>)</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>Metadata cache TTL in seconds (0=disabled)</td></tr>
<tr><td><code>EXPORT_HOST_URL</code></td><td>http://localhost:8082</td><td>BSL export service URL. Windows: <code>http://host.docker.internal:8082</code></td></tr>
<tr><td><code>PLATFORM_PATH</code></td><td>/opt/1cv8/...</td><td>1C platform path</td></tr>
<tr><td><code>HOST_PLATFORM_PATH</code></td><td>/opt/1cv8</td><td>Host platform path (mounted to platform-context)</td></tr>
<tr><td><code>ONEC_TIMEOUT</code></td><td>180</td><td>1C command timeout (seconds)</td></tr>
</table>

<h2>Troubleshooting</h2>
<h3>Backend shows red status</h3>
<p>Check container logs: <code>docker logs onec-mcp-gw -f</code>. Verify all containers running: <code>docker compose ps</code>.</p>
<h3>EPF not connecting</h3>
<p>Verify gateway is up (<code>curl http://localhost:8080/health</code>). Open EPF in 1C client and click "Connect to proxy".</p>
<h3>BSL navigation not working</h3>
<p>Click "Export BSL" in EPF. Wait for indexing (3-5 min for ERP). Check status: <code>lsp_status</code> tool.</p>
<h3>.env edit error in dashboard</h3>
<p>Ensure .env file exists in project root. Create: <code>cp .env.example .env</code>. File must be mounted: <code>./.env:/data/.env:rw</code> in docker-compose.yml.</p>
</body></html>""",
}


def render_docs(lang: str = "ru") -> str:
    return DOCS_HTML.get(lang, DOCS_HTML["ru"])

"""
Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard. Supports Russian (default) and English.
Two tabs: Info + Parameters. Documentation opens in /dashboard/docs.
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
        "tab_info": "Статус",
        "tab_settings": "Параметры",
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
        "epf_ok": "Подкл.",
        "epf_wait": "Не подкл.",
        "name": "Имя",
        "connection": "Подключение",
        "status": "Обработка",
        "setting": "Параметр",
        "value": "Значение",
        "license": "Лицензия",
        "project": "GitHub",
        "connect_db": "Подключить базу",
        "disconnect_db": "Отключить",
        "clear_cache": "Очистить кеш",
        "toggle_anon": "Анонимизация вкл/выкл",
        "restart_hint": "Шлюз перезапустится автоматически после сохранения.",
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
        "diagnostics": "Диагностика",
        "fill_all_fields": "Заполните все поля",
    },
    "en": {
        "title": "onec-mcp-universal",
        "subtitle": "MCP Gateway for 1C:Enterprise",
        "tab_info": "Status",
        "tab_settings": "Parameters",
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
        "epf_ok": "Conn.",
        "epf_wait": "Disconn.",
        "name": "Name",
        "connection": "Connection",
        "status": "EPF",
        "setting": "Setting",
        "value": "Value",
        "license": "License",
        "project": "GitHub",
        "connect_db": "Connect DB",
        "disconnect_db": "Disconnect",
        "clear_cache": "Clear Cache",
        "toggle_anon": "Toggle Anonymization",
        "restart_hint": "Gateway will restart automatically after saving.",
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
        "config_edit_hint": "Gateway will restart automatically after saving.",
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
        "diagnostics": "Diagnostics",
        "fill_all_fields": "Fill all fields",
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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;background:#0f172a;color:#e2e8f0;height:100vh;display:flex;flex-direction:column;overflow:hidden}
a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}
.header{background:#1e293b;border-bottom:1px solid #334155;padding:8px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;flex-shrink:0}
.header-left{display:flex;align-items:center;gap:10px}
.header h1{font-size:1.05rem;color:#f8fafc}
.header .sub{color:#64748b;font-size:.75rem}
.header-right{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.lang-sw{display:flex;border:1px solid #475569;border-radius:5px;overflow:hidden}
.lang-sw a{padding:3px 8px;font-size:.7rem;color:#94a3b8;display:block}
.lang-sw a.on{background:#334155;color:#f8fafc}
.btn{display:inline-flex;align-items:center;gap:4px;padding:5px 12px;border-radius:5px;font-size:.78rem;cursor:pointer;border:1px solid #475569;background:#1e293b;color:#94a3b8;text-decoration:none}
.btn:hover{background:#334155;color:#f8fafc;text-decoration:none}
.btn-p{background:#0369a1;border-color:#0369a1;color:#fff}.btn-p:hover{background:#0284c7}
.btn-d{background:#991b1b;border-color:#991b1b;color:#fff;font-size:.7rem;padding:3px 8px}.btn-d:hover{background:#b91c1c}
.tabs{display:flex;background:#1e293b;border-bottom:1px solid #334155;padding:0 20px;flex-shrink:0}
.tab{padding:8px 16px;font-size:.78rem;color:#64748b;cursor:pointer;border-bottom:2px solid transparent}
.tab:hover{color:#94a3b8}.tab.on{color:#38bdf8;border-bottom-color:#38bdf8}
.tc{display:none;padding:12px 20px;flex:1;overflow-y:auto}.tc.on{display:flex;flex-direction:column}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;flex:1}
.card{background:#1e293b;border-radius:8px;padding:12px;border:1px solid #334155;overflow:hidden}
.card h2{font-size:.65rem;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px;font-weight:600}
.sr{display:flex;align-items:center;gap:6px;margin-bottom:4px;font-size:.8rem}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#22c55e}.dot.err{background:#ef4444}.dot.warn{background:#eab308}
.sn{font-weight:600;color:#f1f5f9;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px}
.st{color:#64748b;font-size:.78rem;white-space:nowrap}
.badge{display:inline-block;background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.65rem;margin-left:4px;white-space:nowrap}
.sv{font-size:1.2rem;font-weight:700;color:#f8fafc;line-height:1.2}
.sl{color:#64748b;font-size:.65rem;margin-top:1px}
.srow{display:flex;gap:20px;flex-wrap:wrap}
table{width:100%;border-collapse:collapse;font-size:.78rem;table-layout:fixed}
th{text-align:left;color:#64748b;padding:4px 6px;border-bottom:1px solid #334155;font-weight:500;font-size:.7rem;overflow:hidden;text-overflow:ellipsis}
td{padding:4px 6px;border-bottom:1px solid #1e293b;color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;word-break:break-all}
.footer{padding:8px 20px;text-align:center;color:#475569;font-size:.68rem;border-top:1px solid #1e293b;flex-shrink:0}
.footer a{color:#64748b}.footer a:hover{color:#94a3b8}
.ag{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.hint{color:#64748b;font-size:.72rem;margin-top:10px;font-style:italic}
@media(max-width:900px){.grid{grid-template-columns:1fr!important}.card{font-size:.8rem}table{font-size:.75rem}.btn,.btn-d{font-size:.7rem;padding:3px 6px}}
.form-row{display:grid;grid-template-columns:140px 1fr;gap:8px;margin-bottom:8px;align-items:center}
.form-row label{font-size:.78rem;color:#94a3b8;text-align:right}
.form-row input{padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem;width:100%}
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
<div class="card"><h2>{{h_databases}}</h2>{{databases_html}}</div>
<div class="card"><h2>{{h_profiling}}</h2>{{profiling_html}}</div>
<div class="card"><h2>{{h_anon}}</h2><div class="sr"><div class="dot {{anon_dot}}"></div><span class="sn">{{anon_status}}</span></div></div>
<div class="card"><h2>{{h_cache}}</h2>{{cache_html}}</div>
<div class="card"><h2>{{h_backends}}</h2>{{backends_html}}</div>
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
<h2>{{h_config}}</h2>
<div id="config-actions" style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #334155;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="act('/api/action/clear-cache')">{{clear_cache}}</button>
<span class="st">{{cache_status}}</span>
<span class="st">|</span>
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="act('/api/action/toggle-anon')">{{toggle_anon}}</button>
<span class="st" style="display:flex;align-items:center;gap:4px"><span class="dot {{anon_dot}}"></span>{{anon_status}}</span>
<span style="margin-left:auto"><button class="btn" style="font-size:.7rem" onclick="editEnv()">{{edit_config}}</button></span>
</div>
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
</div>
</div>
<div class="footer">
{{title}} {{version}} &mdash;
<a href="{{github_url}}">{{project}}</a> &mdash;
<a href="{{github_url}}/blob/main/LICENSE">{{license}}: MIT</a> &mdash;
<a href="/dashboard/diagnostics?lang={{lang}}" target="_blank">{{diagnostics}}</a>
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
function reload(){var h=location.hash;location.href=location.pathname+'?lang={{lang}}'+h}
function act(u){fetch(u,{method:'POST'}).then(r=>r.json()).then(d=>{
var msg=d.message||d.error||'OK';
var h=location.hash||'';
location.href=location.pathname+'?lang={{lang}}&msg='+encodeURIComponent(msg)+h;
}).catch(e=>alert(e))}
// Show message from URL param after reload
(function(){var p=new URLSearchParams(location.search);var m=p.get('msg');if(m){
var d=document.createElement('div');d.style.cssText='position:fixed;top:12px;right:12px;background:#164e63;color:#22d3ee;padding:10px 16px;border-radius:6px;font-size:.85rem;z-index:999;max-width:400px';
d.textContent=m;document.body.appendChild(d);setTimeout(function(){d.remove()},4000);
history.replaceState(null,'',location.pathname+'?lang='+p.get('lang')+(location.hash||''));
}})();
function connectDb(){
var n=document.getElementById('db-name').value.trim();
var c=document.getElementById('db-conn').value.trim();
var p=document.getElementById('db-path').value.trim();
if(!n||!c||!p){alert('{{fill_all_fields}}');return}
fetch('/api/action/connect-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,connection:c,project_path:p})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error||JSON.stringify(d));if(d.ok)setTimeout(reload,300)}).catch(e=>alert(e))
}
function editDb(name,conn,path){
var nc=prompt('{{add_db_conn}}:',conn);if(!nc)return;
var np=prompt('{{add_db_path}}:',path);if(!np)return;
fetch('/api/action/edit-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,connection:nc,project_path:np})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error);setTimeout(reload,300)}).catch(e=>alert(e))
}
function editEnv(){
fetch('/api/action/get-env',{method:'POST'}).then(r=>r.json()).then(d=>{
document.getElementById('env-editor').value=d.env||'';
document.getElementById('config-view').style.display='none';
document.getElementById('config-actions').style.display='none';
document.getElementById('config-edit').style.display='block';
}).catch(e=>alert(e))
}
function saveEnv(){
var c=document.getElementById('env-editor').value;
fetch('/api/action/save-env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c})})
.then(r=>r.json()).then(d=>{alert(d.message||d.error);setTimeout(function(){location.href=location.pathname+'?lang={{lang}}#settings'},3000)}).catch(e=>alert(e))
}
function cancelEnv(){
document.getElementById('config-view').style.display='block';
document.getElementById('config-actions').style.display='flex';
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
        rows = [f'<table style="table-layout:auto">'
                f'<tr><th>{t["name"]}</th><th>{t["connection"]}</th><th>{t["status"]}</th></tr>']
        for db in databases:
            badge = f'<br><span class="badge">{t["default_badge"]}</span>' if db.get("active") else ""
            epf_connected = db.get("epf_connected", False)
            epf_dot = "ok" if epf_connected else "warn"
            epf = t["epf_ok"] if epf_connected else t["epf_wait"]
            conn = db.get("connection", "")
            rows.append(f'<tr><td><b>{db["name"]}</b>{badge}</td><td style="font-size:.78rem">{conn}</td><td><span class="sr" style="margin:0;gap:5px"><span class="dot {epf_dot}"></span>{epf}</span></td></tr>')
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
            badge = f'<br><span class="badge">{t["default_badge"]}</span>' if is_default else ""
            epf_connected = db.get("epf_connected", False)
            epf_dot = "ok" if epf_connected else "warn"
            epf_st = f'<span class="sr" style="margin:0;gap:5px"><span class="dot {epf_dot}"></span>{t["epf_ok"] if epf_connected else t["epf_wait"]}</span>'
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
                f'<tr>'
                f'<td><b>{db["name"]}</b>{badge}</td>'
                f'<td style="font-size:.75rem;word-break:break-all">{conn}</td>'
                f'<td style="white-space:nowrap">{epf_st}</td>'
                f'<td style="white-space:nowrap;text-align:right">{default_btn}{edit_btn} {disc_btn}</td>'
                f'</tr>'
            )
        db_mgmt_html = (
            f'<table style="table-layout:auto;font-size:.82rem">'
            f'<tr><th>{t["name"]}</th><th>{t["connection"]}</th>'
            f'<th>{t["status"]}</th><th></th></tr>'
            + "\n".join(db_lines) + '</table>'
        )
    else:
        db_mgmt_html = f'<span class="st">{t["no_databases"]}</span>'

    html = HTML_TEMPLATE
    for key, val in t.items():
        html = html.replace("{{" + key + "}}", val)
    # Status texts for action buttons
    cache_entries = cache_stats.get("entries", 0)
    cache_status = f"{cache_entries} {t['entries'].lower()}" if cache_entries else "0.0 MB"
    anon_status_text = f'<span class="dot {"ok" if anon_enabled else "warn"}" style="display:inline-block"></span> {anon_status}'

    replacements = {
        "backends_html": backends_html, "databases_html": databases_html, "docker_info_html": docker_info_html,
        "profiling_html": profiling_html, "cache_html": cache_html,
        "anon_dot": anon_dot, "anon_status": anon_status,
        "cache_status": cache_status, "anon_status_text": anon_status_text,
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

<h2>Содержание</h2>
<ol>
<li><a href="#overview-ru">Обзор</a> — что это, зачем нужно, архитектура</li>
<li><a href="#status-ru">Вкладка «Статус»</a> — базы данных, профилирование, анонимизация, кеш, бэкенды, Docker</li>
<li><a href="#params-ru">Вкладка «Параметры»</a> — управление базами, конфигурация, действия</li>
<li><a href="#epf-ru">Обработка MCPToolkit.epf</a> — интерфейс, кнопки, безопасность, журнал</li>
<li><a href="#tools-ru">MCP-инструменты</a> — полный список 47 инструментов</li>
<li><a href="#api-ru">API-эндпоинты</a> — полная таблица</li>
<li><a href="#env-ru">Переменные окружения</a> — все параметры .env</li>
<li><a href="#diagnostics-ru">Диагностика</a> — содержимое отчёта</li>
<li><a href="#troubleshooting-ru">Устранение неполадок</a> — типичные проблемы и решения</li>
</ol>

<!-- ================================================================== -->
<h2 id="overview-ru">1. Обзор</h2>

<h3>Что это такое</h3>
<p><b>onec-mcp-universal</b> — единый MCP-шлюз, который позволяет AI-ассистентам (Claude Code, Cursor, Windsurf и любым MCP-клиентам) работать с информационными базами 1С:Предприятие. MCP (Model Context Protocol) — открытый протокол, через который AI-модель вызывает внешние инструменты: выполняет запросы к базе данных, читает метаданные конфигурации, навигирует по исходному коду и т.д.</p>

<h3>Зачем нужен шлюз</h3>
<p>Без шлюза пришлось бы подключать к AI-ассистенту несколько отдельных MCP-серверов (один для данных 1С, другой для навигации по коду, третий для документации платформы). Шлюз объединяет их в единую точку входа — <code>http://localhost:8080/mcp</code>. AI-ассистент подключается один раз и получает доступ ко всем 47+ инструментам сразу.</p>

<h3>Как работает</h3>
<p>Цепочка взаимодействия выглядит так:</p>
<pre><code>AI-ассистент (Claude Code / Cursor / Windsurf)
    |
    | MCP Streamable HTTP
    v
MCP-шлюз (onec-mcp-universal, порт 8080)
    |
    +---> onec-toolkit      — данные 1С (запросы, код, метаданные)
    +---> platform-context  — документация API платформы
    +---> bsl-lsp-bridge    — навигация по BSL-коду
    +---> test-runner        — запуск тестов YaXUnit (опционально)
    |
    v
MCPToolkit.epf (обработка внутри клиента 1С)
    |
    v
Информационная база 1С:Предприятие</code></pre>

<p>Когда AI-ассистент вызывает инструмент (например, <code>execute_query</code>), шлюз определяет, какому бэкенду он принадлежит, и перенаправляет запрос. Бэкенд <code>onec-toolkit</code> передаёт команду обработке MCPToolkit.epf, запущенной в клиенте 1С. Обработка выполняет запрос в информационной базе и возвращает результат обратно по цепочке.</p>

<h3>Per-session routing</h3>
<p>Каждый сеанс AI-ассистента работает со своей активной базой данных <b>независимо</b>. Это означает, что два разных окна Claude Code могут одновременно работать с разными базами (например, одно с ERP, другое с ЗУП), и их запросы не будут пересекаться. Все зарегистрированные базы остаются подключёнными одновременно. Переключение между базами выполняется командой <code>switch_database</code>. Idle timeout сессий — 8 часов.</p>

<div class="note"><p><b>Одна точка подключения:</b> Вне зависимости от количества подключённых баз и бэкендов, AI-ассистент всегда использует один адрес — <code>http://localhost:8080/mcp</code>.</p></div>

<!-- ================================================================== -->
<h2 id="status-ru">2. Вкладка «Статус»</h2>
<p>Вкладка «Статус» — главный экран дашборда. Она отображает текущее состояние всех компонентов системы в виде шести карточек. Информация на этой вкладке доступна только для чтения — все действия выполняются на вкладке «Параметры».</p>

<h3>Карточка «Базы данных»</h3>
<p>Таблица со списком всех подключённых информационных баз 1С. Каждая строка содержит три столбца:</p>
<table>
<tr><th>Столбец</th><th>Описание</th></tr>
<tr><td><b>Имя</b></td><td>Уникальный идентификатор базы (латинские буквы, цифры, дефис, подчёркивание). Используется в именах Docker-контейнеров: <code>onec-toolkit-{имя}</code> и <code>mcp-lsp-{имя}</code>. Примеры: <code>ERP</code>, <code>ZUP_TEST</code>, <code>buh-main</code>.</td></tr>
<tr><td><b>Подключение</b></td><td>Строка подключения 1С в стандартном формате платформы. Для серверной базы: <code>Srvr=имя_сервера;Ref=имя_базы;</code>. Для файловой: <code>File=/путь/к/базе</code>.</td></tr>
<tr><td><b>Обработка</b></td><td>Статус подключения обработки MCPToolkit.epf. Отображается как цветной индикатор с текстом:<br>
<span style="color:#22c55e">Подкл.</span> (зелёный) — обработка запущена в клиенте 1С, long-polling соединение активно, AI может выполнять запросы к этой базе.<br>
<span style="color:#eab308">Не подкл.</span> (жёлтый) — Docker-контейнеры для базы запущены, но обработка ещё не подключена. Необходимо открыть MCPToolkit.epf в клиенте 1С и нажать «Подключиться».</td></tr>
</table>
<p>У базы, выбранной по умолчанию, рядом с именем отображается бирка <span style="background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.75rem">по умолч.</span>. Эта база используется для новых сеансов AI, если сеанс не переключился на другую базу через <code>switch_database</code>.</p>
<div class="note"><p><b>Автоподключение:</b> Если пользователь нажимает «Подключиться» в обработке MCPToolkit.epf, а база ещё не зарегистрирована в шлюзе, она автоматически подключается — создаются Docker-контейнеры, база появляется в этой таблице.</p></div>

<h3>Карточка «Профилирование»</h3>
<p>Автоматический сбор статистики по производительности всех запросов <code>execute_query</code> к информационным базам. Данные накапливаются с момента запуска шлюза и сбрасываются при перезапуске.</p>
<table>
<tr><th>Показатель</th><th>Описание</th></tr>
<tr><td><b>Запросов</b></td><td>Общее количество выполненных запросов с момента запуска шлюза. Считаются все вызовы <code>execute_query</code> ко всем подключённым базам.</td></tr>
<tr><td><b>Среднее</b></td><td>Среднее время выполнения запроса в миллисекундах. Включает время передачи запроса до 1С и получения ответа. Значение больше 1000 мс сигнализирует о необходимости оптимизации запросов.</td></tr>
<tr><td><b>Макс</b></td><td>Максимальное время выполнения одного запроса в миллисекундах. Помогает выявить «выбросы» — единичные тяжёлые запросы.</td></tr>
<tr><td><b>Медл. (&gt;5с)</b></td><td>Количество запросов, выполнявшихся более 5 секунд. Такие запросы считаются медленными и, как правило, требуют оптимизации (добавление индексов, переработка условий, использование временных таблиц).</td></tr>
</table>
<p>Если запросов ещё не было, карточка показывает надпись «Нет запросов».</p>
<p>Кроме дашборда, статистику профилирования можно получить через MCP-инструмент <code>query_stats</code>. Каждый ответ <code>execute_query</code> автоматически включает поле <code>_profiling</code> с длительностью выполнения и подсказками по оптимизации (например: «запрос использует SELECT *», «отсутствует WHERE», «много JOIN»).</p>

<h3>Карточка «Анонимизация»</h3>
<p>Статус системы маскировки персональных данных (ПД) в ответах от 1С. Отображается как цветной индикатор:</p>
<ul>
<li><span style="color:#22c55e">Включена</span> (зелёный) — все ответы инструментов <code>execute_query</code>, <code>execute_code</code>, <code>get_object_by_link</code>, <code>get_event_log</code> проходят через фильтр анонимизации.</li>
<li><span style="color:#eab308">Выключена</span> (жёлтый) — данные передаются AI без изменений.</li>
</ul>
<p><b>Что маскируется:</b></p>
<ul>
<li><b>ФИО</b> — распознаются паттерны «Фамилия Имя Отчество» и заменяются на стабильные фейковые данные (например, Иванов Иван Иванович всегда превращается в Петров Сергей Александрович)</li>
<li><b>ИНН</b> — 10-значные (юридические лица) и 12-значные (физические лица) номера заменяются на валидные фейковые ИНН</li>
<li><b>СНИЛС</b> — номера формата XXX-XXX-XXX XX</li>
<li><b>Телефоны</b> — российские номера (+7...)</li>
<li><b>Email</b> — адреса электронной почты</li>
<li><b>Названия компаний</b> — юридические лица (ООО, АО, ИП и т.д.)</li>
</ul>
<p><b>Стабильный маппинг:</b> Одно и то же исходное значение <b>всегда</b> заменяется одним и тем же фейком в рамках сессии. Это позволяет AI корректно работать с данными — связи между объектами (например, «у контрагента Альфа есть документы...») сохраняются.</p>
<p><b>Когда использовать:</b> Включайте анонимизацию при работе с production-базами, содержащими реальные персональные данные. Это важно для соответствия 152-ФЗ (закон о персональных данных) — замаскированные данные не являются персональными. На тестовых базах с синтетическими данными анонимизацию можно не включать.</p>

<h3>Карточка «Кеш метаданных»</h3>
<p>Результаты вызова <code>get_metadata</code> (информация о структуре конфигурации: реквизиты, табличные части, типы) кешируются на стороне шлюза, чтобы не запрашивать одни и те же метаданные у 1С повторно.</p>
<table>
<tr><th>Показатель</th><th>Описание</th></tr>
<tr><td><b>Записей</b></td><td>Количество закешированных объектов метаданных. Каждый уникальный вызов <code>get_metadata</code> с определённым набором параметров создаёт одну запись в кеше.</td></tr>
<tr><td><b>Попадания</b></td><td>Процент запросов, обслуженных из кеша (hit rate). Значение 80-100% означает, что кеш работает эффективно. Низкий процент может означать, что AI запрашивает каждый раз разные объекты, или что TTL слишком короткий.</td></tr>
<tr><td><b>TTL</b></td><td>Время жизни записи кеша в секундах. По умолчанию — 600 секунд (10 минут). Настраивается через переменную <code>METADATA_CACHE_TTL</code> в файле <code>.env</code>. Значение 0 полностью отключает кеширование.</td></tr>
</table>
<p><b>Когда очищать кеш:</b> После изменения структуры конфигурации 1С (добавление/удаление реквизитов, табличных частей, объектов метаданных). Очистить можно кнопкой на вкладке «Параметры», через MCP-инструмент <code>invalidate_metadata_cache</code>, или дождаться автоматической инвалидации по TTL.</p>

<h3>Карточка «Бэкенды»</h3>
<p>Бэкенд — это отдельный MCP-сервер, который предоставляет набор инструментов определённой категории. Шлюз агрегирует инструменты всех бэкендов и предоставляет их AI-ассистенту как единый набор.</p>
<p>Каждая строка показывает:</p>
<ul>
<li><b>Цветной индикатор</b> — <span style="color:#22c55e">зелёный</span> = бэкенд доступен и отвечает, <span style="color:#ef4444">красный</span> = бэкенд недоступен (контейнер не запущен или произошла ошибка)</li>
<li><b>Имя</b> — идентификатор бэкенда</li>
<li><b>N инстр.</b> — количество инструментов, которые бэкенд предоставляет</li>
<li><b>Бирка «активная»</b> — отображается у бэкендов, привязанных к текущей активной базе</li>
</ul>
<p><b>Статические бэкенды</b> (создаются при запуске шлюза):</p>
<table>
<tr><th>Бэкенд</th><th>Инструменты</th><th>Назначение</th></tr>
<tr><td><code>onec-toolkit</code></td><td>8</td><td>Запросы к БД, выполнение кода, метаданные, журнал регистрации, права доступа, ссылки на объекты. Работает через обработку MCPToolkit.epf.</td></tr>
<tr><td><code>platform-context</code></td><td>5</td><td>Документация API встроенного языка 1С: поиск методов типов, описания конструкторов, список членов объектов.</td></tr>
<tr><td><code>bsl-lsp-bridge</code></td><td>14</td><td>Навигация по BSL-коду: поиск символов, переход к определению, граф вызовов, диагностика ошибок, переименование.</td></tr>
</table>
<p><b>Динамические бэкенды</b> (создаются при подключении каждой базы):</p>
<ul>
<li><code>onec-toolkit-{имя_базы}</code> — персональный бэкенд данных для конкретной базы</li>
<li><code>mcp-lsp-{имя_базы}</code> — персональный BSL Language Server с индексом конфигурации конкретной базы</li>
</ul>
<p><b>Опциональные бэкенды</b> (подключаются через <code>ENABLED_BACKENDS</code>):</p>
<ul>
<li><code>test-runner</code> — запуск тестов YaXUnit. Добавьте <code>test-runner</code> в <code>ENABLED_BACKENDS</code> и запустите: <code>docker compose --profile test-runner up -d</code>.</li>
</ul>

<h3>Карточка «Docker-контейнеры»</h3>
<p>Верхняя часть карточки показывает информацию о Docker-демоне: версия Docker, количество CPU, объём RAM, суммарный размер образов и томов.</p>
<p>Ниже — таблица контейнеров проекта с тремя столбцами:</p>
<table>
<tr><th>Столбец</th><th>Описание</th></tr>
<tr><td><b>Контейнер</b></td><td>Имя Docker-контейнера с цветным индикатором состояния</td></tr>
<tr><td><b>Образ</b></td><td>Docker-образ, из которого создан контейнер</td></tr>
<tr><td><b>Статус</b></td><td><code>запущен</code> или <code>остановлен</code></td></tr>
</table>
<p><b>Типы контейнеров:</b></p>
<ul>
<li><code>onec-mcp-gw</code> — MCP-шлюз (этот сервер, порт 8080). Принимает MCP-запросы от AI и маршрутизирует их к бэкендам.</li>
<li><code>onec-mcp-toolkit</code> — статический бэкенд данных (порт 6003). Обрабатывает запросы к 1С через long-polling с EPF.</li>
<li><code>onec-mcp-platform</code> — бэкенд документации платформы 1С (порт 8081). Содержит структурированную документацию API встроенного языка.</li>
<li><code>onec-toolkit-{имя_базы}</code> — динамический бэкенд данных, создаётся автоматически при подключении каждой новой базы.</li>
<li><code>mcp-lsp-{имя_базы}</code> — BSL Language Server для каждой базы. Индексирует исходники конфигурации и обеспечивает навигацию по коду.</li>
</ul>

<!-- ================================================================== -->
<h2 id="params-ru">3. Вкладка «Параметры»</h2>
<p>Вкладка «Параметры» содержит инструменты управления: подключение и отключение баз данных, редактирование конфигурации шлюза, действия с кешем и анонимизацией.</p>

<h3>Управление базами данных</h3>
<p>Верхняя часть карточки — таблица подключённых баз (аналогична карточке «Базы данных» на вкладке «Статус»), но с дополнительными кнопками управления у каждой базы:</p>
<table>
<tr><th>Кнопка</th><th>Описание</th></tr>
<tr><td><b>По умолч.</b></td><td>Устанавливает базу как используемую по умолчанию для новых сеансов AI. Кнопка отображается только у баз, которые ещё <b>не являются</b> базой по умолчанию. После нажатия рядом с именем базы появляется бирка <span style="background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.75rem">по умолч.</span>.</td></tr>
<tr><td><b>Изменить</b></td><td>Открывает диалог редактирования строки подключения и пути к проекту. После сохранения изменений необходимо переподключить базу для применения новых параметров.</td></tr>
<tr><td><b>Отключить</b></td><td>Останавливает и удаляет Docker-контейнеры базы (<code>onec-toolkit-{имя}</code> и <code>mcp-lsp-{имя}</code>). <b>Данные информационной базы 1С и выгруженные BSL-исходники на диске не затрагиваются</b> — удаляются только контейнеры. Базу можно подключить снова в любой момент.</td></tr>
</table>

<h3>Добавление базы</h3>
<p>Нижняя часть карточки — форма «Добавить базу» с тремя полями:</p>
<table>
<tr><th>Поле</th><th>Описание</th><th>Пример</th></tr>
<tr><td><b>Имя базы</b></td><td>Уникальный идентификатор. Допустимы латинские буквы, цифры, дефис и подчёркивание. Максимум 63 символа.</td><td><code>ERP_DEMO</code></td></tr>
<tr><td><b>Строка подключения</b></td><td>Стандартная строка подключения платформы 1С. Серверная: <code>Srvr=имя_сервера;Ref=имя_базы;</code>. Файловая: <code>File=/путь/к/базе</code>. С авторизацией: <code>Srvr=srv;Ref=db;Usr=admin;Pwd=пароль;</code></td><td><code>Srvr=localhost;Ref=ERP;</code></td></tr>
<tr><td><b>Путь к проекту</b></td><td>Абсолютный путь на хосте, куда будут выгружены BSL-исходники конфигурации. Этот каталог монтируется в LSP-контейнер для навигации по коду.</td><td><code>/home/user/projects/ERP</code></td></tr>
</table>
<p>После нажатия кнопки «Подключить» шлюз создаст два Docker-контейнера для базы и зарегистрирует её. Далее откройте MCPToolkit.epf в клиенте 1С и нажмите «Подключиться».</p>

<h3>Три способа подключения базы</h3>
<p>Базу 1С можно подключить к шлюзу тремя равноправными способами:</p>
<ol>
<li><b>Из обработки MCPToolkit.epf</b> (рекомендуемый) — откройте обработку в клиенте 1С:Предприятие, нажмите «Подключиться». Обработка автоматически определит имя базы и сервер, зарегистрирует базу в шлюзе и создаст Docker-контейнеры. Никакой ручной настройки не требуется.</li>
<li><b>Из дашборда</b> — перейдите на вкладку «Параметры», заполните форму «Добавить базу» и нажмите «Подключить». После этого откройте MCPToolkit.epf в 1С и нажмите «Подключиться» для установки long-polling соединения.</li>
<li><b>Через AI-ассистент</b> — напишите в чате с AI на естественном языке:
<pre><code>Подключи базу ERP_DEMO, строка подключения Srvr=localhost;Ref=ERP_DEMO;, папка /home/user/projects/ERP_DEMO</code></pre>
AI вызовет инструмент <code>connect_database</code> с указанными параметрами. После этого откройте MCPToolkit.epf в 1С и нажмите «Подключиться».</li>
</ol>

<h3>Конфигурация шлюза</h3>
<p>Вторая карточка на вкладке «Параметры» показывает таблицу текущих значений всех переменных окружения шлюза (файл <code>.env</code>). В верхней части расположены кнопки действий (очистка кеша, анонимизация) и кнопка «Редактировать».</p>
<p><b>Процесс редактирования:</b></p>
<ol>
<li>Нажмите кнопку <b>«Редактировать»</b> — таблица заменится на текстовый редактор с полным содержимым файла <code>.env</code>.</li>
<li>Внесите изменения. Формат: <code>ПЕРЕМЕННАЯ=значение</code>, по одной переменной на строку. Строки, начинающиеся с <code>#</code>, являются комментариями.</li>
<li>Нажмите <b>«Сохранить»</b> — файл сохранится, и шлюз <b>автоматически перезапустится</b> через несколько секунд. Все текущие MCP-сессии будут разорваны (AI-ассистент переподключится автоматически).</li>
<li>Или нажмите <b>«Отмена»</b> — редактор закроется без сохранения.</li>
</ol>
<div class="note"><p><b>Монтирование:</b> Файл <code>.env</code> монтируется в контейнер как <code>./.env:/data/.env:rw</code>. Изменения из дашборда записываются напрямую в файл на хосте. Работает на Linux и Windows (через <code>docker-compose.windows.yml</code>).</p></div>

<h3>Действия</h3>
<p>Кнопки быстрых действий расположены над таблицей конфигурации:</p>
<table>
<tr><th>Действие</th><th>Описание</th><th>Когда использовать</th></tr>
<tr><td><b>Очистить кеш</b></td><td>Удаляет все закешированные результаты <code>get_metadata</code>. Следующие запросы метаданных обратятся напрямую к 1С.</td><td>После изменения структуры конфигурации: добавления/удаления реквизитов, табличных частей, объектов метаданных. Также полезно, если AI получает устаревшую информацию о структуре.</td></tr>
<tr><td><b>Анонимизация вкл/выкл</b></td><td>Переключает маскировку персональных данных в ответах инструментов. Не требует перезапуска шлюза, вступает в силу мгновенно.</td><td>Включайте при работе с production-базами, содержащими реальные ФИО, ИНН, телефоны. Выключайте при работе с тестовыми базами или когда маскировка мешает анализу данных.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="epf-ru">4. Обработка MCPToolkit.epf</h2>
<p>Внешняя обработка <code>MCPToolkit.epf</code> — это ключевой компонент, работающий на стороне 1С. Она запускается в клиенте 1С:Предприятие и выступает посредником между MCP-шлюзом и информационной базой. Без неё невозможны операции с данными 1С (запросы, выполнение кода, чтение метаданных).</p>
<p>Файл обработки находится в каталоге проекта: <code>1c/MCPToolkit.epf</code>.</p>

<h3>Поля интерфейса</h3>
<table>
<tr><th>Поле</th><th>Описание</th><th>Заполнение</th></tr>
<tr><td><b>Адрес шлюза</b></td><td>URL MCP-шлюза. Используется для регистрации базы и отправки результатов.</td><td>По умолчанию <code>http://localhost:8080</code>. Измените, если шлюз работает на другом хосте или порту.</td></tr>
<tr><td><b>Информационная база: имя</b></td><td>Идентификатор текущей информационной базы. Определяет, к какому набору Docker-контейнеров будет привязана обработка.</td><td>Заполняется автоматически из строки подключения текущей ИБ. Только чтение.</td></tr>
<tr><td><b>Информационная база: сервер</b></td><td>Имя сервера 1С или путь к файловой базе.</td><td>Определяется автоматически. Только чтение.</td></tr>
<tr><td><b>Информационная база: пользователь</b></td><td>Имя пользователя текущего сеанса 1С.</td><td>Определяется автоматически. Только чтение.</td></tr>
<tr><td><b>Информационная база: пароль</b></td><td>Пароль для выгрузки BSL-исходников через DESIGNER. Необходим только для операции «Выгрузить BSL».</td><td>Вводится вручную. Не сохраняется между сеансами.</td></tr>
</table>

<h3>Кнопки</h3>
<table>
<tr><th>Кнопка</th><th>Действие</th></tr>
<tr><td><b>Подключиться</b></td><td>Выполняет два действия:<br>1. <b>Регистрация</b> — отправляет данные базы (имя, строку подключения) на шлюз через <code>/api/register</code>. Если база ещё не подключена, шлюз автоматически создаёт Docker-контейнеры.<br>2. <b>Long-polling</b> — устанавливает постоянное соединение с toolkit-бэкендом. Обработка начинает «слушать» входящие команды от AI и выполнять их в контексте текущей информационной базы.</td></tr>
<tr><td><b>Отключиться</b></td><td>Прекращает long-polling соединение. Обработка перестаёт принимать команды. Docker-контейнеры продолжают работать — база остаётся зарегистрированной, но статус EPF меняется на «Не подкл.».</td></tr>
<tr><td><b>Выгрузить BSL</b></td><td>Запускает выгрузку исходников конфигурации 1С в BSL-файлы для навигации по коду. Использует ibcmd (утилита командной строки платформы) или сервис выгрузки на хосте (export-host-service.py). На крупных конфигурациях (ERP — ~18 000 модулей, ЗУП — ~12 000 модулей) индексация занимает 3-5 минут. После завершения BSL Language Server автоматически переиндексирует файлы.</td></tr>
</table>

<h3>Автоматически разрешать операции</h3>
<p>Два чекбокса управляют автоматическим подтверждением потенциально опасных операций, когда AI выполняет произвольный код через инструмент <code>execute_code</code>:</p>
<table>
<tr><th>Чекбокс</th><th>Описание</th><th>Рекомендация</th></tr>
<tr><td><b>Записать объект</b></td><td>Если включён — AI может выполнять запись данных (<code>Объект.Записать()</code>, <code>Документ.Записать(РежимЗаписиДокумента.Проведение)</code>) без ручного подтверждения оператором. Если выключён — каждая попытка записи вызывает диалоговое окно в клиенте 1С с вопросом «Разрешить запись?».</td><td>На production-базах — <b>выключен</b>. На тестовых базах — на усмотрение пользователя.</td></tr>
<tr><td><b>Привилегированный режим</b></td><td>Если включён — AI может устанавливать привилегированный режим (<code>УстановитьПривилегированныйРежим(Истина)</code>) без подтверждения. Привилегированный режим отключает проверку прав доступа в 1С — код выполняется от имени пользователя с полными правами.</td><td>На production-базах — <b>выключен</b>. Включать только при необходимости и с пониманием рисков.</td></tr>
</table>
<div class="warn"><p><b>Безопасность:</b> На production-базах с реальными данными рекомендуется оставить оба чекбокса выключенными. Каждая потенциально опасная операция будет требовать ручного подтверждения оператором в клиенте 1С. Это предотвращает случайное удаление или модификацию данных.</p></div>

<h3>Статус и ссылки</h3>
<p>В нижней части формы отображается текущий статус подключения (Подключено / Отключено) и ссылки:</p>
<ul>
<li><b>Дашборд</b> — открывает веб-интерфейс шлюза (<code>/dashboard</code>) в браузере</li>
<li><b>GitHub</b> — ссылка на репозиторий проекта</li>
</ul>

<h3>Журнал событий</h3>
<p>Единый журнал в нижней части формы отображает все события в хронологическом порядке:</p>
<ul>
<li>Успешные подключения и отключения</li>
<li>Входящие команды от AI (имя инструмента, параметры)</li>
<li>Результаты выполнения команд</li>
<li>Ошибки (сетевые, исключения 1С, таймауты)</li>
<li>Информация о выгрузке BSL</li>
</ul>
<p>Журнал полезен для отладки — если AI-ассистент получает ошибку, в журнале будет видно, что именно произошло на стороне 1С.</p>

<h3>Вкладка «Анонимизация»</h3>
<p>Дополнительная вкладка в обработке позволяет настроить правила <b>точной анонимизации</b> на стороне EPF: regex-паттерны, словари замен, списки исключений. Эта анонимизация работает <b>независимо</b> от серверной анонимизации шлюза и может использоваться совместно с ней или отдельно.</p>

<!-- ================================================================== -->
<h2 id="tools-ru">5. MCP-инструменты (полный список)</h2>
<p>Шлюз предоставляет AI-ассистенту 47 инструментов, объединённых из всех бэкендов. Инструменты разделены на категории.</p>

<h3>Данные 1С (через onec-toolkit, 8 инструментов)</h3>
<table>
<tr><th>Инструмент</th><th>Описание</th></tr>
<tr><td><code>execute_query</code></td><td>Выполнение запроса к БД на встроенном языке запросов 1С. Поддерживает параметры (<code>&amp;Параметр</code>), лимиты, вложенные запросы. Автоматически профилируется и анонимизируется (если включено).</td></tr>
<tr><td><code>execute_code</code></td><td>Выполнение произвольного кода на встроенном языке 1С в контексте информационной базы. Код выполняется на сервере 1С. Поддерживает возврат результата.</td></tr>
<tr><td><code>get_metadata</code></td><td>Получение структуры объекта метаданных конфигурации: реквизиты, табличные части, типы полей, длина строк, и т.д. Результат кешируется.</td></tr>
<tr><td><code>get_event_log</code></td><td>Чтение журнала регистрации 1С с фильтрацией по дате, событию, пользователю, уровню важности.</td></tr>
<tr><td><code>get_object_by_link</code></td><td>Получение данных объекта по навигационной ссылке 1С (формат <code>e1cib/...</code>).</td></tr>
<tr><td><code>get_link_of_object</code></td><td>Генерация навигационной ссылки на объект из результатов запроса.</td></tr>
<tr><td><code>find_references_to_object</code></td><td>Поиск всех мест использования объекта (ссылки в документах, регистрах, справочниках).</td></tr>
<tr><td><code>get_access_rights</code></td><td>Анализ ролей и прав доступа на объекты метаданных. Показывает, какие роли имеют доступ и какие операции разрешены.</td></tr>
</table>

<h3>Документация платформы (через platform-context, 5 инструментов)</h3>
<table>
<tr><th>Инструмент</th><th>Описание</th></tr>
<tr><td><code>info</code></td><td>Общая информация о типе платформы 1С: описание, назначение, базовый тип.</td></tr>
<tr><td><code>getMembers</code></td><td>Список всех свойств и методов типа (например, все методы объекта <code>Запрос</code>).</td></tr>
<tr><td><code>getMember</code></td><td>Детальное описание конкретного метода или свойства типа: параметры, типы возврата, описание.</td></tr>
<tr><td><code>getConstructors</code></td><td>Описание конструкторов типа (варианты создания через <code>Новый</code>).</td></tr>
<tr><td><code>search</code></td><td>Полнотекстовый поиск по документации платформы: типы, методы, свойства.</td></tr>
</table>

<h3>Навигация по BSL-коду (через bsl-lsp-bridge, 14 инструментов)</h3>
<table>
<tr><th>Инструмент</th><th>Описание</th></tr>
<tr><td><code>symbol_explore</code></td><td>Семантический поиск символов (процедур, функций, переменных) в BSL-коде проекта.</td></tr>
<tr><td><code>definition</code></td><td>Переход к определению символа — показывает файл и строку, где объявлена процедура/функция.</td></tr>
<tr><td><code>hover</code></td><td>Информация о символе под курсором: тип, параметры, документация.</td></tr>
<tr><td><code>call_hierarchy</code></td><td>Дерево вызовов: кто вызывает данную процедуру (incoming) и что она вызывает (outgoing).</td></tr>
<tr><td><code>call_graph</code></td><td>Построение графа вызовов с определением точек входа. Показывает цепочки вызовов между модулями.</td></tr>
<tr><td><code>document_diagnostics</code></td><td>Ошибки и предупреждения в конкретном BSL-файле (синтаксические ошибки, стилевые замечания).</td></tr>
<tr><td><code>project_analysis</code></td><td>Общий анализ проекта: количество символов, связи между модулями, структура.</td></tr>
<tr><td><code>lsp_status</code></td><td>Статус BSL Language Server: версия, состояние индексации, количество проиндексированных файлов.</td></tr>
<tr><td><code>prepare_rename</code></td><td>Проверка возможности переименования символа перед выполнением.</td></tr>
<tr><td><code>rename</code></td><td>Переименование символа (процедуры, функции, переменной) во всех местах использования.</td></tr>
<tr><td><code>selection_range</code></td><td>Определение диапазона выделения для символа (smart selection).</td></tr>
<tr><td><code>get_range_content</code></td><td>Получение содержимого указанного диапазона строк в файле.</td></tr>
<tr><td><code>code_actions</code></td><td>Доступные действия рефакторинга для выбранного фрагмента кода.</td></tr>
<tr><td><code>did_change_watched_files</code></td><td>Уведомление LSP об изменении файлов (для переиндексации).</td></tr>
</table>

<h3>Шлюзовые инструменты (встроены в шлюз, 20 инструментов)</h3>
<table>
<tr><th>Инструмент</th><th>Описание</th></tr>
<tr><td><code>get_server_status</code></td><td>Статус всех MCP-бэкендов: доступность, количество инструментов.</td></tr>
<tr><td><code>export_bsl_sources</code></td><td>Выгрузка исходников конфигурации 1С через ibcmd или сервис выгрузки на хосте.</td></tr>
<tr><td><code>connect_database</code></td><td>Подключение новой базы 1С: регистрация, создание Docker-контейнеров.</td></tr>
<tr><td><code>disconnect_database</code></td><td>Отключение базы: остановка контейнеров, удаление из реестра.</td></tr>
<tr><td><code>switch_database</code></td><td>Переключение активной базы для текущей MCP-сессии (per-session routing).</td></tr>
<tr><td><code>list_databases</code></td><td>Список всех зарегистрированных баз и их статусы подключения.</td></tr>
<tr><td><code>validate_query</code></td><td>Проверка синтаксиса запроса 1С без выполнения: статические проверки (скобки, ключевые слова) + серверная валидация через <code>ПЕРВЫЕ 0</code>.</td></tr>
<tr><td><code>reindex_bsl</code></td><td>Принудительная переиндексация BSL Language Server. Используйте после ручного изменения файлов, git pull или внешней выгрузки.</td></tr>
<tr><td><code>write_bsl</code></td><td>Запись BSL-модуля в проект с автоматической переиндексацией LSP.</td></tr>
<tr><td><code>bsl_index</code></td><td>Построение полнотекстового поискового индекса по BSL-исходникам: все процедуры, функции, комментарии.</td></tr>
<tr><td><code>bsl_search_tool</code></td><td>Поиск процедур и функций в индексе BSL. Поддерживает фильтрацию по экспортным символам.</td></tr>
<tr><td><code>enable_anonymization</code></td><td>Включение маскировки персональных данных в ответах инструментов.</td></tr>
<tr><td><code>disable_anonymization</code></td><td>Выключение маскировки персональных данных.</td></tr>
<tr><td><code>its_search</code></td><td>Поиск по документации ИТС (1С:Информационно-технологическое сопровождение) через API 1С:Напарника. Требует настройки <code>NAPARNIK_API_KEY</code>.</td></tr>
<tr><td><code>invalidate_metadata_cache</code></td><td>Очистка кеша метаданных. Аналог кнопки «Очистить кеш» в дашборде.</td></tr>
<tr><td><code>query_stats</code></td><td>Статистика производительности запросов: количество, среднее/максимальное время, процент ошибок.</td></tr>
<tr><td><code>capture_form</code></td><td>Снимок экрана (скриншот) текущей открытой формы в клиенте 1С. Возвращает изображение в формате base64.</td></tr>
<tr><td><code>graph_stats</code></td><td>Статистика графа зависимостей BSL: количество узлов, рёбер, распределение по типам объектов. Требует bsl-graph.</td></tr>
<tr><td><code>graph_search</code></td><td>Поиск объектов конфигурации в графе зависимостей. Требует bsl-graph.</td></tr>
<tr><td><code>graph_related</code></td><td>Поиск связанных объектов в графе зависимостей: что использует объект и что его использует (impact analysis). Требует bsl-graph.</td></tr>
</table>

<h3>MCP-ресурс</h3>
<p>Шлюз также предоставляет один MCP-ресурс: <code>syntax_1c.txt</code> — справочник синтаксиса встроенного языка 1С (BSL): типы, операторы, управляющие конструкции, процедуры, исключения, директивы препроцессора. AI использует его как контекст при написании BSL-кода.</p>

<!-- ================================================================== -->
<h2 id="api-ru">6. API-эндпоинты</h2>
<p>Полный список HTTP-эндпоинтов шлюза. Основной вход для AI-ассистентов — <code>/mcp</code>. Остальные эндпоинты используются дашбордом, обработкой EPF или внешними системами.</p>
<table>
<tr><th>Путь</th><th>Метод</th><th>Описание</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP — основная точка входа для AI-ассистентов. Поддерживает stateful сессии с idle timeout 8 часов.</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>JSON-статус всех бэкендов. Возвращает <code>{"status":"ok"}</code> если все бэкенды доступны, <code>{"status":"degraded"}</code> если хотя бы один недоступен.</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI дашборд. Параметр <code>?lang=ru|en</code> для переключения языка.</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>Эта страница документации. Параметр <code>?lang=ru|en</code>.</td></tr>
<tr><td><code>/dashboard/diagnostics</code></td><td>GET</td><td>Полный диагностический отчёт в формате JSON (открывается в новой вкладке).</td></tr>
<tr><td><code>/api/export-bsl</code></td><td>POST</td><td>REST для выгрузки BSL-исходников. Вызывается обработкой MCPToolkit.epf при нажатии «Выгрузить BSL». Тело: <code>{"connection":"...","output_dir":"..."}</code>.</td></tr>
<tr><td><code>/api/register</code></td><td>POST</td><td>Регистрация обработки EPF в шлюзе. Вызывается MCPToolkit.epf при нажатии «Подключиться». Тело: <code>{"name":"...","connection":"..."}</code>. Если база не подключена — автоматически подключает.</td></tr>
<tr><td><code>/api/unregister</code></td><td>POST</td><td>Отмена регистрации EPF. Вызывается при нажатии «Отключиться» в обработке. Тело: <code>{"name":"..."}</code>.</td></tr>
<tr><td><code>/api/action/connect-db</code></td><td>POST</td><td>Подключение базы данных из дашборда. Тело: <code>{"name":"...","connection":"...","project_path":"..."}</code>.</td></tr>
<tr><td><code>/api/action/disconnect</code></td><td>POST</td><td>Отключение базы. Параметр: <code>?name=имя_базы</code>.</td></tr>
<tr><td><code>/api/action/switch</code></td><td>POST</td><td>Установка базы по умолчанию. Параметр: <code>?name=имя_базы</code>.</td></tr>
<tr><td><code>/api/action/edit-db</code></td><td>POST</td><td>Редактирование параметров базы. Тело: <code>{"name":"...","connection":"...","project_path":"..."}</code>.</td></tr>
<tr><td><code>/api/action/clear-cache</code></td><td>POST</td><td>Очистка кеша метаданных.</td></tr>
<tr><td><code>/api/action/toggle-anon</code></td><td>POST</td><td>Переключение анонимизации (вкл/выкл).</td></tr>
<tr><td><code>/api/action/get-env</code></td><td>POST</td><td>Чтение содержимого файла <code>.env</code> для отображения в редакторе дашборда.</td></tr>
<tr><td><code>/api/action/save-env</code></td><td>POST</td><td>Сохранение файла <code>.env</code> с автоперезапуском шлюза. Тело: <code>{"content":"..."}</code>.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="env-ru">7. Переменные окружения (.env)</h2>
<p>Все параметры настраиваются через файл <code>.env</code> в корне проекта. Файл монтируется в контейнер шлюза. Редактировать можно из дашборда (вкладка «Параметры» → «Редактировать») или напрямую на хосте.</p>
<table>
<tr><th>Переменная</th><th>По умолч.</th><th>Описание</th></tr>
<tr><td><code>PORT</code></td><td>8080</td><td>Порт, на котором слушает MCP-шлюз. AI-ассистент подключается к <code>http://localhost:{PORT}/mcp</code>.</td></tr>
<tr><td><code>LOG_LEVEL</code></td><td>INFO</td><td>Уровень логирования: <code>DEBUG</code> (максимум деталей), <code>INFO</code>, <code>WARNING</code>, <code>ERROR</code> (только ошибки). Для отладки проблем установите <code>DEBUG</code>.</td></tr>
<tr><td><code>ONEC_TOOLKIT_URL</code></td><td>http://onec-toolkit:6003/mcp</td><td>URL статического бэкенда onec-toolkit внутри Docker-сети. Изменяйте только если используете нестандартную конфигурацию контейнеров.</td></tr>
<tr><td><code>PLATFORM_CONTEXT_URL</code></td><td>http://platform-context:8080/sse</td><td>URL бэкенда документации платформы внутри Docker-сети.</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Список включённых бэкендов через запятую. Чтобы добавить YaXUnit, укажите: <code>onec-toolkit,platform-context,bsl-lsp-bridge,test-runner</code>.</td></tr>
<tr><td><code>EXPORT_HOST_URL</code></td><td>http://localhost:8082</td><td>URL сервиса выгрузки BSL, запущенного на хосте (<code>tools/export-host-service.py</code>). На Windows: <code>http://host.docker.internal:8082</code>.</td></tr>
<tr><td><code>IBCMD_PATH</code></td><td>/opt/1cv8/.../ibcmd</td><td>Полный путь к утилите ibcmd платформы 1С внутри контейнера. Используется для выгрузки BSL, если EXPORT_HOST_URL не задан.</td></tr>
<tr><td><code>BSL_WORKSPACE</code></td><td>/projects</td><td>Рабочий каталог BSL-исходников внутри LSP-контейнера. Сюда монтируются исходники конфигурации.</td></tr>
<tr><td><code>BSL_HOST_WORKSPACE</code></td><td>—</td><td>Путь к BSL-исходникам на хосте. Используется для преобразования путей между контейнером и хостом (чтобы AI видел реальные пути файлов).</td></tr>
<tr><td><code>LSP_DOCKER_CONTAINER</code></td><td>mcp-lsp-zup</td><td>Имя статического LSP-контейнера (устаревший параметр). Динамические контейнеры создаются автоматически при подключении баз.</td></tr>
<tr><td><code>BSL_LSP_COMMAND</code></td><td>—</td><td>Команда для прямого запуска BSL Language Server (all-in-one режим, без Docker). Используется вместо docker exec, если LSP установлен локально.</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>Ключ API для 1С:Напарника (поиск по ИТС). Получите на <a href="https://code.1c.ai">code.1c.ai</a> → Профиль → API-токен. Требует подписку ИТС.</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>Время жизни кеша метаданных в секундах. 600 = 10 минут. Значение <code>0</code> полностью отключает кеширование.</td></tr>
<tr><td><code>TEST_RUNNER_URL</code></td><td>http://localhost:8000/sse</td><td>URL бэкенда mcp-onec-test-runner для запуска тестов YaXUnit. Опционально.</td></tr>
<tr><td><code>BSL_GRAPH_URL</code></td><td>http://localhost:8888</td><td>URL сервиса bsl-graph для графа зависимостей. Опционально, требует NebulaGraph.</td></tr>
<tr><td><code>PLATFORM_PATH</code></td><td>/opt/1cv8/x86_64/8.3.27.2074</td><td>Полный путь к каталогу конкретной версии платформы 1С. Используется бэкендом platform-context для чтения документации.</td></tr>
<tr><td><code>HOST_PLATFORM_PATH</code></td><td>/opt/1cv8</td><td>Корневой путь к платформе 1С на хосте. Монтируется в контейнеры для доступа к ibcmd и другим утилитам.</td></tr>
<tr><td><code>ONEC_TIMEOUT</code></td><td>180</td><td>Таймаут выполнения команд в 1С (секунды). Если запрос или код не завершится за это время, будет возвращена ошибка таймаута.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="diagnostics-ru">8. Диагностика</h2>
<p>Ссылка «Диагностика» расположена в нижней части дашборда (footer). Она открывает полный диагностический отчёт в новой вкладке браузера в формате JSON.</p>

<h3>Что содержит отчёт</h3>
<table>
<tr><th>Раздел</th><th>Содержимое</th></tr>
<tr><td><b>gateway</b></td><td>Версия шлюза, порт, количество активных MCP-сессий, настройка idle timeout.</td></tr>
<tr><td><b>backends</b></td><td>Статус каждого бэкенда: доступность, количество инструментов, ошибки. Аналог эндпоинта <code>/health</code>.</td></tr>
<tr><td><b>databases</b></td><td>Список всех подключённых баз: имя, строка подключения, путь к проекту, статус EPF, порт toolkit-бэкенда, имя LSP-контейнера.</td></tr>
<tr><td><b>profiling</b></td><td>Статистика execute_query: количество, среднее/макс/мин время, медленные запросы, процент ошибок.</td></tr>
<tr><td><b>cache</b></td><td>Состояние кеша метаданных: количество записей, hit rate, TTL, размер в памяти.</td></tr>
<tr><td><b>anonymization</b></td><td>Включена ли анонимизация, количество замен в текущей сессии.</td></tr>
<tr><td><b>docker</b></td><td>Информация о Docker-демоне: версия, ОС, количество CPU, объём RAM, размер образов и томов.</td></tr>
<tr><td><b>containers</b></td><td>Список контейнеров проекта: имя, образ, статус, время запуска.</td></tr>
<tr><td><b>config</b></td><td>Все переменные окружения (кроме секретных, которые маскируются как <code>***</code>).</td></tr>
<tr><td><b>container_logs</b></td><td>Последние 10 строк логов каждого контейнера проекта. Помогает быстро увидеть ошибки без использования <code>docker logs</code>.</td></tr>
</table>

<h3>Когда использовать</h3>
<ul>
<li>При поиске причины проблемы — отчёт содержит всю необходимую информацию в одном месте</li>
<li>При обращении за помощью — скопируйте JSON-отчёт и приложите к описанию проблемы</li>
<li>Для мониторинга — периодическая проверка состояния всех компонентов</li>
</ul>
<p>Диагностика также доступна через API: <code>POST /api/action/diagnostics</code>.</p>

<!-- ================================================================== -->
<h2 id="troubleshooting-ru">9. Устранение неполадок</h2>

<h3>Бэкенд показывает красный статус</h3>
<p><b>Симптом:</b> На вкладке «Статус» один или несколько бэкендов отображаются с красным индикатором.</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Контейнер не запущен. Проверьте: <code>docker compose ps</code>. Если контейнер остановлен — запустите: <code>docker compose up -d</code>.</li>
<li>Контейнер упал с ошибкой. Посмотрите логи: <code>docker logs onec-mcp-gw -f</code> (для шлюза), <code>docker logs onec-mcp-toolkit -f</code> (для toolkit). Частая причина — нехватка памяти.</li>
<li>Сетевая проблема между контейнерами. Убедитесь, что контейнеры находятся в одной Docker-сети: <code>docker network ls</code>.</li>
</ol>

<h3>Обработка EPF не подключается</h3>
<p><b>Симптом:</b> В обработке MCPToolkit.epf при нажатии «Подключиться» появляется ошибка или статус остаётся «Не подключено».</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Шлюз не запущен. Проверьте: <code>curl http://localhost:8080/health</code>. Должен вернуть JSON.</li>
<li>Неверный адрес шлюза в обработке. Убедитесь, что поле «Адрес шлюза» содержит правильный URL (по умолчанию <code>http://localhost:8080</code>).</li>
<li>Брандмауэр блокирует порт. На Windows проверьте, разрешён ли порт 8080 в настройках брандмауэра.</li>
<li>1С запущена в режиме тонкого клиента с ограничениями HTTP. Попробуйте использовать толстый клиент.</li>
</ol>

<h3>BSL-навигация не работает</h3>
<p><b>Симптом:</b> Инструменты <code>definition</code>, <code>symbol_explore</code>, <code>call_hierarchy</code> возвращают пустые результаты или ошибки.</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Исходники не выгружены. Нажмите «Выгрузить BSL» в обработке MCPToolkit.epf. Дождитесь завершения (3-5 минут для крупных конфигураций).</li>
<li>LSP ещё индексирует файлы. Проверьте статус: вызовите инструмент <code>lsp_status</code>. Индексация крупных проектов (ERP — 18 000 модулей) занимает несколько минут.</li>
<li>LSP-контейнер не запущен. Проверьте: <code>docker ps | grep mcp-lsp</code>.</li>
<li>Путь к проекту указан неверно. Убедитесь, что каталог BSL-исходников на хосте содержит файлы <code>.bsl</code> и корректно монтируется в контейнер.</li>
</ol>

<h3>Ошибка при редактировании .env в дашборде</h3>
<p><b>Симптом:</b> При нажатии «Редактировать» в конфигурации шлюза появляется сообщение «.env file not found».</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Файл .env не существует. Создайте: <code>cp .env.example .env</code> в корне проекта.</li>
<li>Файл не монтируется в контейнер. Проверьте, что в <code>docker-compose.yml</code> присутствует строка <code>./.env:/data/.env:rw</code>.</li>
<li>Нет прав на запись. Проверьте права: <code>ls -la .env</code>. Файл должен быть доступен для записи.</li>
</ol>

<h3>AI получает устаревшие метаданные</h3>
<p><b>Симптом:</b> AI утверждает, что у объекта есть реквизит, которого нет (или наоборот).</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Кеш метаданных содержит устаревшие данные. Очистите кеш: кнопка «Очистить кеш» на вкладке «Параметры» или инструмент <code>invalidate_metadata_cache</code>.</li>
<li>Уменьшите TTL кеша в настройках: <code>METADATA_CACHE_TTL=60</code> (1 минута вместо 10).</li>
</ol>

<h3>Запросы execute_query выполняются медленно</h3>
<p><b>Симптом:</b> Запросы занимают более 5 секунд, карточка «Профилирование» показывает большие числа.</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Неоптимальные запросы от AI. Проверьте поле <code>_profiling</code> в ответе — оно содержит подсказки (SELECT *, отсутствие WHERE, много JOIN).</li>
<li>Нагрузка на сервер 1С. Запросы выполняются в контексте информационной базы и конкурируют с другими пользователями.</li>
<li>Сетевые задержки. Если сервер 1С находится на удалённом хосте — проверьте ping и пропускную способность.</li>
<li>Увеличьте таймаут: <code>ONEC_TIMEOUT=300</code> (5 минут вместо 3).</li>
</ol>

<h3>Обработка показывает «Нет ответа от шлюза» (таймаут)</h3>
<p><b>Симптом:</b> Обработка MCPToolkit.epf периодически выводит в журнал ошибку таймаута.</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Шлюз перегружен или перезапускается. Проверьте логи: <code>docker logs onec-mcp-gw --tail 50</code>.</li>
<li>Long-polling соединение разорвалось. Нажмите «Отключиться» и затем «Подключиться» повторно.</li>
<li>Проблемы с Docker-сетью. Перезапустите контейнеры: <code>docker compose restart</code>.</li>
</ol>

<h3>Docker-контейнеры не создаются при подключении базы</h3>
<p><b>Симптом:</b> При подключении базы появляется ошибка «Failed to create container».</p>
<p><b>Причины и решения:</b></p>
<ol>
<li>Недостаточно ресурсов Docker. Проверьте свободное место: <code>docker system df</code>. Очистите неиспользуемые образы: <code>docker system prune</code>.</li>
<li>Нет доступа к Docker API. Шлюз обращается к Docker через сокет. Убедитесь, что <code>/var/run/docker.sock</code> монтируется в контейнер шлюза.</li>
<li>Конфликт имён. Контейнер с таким именем уже существует. Удалите вручную: <code>docker rm -f onec-toolkit-{имя_базы}</code>.</li>
</ol>

</body></html>""",

    "en": r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Documentation — onec-mcp-universal</title>
<style>""" + _DOC_STYLE + """</style></head><body>
<a class="back" href="/dashboard?lang=en">&larr; Back to dashboard</a>
<h1>onec-mcp-universal Documentation</h1>
<p>Version: """ + VERSION + """ | <a href="https://github.com/AlekseiSeleznev/onec-mcp-universal">GitHub</a> | License: MIT</p>

<h2>Contents</h2>
<ol>
<li><a href="#overview-en">Overview</a> — what it is, why it exists, architecture</li>
<li><a href="#status-en">Status Tab</a> — databases, profiling, anonymization, cache, backends, Docker</li>
<li><a href="#params-en">Parameters Tab</a> — database management, configuration, actions</li>
<li><a href="#epf-en">MCPToolkit.epf Data Processor</a> — interface, buttons, security, event log</li>
<li><a href="#tools-en">MCP Tools</a> — complete list of 47 tools</li>
<li><a href="#api-en">API Endpoints</a> — full table</li>
<li><a href="#env-en">Environment Variables</a> — all .env parameters</li>
<li><a href="#diagnostics-en">Diagnostics</a> — report contents</li>
<li><a href="#troubleshooting-en">Troubleshooting</a> — common problems and solutions</li>
</ol>

<!-- ================================================================== -->
<h2 id="overview-en">1. Overview</h2>

<h3>What it is</h3>
<p><b>onec-mcp-universal</b> is a unified MCP gateway that enables AI assistants (Claude Code, Cursor, Windsurf, and any MCP clients) to work with 1C:Enterprise databases. MCP (Model Context Protocol) is an open protocol through which an AI model calls external tools: executes database queries, reads configuration metadata, navigates source code, and more.</p>

<h3>Why a gateway is needed</h3>
<p>Without the gateway, you would need to connect several separate MCP servers to the AI assistant (one for 1C data, another for code navigation, a third for platform documentation). The gateway combines them into a single entry point — <code>http://localhost:8080/mcp</code>. The AI assistant connects once and gets access to all 47+ tools at once.</p>

<h3>How it works</h3>
<p>The interaction chain looks like this:</p>
<pre><code>AI assistant (Claude Code / Cursor / Windsurf)
    |
    | MCP Streamable HTTP
    v
MCP gateway (onec-mcp-universal, port 8080)
    |
    +---> onec-toolkit      — 1C data (queries, code, metadata)
    +---> platform-context  — platform API documentation
    +---> bsl-lsp-bridge    — BSL code navigation
    +---> test-runner        — YaXUnit test execution (optional)
    |
    v
MCPToolkit.epf (data processor inside 1C client)
    |
    v
1C:Enterprise database</code></pre>

<p>When the AI assistant calls a tool (e.g. <code>execute_query</code>), the gateway determines which backend owns it and forwards the request. The <code>onec-toolkit</code> backend passes the command to the MCPToolkit.epf data processor running in the 1C client. The data processor executes the query in the database and returns the result back through the chain.</p>

<h3>Per-session routing</h3>
<p>Each AI assistant session works with its own active database <b>independently</b>. This means two different Claude Code windows can simultaneously work with different databases (e.g. one with ERP, another with HRM), and their requests will not interfere. All registered databases remain connected simultaneously. Switching between databases is done via the <code>switch_database</code> command. Session idle timeout is 8 hours.</p>

<div class="note"><p><b>Single connection point:</b> Regardless of how many databases and backends are connected, the AI assistant always uses a single address — <code>http://localhost:8080/mcp</code>.</p></div>

<!-- ================================================================== -->
<h2 id="status-en">2. Status Tab</h2>
<p>The Status tab is the main dashboard screen. It displays the current state of all system components as six cards. Information on this tab is read-only — all actions are performed on the Parameters tab.</p>

<h3>Databases Card</h3>
<p>A table listing all connected 1C databases. Each row contains three columns:</p>
<table>
<tr><th>Column</th><th>Description</th></tr>
<tr><td><b>Name</b></td><td>Unique database identifier (Latin letters, digits, hyphens, underscores). Used in Docker container names: <code>onec-toolkit-{name}</code> and <code>mcp-lsp-{name}</code>. Examples: <code>ERP</code>, <code>ZUP_TEST</code>, <code>buh-main</code>.</td></tr>
<tr><td><b>Connection</b></td><td>1C connection string in standard platform format. For server databases: <code>Srvr=server_name;Ref=db_name;</code>. For file databases: <code>File=/path/to/db</code>.</td></tr>
<tr><td><b>EPF</b></td><td>MCPToolkit.epf connection status. Displayed as a colored indicator with text:<br>
<span style="color:#22c55e">Conn.</span> (green) — the data processor is running in the 1C client, long-polling connection is active, AI can execute queries to this database.<br>
<span style="color:#eab308">Disconn.</span> (yellow) — Docker containers for the database are running, but the data processor is not yet connected. You need to open MCPToolkit.epf in the 1C client and click "Connect".</td></tr>
</table>
<p>The default database has a badge <span style="background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.75rem">default</span> next to its name. This database is used for new AI sessions unless the session switches to another database via <code>switch_database</code>.</p>
<div class="note"><p><b>Auto-connect:</b> If the user clicks "Connect" in the MCPToolkit.epf data processor and the database is not yet registered in the gateway, it is automatically connected — Docker containers are created, the database appears in this table.</p></div>

<h3>Profiling Card</h3>
<p>Automatic performance statistics collection for all <code>execute_query</code> calls to 1C databases. Data accumulates from gateway startup and resets on restart.</p>
<table>
<tr><th>Metric</th><th>Description</th></tr>
<tr><td><b>Queries</b></td><td>Total number of queries executed since gateway startup. All <code>execute_query</code> calls to all connected databases are counted.</td></tr>
<tr><td><b>Avg</b></td><td>Average query execution time in milliseconds. Includes time to send the query to 1C and receive the response. Values above 1000 ms signal a need for query optimization.</td></tr>
<tr><td><b>Max</b></td><td>Maximum execution time for a single query in milliseconds. Helps identify outliers — individual heavy queries.</td></tr>
<tr><td><b>Slow (&gt;5s)</b></td><td>Number of queries that took more than 5 seconds. Such queries are considered slow and typically require optimization (adding indexes, reworking conditions, using temp tables).</td></tr>
</table>
<p>If no queries have been executed yet, the card shows "No queries yet".</p>
<p>Besides the dashboard, profiling statistics can be obtained via the <code>query_stats</code> MCP tool. Each <code>execute_query</code> response automatically includes a <code>_profiling</code> field with execution duration and optimization hints (e.g. "query uses SELECT *", "missing WHERE", "many JOINs").</p>

<h3>Anonymization Card</h3>
<p>Status of the personal data (PII) masking system in responses from 1C. Displayed as a colored indicator:</p>
<ul>
<li><span style="color:#22c55e">Enabled</span> (green) — all responses from <code>execute_query</code>, <code>execute_code</code>, <code>get_object_by_link</code>, <code>get_event_log</code> tools pass through the anonymization filter.</li>
<li><span style="color:#eab308">Disabled</span> (yellow) — data is passed to AI without modification.</li>
</ul>
<p><b>What is masked:</b></p>
<ul>
<li><b>Full names (FIO)</b> — patterns like "Last First Middle" are recognized and replaced with stable fake data (e.g. Ivanov Ivan Ivanovich always becomes Petrov Sergey Alexandrovich)</li>
<li><b>INN (tax ID)</b> — 10-digit (legal entities) and 12-digit (individuals) numbers are replaced with valid fake INNs</li>
<li><b>SNILS (social security)</b> — numbers in format XXX-XXX-XXX XX</li>
<li><b>Phone numbers</b> — Russian numbers (+7...)</li>
<li><b>Email addresses</b></li>
<li><b>Company names</b> — legal entities (LLC, JSC, etc.)</li>
</ul>
<p><b>Stable mapping:</b> The same original value is <b>always</b> replaced with the same fake within a session. This allows AI to work correctly with the data — relationships between objects (e.g. "client Alpha has documents...") are preserved.</p>
<p><b>When to use:</b> Enable anonymization when working with production databases containing real personal data. This is important for compliance with data protection regulations (e.g. Russian Federal Law 152-FZ) — masked data is no longer considered personal. On test databases with synthetic data, anonymization can be left disabled.</p>

<h3>Metadata Cache Card</h3>
<p>Results of <code>get_metadata</code> calls (configuration structure information: attributes, tabular sections, types) are cached on the gateway side to avoid requesting the same metadata from 1C repeatedly.</p>
<table>
<tr><th>Metric</th><th>Description</th></tr>
<tr><td><b>Entries</b></td><td>Number of cached metadata objects. Each unique <code>get_metadata</code> call with a specific set of parameters creates one cache entry.</td></tr>
<tr><td><b>Hit Rate</b></td><td>Percentage of requests served from cache. Values of 80-100% mean the cache is working effectively. A low percentage may mean AI is requesting different objects each time, or the TTL is too short.</td></tr>
<tr><td><b>TTL</b></td><td>Cache entry lifetime in seconds. Default is 600 seconds (10 minutes). Configured via the <code>METADATA_CACHE_TTL</code> variable in the <code>.env</code> file. Value of 0 completely disables caching.</td></tr>
</table>
<p><b>When to clear the cache:</b> After changing the 1C configuration structure (adding/removing attributes, tabular sections, metadata objects). You can clear it using the button on the Parameters tab, via the <code>invalidate_metadata_cache</code> MCP tool, or wait for automatic invalidation by TTL.</p>

<h3>Backends Card</h3>
<p>A backend is a separate MCP server that provides a set of tools in a specific category. The gateway aggregates tools from all backends and presents them to the AI assistant as a single set.</p>
<p>Each row shows:</p>
<ul>
<li><b>Colored indicator</b> — <span style="color:#22c55e">green</span> = backend is available and responding, <span style="color:#ef4444">red</span> = backend is unavailable (container not running or an error occurred)</li>
<li><b>Name</b> — backend identifier</li>
<li><b>N tools</b> — number of tools the backend provides</li>
<li><b>"active" badge</b> — displayed for backends bound to the current active database</li>
</ul>
<p><b>Static backends</b> (created at gateway startup):</p>
<table>
<tr><th>Backend</th><th>Tools</th><th>Purpose</th></tr>
<tr><td><code>onec-toolkit</code></td><td>8</td><td>DB queries, code execution, metadata, event log, access rights, object links. Works through the MCPToolkit.epf data processor.</td></tr>
<tr><td><code>platform-context</code></td><td>5</td><td>1C built-in language API documentation: type method search, constructor descriptions, object member listings.</td></tr>
<tr><td><code>bsl-lsp-bridge</code></td><td>14</td><td>BSL code navigation: symbol search, go-to-definition, call graphs, error diagnostics, renaming.</td></tr>
</table>
<p><b>Dynamic backends</b> (created when each database is connected):</p>
<ul>
<li><code>onec-toolkit-{db_name}</code> — dedicated data backend for a specific database</li>
<li><code>mcp-lsp-{db_name}</code> — dedicated BSL Language Server with the configuration index of a specific database</li>
</ul>
<p><b>Optional backends</b> (enabled via <code>ENABLED_BACKENDS</code>):</p>
<ul>
<li><code>test-runner</code> — YaXUnit test execution. Add <code>test-runner</code> to <code>ENABLED_BACKENDS</code> and start: <code>docker compose --profile test-runner up -d</code>.</li>
</ul>

<h3>Docker Containers Card</h3>
<p>The upper part of the card shows Docker daemon information: Docker version, CPU count, RAM, total image and volume sizes.</p>
<p>Below is a table of project containers with three columns:</p>
<table>
<tr><th>Column</th><th>Description</th></tr>
<tr><td><b>Container</b></td><td>Docker container name with a colored status indicator</td></tr>
<tr><td><b>Image</b></td><td>Docker image from which the container was created</td></tr>
<tr><td><b>Status</b></td><td><code>running</code> or <code>stopped</code></td></tr>
</table>
<p><b>Container types:</b></p>
<ul>
<li><code>onec-mcp-gw</code> — MCP gateway (this server, port 8080). Receives MCP requests from AI and routes them to backends.</li>
<li><code>onec-mcp-toolkit</code> — static data backend (port 6003). Processes 1C requests via long-polling with EPF.</li>
<li><code>onec-mcp-platform</code> — 1C platform documentation backend (port 8081). Contains structured built-in language API documentation.</li>
<li><code>onec-toolkit-{db_name}</code> — dynamic data backend, created automatically when each new database is connected.</li>
<li><code>mcp-lsp-{db_name}</code> — BSL Language Server for each database. Indexes configuration sources and provides code navigation.</li>
</ul>

<!-- ================================================================== -->
<h2 id="params-en">3. Parameters Tab</h2>
<p>The Parameters tab contains management tools: connecting and disconnecting databases, editing gateway configuration, cache and anonymization actions.</p>

<h3>Database Management</h3>
<p>The upper part of the card is a table of connected databases (similar to the Databases card on the Status tab), but with additional control buttons for each database:</p>
<table>
<tr><th>Button</th><th>Description</th></tr>
<tr><td><b>Default</b></td><td>Sets the database as the default for new AI sessions. The button is only shown for databases that are <b>not yet</b> the default. After clicking, a badge <span style="background:#164e63;color:#22d3ee;padding:1px 6px;border-radius:3px;font-size:.75rem">default</span> appears next to the database name.</td></tr>
<tr><td><b>Edit</b></td><td>Opens a dialog to edit the connection string and project path. After saving changes, you need to reconnect the database to apply the new parameters.</td></tr>
<tr><td><b>Disconnect</b></td><td>Stops and removes the database Docker containers (<code>onec-toolkit-{name}</code> and <code>mcp-lsp-{name}</code>). <b>The 1C database data and exported BSL sources on disk are not affected</b> — only containers are removed. The database can be reconnected at any time.</td></tr>
</table>

<h3>Adding a Database</h3>
<p>The lower part of the card is the "Add Database" form with three fields:</p>
<table>
<tr><th>Field</th><th>Description</th><th>Example</th></tr>
<tr><td><b>DB name</b></td><td>Unique identifier. Latin letters, digits, hyphens, and underscores are allowed. Maximum 63 characters.</td><td><code>ERP_DEMO</code></td></tr>
<tr><td><b>Connection string</b></td><td>Standard 1C platform connection string. Server: <code>Srvr=server_name;Ref=db_name;</code>. File: <code>File=/path/to/db</code>. With authentication: <code>Srvr=srv;Ref=db;Usr=admin;Pwd=password;</code></td><td><code>Srvr=localhost;Ref=ERP;</code></td></tr>
<tr><td><b>Project path</b></td><td>Absolute path on the host where BSL configuration sources will be exported. This directory is mounted into the LSP container for code navigation.</td><td><code>/home/user/projects/ERP</code></td></tr>
</table>
<p>After clicking the "Connect" button, the gateway will create two Docker containers for the database and register it. Then open MCPToolkit.epf in the 1C client and click "Connect".</p>

<h3>Three Ways to Connect a Database</h3>
<p>A 1C database can be connected to the gateway in three equivalent ways:</p>
<ol>
<li><b>From the MCPToolkit.epf data processor</b> (recommended) — open the data processor in the 1C:Enterprise client, click "Connect". The data processor will automatically determine the database name and server, register the database in the gateway, and create Docker containers. No manual configuration is required.</li>
<li><b>From the dashboard</b> — go to the Parameters tab, fill in the "Add Database" form, and click "Connect". Then open MCPToolkit.epf in 1C and click "Connect" to establish the long-polling connection.</li>
<li><b>Via AI assistant</b> — type in the AI chat in natural language:
<pre><code>Connect database ERP_DEMO, connection string Srvr=localhost;Ref=ERP_DEMO;, folder /home/user/projects/ERP_DEMO</code></pre>
The AI will call the <code>connect_database</code> tool with the specified parameters. Then open MCPToolkit.epf in 1C and click "Connect".</li>
</ol>

<h3>Gateway Configuration</h3>
<p>The second card on the Parameters tab shows a table of current values for all gateway environment variables (<code>.env</code> file). At the top are action buttons (clear cache, anonymization) and an "Edit" button.</p>
<p><b>Editing process:</b></p>
<ol>
<li>Click the <b>"Edit"</b> button — the table is replaced with a text editor showing the full contents of the <code>.env</code> file.</li>
<li>Make your changes. Format: <code>VARIABLE=value</code>, one variable per line. Lines starting with <code>#</code> are comments.</li>
<li>Click <b>"Save"</b> — the file is saved, and the gateway <b>automatically restarts</b> within a few seconds. All current MCP sessions will be disconnected (the AI assistant will reconnect automatically).</li>
<li>Or click <b>"Cancel"</b> — the editor closes without saving.</li>
</ol>
<div class="note"><p><b>Mounting:</b> The <code>.env</code> file is mounted into the container as <code>./.env:/data/.env:rw</code>. Changes from the dashboard are written directly to the file on the host. Works on Linux and Windows (via <code>docker-compose.windows.yml</code>).</p></div>

<h3>Actions</h3>
<p>Quick action buttons are located above the configuration table:</p>
<table>
<tr><th>Action</th><th>Description</th><th>When to use</th></tr>
<tr><td><b>Clear Cache</b></td><td>Removes all cached <code>get_metadata</code> results. Subsequent metadata requests will go directly to 1C.</td><td>After changing the configuration structure: adding/removing attributes, tabular sections, metadata objects. Also useful when AI receives outdated structure information.</td></tr>
<tr><td><b>Toggle Anonymization</b></td><td>Toggles personal data masking in tool responses. Does not require gateway restart, takes effect immediately.</td><td>Enable when working with production databases containing real names, tax IDs, phone numbers. Disable when working with test databases or when masking interferes with data analysis.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="epf-en">4. MCPToolkit.epf Data Processor</h2>
<p>The external data processor <code>MCPToolkit.epf</code> is a key component that runs on the 1C side. It is launched in the 1C:Enterprise client and acts as a mediator between the MCP gateway and the database. Without it, operations with 1C data (queries, code execution, metadata reading) are impossible.</p>
<p>The data processor file is located in the project directory: <code>1c/MCPToolkit.epf</code>.</p>

<h3>Interface Fields</h3>
<table>
<tr><th>Field</th><th>Description</th><th>How to fill</th></tr>
<tr><td><b>Gateway address</b></td><td>MCP gateway URL. Used for database registration and sending results.</td><td>Default is <code>http://localhost:8080</code>. Change if the gateway runs on a different host or port.</td></tr>
<tr><td><b>Database: name</b></td><td>Current database identifier. Determines which set of Docker containers the data processor will be bound to.</td><td>Auto-filled from the current database connection string. Read-only.</td></tr>
<tr><td><b>Database: server</b></td><td>1C server name or file database path.</td><td>Auto-detected. Read-only.</td></tr>
<tr><td><b>Database: user</b></td><td>Current 1C session user name.</td><td>Auto-detected. Read-only.</td></tr>
<tr><td><b>Database: password</b></td><td>Password for BSL source export via DESIGNER. Only needed for the "Export BSL" operation.</td><td>Enter manually. Not saved between sessions.</td></tr>
</table>

<h3>Buttons</h3>
<table>
<tr><th>Button</th><th>Action</th></tr>
<tr><td><b>Connect</b></td><td>Performs two actions:<br>1. <b>Registration</b> — sends database details (name, connection string) to the gateway via <code>/api/register</code>. If the database is not yet connected, the gateway automatically creates Docker containers.<br>2. <b>Long-polling</b> — establishes a persistent connection with the toolkit backend. The data processor starts "listening" for incoming commands from AI and executing them in the context of the current database.</td></tr>
<tr><td><b>Disconnect</b></td><td>Stops the long-polling connection. The data processor stops accepting commands. Docker containers continue running — the database remains registered, but the EPF status changes to "Disconn.".</td></tr>
<tr><td><b>Export BSL</b></td><td>Starts exporting 1C configuration sources to BSL files for code navigation. Uses ibcmd (platform command-line utility) or the host export service (export-host-service.py). On large configurations (ERP — ~18,000 modules, HRM — ~12,000 modules), indexing takes 3-5 minutes. After completion, the BSL Language Server automatically re-indexes the files.</td></tr>
</table>

<h3>Auto-allow operations</h3>
<p>Two checkboxes control automatic approval of potentially dangerous operations when AI executes arbitrary code via the <code>execute_code</code> tool:</p>
<table>
<tr><th>Checkbox</th><th>Description</th><th>Recommendation</th></tr>
<tr><td><b>Write object</b></td><td>If enabled — AI can write data (<code>Object.Write()</code>, <code>Document.Write(PostingMode.Posting)</code>) without manual operator confirmation. If disabled — each write attempt triggers a dialog in the 1C client asking "Allow write?".</td><td>On production databases — <b>disabled</b>. On test databases — at user's discretion.</td></tr>
<tr><td><b>Privileged mode</b></td><td>If enabled — AI can set privileged mode (<code>SetPrivilegedMode(True)</code>) without confirmation. Privileged mode disables access rights checking in 1C — code executes with full permissions.</td><td>On production databases — <b>disabled</b>. Enable only when necessary and with understanding of the risks.</td></tr>
</table>
<div class="warn"><p><b>Security:</b> On production databases with real data, it is recommended to keep both checkboxes disabled. Each potentially dangerous operation will require manual operator confirmation in the 1C client. This prevents accidental deletion or modification of data.</p></div>

<h3>Status and Links</h3>
<p>The lower part of the form displays the current connection status (Connected / Disconnected) and links:</p>
<ul>
<li><b>Dashboard</b> — opens the gateway web interface (<code>/dashboard</code>) in the browser</li>
<li><b>GitHub</b> — link to the project repository</li>
</ul>

<h3>Event Log</h3>
<p>A unified log at the bottom of the form displays all events in chronological order:</p>
<ul>
<li>Successful connections and disconnections</li>
<li>Incoming commands from AI (tool name, parameters)</li>
<li>Command execution results</li>
<li>Errors (network, 1C exceptions, timeouts)</li>
<li>BSL export information</li>
</ul>
<p>The log is useful for debugging — if the AI assistant receives an error, the log will show what exactly happened on the 1C side.</p>

<h3>Anonymization Tab</h3>
<p>An additional tab in the data processor allows configuring <b>precise anonymization</b> rules on the EPF side: regex patterns, replacement dictionaries, exclusion lists. This anonymization works <b>independently</b> from the gateway's server-side anonymization and can be used together with it or separately.</p>

<!-- ================================================================== -->
<h2 id="tools-en">5. MCP Tools (complete list)</h2>
<p>The gateway provides the AI assistant with 47 tools, aggregated from all backends. Tools are divided into categories.</p>

<h3>1C Data (via onec-toolkit, 8 tools)</h3>
<table>
<tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>execute_query</code></td><td>Execute a database query in 1C built-in query language. Supports parameters (<code>&amp;Parameter</code>), limits, nested queries. Automatically profiled and anonymized (if enabled).</td></tr>
<tr><td><code>execute_code</code></td><td>Execute arbitrary code in the 1C built-in language within the database context. Code runs on the 1C server. Supports returning results.</td></tr>
<tr><td><code>get_metadata</code></td><td>Get configuration metadata object structure: attributes, tabular sections, field types, string lengths, etc. Results are cached.</td></tr>
<tr><td><code>get_event_log</code></td><td>Read the 1C event log with filtering by date, event, user, severity level.</td></tr>
<tr><td><code>get_object_by_link</code></td><td>Get object data by 1C navigation link (format <code>e1cib/...</code>).</td></tr>
<tr><td><code>get_link_of_object</code></td><td>Generate a navigation link for an object from query results.</td></tr>
<tr><td><code>find_references_to_object</code></td><td>Find all places where an object is used (references in documents, registers, catalogs).</td></tr>
<tr><td><code>get_access_rights</code></td><td>Analyze roles and access rights for metadata objects. Shows which roles have access and which operations are permitted.</td></tr>
</table>

<h3>Platform Documentation (via platform-context, 5 tools)</h3>
<table>
<tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>info</code></td><td>General information about a 1C platform type: description, purpose, base type.</td></tr>
<tr><td><code>getMembers</code></td><td>List of all properties and methods of a type (e.g. all methods of the <code>Query</code> object).</td></tr>
<tr><td><code>getMember</code></td><td>Detailed description of a specific method or property: parameters, return types, description.</td></tr>
<tr><td><code>getConstructors</code></td><td>Type constructor descriptions (creation variants via <code>New</code>).</td></tr>
<tr><td><code>search</code></td><td>Full-text search across platform documentation: types, methods, properties.</td></tr>
</table>

<h3>BSL Code Navigation (via bsl-lsp-bridge, 14 tools)</h3>
<table>
<tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>symbol_explore</code></td><td>Semantic search for symbols (procedures, functions, variables) in the BSL project code.</td></tr>
<tr><td><code>definition</code></td><td>Go to symbol definition — shows the file and line where the procedure/function is declared.</td></tr>
<tr><td><code>hover</code></td><td>Information about the symbol at cursor: type, parameters, documentation.</td></tr>
<tr><td><code>call_hierarchy</code></td><td>Call tree: who calls this procedure (incoming) and what it calls (outgoing).</td></tr>
<tr><td><code>call_graph</code></td><td>Build a call graph with entry point detection. Shows call chains between modules.</td></tr>
<tr><td><code>document_diagnostics</code></td><td>Errors and warnings in a specific BSL file (syntax errors, style issues).</td></tr>
<tr><td><code>project_analysis</code></td><td>Overall project analysis: symbol count, inter-module relationships, structure.</td></tr>
<tr><td><code>lsp_status</code></td><td>BSL Language Server status: version, indexing state, number of indexed files.</td></tr>
<tr><td><code>prepare_rename</code></td><td>Check if a symbol can be renamed before execution.</td></tr>
<tr><td><code>rename</code></td><td>Rename a symbol (procedure, function, variable) in all usage locations.</td></tr>
<tr><td><code>selection_range</code></td><td>Determine selection range for a symbol (smart selection).</td></tr>
<tr><td><code>get_range_content</code></td><td>Get the content of a specified line range in a file.</td></tr>
<tr><td><code>code_actions</code></td><td>Available refactoring actions for a selected code fragment.</td></tr>
<tr><td><code>did_change_watched_files</code></td><td>Notify LSP about file changes (for re-indexing).</td></tr>
</table>

<h3>Gateway Tools (built into the gateway, 20 tools)</h3>
<table>
<tr><th>Tool</th><th>Description</th></tr>
<tr><td><code>get_server_status</code></td><td>Status of all MCP backends: availability, tool counts.</td></tr>
<tr><td><code>export_bsl_sources</code></td><td>Export 1C configuration sources via ibcmd or the host export service.</td></tr>
<tr><td><code>connect_database</code></td><td>Connect a new 1C database: registration, Docker container creation.</td></tr>
<tr><td><code>disconnect_database</code></td><td>Disconnect a database: stop containers, remove from registry.</td></tr>
<tr><td><code>switch_database</code></td><td>Switch the active database for the current MCP session (per-session routing).</td></tr>
<tr><td><code>list_databases</code></td><td>List all registered databases and their connection statuses.</td></tr>
<tr><td><code>validate_query</code></td><td>Validate 1C query syntax without executing: static checks (parentheses, keywords) + server-side validation via <code>TOP 0</code>.</td></tr>
<tr><td><code>reindex_bsl</code></td><td>Force BSL Language Server re-indexing. Use after manual file changes, git pull, or external export.</td></tr>
<tr><td><code>write_bsl</code></td><td>Write a BSL module to the project with automatic LSP re-indexing.</td></tr>
<tr><td><code>bsl_index</code></td><td>Build a full-text search index over BSL sources: all procedures, functions, comments.</td></tr>
<tr><td><code>bsl_search_tool</code></td><td>Search for procedures and functions in the BSL index. Supports filtering by exported symbols.</td></tr>
<tr><td><code>enable_anonymization</code></td><td>Enable personal data masking in tool responses.</td></tr>
<tr><td><code>disable_anonymization</code></td><td>Disable personal data masking.</td></tr>
<tr><td><code>its_search</code></td><td>Search ITS documentation (1C Information and Technology Support) via the 1C:Naparnik API. Requires <code>NAPARNIK_API_KEY</code> configuration.</td></tr>
<tr><td><code>invalidate_metadata_cache</code></td><td>Clear the metadata cache. Equivalent to the "Clear Cache" button in the dashboard.</td></tr>
<tr><td><code>query_stats</code></td><td>Query performance statistics: count, avg/max time, error rate.</td></tr>
<tr><td><code>capture_form</code></td><td>Screenshot of the currently open form in the 1C client. Returns the image in base64 format.</td></tr>
<tr><td><code>graph_stats</code></td><td>BSL dependency graph statistics: node count, edge count, distribution by object types. Requires bsl-graph.</td></tr>
<tr><td><code>graph_search</code></td><td>Search for configuration objects in the dependency graph. Requires bsl-graph.</td></tr>
<tr><td><code>graph_related</code></td><td>Find related objects in the dependency graph: what the object uses and what uses it (impact analysis). Requires bsl-graph.</td></tr>
</table>

<h3>MCP Resource</h3>
<p>The gateway also provides one MCP resource: <code>syntax_1c.txt</code> — a BSL (1C built-in language) syntax reference: types, operators, control structures, procedures, exceptions, preprocessor directives. AI uses it as context when writing BSL code.</p>

<!-- ================================================================== -->
<h2 id="api-en">6. API Endpoints</h2>
<p>Complete list of gateway HTTP endpoints. The main entry point for AI assistants is <code>/mcp</code>. Other endpoints are used by the dashboard, the EPF data processor, or external systems.</p>
<table>
<tr><th>Path</th><th>Method</th><th>Description</th></tr>
<tr><td><code>/mcp</code></td><td>POST/GET</td><td>MCP Streamable HTTP — main entry point for AI assistants. Supports stateful sessions with an 8-hour idle timeout.</td></tr>
<tr><td><code>/health</code></td><td>GET</td><td>JSON status of all backends. Returns <code>{"status":"ok"}</code> if all backends are available, <code>{"status":"degraded"}</code> if at least one is unavailable.</td></tr>
<tr><td><code>/dashboard</code></td><td>GET</td><td>Web UI dashboard. Parameter <code>?lang=ru|en</code> for language switching.</td></tr>
<tr><td><code>/dashboard/docs</code></td><td>GET</td><td>This documentation page. Parameter <code>?lang=ru|en</code>.</td></tr>
<tr><td><code>/dashboard/diagnostics</code></td><td>GET</td><td>Full diagnostic report in JSON format (opens in a new tab).</td></tr>
<tr><td><code>/api/export-bsl</code></td><td>POST</td><td>REST endpoint for BSL source export. Called by MCPToolkit.epf when "Export BSL" is clicked. Body: <code>{"connection":"...","output_dir":"..."}</code>.</td></tr>
<tr><td><code>/api/register</code></td><td>POST</td><td>EPF registration in the gateway. Called by MCPToolkit.epf when "Connect" is clicked. Body: <code>{"name":"...","connection":"..."}</code>. If the database is not connected — auto-connects it.</td></tr>
<tr><td><code>/api/unregister</code></td><td>POST</td><td>EPF unregistration. Called when "Disconnect" is clicked in the data processor. Body: <code>{"name":"..."}</code>.</td></tr>
<tr><td><code>/api/action/connect-db</code></td><td>POST</td><td>Connect a database from the dashboard. Body: <code>{"name":"...","connection":"...","project_path":"..."}</code>.</td></tr>
<tr><td><code>/api/action/disconnect</code></td><td>POST</td><td>Disconnect a database. Parameter: <code>?name=db_name</code>.</td></tr>
<tr><td><code>/api/action/switch</code></td><td>POST</td><td>Set the default database. Parameter: <code>?name=db_name</code>.</td></tr>
<tr><td><code>/api/action/edit-db</code></td><td>POST</td><td>Edit database parameters. Body: <code>{"name":"...","connection":"...","project_path":"..."}</code>.</td></tr>
<tr><td><code>/api/action/clear-cache</code></td><td>POST</td><td>Clear metadata cache.</td></tr>
<tr><td><code>/api/action/toggle-anon</code></td><td>POST</td><td>Toggle anonymization (on/off).</td></tr>
<tr><td><code>/api/action/get-env</code></td><td>POST</td><td>Read the <code>.env</code> file contents for display in the dashboard editor.</td></tr>
<tr><td><code>/api/action/save-env</code></td><td>POST</td><td>Save the <code>.env</code> file with automatic gateway restart. Body: <code>{"content":"..."}</code>.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="env-en">7. Environment Variables (.env)</h2>
<p>All parameters are configured via the <code>.env</code> file in the project root. The file is mounted into the gateway container. You can edit it from the dashboard (Parameters tab, "Edit") or directly on the host.</p>
<table>
<tr><th>Variable</th><th>Default</th><th>Description</th></tr>
<tr><td><code>PORT</code></td><td>8080</td><td>Port the MCP gateway listens on. The AI assistant connects to <code>http://localhost:{PORT}/mcp</code>.</td></tr>
<tr><td><code>LOG_LEVEL</code></td><td>INFO</td><td>Logging level: <code>DEBUG</code> (maximum detail), <code>INFO</code>, <code>WARNING</code>, <code>ERROR</code> (errors only). Set to <code>DEBUG</code> for troubleshooting.</td></tr>
<tr><td><code>ONEC_TOOLKIT_URL</code></td><td>http://onec-toolkit:6003/mcp</td><td>Static onec-toolkit backend URL inside the Docker network. Change only if using a non-standard container configuration.</td></tr>
<tr><td><code>PLATFORM_CONTEXT_URL</code></td><td>http://platform-context:8080/sse</td><td>Platform documentation backend URL inside the Docker network.</td></tr>
<tr><td><code>ENABLED_BACKENDS</code></td><td>onec-toolkit,platform-context,bsl-lsp-bridge</td><td>Comma-separated list of enabled backends. To add YaXUnit, specify: <code>onec-toolkit,platform-context,bsl-lsp-bridge,test-runner</code>.</td></tr>
<tr><td><code>EXPORT_HOST_URL</code></td><td>http://localhost:8082</td><td>URL of the BSL export service running on the host (<code>tools/export-host-service.py</code>). On Windows: <code>http://host.docker.internal:8082</code>.</td></tr>
<tr><td><code>IBCMD_PATH</code></td><td>/opt/1cv8/.../ibcmd</td><td>Full path to the ibcmd utility of the 1C platform inside the container. Used for BSL export if EXPORT_HOST_URL is not set.</td></tr>
<tr><td><code>BSL_WORKSPACE</code></td><td>/projects</td><td>BSL source working directory inside the LSP container. Configuration sources are mounted here.</td></tr>
<tr><td><code>BSL_HOST_WORKSPACE</code></td><td>—</td><td>Path to BSL sources on the host. Used for path conversion between container and host (so AI sees real file paths).</td></tr>
<tr><td><code>LSP_DOCKER_CONTAINER</code></td><td>mcp-lsp-zup</td><td>Static LSP container name (legacy parameter). Dynamic containers are created automatically when databases are connected.</td></tr>
<tr><td><code>BSL_LSP_COMMAND</code></td><td>—</td><td>Command for direct BSL Language Server launch (all-in-one mode, without Docker). Used instead of docker exec if LSP is installed locally.</td></tr>
<tr><td><code>NAPARNIK_API_KEY</code></td><td>—</td><td>API key for 1C:Naparnik (ITS search). Get it at <a href="https://code.1c.ai">code.1c.ai</a> → Profile → API token. Requires an ITS subscription.</td></tr>
<tr><td><code>METADATA_CACHE_TTL</code></td><td>600</td><td>Metadata cache lifetime in seconds. 600 = 10 minutes. Value of <code>0</code> completely disables caching.</td></tr>
<tr><td><code>TEST_RUNNER_URL</code></td><td>http://localhost:8000/sse</td><td>URL of the mcp-onec-test-runner backend for YaXUnit test execution. Optional.</td></tr>
<tr><td><code>BSL_GRAPH_URL</code></td><td>http://localhost:8888</td><td>URL of the bsl-graph service for the dependency graph. Optional, requires NebulaGraph.</td></tr>
<tr><td><code>PLATFORM_PATH</code></td><td>/opt/1cv8/x86_64/8.3.27.2074</td><td>Full path to the specific 1C platform version directory. Used by the platform-context backend to read documentation.</td></tr>
<tr><td><code>HOST_PLATFORM_PATH</code></td><td>/opt/1cv8</td><td>Root path to the 1C platform on the host. Mounted into containers for access to ibcmd and other utilities.</td></tr>
<tr><td><code>ONEC_TIMEOUT</code></td><td>180</td><td>Timeout for 1C command execution (seconds). If a query or code does not complete within this time, a timeout error is returned.</td></tr>
</table>

<!-- ================================================================== -->
<h2 id="diagnostics-en">8. Diagnostics</h2>
<p>The "Diagnostics" link is located at the bottom of the dashboard (footer). It opens a full diagnostic report in a new browser tab in JSON format.</p>

<h3>Report Contents</h3>
<table>
<tr><th>Section</th><th>Contents</th></tr>
<tr><td><b>gateway</b></td><td>Gateway version, port, number of active MCP sessions, idle timeout setting.</td></tr>
<tr><td><b>backends</b></td><td>Status of each backend: availability, tool count, errors. Equivalent to the <code>/health</code> endpoint.</td></tr>
<tr><td><b>databases</b></td><td>List of all connected databases: name, connection string, project path, EPF status, toolkit backend port, LSP container name.</td></tr>
<tr><td><b>profiling</b></td><td>execute_query statistics: count, avg/max/min time, slow queries, error rate.</td></tr>
<tr><td><b>cache</b></td><td>Metadata cache state: entry count, hit rate, TTL, memory size.</td></tr>
<tr><td><b>anonymization</b></td><td>Whether anonymization is enabled, number of replacements in the current session.</td></tr>
<tr><td><b>docker</b></td><td>Docker daemon information: version, OS, CPU count, RAM, image and volume sizes.</td></tr>
<tr><td><b>containers</b></td><td>List of project containers: name, image, status, start time.</td></tr>
<tr><td><b>config</b></td><td>All environment variables (secrets are masked as <code>***</code>).</td></tr>
<tr><td><b>container_logs</b></td><td>Last 10 lines of logs from each project container. Helps quickly see errors without using <code>docker logs</code>.</td></tr>
</table>

<h3>When to Use</h3>
<ul>
<li>When investigating the cause of a problem — the report contains all necessary information in one place</li>
<li>When seeking help — copy the JSON report and attach it to the problem description</li>
<li>For monitoring — periodic check of all component states</li>
</ul>
<p>Diagnostics are also available via the API: <code>POST /api/action/diagnostics</code>.</p>

<!-- ================================================================== -->
<h2 id="troubleshooting-en">9. Troubleshooting</h2>

<h3>Backend shows red status</h3>
<p><b>Symptom:</b> On the Status tab, one or more backends display a red indicator.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Container is not running. Check: <code>docker compose ps</code>. If the container is stopped, start it: <code>docker compose up -d</code>.</li>
<li>Container crashed with an error. Check logs: <code>docker logs onec-mcp-gw -f</code> (for the gateway), <code>docker logs onec-mcp-toolkit -f</code> (for toolkit). A common cause is out of memory.</li>
<li>Network issue between containers. Verify that containers are in the same Docker network: <code>docker network ls</code>.</li>
</ol>

<h3>EPF data processor not connecting</h3>
<p><b>Symptom:</b> In the MCPToolkit.epf data processor, clicking "Connect" results in an error or the status remains "Not connected".</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Gateway is not running. Check: <code>curl http://localhost:8080/health</code>. Should return JSON.</li>
<li>Wrong gateway address in the data processor. Verify that the "Gateway address" field contains the correct URL (default <code>http://localhost:8080</code>).</li>
<li>Firewall is blocking the port. On Windows, check whether port 8080 is allowed in firewall settings.</li>
<li>1C is running in thin client mode with HTTP restrictions. Try using the thick client.</li>
</ol>

<h3>BSL navigation not working</h3>
<p><b>Symptom:</b> The <code>definition</code>, <code>symbol_explore</code>, <code>call_hierarchy</code> tools return empty results or errors.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Sources not exported. Click "Export BSL" in the MCPToolkit.epf data processor. Wait for completion (3-5 minutes for large configurations).</li>
<li>LSP is still indexing files. Check status: call the <code>lsp_status</code> tool. Indexing large projects (ERP — 18,000 modules) takes several minutes.</li>
<li>LSP container is not running. Check: <code>docker ps | grep mcp-lsp</code>.</li>
<li>Project path is incorrect. Verify that the BSL source directory on the host contains <code>.bsl</code> files and is correctly mounted into the container.</li>
</ol>

<h3>.env edit error in dashboard</h3>
<p><b>Symptom:</b> When clicking "Edit" in the gateway configuration, the message ".env file not found" appears.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>.env file does not exist. Create it: <code>cp .env.example .env</code> in the project root.</li>
<li>File is not mounted into the container. Verify that <code>docker-compose.yml</code> contains the line <code>./.env:/data/.env:rw</code>.</li>
<li>No write permissions. Check permissions: <code>ls -la .env</code>. The file must be writable.</li>
</ol>

<h3>AI receives outdated metadata</h3>
<p><b>Symptom:</b> AI claims an object has an attribute that doesn't exist (or vice versa).</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Metadata cache contains stale data. Clear the cache: "Clear Cache" button on the Parameters tab or the <code>invalidate_metadata_cache</code> tool.</li>
<li>Reduce cache TTL in settings: <code>METADATA_CACHE_TTL=60</code> (1 minute instead of 10).</li>
</ol>

<h3>execute_query queries run slowly</h3>
<p><b>Symptom:</b> Queries take more than 5 seconds, the Profiling card shows large numbers.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Suboptimal queries from AI. Check the <code>_profiling</code> field in the response — it contains hints (SELECT *, missing WHERE, many JOINs).</li>
<li>Load on the 1C server. Queries execute in the database context and compete with other users.</li>
<li>Network latency. If the 1C server is on a remote host, check ping and bandwidth.</li>
<li>Increase timeout: <code>ONEC_TIMEOUT=300</code> (5 minutes instead of 3).</li>
</ol>

<h3>Data processor shows "No response from gateway" (timeout)</h3>
<p><b>Symptom:</b> MCPToolkit.epf periodically outputs a timeout error to the event log.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Gateway is overloaded or restarting. Check logs: <code>docker logs onec-mcp-gw --tail 50</code>.</li>
<li>Long-polling connection was broken. Click "Disconnect" and then "Connect" again.</li>
<li>Docker network issues. Restart containers: <code>docker compose restart</code>.</li>
</ol>

<h3>Docker containers not created when connecting a database</h3>
<p><b>Symptom:</b> When connecting a database, the error "Failed to create container" appears.</p>
<p><b>Causes and solutions:</b></p>
<ol>
<li>Insufficient Docker resources. Check free space: <code>docker system df</code>. Clean up unused images: <code>docker system prune</code>.</li>
<li>No access to Docker API. The gateway accesses Docker via socket. Verify that <code>/var/run/docker.sock</code> is mounted into the gateway container.</li>
<li>Name conflict. A container with that name already exists. Remove manually: <code>docker rm -f onec-toolkit-{db_name}</code>.</li>
</ol>

</body></html>""",
}


def render_docs(lang: str = "ru") -> str:
    return DOCS_HTML.get(lang, DOCS_HTML["ru"])

"""
Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard. Supports Russian (default) and English.
Two tabs: Status + Settings. Documentation opens in /dashboard/docs.
"""
from __future__ import annotations

import html as _html

from .web_docs import render_docs
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
        "tab_reports": "Отчёты",
        "tab_settings": "Настройки",
        "btn_docs": "Документация",
        "btn_refresh": "Обновить",
        "btn_refresh_stats": "Обновить статистику",
        "h_backends": "Бэкенды",
        "h_optional_services": "Опциональные сервисы",
        "h_databases": "Базы данных",
        "h_profiling": "Профилирование",
        "h_cache": "Кеш метаданных",
        "h_anon": "Анонимизация",
        "h_system": "Docker-контейнеры",
        "h_reports": "Отчёты 1С",
        "h_report_engine": "ДВИЖОК ОТЧЁТОВ 1С",
        "reports_none": "Каталог ещё не построен",
        "reports_analyzed": "Последний анализ",
        "reports_snapshot_hint": "Статусы по последнему запуску каждого отчёта",
        "reports_found": "Отчётов",
        "reports_variants": "Вариантов",
        "reports_runs": "Проверено",
        "reports_artifacts": "Результатов",
        "reports_done": "Готово",
        "reports_needs_input": "Нужен ввод",
        "reports_unsupported": "Не поддерживается",
        "reports_error": "Ошибки",
        "reports_no_validation": "Нет данных валидации",
        "reports_hint": "Поиск и запуск отчётов по пользовательскому названию, например «Расчетный листок».",
        "reports_database": "База",
        "reports_query": "Название отчёта",
        "reports_find": "Найти",
        "reports_analyze": "Проанализировать отчёты",
        "reports_run": "Запустить",
        "reports_period_from": "Период с",
        "reports_period_to": "по",
        "reports_filters": "Фильтры JSON",
        "reports_result": "Результат",
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
        "no_optional_services": "Нет опциональных сервисов",
        "no_databases": "Нет подключённых баз",
        "no_queries": "Нет запросов",
        "epf_ok": "",
        "epf_wait": "",
        "name": "Имя",
        "connection": "Подключение",
        "status": "EPF",
        "setting": "Параметр",
        "value": "Значение",
        "license": "Лицензия",
        "project": "GitHub",
        "connect_db": "Подключить базу",
        "disconnect_db": "Отключить",
        "reconnect_db": "Подключить",
        "remove_db": "Удалить",
        "open_graph": "Открыть граф",
        "clear_cache": "Очистить кеш",
        "toggle_anon": "Анонимизация вкл/выкл",
        "restart_hint": "Шлюз перезапустится автоматически после сохранения.",
        "add_db_name": "Имя базы",
        "add_db_conn": "Строка подключения",
        "add_db_path": "Путь к проекту",
        "add_db_btn": "Подключить",
        "container": "Контейнер",
        "image": "Образ",
        "container_status": "Статус контейнера",
        "ram_now": "RAM сейчас",
        "image_disk": "Образ на диске",
        "unknown_short": "н/д",
        "no_containers": "Нет контейнеров",
        "edit_config": "Редактировать",
        "save_config": "Сохранить",
        "cancel": "Отмена",
        "config_edit_hint": "Перезапуск шлюза произойдёт автоматически.",
        "docker_version": "Docker",
        "docker_os": "ОС",
        "docker_cpus": "CPU",
        "docker_mem": "RAM хоста",
        "docker_imgs": "Образы",
        "docker_imgs_size": "Размер образов",
        "docker_vols_size": "Размер томов",
        "docker_stats_unloaded": "Статистика не загружена",
        "running": "запущен",
        "stopped": "остановлен",
        "configure": "По умолчанию",
        "add_db": "Добавить базу",
        "edit_db": "Изменить",
        "confirm_disconnect": "Отключить базу",
        "confirm_remove": "Удалить базу",
        "remove_warning": "База будет удалена из реестра без возможности восстановления.",
        "default_badge": "По умолчанию",
        "edit_db_title": "Редактирование базы",
        "save": "Сохранить",
        "diagnostics": "Диагностика",
        "fill_all_fields": "Заполните все поля",
        "reindex_bsl": "Переиндексировать BSL",
        "h_params": "Настройки",
        "h_bsl_workspace": "ПАПКА ВЫГРУЗКИ BSL",
        "h_report_settings": "Параметры",
        "bsl_workspace_save": "Сохранить",
        "bsl_workspace_edit": "Изменить",
        "bsl_workspace_saving": "Сохранение...",
        "bsl_workspace_saved": "Сохранено и применено без перезапуска.",
        "bsl_workspace_select": "Выбрать эту папку",
        "bsl_workspace_hint": "Папка на этом компьютере для хранения выгруженных BSL-исходников. Для каждой базы создаётся подкаталог.",
        "browse_btn": "Обзор...",
        "report_settings_hint": "Эти значения используются по умолчанию для запуска одного отчёта и массовой проверки каталога.",
        "report_auto_analyze": "Автоанализ после подключения, выгрузки и переиндексации BSL",
        "report_run_rows": "Строк при запуске",
        "report_run_timeout": "Таймаут запуска, сек",
        "report_validate_rows": "Строк при проверке",
        "report_validate_timeout": "Таймаут проверки, сек",
        "report_settings_saved": "Настройки отчётов сохранены и применены без перезапуска.",
        "api_token_prompt": "Введите GATEWAY_API_TOKEN для API-действий:",
        "progress_connecting_db": "Подключаем базу...",
        "progress_reconnecting_db": "Подключаем базу...",
        "progress_disconnecting_db": "Отключаем базу...",
        "progress_removing_db": "Удаляем базу...",
        "progress_switching_default": "Переключаем базу по умолчанию...",
        "progress_reindexing_bsl": "Запускаем переиндексацию BSL...",
        "progress_clearing_cache": "Очищаем кеш метаданных...",
        "progress_toggling_anon": "Переключаем анонимизацию...",
        "progress_saving_db": "Сохраняем параметры базы...",
        "progress_saving_workspace": "Сохраняем папку выгрузки BSL...",
        "progress_saving_report_settings": "Сохраняем настройки отчётов...",
        "progress_saving_env": "Сохраняем конфигурацию шлюза...",
        "progress_refreshing_stats": "Обновляем статистику Docker...",
        "stats_updated": "Статистика обновлена.",
    },
    "en": {
        "title": "onec-mcp-universal",
        "subtitle": "MCP Gateway for 1C:Enterprise",
        "tab_info": "Status",
        "tab_reports": "Reports",
        "tab_settings": "Settings",
        "btn_docs": "Docs",
        "btn_refresh": "Refresh",
        "btn_refresh_stats": "Refresh stats",
        "h_backends": "Backends",
        "h_optional_services": "Optional Services",
        "h_databases": "Databases",
        "h_profiling": "Profiling",
        "h_cache": "Metadata Cache",
        "h_anon": "Anonymization",
        "h_system": "Docker Containers",
        "h_reports": "1C Reports",
        "h_report_engine": "1C REPORT ENGINE",
        "reports_none": "Catalog has not been built yet",
        "reports_analyzed": "Last analysis",
        "reports_snapshot_hint": "Statuses by the latest run of each report",
        "reports_found": "Reports",
        "reports_variants": "Variants",
        "reports_runs": "Checked",
        "reports_artifacts": "Results",
        "reports_done": "Done",
        "reports_needs_input": "Needs input",
        "reports_unsupported": "Unsupported",
        "reports_error": "Errors",
        "reports_no_validation": "No validation data",
        "reports_hint": "Find and run reports by user-facing title, for example \"Payroll sheet\".",
        "reports_database": "Database",
        "reports_query": "Report title",
        "reports_find": "Find",
        "reports_analyze": "Analyze reports",
        "reports_run": "Run",
        "reports_period_from": "Period from",
        "reports_period_to": "to",
        "reports_filters": "Filters JSON",
        "reports_result": "Result",
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
        "no_optional_services": "No optional services",
        "no_databases": "No databases",
        "no_queries": "No queries yet",
        "epf_ok": "",
        "epf_wait": "",
        "name": "Name",
        "connection": "Connection",
        "status": "EPF",
        "setting": "Setting",
        "value": "Value",
        "license": "License",
        "project": "GitHub",
        "connect_db": "Connect DB",
        "disconnect_db": "Disconnect",
        "reconnect_db": "Connect",
        "remove_db": "Delete",
        "open_graph": "Open Graph",
        "clear_cache": "Clear Cache",
        "toggle_anon": "Toggle Anonymization",
        "restart_hint": "Gateway will restart automatically after saving.",
        "add_db_name": "DB name",
        "add_db_conn": "Connection string",
        "add_db_path": "Project path",
        "add_db_btn": "Connect",
        "container": "Container",
        "image": "Image",
        "container_status": "Container status",
        "ram_now": "RAM now",
        "image_disk": "Image on disk",
        "unknown_short": "n/a",
        "no_containers": "No containers",
        "edit_config": "Edit",
        "save_config": "Save",
        "cancel": "Cancel",
        "config_edit_hint": "Gateway will restart automatically after saving.",
        "docker_version": "Docker",
        "docker_os": "OS",
        "docker_cpus": "CPUs",
        "docker_mem": "Host RAM",
        "docker_imgs": "Images",
        "docker_imgs_size": "Images size",
        "docker_vols_size": "Volumes size",
        "docker_stats_unloaded": "Stats not loaded",
        "running": "running",
        "stopped": "stopped",
        "configure": "Default",
        "add_db": "Add Database",
        "edit_db": "Edit",
        "confirm_disconnect": "Disconnect database",
        "confirm_remove": "Delete database",
        "remove_warning": "The database will be permanently removed from the registry.",
        "default_badge": "Default",
        "edit_db_title": "Edit Database",
        "save": "Save",
        "diagnostics": "Diagnostics",
        "fill_all_fields": "Fill all fields",
        "reindex_bsl": "Reindex BSL",
        "h_params": "Settings",
        "h_bsl_workspace": "BSL EXPORT FOLDER",
        "h_report_settings": "Parameters",
        "bsl_workspace_save": "Save",
        "bsl_workspace_edit": "Edit",
        "bsl_workspace_saving": "Saving...",
        "bsl_workspace_saved": "Saved and applied without restart.",
        "bsl_workspace_select": "Select this folder",
        "bsl_workspace_hint": "Local folder on this machine for storing exported BSL sources. A subdirectory is created per database.",
        "browse_btn": "Browse...",
        "report_settings_hint": "These values are used as defaults for running a single report and for validating the catalog in bulk.",
        "report_auto_analyze": "Auto-analyze after connect, export, and BSL reindex",
        "report_run_rows": "Rows per run",
        "report_run_timeout": "Run timeout, sec",
        "report_validate_rows": "Rows per validation",
        "report_validate_timeout": "Validation timeout, sec",
        "report_settings_saved": "Report settings saved and applied without restart.",
        "api_token_prompt": "Enter GATEWAY_API_TOKEN for API actions:",
        "progress_connecting_db": "Connecting database...",
        "progress_reconnecting_db": "Connecting database...",
        "progress_disconnecting_db": "Disconnecting database...",
        "progress_removing_db": "Removing database...",
        "progress_switching_default": "Switching default database...",
        "progress_reindexing_bsl": "Starting BSL reindex...",
        "progress_clearing_cache": "Clearing metadata cache...",
        "progress_toggling_anon": "Toggling anonymization...",
        "progress_saving_db": "Saving database settings...",
        "progress_saving_workspace": "Saving BSL export folder...",
        "progress_saving_report_settings": "Saving report settings...",
        "progress_saving_env": "Saving gateway configuration...",
        "progress_refreshing_stats": "Refreshing Docker stats...",
        "stats_updated": "Stats refreshed.",
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
.btn-p{background:#1e293b;border-color:#475569;color:#94a3b8}.btn-p:hover{background:#334155;color:#f8fafc}
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
@media(max-width:900px){.grid{grid-template-columns:1fr!important}.card{font-size:.8rem}table{font-size:.75rem}.btn{font-size:.7rem;padding:3px 6px}}
.form-row{display:grid;grid-template-columns:140px 1fr;gap:8px;margin-bottom:8px;align-items:center}
.form-row label{font-size:.78rem;color:#94a3b8;text-align:right}
.form-row input{padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem;width:100%}
.form-row input:focus{outline:none;border-color:#38bdf8}
.num-wrap{display:flex;align-items:stretch;width:100%;border:1px solid #475569;border-radius:4px;overflow:hidden;background:#0f172a}
.num-wrap:focus-within{border-color:#38bdf8}
.num-wrap input{border:none!important;border-radius:0!important;background:transparent!important}
.num-wrap input:focus{border-color:transparent!important}
.num-wrap input[type=number]{appearance:textfield;-moz-appearance:textfield}
.num-wrap input[type=number]::-webkit-outer-spin-button,.num-wrap input[type=number]::-webkit-inner-spin-button{-webkit-appearance:none;margin:0}
.num-stepper{display:flex;flex-direction:column;flex-shrink:0;border-left:1px solid #334155}
.num-stepper button{width:28px;height:16px;border:0;background:#1e293b;color:#94a3b8;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:.58rem;line-height:1}
.num-stepper button + button{border-top:1px solid #334155}
.num-stepper button:hover{background:#334155;color:#f8fafc}
</style>
</head>
<body>
<div class="header">
<div class="header-left">
<div><h1>{{title}}</h1><span class="sub">{{subtitle}}</span></div>
</div>
<div class="header-right">
<div class="lang-sw">
<a href="#" onclick="location.href='/dashboard?lang=ru'+location.hash;return false;" class="{{ru_on}}">RU</a>
<a href="#" onclick="location.href='/dashboard?lang=en'+location.hash;return false;" class="{{en_on}}">EN</a>
</div>
<a class="btn" href="/dashboard/docs?lang={{lang}}" target="_blank">{{btn_docs}}</a>
<button class="btn" onclick="location.reload()">{{btn_refresh}}</button>
<button class="btn" id="refresh-stats-btn" onclick="refreshDockerStats()">{{btn_refresh_stats}}</button>
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
<div class="card"><h2>{{h_optional_services}}</h2>{{optional_services_html}}</div>
<div class="card"><h2>{{h_reports}}</h2><div id="reports-summary-root">{{reports_summary_html}}</div></div>
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
<div class="ag"><button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="connectDb()">{{add_db_btn}}</button></div>
</div>
</div>
<div class="card">
<h2>{{h_config}}</h2>
<hr style="border:none;border-top:1px solid #334155;margin:8px 0">
<h3 style="font-size:.65rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">{{h_actions}}</h3>
<div id="config-actions" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding-bottom:10px;border-bottom:1px solid #334155">
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="act('/api/action/clear-cache')">{{clear_cache}}</button>
<span class="st">{{cache_status}}</span>
<span class="st">|</span>
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="act('/api/action/toggle-anon')">{{toggle_anon}}</button>
<span class="st" style="display:flex;align-items:center;gap:4px"><span class="dot {{anon_dot}}"></span>{{anon_status}}</span>
</div>
<h3 style="font-size:.65rem;color:#64748b;text-transform:uppercase;letter-spacing:.05em;margin:10px 0 6px">{{h_params}} <button class="btn" style="font-size:.65rem;padding:2px 6px;float:right" onclick="editEnv()">{{edit_config}}</button></h3>
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
<h2>{{h_bsl_workspace}}</h2>
<p style="color:#64748b;font-size:.72rem;margin-bottom:8px">{{bsl_workspace_hint}}</p>
<div id="bsl-ws-view">
<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
<code id="bsl-ws-current" style="background:#0f172a;padding:3px 8px;border-radius:4px;font-size:.8rem;color:#e2e8f0;flex:1;word-break:break-all">...</code>
<button class="btn" style="font-size:.7rem;padding:3px 8px;flex-shrink:0" onclick="editBslWorkspace()">{{bsl_workspace_edit}}</button>
</div>
</div>
<div id="bsl-ws-edit" style="display:none;margin-top:8px">
<div style="display:flex;gap:6px;align-items:center">
<input id="bsl-ws-input" style="flex:1;min-width:0" placeholder="">
<button class="btn" style="font-size:.7rem;padding:3px 8px;flex-shrink:0" onclick="openSystemDirectoryDialog('bsl-ws-input')">{{browse_btn}}</button>
</div>
<div class="ag" style="margin-top:6px">
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="saveBslWorkspace()">{{bsl_workspace_save}}</button>
<button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="cancelBslWorkspace()">{{cancel}}</button>
</div>
</div>
</div>
<div class="card">
<h2>{{h_report_engine}}</h2>
<p style="color:#64748b;font-size:.72rem;margin-bottom:8px">{{report_settings_hint}}</p>
<div class="form-row"><label>{{report_auto_analyze}}</label><input id="report-auto-analyze" type="checkbox" style="width:auto;justify-self:start"></div>
<div class="form-row"><label>{{report_run_rows}}</label><div class="num-wrap"><input id="report-run-rows" type="number" min="0" step="1"><div class="num-stepper"><button type="button" onclick="stepNumberInput('report-run-rows',1)">▲</button><button type="button" onclick="stepNumberInput('report-run-rows',-1)">▼</button></div></div></div>
<div class="form-row"><label>{{report_run_timeout}}</label><div class="num-wrap"><input id="report-run-timeout" type="number" min="0" step="1"><div class="num-stepper"><button type="button" onclick="stepNumberInput('report-run-timeout',1)">▲</button><button type="button" onclick="stepNumberInput('report-run-timeout',-1)">▼</button></div></div></div>
<div class="form-row"><label>{{report_validate_rows}}</label><div class="num-wrap"><input id="report-validate-rows" type="number" min="0" step="1"><div class="num-stepper"><button type="button" onclick="stepNumberInput('report-validate-rows',1)">▲</button><button type="button" onclick="stepNumberInput('report-validate-rows',-1)">▼</button></div></div></div>
<div class="form-row"><label>{{report_validate_timeout}}</label><div class="num-wrap"><input id="report-validate-timeout" type="number" min="0" step="1"><div class="num-stepper"><button type="button" onclick="stepNumberInput('report-validate-timeout',1)">▲</button><button type="button" onclick="stepNumberInput('report-validate-timeout',-1)">▼</button></div></div></div>
<div class="ag"><button class="btn" style="font-size:.7rem;padding:3px 8px" onclick="saveReportSettings()">{{save}}</button></div>
</div>
</div>
</div>
<div class="footer">
{{title}} &mdash;
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
function setText(id,value){
var el=document.getElementById(id);
if(el){el.textContent=String(value);}
}
function findByDataAttr(attr,value){
var els=document.querySelectorAll('['+attr+']');
for(var i=0;i<els.length;i++){
if(els[i].getAttribute(attr)===String(value))return els[i];
}
return null;
}
function escHtml(v){
return String(v==null?'':v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;');
}
function renderReportsSummary(items){
var root=document.getElementById('reports-summary-root');
if(!root)return;
items=Array.isArray(items)?items:[];
if(!items.length){root.innerHTML='<span class="st">{{reports_none}}</span>';return;}
var html=items.map(function(item){
var name=escHtml(item.database||'');
if(!item.catalog_ready){
return '<div style="padding:8px 0;border-bottom:1px solid #334155"><div class="sr"><span class="sn">'+name+'</span></div><div class="st" style="white-space:normal">{{reports_none}}</div></div>';
}
var counts=item.status_counts||{};
return '<div style="padding:8px 0;border-bottom:1px solid #334155">'
  +'<div class="sr"><span class="sn">'+name+'</span></div>'
  +'<div class="st">{{reports_analyzed}}: '+escHtml(item.analyzed_at||'{{unknown_short}}')+'</div>'
  +'<div class="srow" style="margin-top:8px">'
  +'<div><div class="sv" style="font-size:1rem">'+String(item.reports_count||0)+'</div><div class="sl">{{reports_found}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(item.variants_count||0)+'</div><div class="sl">{{reports_variants}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(item.runs_count||0)+'</div><div class="sl">{{reports_runs}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(item.artifacts_count||0)+'</div><div class="sl">{{reports_artifacts}}</div></div>'
  +'</div>'
  +'<div class="srow" style="margin-top:8px">'
  +'<div><div class="sv" style="font-size:1rem">'+String(counts.done||0)+'</div><div class="sl">{{reports_done}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(counts.needs_input||0)+'</div><div class="sl">{{reports_needs_input}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(counts.unsupported||0)+'</div><div class="sl">{{reports_unsupported}}</div></div>'
  +'<div><div class="sv" style="font-size:1rem">'+String(counts.error||0)+'</div><div class="sl">{{reports_error}}</div></div>'
  +'</div>'
  +'</div>';
}).join('');
root.innerHTML=html;
}
function refreshDockerStats(){
var btn=document.getElementById('refresh-stats-btn');
if(btn&&btn.disabled)return;
if(btn){btn.disabled=true;btn.style.opacity='0.6';}
showToast('{{progress_refreshing_stats}}',1600);
apiFetch('/api/action/docker-info').then(function(r){return r.json();}).then(function(d){
if(!d.ok){throw new Error(d.error||'Error');}
var payload=d.data||{};
var ds=payload.docker_system||{};
var containers=payload.container_info||[];
setText('docker-version', ds.version||'?');
setText('docker-cpus', ds.cpus||0);
setText('docker-memory-gb', (ds.memory_gb||0)+' GB');
setText('docker-images-size', (ds.images_size_gb||0)+' GB');
var vol=(typeof ds.volumes_size_gb==='number'&&ds.volumes_size_gb<0.01)?'<1 MB>':((ds.volumes_size_gb||0)+' GB');
setText('docker-volumes-size', vol);
containers.forEach(function(c){
var name=String(c.name||'');
var mem=findByDataAttr('data-container-memory', name);
var img=findByDataAttr('data-container-image-size', name);
if(mem){mem.textContent=String(c.memory_usage_human||'{{unknown_short}}');}
if(img){img.textContent=String(c.image_size_human||'{{unknown_short}}');}
});
renderReportsSummary(payload.reports_summary||[]);
showToast('{{stats_updated}}',1800);
}).catch(function(e){
showToast(String(e));
}).finally(function(){
if(btn){btn.disabled=false;btn.style.opacity='';}
});
}
var _apiToken=(function(){
try{return window.sessionStorage.getItem('gateway_api_token')||'';}catch(e){return '';}
})();
function setApiToken(token){
_apiToken=String(token||'').trim();
try{
if(_apiToken){window.sessionStorage.setItem('gateway_api_token',_apiToken);}
else{window.sessionStorage.removeItem('gateway_api_token');}
}catch(e){}
}
function apiFetch(url,options,retried){
var opts=Object.assign({},options||{});
var headers=Object.assign({},opts.headers||{});
if(_apiToken){headers['Authorization']='Bearer '+_apiToken;}
if(Object.keys(headers).length){opts.headers=headers;}
return fetch(url,opts).then(function(resp){
if((resp.status===401||resp.status===403)&&!retried){
var entered=window.prompt('{{api_token_prompt}}',_apiToken||'');
if(entered!==null){
setApiToken(entered);
return apiFetch(url,options,true);
}
}
return resp;
});
}
function progressMessageForAction(u){
if(u.includes('/api/action/disconnect'))return '{{progress_disconnecting_db}}';
if(u.includes('/api/action/reconnect'))return '{{progress_reconnecting_db}}';
if(u.includes('/api/action/remove'))return '{{progress_removing_db}}';
if(u.includes('/api/action/switch'))return '{{progress_switching_default}}';
if(u.includes('/api/action/reindex-bsl'))return '{{progress_reindexing_bsl}}';
if(u.includes('/api/action/clear-cache'))return '{{progress_clearing_cache}}';
if(u.includes('/api/action/toggle-anon'))return '{{progress_toggling_anon}}';
return '';
}
function showActionProgress(u){
var msg=progressMessageForAction(u);
if(msg)showToast(msg,1600);
}
function act(u){showActionProgress(u);apiFetch(u,{method:'POST'}).then(r=>r.json()).then(d=>{
var msg=d.message||d.error||'OK';
var h=location.hash||'';
if(u.includes('reconnect')){
var m=u.match(/name=([^&]+)/);var name=m?decodeURIComponent(m[1]):'';
location.href=location.pathname+'?lang={{lang}}&reconnecting='+encodeURIComponent(name)+h;
}else{
var delay=u.includes('disconnect')?1000:100;
setTimeout(function(){location.href=location.pathname+'?lang={{lang}}&msg='+encodeURIComponent(msg)+h},delay);
}
}).catch(e=>showToast(e))}
// Auto-poll after reconnect redirect
(function(){
var p=new URLSearchParams(location.search);
var rn=p.get('reconnecting');
if(!rn)return;
var lang=p.get('lang')||'ru';
var h=location.hash||'';
var base=location.pathname+'?lang='+lang;
var t=setInterval(function(){
apiFetch('/api/action/db-status?name='+encodeURIComponent(rn),{method:'POST'})
.then(function(r){return r.json();}).then(function(d){
if(d.connected){clearInterval(t);location.href=base+h;}
}).catch(function(){});
},2000);
setTimeout(function(){clearInterval(t);location.href=base+h;},120000);
})();
// Show message from URL param after reload
(function(){var p=new URLSearchParams(location.search);var m=p.get('msg');if(m){
var d=document.createElement('div');d.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#164e63;color:#22d3ee;padding:14px 24px;border-radius:8px;font-size:.9rem;z-index:999;max-width:500px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.5)';
d.textContent=m;document.body.appendChild(d);setTimeout(function(){d.remove()},4000);
history.replaceState(null,'',location.pathname+'?lang='+p.get('lang')+(location.hash||''));
}})();
function showToast(msg,ms){
var d=document.createElement('div');
d.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#164e63;color:#22d3ee;padding:14px 24px;border-radius:8px;font-size:.9rem;z-index:999;max-width:500px;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,.5)';
var s=String(msg&&msg.message?msg.message:msg||'');
d.textContent=s;document.body.appendChild(d);setTimeout(function(){d.remove()},ms||4000);
}
// Poll /api/databases every 5 s.
// EPF dot is updated in-place; backend connectivity changes trigger full reload
// because row actions/strikethrough depend on backend_connected.
(function(){
function pollEpf(){
  apiFetch('/api/databases').then(function(r){return r.json();}).then(function(data){
    var reloadNeeded=false;
    (data.databases||[]).forEach(function(db){
      var selector='[data-epf-name='+JSON.stringify(String(db.name))+']';
      var els=document.querySelectorAll(selector);
      if(!els.length){reloadNeeded=true;return;}
      var epfOk=!!db.epf_connected;
      var backendOk=!!db.backend_connected;
      els.forEach(function(el){
        var prevBackend=el.getAttribute('data-backend-connected')==='1';
        if(prevBackend!==backendOk){reloadNeeded=true;}
        el.setAttribute('data-backend-connected', backendOk?'1':'0');
        el.className='dot epf-dot '+(epfOk?'ok':'warn');
        el.title=epfOk?'EPF connected':'EPF not connected';
      });
    });
    if(reloadNeeded){setTimeout(reload,100);}
  }).catch(function(){});
}
setInterval(pollEpf,5000);
})();
function connectDb(){
var n=document.getElementById('db-name').value.trim();
var c=document.getElementById('db-conn').value.trim();
var p=document.getElementById('db-path').value.trim();
if(!n||!c||!p){showToast('{{fill_all_fields}}');return}
showToast('{{progress_connecting_db}}',1600);
apiFetch('/api/action/connect-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n,connection:c,project_path:p})})
.then(r=>r.json()).then(d=>{showToast(d.message||d.error||'OK');if(d.ok)setTimeout(reload,1000)}).catch(e=>showToast(e))
}
function editDb(name,conn,path){
var ov=document.createElement('div');
ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center';
ov.innerHTML='<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;width:420px;max-width:90%"><h3 style="color:#f8fafc;font-size:.9rem;margin-bottom:12px">'+name+'</h3><div style="margin-bottom:8px"><label style="color:#94a3b8;font-size:.75rem;display:block;margin-bottom:3px">{{add_db_conn}}</label><input id="ed-conn" value="'+conn+'" style="width:100%;padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem"></div><div style="margin-bottom:12px"><label style="color:#94a3b8;font-size:.75rem;display:block;margin-bottom:3px">{{add_db_path}}</label><input id="ed-path" value="'+path+'" style="width:100%;padding:5px 8px;border-radius:4px;border:1px solid #475569;background:#0f172a;color:#e2e8f0;font-size:.8rem"></div><div style="display:flex;gap:8px;justify-content:flex-end"><button onclick="this.closest(\'div[style*=fixed]\').remove()" style="padding:5px 12px;border-radius:5px;border:1px solid #475569;background:#1e293b;color:#94a3b8;cursor:pointer;font-size:.78rem">{{cancel}}</button><button onclick="saveEditDb(\''+name+'\')" style="padding:5px 12px;border-radius:5px;border:1px solid #475569;background:#1e293b;color:#94a3b8;cursor:pointer;font-size:.78rem">{{save_config}}</button></div></div>';
document.body.appendChild(ov);
ov.addEventListener('click',function(e){if(e.target===ov)ov.remove()});
}
function saveEditDb(name){
var nc=document.getElementById('ed-conn').value.trim();
var np=document.getElementById('ed-path').value.trim();
document.querySelector('div[style*="position:fixed"][style*="inset:0"]').remove();
showToast('{{progress_saving_db}}',1600);
apiFetch('/api/action/edit-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,connection:nc,project_path:np})})
.then(r=>r.json()).then(d=>{showToast(d.message||d.error);setTimeout(reload,1000)}).catch(e=>showToast(e))
}
function editEnv(){
apiFetch('/api/action/get-env',{method:'POST'}).then(r=>r.json()).then(d=>{
document.getElementById('env-editor').value=d.env||'';
document.getElementById('config-view').style.display='none';
document.getElementById('config-actions').style.display='none';
document.getElementById('config-edit').style.display='block';
}).catch(e=>showToast(e))
}
function saveEnv(){
var c=document.getElementById('env-editor').value;
showToast('{{progress_saving_env}}',1600);
apiFetch('/api/action/save-env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:c,mode:'replace'})})
.then(r=>r.json()).then(d=>{showToast(d.message||d.error);setTimeout(function(){location.href=location.pathname+'?lang={{lang}}#settings'},3000)}).catch(e=>showToast(e))
}
function cancelEnv(){
document.getElementById('config-view').style.display='block';
document.getElementById('config-actions').style.display='flex';
document.getElementById('config-edit').style.display='none';
}
var _bslWsData={value:''};
function loadBslWorkspace(){
apiFetch('/api/action/get-bsl-workspace',{method:'POST'}).then(r=>r.json()).then(function(d){
_bslWsData=d;
var cur=document.getElementById('bsl-ws-current');
if(cur)cur.textContent=d.value||'(не задан)';
var inp=document.getElementById('bsl-ws-input');
if(inp&&d.placeholder)inp.placeholder=d.placeholder;
}).catch(function(){});
}
function editBslWorkspace(){
document.getElementById('bsl-ws-view').style.display='none';
document.getElementById('bsl-ws-edit').style.display='block';
var inp=document.getElementById('bsl-ws-input');
inp.value=_bslWsData.value||'';
}
function cancelBslWorkspace(){
document.getElementById('bsl-ws-view').style.display='block';
document.getElementById('bsl-ws-edit').style.display='none';
}
function stepNumberInput(id,delta){
var input=document.getElementById(id);
if(!input)return;
var step=Number(input.step||1);
if(!isFinite(step)||step<=0)step=1;
var current=input.value===''?0:Number(input.value);
if(!isFinite(current))current=0;
var next=current+(delta*step);
if(input.min!==''&&isFinite(Number(input.min)))next=Math.max(Number(input.min),next);
if(input.max!==''&&isFinite(Number(input.max)))next=Math.min(Number(input.max),next);
input.value=String(next);
input.dispatchEvent(new Event('input',{bubbles:true}));
input.dispatchEvent(new Event('change',{bubbles:true}));
}
function selectDirectoryWithOsDialog(currentPath){
return apiFetch('/api/select-directory',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({currentPath:currentPath||''})
}).then(function(r){return r.json();});
}
function openSystemDirectoryDialog(targetId){
var input=document.getElementById(targetId);
var currentPath=input?input.value.trim():'';
selectDirectoryWithOsDialog(currentPath).then(function(result){
if(!result||result.error){
showToast((result&&result.error)||'Error');
return;
}
if(result.cancelled)return;
if(input)input.value=result.path||'';
}).catch(function(e){showToast(String(e));});
}
function saveBslWorkspace(){
var v=document.getElementById('bsl-ws-input').value.trim();
showToast('{{progress_saving_workspace}}',1600);
apiFetch('/api/action/save-bsl-workspace',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value:v})})
.then(r=>r.json()).then(function(d){
if(d.ok){
showToast(d.message||'{{bsl_workspace_saved}}');
_bslWsData.value=v;
var cur=document.getElementById('bsl-ws-current');
if(cur)cur.textContent=v||'(не задан)';
cancelBslWorkspace();
setTimeout(reload,3000);
}else{showToast(d.error||'Error');}
}).catch(function(e){showToast(String(e));});
}
var _reportSettingsData={};
function loadReportSettings(){
apiFetch('/api/action/get-report-settings',{method:'POST'}).then(r=>r.json()).then(function(d){
if(!d||!d.ok)return;
_reportSettingsData=d;
var auto=document.getElementById('report-auto-analyze');
var runRows=document.getElementById('report-run-rows');
var runTimeout=document.getElementById('report-run-timeout');
var validateRows=document.getElementById('report-validate-rows');
var validateTimeout=document.getElementById('report-validate-timeout');
if(auto)auto.checked=!!d.auto_analyze_enabled;
if(runRows)runRows.value=String(d.run_default_max_rows||0);
if(runTimeout)runTimeout.value=String(d.run_default_timeout_seconds||0);
if(validateRows)validateRows.value=String(d.validate_default_max_rows||0);
if(validateTimeout)validateTimeout.value=String(d.validate_default_timeout_seconds||0);
}).catch(function(){});
}
function saveReportSettings(){
var payload={
auto_analyze_enabled:!!document.getElementById('report-auto-analyze').checked,
run_default_max_rows:Number(document.getElementById('report-run-rows').value||0),
run_default_timeout_seconds:Number(document.getElementById('report-run-timeout').value||0),
validate_default_max_rows:Number(document.getElementById('report-validate-rows').value||0),
validate_default_timeout_seconds:Number(document.getElementById('report-validate-timeout').value||0)
};
showToast('{{progress_saving_report_settings}}',1600);
apiFetch('/api/action/save-report-settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
.then(r=>r.json()).then(function(d){
if(d&&d.ok){
_reportSettingsData=d;
showToast(d.message||'{{report_settings_saved}}');
loadReportSettings();
}else{
showToast((d&&d.error)||'Error');
}
}).catch(function(e){showToast(String(e));});
}
// Load BSL workspace info when settings tab is opened
(function(){
var origStab=window.stab;
window.stab=function(el,id){origStab(el,id);if(id==='settings'){loadBslWorkspace();loadReportSettings();}};
// Also load if settings tab is already active on page load
if(location.hash==='#settings'||document.getElementById('t-settings').classList.contains('on')){loadBslWorkspace();loadReportSettings();}
})();
function confirmDisconnect(name){
var ov=document.createElement('div');
ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center';
ov.innerHTML='<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;width:360px;max-width:90%;text-align:center"><h3 style="color:#f8fafc;font-size:.9rem;margin-bottom:16px">{{confirm_disconnect}} '+name+'?</h3><div style="display:flex;gap:8px;justify-content:center"><button onclick="this.closest(\'div[style*=fixed]\').remove()" style="padding:5px 14px;border-radius:5px;border:1px solid #475569;background:#1e293b;color:#94a3b8;cursor:pointer;font-size:.8rem">{{cancel}}</button><button onclick="this.closest(\'div[style*=fixed]\').remove();act(\'/api/action/disconnect?name='+name+'\')" style="padding:5px 14px;border-radius:5px;border:1px solid #ef4444;background:transparent;color:#ef4444;cursor:pointer;font-size:.8rem">{{disconnect_db}}</button></div></div>';
document.body.appendChild(ov);
ov.addEventListener('click',function(e){if(e.target===ov)ov.remove()});
}
function confirmRemove(name){
var ov=document.createElement('div');
ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:100;display:flex;align-items:center;justify-content:center';
ov.innerHTML='<div style="background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;width:360px;max-width:90%;text-align:center"><h3 style="color:#f8fafc;font-size:.9rem;margin-bottom:8px">{{confirm_remove}} '+name+'?</h3><p style="color:#94a3b8;font-size:.78rem;margin-bottom:16px">{{remove_warning}}</p><div style="display:flex;gap:8px;justify-content:center"><button onclick="this.closest(\'div[style*=fixed]\').remove()" style="padding:5px 14px;border-radius:5px;border:1px solid #475569;background:#1e293b;color:#94a3b8;cursor:pointer;font-size:.8rem">{{cancel}}</button><button onclick="this.closest(\'div[style*=fixed]\').remove();act(\'/api/action/remove?name='+name+'\')" style="padding:5px 14px;border-radius:5px;border:1px solid #ef4444;background:transparent;color:#ef4444;cursor:pointer;font-size:.8rem">{{remove_db}}</button></div></div>';
document.body.appendChild(ov);
ov.addEventListener('click',function(e){if(e.target===ov)ov.remove()});
}
</script>
</body></html>"""


def _esc(value: str) -> str:
    """Escape a string for safe embedding in HTML."""
    return _html.escape(str(value), quote=True)


def _esc_js(value: str) -> str:
    """Escape a string for safe embedding inside JS single-quoted strings."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace('"', '\\"')
        .replace("<", "\\x3c")
        .replace(">", "\\x3e")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _format_bytes_compact(value: int | float | None) -> str:
    """Format byte sizes for compact dashboard display."""
    if value is None:
        return ""
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def render_dashboard(
    backends_status: dict,
    databases: list[dict],
    profiling_stats: dict,
    cache_stats: dict,
    anon_enabled: bool,
    config_items: list[tuple[str, str]],
    container_info: list[dict] | None = None,
    docker_system: dict | None = None,
    optional_services: list[dict] | None = None,
    reports_summary: list[dict] | None = None,
    report_settings: dict | None = None,
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
            f'<span class="sn">{_esc(name)}</span>'
            f'<span class="st">{tools} {t["tools"]}</span>{badge}</div>'
        )
    backends_html = "\n".join(b_lines) or f'<span class="st">{t["no_backends"]}</span>'

    # Optional services (LSP image/graph/export host/test runner visibility)
    o_lines = []
    for svc in optional_services or []:
        state = str(svc.get("state", "warn"))
        if state not in ("ok", "warn", "err"):
            state = "warn"
        name = _esc(svc.get("name", ""))
        details = _esc(svc.get("details", ""))
        svc_url = str(svc.get("url") or "").strip()
        svc_title = _esc(svc.get("title", ""))
        if svc_url:
            name_html = (
                f'<a class="sn" href="{_esc(svc_url)}" target="_blank" rel="noopener" '
                f'style="text-decoration:underline" title="{svc_title}">{name}</a>'
            )
        else:
            name_html = f'<span class="sn">{name}</span>'
        o_lines.append(
            f'<div class="sr"><div class="dot {state}"></div>{name_html}</div>'
        )
        if details:
            o_lines.append(
                f'<div class="st" style="margin:-2px 0 6px 14px;white-space:normal">{details}</div>'
            )
    optional_services_html = (
        "\n".join(o_lines) or f'<span class="st">{t["no_optional_services"]}</span>'
    )

    # Databases — with default column
    if databases:
        rows = [f'<table style="table-layout:auto">'
                f'<tr><th>{t["name"]}</th><th>{t["connection"]}</th><th style="text-align:center">{t["status"]}</th><th style="text-align:center">{t["default_badge"]}</th></tr>']
        for db in sorted(databases, key=lambda d: d.get('name', '')):
            epf_connected = db.get("epf_connected", False)
            backend_connected = db.get("backend_connected", True)
            epf_dot = "ok" if epf_connected else "warn"
            conn = _esc(db.get("connection", ""))
            default_icon = '<span class="dot ok" style="display:inline-block"></span>' if db.get("active") else ""
            name_style = 'text-decoration:line-through;color:#64748b;font-weight:bold' if not backend_connected else ''
            db_id = _esc(db["name"])
            graph_url = _esc(f'http://localhost:8888/?lang={lang}&db={db["name"]}')
            epf_title = "Обработка подключена" if epf_connected else "Обработка не подключена"
            rows.append(
                f'<tr><td><span style="{name_style}">{_esc(db["name"])}</span>'
                f' <a class="btn" style="font-size:.65rem;padding:2px 6px;margin-left:6px" href="{graph_url}" target="_blank" rel="noopener">{t["open_graph"]}</a></td>'
                f'<td style="font-size:.78rem">{conn}</td>'
                f'<td style="text-align:center">'
                f'<span class="dot {epf_dot} epf-dot" style="display:inline-block" '
                f'data-epf-name="{db_id}" data-backend-connected="{"1" if backend_connected else "0"}" '
                f'title="{epf_title}"></span></td>'
                f'<td style="text-align:center">{default_icon}</td></tr>'
            )
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
        c_rows = [
            f'<table><colgroup><col style="width:28%"><col style="width:27%"><col style="width:15%"><col style="width:15%"><col style="width:15%"></colgroup>'
            f'<tr><th>{t["container"]}</th><th>{t["image"]}</th><th>{t["ram_now"]}</th><th>{t["image_disk"]}</th><th>{t["container_status"]}</th></tr>'
        ]
        for c in container_info:
            dot = "ok" if c.get("running") else "err"
            img = _esc(c.get("image", "")[:30])
            st = _esc(status_map.get(c.get("status", ""), c.get("status", "")))
            mem_now = _format_bytes_compact(c.get("memory_usage_bytes")) or t["unknown_short"]
            img_disk = _format_bytes_compact(c.get("image_size_bytes")) or t["unknown_short"]
            container_name = _esc(c["name"])
            c_rows.append(
                f'<tr>'
                f'<td><span class="sr" style="margin:0;gap:5px"><span class="dot {dot}"></span>{container_name}</span></td>'
                f'<td style="font-size:.72rem">{img}</td>'
                f'<td style="font-size:.72rem" data-container-memory="{container_name}">{_esc(mem_now)}</td>'
                f'<td style="font-size:.72rem" data-container-image-size="{container_name}">{_esc(img_disk)}</td>'
                f'<td>{st}</td>'
                f'</tr>'
            )
        c_rows.append("</table>")
        system_html = "\n".join(c_rows)
    else:
        system_html = f'<span class="st">{t["no_containers"]}</span>'

    # Docker system info
    if docker_system and not docker_system.get("error"):
        ds = docker_system
        vol_size = ds.get("volumes_size_gb", 0)
        vol_str = f"{vol_size} GB" if vol_size >= 0.01 else "<1 MB"
    else:
        ds = {}
        vol_str = t["docker_stats_unloaded"]
    docker_info_html = (
        f'<div class="srow" style="margin-bottom:12px">'
        f'<div><div class="sv" id="docker-version" style="font-size:1rem">{_esc(str(ds.get("version","?")))}</div><div class="sl">{t["docker_version"]}</div></div>'
        f'<div><div class="sv" id="docker-cpus" style="font-size:1rem">{_esc(str(ds.get("cpus",0)))}</div><div class="sl">{t["docker_cpus"]}</div></div>'
        f'<div><div class="sv" id="docker-memory-gb" style="font-size:1rem">{_esc(str(ds.get("memory_gb", t["unknown_short"])))}{" GB" if ds.get("memory_gb") is not None else ""}</div><div class="sl">{t["docker_mem"]}</div></div>'
        f'<div><div class="sv" id="docker-images-size" style="font-size:1rem">{_esc(str(ds.get("images_size_gb", t["unknown_short"])))}{" GB" if ds.get("images_size_gb") is not None else ""}</div><div class="sl">{t["docker_imgs_size"]}</div></div>'
        f'<div><div class="sv" id="docker-volumes-size" style="font-size:1rem">{_esc(vol_str)}</div><div class="sl">{t["docker_vols_size"]}</div></div>'
        f'</div>'
    )

    report_blocks = []
    for item in reports_summary or []:
        database = _esc(item.get("database", ""))
        if not item.get("catalog_ready"):
            report_blocks.append(
                f'<div style="padding:8px 0;border-bottom:1px solid #334155">'
                f'<div class="sr"><span class="sn">{database}</span></div>'
                f'<div class="st" style="white-space:normal">{t["reports_none"]}</div>'
                f'</div>'
            )
            continue
        counts = item.get("status_counts") or {}
        report_blocks.append(
            f'<div style="padding:8px 0;border-bottom:1px solid #334155">'
            f'<div class="sr"><span class="sn">{database}</span></div>'
            f'<div class="st">{t["reports_analyzed"]}: {_esc(item.get("analyzed_at", "") or t["unknown_short"])}</div>'
            f'<div class="srow" style="margin-top:8px">'
            f'<div><div class="sv" style="font-size:1rem">{int(item.get("reports_count", 0) or 0)}</div><div class="sl">{t["reports_found"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(item.get("variants_count", 0) or 0)}</div><div class="sl">{t["reports_variants"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(item.get("runs_count", 0) or 0)}</div><div class="sl">{t["reports_runs"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(item.get("artifacts_count", 0) or 0)}</div><div class="sl">{t["reports_artifacts"]}</div></div>'
            f'</div>'
            f'<div class="srow" style="margin-top:8px">'
            f'<div><div class="sv" style="font-size:1rem">{int(counts.get("done", 0) or 0)}</div><div class="sl">{t["reports_done"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(counts.get("needs_input", 0) or 0)}</div><div class="sl">{t["reports_needs_input"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(counts.get("unsupported", 0) or 0)}</div><div class="sl">{t["reports_unsupported"]}</div></div>'
            f'<div><div class="sv" style="font-size:1rem">{int(counts.get("error", 0) or 0)}</div><div class="sl">{t["reports_error"]}</div></div>'
            f'</div>'
            f'</div>'
        )
    reports_summary_html = "".join(report_blocks) or f'<span class="st">{t["reports_none"]}</span>'

    # Config
    config_html = "\n".join(f"<tr><td>{_esc(k)}</td><td><code>{_esc(v)}</code></td></tr>" for k, v in config_items)
    # DB management — buttons under each DB, separated by lines
    if databases:
        db_blocks = []
        for i, db in enumerate(sorted(databases, key=lambda d: d.get('name', ''))):
            is_default = db.get("active", False)
            epf_connected = db.get("epf_connected", False)
            backend_connected = db.get("backend_connected", True)  # is DB in manager
            epf_dot = "ok" if epf_connected else "warn"
            db_id = _esc(db["name"])
            epf_title = "Обработка подключена" if epf_connected else "Обработка не подключена"
            epf_st = (
                f'<span class="dot {epf_dot} epf-dot" style="display:inline-block" '
                f'data-epf-name="{db_id}" data-backend-connected="{"1" if backend_connected else "0"}" '
                f'title="{epf_title}"></span>'
            )
            conn_escaped = _esc(db.get("connection", ""))
            proj_escaped = _esc(db.get("project_path", ""))
            name_escaped = _esc(db["name"])
            name_js = _esc_js(db["name"])
            conn_js = _esc_js(db.get("connection", ""))
            proj_js = _esc_js(db.get("project_path", ""))
            sep = '<tr><td colspan="4" style="padding:0"><hr style="border:none;border-top:1px solid #334155;margin:4px 0"></td></tr>' if i > 0 else ""
            # Backend connectivity controls DB availability via MCP routing.
            # EPF status is shown independently in the EPF column.
            name_style = 'text-decoration:line-through;color:#64748b;font-weight:bold' if not backend_connected else ''
            name_cell = f'<span style="{name_style}">{name_escaped}</span>'
            # Default column: active dot or switch button (only when backend is connected)
            if is_default and backend_connected:
                default_cell = '<span class="dot ok" style="display:inline-block"></span>'
            elif backend_connected:
                default_cell = (
                    f'<button class="btn" style="font-size:.65rem;padding:2px 6px" '
                    f'onclick="act(\'/api/action/switch?name={_esc(db["name"])}\')">{t["configure"]}</button>'
                )
            else:
                default_cell = ""
            # Crimson outlined button style
            _crimson = 'background:transparent;border-color:#ef4444;color:#ef4444'
            # Action buttons under DB
            edit_btn = (
                f'<button class="btn" style="font-size:.65rem;padding:2px 6px" '
                f'onclick="editDb(\'{name_js}\',\'{conn_js}\',\'{proj_js}\')">{t["edit_db"]}</button> '
            )
            reindex_btn = (
                f'<button class="btn" style="font-size:.65rem;padding:2px 6px" '
                f'onclick="act(\'/api/action/reindex-bsl?name={_esc(db["name"])}\')">{t["reindex_bsl"]}</button> '
            )
            if backend_connected:
                connect_toggle_btn = (
                    f'<button class="btn" style="font-size:.65rem;padding:2px 6px;{_crimson}" '
                    f'onclick="confirmDisconnect(\'{name_js}\')">'
                    f'{t["disconnect_db"]}</button>'
                )
            else:
                connect_toggle_btn = (
                    f'<button class="btn" style="font-size:.65rem;padding:2px 6px" '
                    f'onclick="act(\'/api/action/reconnect?name={_esc(db["name"])}\')">'
                    f'{t["reconnect_db"]}</button>'
                )
            remove_btn = (
                f'<button class="btn" style="font-size:.65rem;padding:2px 6px;{_crimson}" '
                f'onclick="confirmRemove(\'{name_js}\')">'
                f'{t["remove_db"]}</button>'
            )
            db_blocks.append(
                f'{sep}'
                f'<tr style="vertical-align:middle">'
                f'<td>{name_cell}</td>'
                f'<td style="font-size:.75rem">{conn_escaped}</td>'
                f'<td style="text-align:center">{epf_st}</td>'
                f'<td style="text-align:center">{default_cell}</td>'
                f'</tr>'
                f'<tr><td colspan="4" style="padding:2px 6px">'
                f'{edit_btn}{reindex_btn}{connect_toggle_btn} {remove_btn}'
                f'</td></tr>'
            )
        db_mgmt_html = (
            f'<table style="table-layout:auto;font-size:.82rem">'
            f'<tr><th>{t["name"]}</th><th>{t["connection"]}</th>'
            f'<th style="text-align:center">{t["status"]}</th><th style="text-align:center">{t["default_badge"]}</th></tr>'
            + "\n".join(db_blocks) + '</table>'
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
        "optional_services_html": optional_services_html,
        "system_html": system_html, "config_html": config_html,
        "db_mgmt_html": db_mgmt_html,
        "reports_summary_html": reports_summary_html,
        "github_url": GITHUB_URL, "lang": lang,
        "ru_on": "on" if lang == "ru" else "",
        "en_on": "on" if lang == "en" else "",
        "logo": LOGO_SVG,
    }
    for k, v in replacements.items():
        html = html.replace("{{" + k + "}}", v)
    return html

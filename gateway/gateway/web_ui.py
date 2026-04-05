"""
Minimal Web UI dashboard for onec-mcp-universal gateway.
Served at GET /dashboard.
"""
from __future__ import annotations

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>onec-mcp-universal</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f172a;color:#e2e8f0;padding:24px}
h1{font-size:1.5rem;margin-bottom:4px;color:#f8fafc}
.subtitle{color:#94a3b8;margin-bottom:24px;font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-bottom:24px}
.card{background:#1e293b;border-radius:12px;padding:20px;border:1px solid #334155}
.card h2{font-size:1rem;color:#94a3b8;margin-bottom:12px;text-transform:uppercase;font-size:.75rem;letter-spacing:.05em}
.status{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot.ok{background:#22c55e}.dot.err{background:#ef4444}.dot.warn{background:#f59e0b}
.name{font-weight:600;color:#f8fafc}.tools-count{color:#64748b;font-size:.85rem}
.badge{display:inline-block;background:#334155;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:.75rem;margin-left:8px}
.badge.active{background:#164e63;color:#22d3ee}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;color:#64748b;padding:8px;border-bottom:1px solid #334155;font-weight:500}
td{padding:8px;border-bottom:1px solid #1e293b;color:#cbd5e1}
.refresh{color:#38bdf8;text-decoration:none;font-size:.85rem;cursor:pointer;border:none;background:none}
.refresh:hover{text-decoration:underline}
.stat-value{font-size:1.5rem;font-weight:700;color:#f8fafc}
.stat-label{color:#64748b;font-size:.75rem}
.stats-row{display:flex;gap:24px;margin-top:8px}
.footer{color:#475569;font-size:.75rem;margin-top:24px;text-align:center}
</style>
</head>
<body>
<h1>onec-mcp-universal</h1>
<p class="subtitle">MCP Gateway Dashboard &mdash; <button class="refresh" onclick="location.reload()">Refresh</button></p>

<div class="grid">
<div class="card">
<h2>Backends</h2>
{{backends_html}}
</div>

<div class="card">
<h2>Databases</h2>
{{databases_html}}
</div>

<div class="card">
<h2>Query Profiling</h2>
{{profiling_html}}
</div>

<div class="card">
<h2>Metadata Cache</h2>
{{cache_html}}
</div>

<div class="card">
<h2>Anonymization</h2>
<div class="status">
<div class="dot {{anon_dot}}"></div>
<span class="name">{{anon_status}}</span>
</div>
</div>

<div class="card">
<h2>Configuration</h2>
<table>
<tr><th>Setting</th><th>Value</th></tr>
{{config_html}}
</table>
</div>
</div>

<p class="footer">onec-mcp-universal {{version}} &mdash; <a href="/health" style="color:#38bdf8">API Health</a> &mdash; <a href="/mcp" style="color:#38bdf8">MCP Endpoint</a></p>
</body>
</html>"""


def render_dashboard(
    backends_status: dict,
    databases: list[dict],
    profiling_stats: dict,
    cache_stats: dict,
    anon_enabled: bool,
    config_items: list[tuple[str, str]],
    version: str = "v0.4",
) -> str:
    """Render the dashboard HTML."""

    # Backends
    backends_lines = []
    for name, info in backends_status.items():
        ok = info.get("ok", False)
        dot_class = "ok" if ok else "err"
        tools = info.get("tools", 0)
        active = info.get("active", False)
        badge = '<span class="badge active">active</span>' if active else ""
        backends_lines.append(
            f'<div class="status"><div class="dot {dot_class}"></div>'
            f'<span class="name">{name}</span>'
            f'<span class="tools-count">{tools} tools</span>{badge}</div>'
        )
    backends_html = "\n".join(backends_lines) if backends_lines else '<span class="tools-count">No backends</span>'

    # Databases
    if databases:
        db_lines = ['<table><tr><th>Name</th><th>Connection</th><th>Status</th></tr>']
        for db in databases:
            active_badge = '<span class="badge active">active</span>' if db.get("active") else ""
            epf = "EPF connected" if db.get("epf_connected") else "waiting for EPF"
            db_lines.append(f'<tr><td>{db["name"]} {active_badge}</td><td>{db.get("connection","")[:40]}</td><td>{epf}</td></tr>')
        db_lines.append("</table>")
        databases_html = "\n".join(db_lines)
    else:
        databases_html = '<span class="tools-count">No databases connected</span>'

    # Profiling
    if profiling_stats.get("total_queries", 0) > 0:
        ps = profiling_stats
        profiling_html = f"""
        <div class="stats-row">
            <div><div class="stat-value">{ps['total_queries']}</div><div class="stat-label">Queries</div></div>
            <div><div class="stat-value">{ps['avg_ms']}ms</div><div class="stat-label">Avg</div></div>
            <div><div class="stat-value">{ps['max_ms']}ms</div><div class="stat-label">Max</div></div>
            <div><div class="stat-value">{ps['slow_queries_over_5s']}</div><div class="stat-label">Slow (&gt;5s)</div></div>
        </div>"""
    else:
        profiling_html = '<span class="tools-count">No queries recorded yet</span>'

    # Cache
    cs = cache_stats
    cache_html = f"""
    <div class="stats-row">
        <div><div class="stat-value">{cs.get('entries',0)}</div><div class="stat-label">Entries</div></div>
        <div><div class="stat-value">{cs.get('hit_rate','0%')}</div><div class="stat-label">Hit Rate</div></div>
        <div><div class="stat-value">{cs.get('ttl_seconds',0)}s</div><div class="stat-label">TTL</div></div>
    </div>"""

    # Anonymization
    anon_dot = "ok" if anon_enabled else "warn"
    anon_status = "Enabled" if anon_enabled else "Disabled"

    # Config
    config_rows = [f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in config_items]
    config_html = "\n".join(config_rows)

    html = HTML_TEMPLATE
    html = html.replace("{{backends_html}}", backends_html)
    html = html.replace("{{databases_html}}", databases_html)
    html = html.replace("{{profiling_html}}", profiling_html)
    html = html.replace("{{cache_html}}", cache_html)
    html = html.replace("{{anon_dot}}", anon_dot)
    html = html.replace("{{anon_status}}", anon_status)
    html = html.replace("{{config_html}}", config_html)
    html = html.replace("{{version}}", version)
    return html

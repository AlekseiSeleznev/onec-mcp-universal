#!/usr/bin/env python3
"""
Хостовый HTTP-сервис для выгрузки BSL-исходников через 1cv8c.
Запускается на хосте (не в контейнере), слушает на порту 8082.
Контейнер вызывает его через host.docker.internal:8082 или IP хоста.

Запуск:
    python3 tools/export-host-service.py
    python3 tools/export-host-service.py --port 8082 --workspace /home/aleksei/projects
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer

V8_PATH = os.environ.get("V8_PATH", "/opt/1cv8/x86_64/8.3.27.2074")
WORKSPACE = os.environ.get("BSL_WORKSPACE", "/home/aleksei/projects")


def _parse_connection(conn: str) -> dict:
    result = {}
    for part in conn.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        result[k.lower().strip()] = v.strip()
    return result


def run_export(connection: str, output_dir: str) -> tuple[bool, str]:
    parsed = _parse_connection(connection)
    server = parsed.get("srvr", "")
    ref    = parsed.get("ref", "")
    user   = parsed.get("usr", "")
    pwd    = parsed.get("pwd", "")
    fpath  = parsed.get("file", "")

    os.makedirs(output_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as lf:
        log_path = lf.name

    cmd = [f"{V8_PATH}/1cv8", "DESIGNER"]
    if server and ref:
        cmd += [f"/S", f"{server}\\{ref}"]
    elif fpath:
        cmd += ["/F", fpath]
    else:
        return False, f"Cannot parse connection string: {connection}"

    if user:
        cmd += ["/N", user]
    if pwd:
        cmd += ["/P", pwd]

    cmd += ["/DumpConfigToFiles", output_dir, "/DisableStartupDialogs", "/Out", log_path]

    display = os.environ.get("DISPLAY", "")
    if not display:
        for d in [":0", ":1", ":2"]:
            sock = f"/tmp/.X11-unix/X{d[1:]}"
            if os.path.exists(sock):
                display = d
                break

    env = dict(os.environ)
    if display:
        env["DISPLAY"] = display

    try:
        proc = subprocess.run(cmd, env=env, timeout=1800, capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return False, "Export timed out (30 min)"
    except FileNotFoundError:
        return False, f"1cv8c not found at {V8_PATH}/1cv8c"

    log_content = ""
    try:
        with open(log_path) as f:
            log_content = f.read()
    except Exception:
        pass

    if proc.returncode != 0:
        return False, f"Export failed (rc={proc.returncode}):\n{log_content or proc.stderr}"

    file_count = sum(1 for _ in os.walk(output_dir) for _ in _[2])
    return True, f"Export completed: {file_count} files in {output_dir}\n{log_content}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": True, "service": "export-host-service"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/export-bsl":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return

        connection  = body.get("connection", "").strip()
        output_dir  = body.get("output_dir", WORKSPACE).strip()

        if not connection:
            resp = json.dumps({"ok": False, "result": "Field 'connection' is required"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp)
            return

        ok, result = run_export(connection, output_dir)
        resp = json.dumps({"ok": ok, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(resp)


def main():
    global WORKSPACE
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--workspace", default=WORKSPACE)
    args = ap.parse_args()
    WORKSPACE = args.workspace

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Export host service listening on {args.host}:{args.port}")
    print(f"  BSL workspace: {WORKSPACE}")
    print(f"  V8 path:       {V8_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()

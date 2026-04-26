#!/usr/bin/env python3
"""
Хостовый HTTP-сервис для выгрузки BSL-исходников через 1cv8 DESIGNER.
Запускается на хосте (не в контейнере), слушает на порту 8082.
Контейнер вызывает его через --network host → localhost:8082.

ВАЖНО: использует 1cv8 (толстый клиент), НЕ 1cv8c.
1cv8c не поддерживает режим DESIGNER и игнорирует DumpConfigToFiles.

Запуск:
    python3 tools/export-host-service.py
    python3 tools/export-host-service.py --port 8082 --workspace /z/Z01

ИЗВЕСТНОЕ ОГРАНИЧЕНИЕ: ERP содержит роли с именами длиннее 255 байт.
На Linux-файловых системах (ext4/btrfs) такие имена не поддерживаются,
выгрузка завершится с ошибкой "File name too long" на соответствующей роли.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import platform as _platform

_IS_WINDOWS = _platform.system() == "Windows"
_DEFAULT_V8 = r"C:\Program Files\1cv8" if _IS_WINDOWS else "/opt/1cv8/x86_64/8.3.27.2074"
_DEFAULT_WS = (
    str(Path.home() / "bsl-projects")
    if _IS_WINDOWS
    else os.path.join(os.path.expanduser("~"), "bsl-projects")
)
V8_PATH = os.environ.get("V8_PATH", _DEFAULT_V8)
WORKSPACE = os.environ.get("BSL_WORKSPACE", _DEFAULT_WS)
WORKSPACE_OVERRIDE = ""
_PROC_RE = re.compile(
    r'^(Процедура|Функция|Procedure|Function)\s+(\w+)\s*\(([^)]*)\)(\s+Экспорт|\s+Export)?',
    re.MULTILINE | re.IGNORECASE,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_env_value(key: str) -> str:
    env_file = _repo_root() / ".env"
    if not env_file.is_file():
        return ""

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, _, value = line.partition("=")
        if current_key.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
            value = value[1:-1]
        return value
    return ""


def current_workspace() -> str:
    workspace = (
        WORKSPACE_OVERRIDE
        or _read_env_value("BSL_HOST_WORKSPACE")
        or _read_env_value("BSL_WORKSPACE")
        or WORKSPACE
        or _DEFAULT_WS
    )
    path = Path(workspace).expanduser()
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return str(path)


def browse_directories(raw_path: str) -> dict:
    """Return a host-side directory listing for the dashboard folder picker."""
    raw = (raw_path or "").strip()
    if raw == "~" or not raw:
        raw = current_workspace()

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path(current_workspace()) / path).resolve()
    else:
        path = path.resolve()

    try:
        if not path.is_dir():
            path = path.parent

        dirs = sorted(
            entry.name
            for entry in path.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        )
        return {
            "path": str(path),
            "parent": str(path.parent if path.parent != path else path),
            "dirs": dirs,
        }
    except PermissionError:
        return {
            "path": str(path),
            "parent": str(path.parent if path.parent != path else path),
            "dirs": [],
            "error": "Permission denied",
        }


def _normalize_directory_dialog_path(raw_path: str) -> str:
    raw = (raw_path or "").strip()
    if raw == "~" or not raw:
        raw = current_workspace()

    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path(current_workspace()) / path).resolve()
    else:
        path = path.resolve()

    if not path.is_dir():
        path = path.parent
    return str(path)


def _build_windows_directory_dialog_script(initial_path: str) -> str:
    escaped = initial_path.replace("'", "''")
    return "; ".join(
        [
            "Add-Type -AssemblyName System.Windows.Forms",
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog",
            '$dialog.Description = "Select BSL Export Folder"',
            "$dialog.ShowNewFolderButton = $true",
            f"$dialog.SelectedPath = '{escaped}'",
            "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {",
            "  Write-Output $dialog.SelectedPath",
            "  exit 0",
            "}",
            "exit 1",
        ]
    )


def _build_mac_directory_dialog_script(initial_path: str) -> list[str]:
    escaped = initial_path.replace('"', '\\"')
    return [
        (
            'set chosenFolder to choose folder with prompt "Select BSL Export Folder" '
            f'default location POSIX file "{escaped}"'
        ),
        "POSIX path of chosenFolder",
    ]


def _build_native_directory_dialog_strategies(initial_path: str, platform_name: str | None = None) -> list[tuple[str, list[str]]]:
    platform_name = (platform_name or _platform.system()).lower()
    candidate = _normalize_directory_dialog_path(initial_path)
    trailing = candidate if candidate.endswith(os.path.sep) else f"{candidate}{os.path.sep}"

    if platform_name.startswith("win"):
        return [
            (
                "powershell",
                ["-NoProfile", "-STA", "-Command", _build_windows_directory_dialog_script(candidate)],
            )
        ]
    if platform_name == "darwin":
        args: list[str] = []
        for line in _build_mac_directory_dialog_script(candidate):
            args.extend(["-e", line])
        return [("osascript", args)]
    return [
        (
            "zenity",
            ["--file-selection", "--directory", "--title=Select BSL Export Folder", f"--filename={trailing}"],
        ),
        (
            "qarma",
            ["--file-selection", "--directory", "--title=Select BSL Export Folder", f"--filename={trailing}"],
        ),
        (
            "yad",
            ["--file-selection", "--directory", "--title=Select BSL Export Folder", f"--filename={trailing}"],
        ),
        ("kdialog", ["--getexistingdirectory", candidate]),
    ]


def _run_dialog_process(command: str, args: list[str]) -> dict:
    env = dict(os.environ)
    if not _IS_WINDOWS and _platform.system() != "Darwin":
        env.setdefault("DISPLAY", env.get("DISPLAY") or ":0")
    completed = subprocess.run(
        [command, *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    return {
        "code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def choose_directory_with_os_dialog(
    initial_path: str,
    *,
    process_runner=None,
    platform_name: str | None = None,
) -> dict:
    runner = process_runner or _run_dialog_process
    last_error = ""
    for command, args in _build_native_directory_dialog_strategies(initial_path, platform_name):
        try:
            result = runner(command, args)
        except FileNotFoundError:
            continue
        except OSError as exc:
            last_error = str(exc)
            continue

        raw_code = result.get("code", 1)
        code = 1 if raw_code is None else int(raw_code)
        stdout = str(result.get("stdout", "") or "").strip()
        stderr = str(result.get("stderr", "") or "").strip()

        if code == 0 and stdout:
            return {"ok": True, "cancelled": False, "path": stdout}
        if code == 1:
            return {"ok": True, "cancelled": True, "path": ""}
        last_error = stderr or f"Dialog exited with code {code}"

    return {
        "ok": False,
        "error": last_error or "No supported native directory dialog is available on this host.",
    }


def _find_v8_binaries() -> dict:
    """Scan host filesystem for installed 1cv8 thick-client binaries."""
    result = {}
    if _IS_WINDOWS:
        base = Path(r"C:\Program Files\1cv8")
        if base.is_dir():
            for ver_dir in base.iterdir():
                if not ver_dir.is_dir():
                    continue
                binary = ver_dir / "bin" / "1cv8.exe"
                if binary.is_file():
                    result[ver_dir.name] = str(binary)
        return result

    base = "/opt/1cv8/x86_64"
    if os.path.isdir(base):
        for ver in os.listdir(base):
            binary = os.path.join(base, ver, "1cv8")
            if os.path.isfile(binary) and os.access(binary, os.X_OK):
                result[ver] = binary
    return result


def _resolve_v8_binary() -> str | None:
    """Resolve a runnable 1cv8 binary from V8_PATH with OS-specific fallbacks."""
    if _IS_WINDOWS:
        candidates = []
        if V8_PATH.lower().endswith(".exe"):
            candidates.append(V8_PATH)
        candidates.append(os.path.join(V8_PATH, "1cv8.exe"))
        candidates.append(os.path.join(V8_PATH, "bin", "1cv8.exe"))
        for binary in candidates:
            if os.path.isfile(binary):
                return binary

        discovered = _find_v8_binaries()
        if discovered:
            latest = sorted(discovered.keys())[-1]
            return discovered[latest]
        return None

    candidates = [
        os.path.join(V8_PATH, "1cv8"),
        os.path.join(V8_PATH, "bin", "1cv8"),
    ]
    for binary in candidates:
        if os.path.isfile(binary) and os.access(binary, os.X_OK):
            return binary
    return None


def _parse_connection(conn: str) -> dict:
    result = {}
    for part in conn.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        result[k.lower().strip()] = v.strip()
    return result


def _sample_bsl_symbol_hits(output_dir: str, *, sample_limit: int = 32) -> tuple[int, int]:
    """Return (sampled_files, files_with_proc_decl) for a BSL export tree."""
    files = sorted(Path(output_dir).rglob("*.bsl"))[:sample_limit]
    hits = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            continue
        if _PROC_RE.search(text):
            hits += 1
    return len(files), hits


def _wait_for_export_stabilization(
    output_dir: str,
    *,
    bsl_count: int,
    attempts: int = 12,
    delay_seconds: float = 10.0,
) -> None:
    """
    Wait until a large export tree contains readable procedure/function declarations.

    1cv8 can finish DumpConfigToFiles before the host filesystem view is fully mature.
    Avoid reporting `done` while the tree still looks like thousands of empty/partial
    BSL files to the gateway indexer.
    """
    if bsl_count < 100:
        return

    for attempt in range(attempts):
        sampled, hits = _sample_bsl_symbol_hits(output_dir)
        if sampled == 0 or hits > 0:
            return
        print(
            f"[export] waiting for BSL stabilization: "
            f"sampled={sampled} files, symbol_hits={hits}, "
            f"attempt={attempt + 1}/{attempts}, sleep={delay_seconds}s"
        )
        time.sleep(delay_seconds)


def _ensure_gateway_readable(output_dir: str) -> None:
    """
    Make exported BSL tree readable/traversable for the non-root gateway user.

    Host-side DumpConfigToFiles can create files with umask 007 (e.g. 660), which
    leaves the gateway container app user unable to read host-mounted BSL files.
    Grant world read on files and world execute on directories so the gateway can
    index the export regardless of host uid/gid mismatch.
    """
    root = Path(output_dir)
    if not root.exists():
        return

    for path in [root, *root.rglob("*")]:
        try:
            current_mode = stat.S_IMODE(path.stat().st_mode)
            if path.is_dir():
                desired_mode = current_mode | stat.S_IXOTH | stat.S_IROTH
            else:
                desired_mode = current_mode | stat.S_IROTH
            if desired_mode != current_mode:
                path.chmod(desired_mode)
        except Exception as exc:
            print(f"[export] warning: failed to adjust permissions for {path}: {exc}")


def _swap_export_tree(stage_dir: str, output_dir: str) -> None:
    """Atomically replace the export root with a prepared staging tree."""
    output_path = Path(output_dir)
    stage_path = Path(stage_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    if output_path.exists():
        backup_path = output_path.parent / f".{output_path.name}.backup-{int(time.time() * 1000)}"
        os.replace(output_path, backup_path)

    try:
        os.replace(stage_path, output_path)
    except Exception:
        if backup_path is not None and backup_path.exists() and not output_path.exists():
            os.replace(backup_path, output_path)
        raise

    if backup_path is not None and backup_path.exists():
        shutil.rmtree(backup_path, ignore_errors=True)


def run_export(connection: str, output_dir: str) -> tuple[bool, str]:
    parsed = _parse_connection(connection)
    server = parsed.get("srvr", "")
    ref    = parsed.get("ref", "")
    user   = parsed.get("usr", "")
    pwd    = parsed.get("pwd", "")
    fpath  = parsed.get("file", "")

    output_path = Path(output_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = tempfile.mkdtemp(prefix=f".{output_path.name}.staging-", dir=str(output_path.parent))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as lf:
        log_path = lf.name

    v8_binary = _resolve_v8_binary()
    if not v8_binary:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return False, f"1cv8 not found (V8_PATH={V8_PATH})"
    cmd = [v8_binary, "DESIGNER"]
    if server and ref:
        cmd += [f"/S", f"{server}\\{ref}"]
    elif fpath:
        cmd += ["/F", fpath]
    else:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return False, f"Cannot parse connection string: {connection}"

    if user:
        cmd += ["/N", user]
    if pwd:
        cmd += ["/P", pwd]

    cmd += ["/DumpConfigToFiles", stage_dir, "/DisableStartupDialogs", "/Out", log_path]

    env = dict(os.environ)
    if not _IS_WINDOWS:
        display = os.environ.get("DISPLAY", "")
        if not display:
            for d in [":0", ":1", ":2"]:
                sock = f"/tmp/.X11-unix/X{d[1:]}"
                if os.path.exists(sock):
                    display = d
                    break
        if display:
            env["DISPLAY"] = display

    conn_key = connection
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _export_procs[conn_key] = proc
        try:
            _, _ = proc.communicate(timeout=10800)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            _export_procs.pop(conn_key, None)
            shutil.rmtree(stage_dir, ignore_errors=True)
            return False, "Export timed out (3 hours)"
        _export_procs.pop(conn_key, None)
        if proc.returncode in (-9, -15):
            shutil.rmtree(stage_dir, ignore_errors=True)
            return False, "Export cancelled"
    except FileNotFoundError:
        _export_procs.pop(conn_key, None)
        shutil.rmtree(stage_dir, ignore_errors=True)
        return False, f"1cv8 not found at {v8_binary}"

    log_content = ""
    try:
        with open(log_path, encoding="utf-8-sig") as f:
            log_content = f.read().replace("\ufeff", "").strip()
    except Exception:
        pass

    if proc.returncode != 0:
        # Auto-retry with matching version on client/server mismatch
        vm = re.search(r"([\d.]+) - ([\d.]+)\)", log_content)
        if vm:
            server_ver = vm.group(2)
            available = _find_v8_binaries()
            if server_ver in available and available[server_ver] != v8_binary:
                print(f"[export] version mismatch: client={vm.group(1)}, server={server_ver}. Retrying with {available[server_ver]}")
                cmd[0] = available[server_ver]
                proc2 = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                _export_procs[conn_key] = proc2
                try:
                    _, _ = proc2.communicate(timeout=10800)
                except subprocess.TimeoutExpired:
                    proc2.kill(); proc2.communicate()
                    _export_procs.pop(conn_key, None)
                    shutil.rmtree(stage_dir, ignore_errors=True)
                    return False, "Export timed out (3 hours)"
                _export_procs.pop(conn_key, None)
                if proc2.returncode == 0:
                    proc = proc2
                    try:
                        with open(log_path, encoding="utf-8-sig") as f:
                            log_content = f.read().replace("\ufeff", "").strip()
                    except Exception:
                        pass
                else:
                    try:
                        with open(log_path, encoding="utf-8-sig") as f:
                            log_content = f.read().replace("\ufeff", "").strip()
                    except Exception:
                        pass
                    shutil.rmtree(stage_dir, ignore_errors=True)
                    return False, f"Export failed (rc={proc2.returncode}):\n{log_content or proc2.stderr}"
            elif server_ver not in available:
                installed = ", ".join(sorted(available.keys())) or "(none)"
                shutil.rmtree(stage_dir, ignore_errors=True)
                return False, f"Export failed: версия сервера {server_ver} не установлена. Установлены: {installed}"
        if proc.returncode != 0:
            shutil.rmtree(stage_dir, ignore_errors=True)
            return False, f"Export failed (rc={proc.returncode}):\n{log_content or proc.stderr}"

    bsl_count = sum(
        1 for root, _, files in os.walk(stage_dir) for f in files if f.endswith(".bsl")
    )
    _ensure_gateway_readable(stage_dir)
    _wait_for_export_stabilization(stage_dir, bsl_count=bsl_count)
    try:
        _swap_export_tree(stage_dir, output_dir)
    except Exception as exc:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return False, f"Export failed while replacing destination: {exc}"
    return True, f"Export completed: {bsl_count} BSL files in {output_dir}\n{log_content}"


# Per-connection export state: {conn_key: {"status": "running"|"done"|"error"|"cancelled", "result": str}}
_export_jobs: dict = {}
_export_procs: dict = {}  # {conn_key: Popen} — for cancellation
_export_lock = None  # threading.Lock for _export_jobs dict mutations


def _run_export_background(connection: str, output_dir: str) -> None:
    try:
        ok, result = run_export(connection, output_dir)
        _export_jobs[connection] = {"status": "done" if ok else "error", "result": result}
    except Exception as e:
        _export_jobs[connection] = {"status": "error", "result": f"Export failed: {e}"}
    print(f"[export] finished: conn={connection!r} status={_export_jobs[connection]['status']}")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {
                "ok": True,
                "service": "export-host-service",
                "workspace": current_workspace(),
            })
        elif self.path.startswith("/browse"):
            from urllib.parse import parse_qs, urlparse

            raw = parse_qs(urlparse(self.path).query).get("path", [""])[0]
            self._send_json(200, browse_directories(raw))
        elif self.path.startswith("/export-status"):
            from urllib.parse import urlparse, parse_qs
            conn = parse_qs(urlparse(self.path).query).get("connection", [None])[0]
            if conn:
                job = _export_jobs.get(conn, {"status": "idle", "result": ""})
                self._send_json(200, job)
            else:
                # Return all jobs summary
                self._send_json(200, {"jobs": _export_jobs})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = {}
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except Exception:
                self._send_json(400, {"ok": False, "result": "Invalid JSON"})
                return

        if self.path == "/select-directory":
            result = choose_directory_with_os_dialog(body.get("currentPath", ""))
            self._send_json(200 if result.get("ok", False) else 500, result)
            return

        if self.path == "/cancel":
            conn = body.get("connection", "").strip()
            if conn:
                proc = _export_procs.get(conn)
                if proc is not None:
                    proc.kill()
                    _export_jobs[conn] = {"status": "cancelled", "result": "Выгрузка отменена пользователем."}
                    self._send_json(200, {"ok": True, "result": f"Export cancelled: {conn}"})
                else:
                    self._send_json(200, {"ok": False, "result": "No export running for this connection."})
            else:
                # Cancel ALL running exports
                killed = []
                for c, proc in list(_export_procs.items()):
                    if proc is not None:
                        proc.kill()
                        _export_jobs[c] = {"status": "cancelled", "result": "Выгрузка отменена пользователем."}
                        killed.append(c)
                self._send_json(200, {"ok": True, "result": f"Cancelled: {killed}"})
            return

        if self.path != "/export-bsl":
            self.send_response(404)
            self.end_headers()
            return

        connection = body.get("connection", "").strip()
        output_dir = body.get("output_dir", "").strip() or current_workspace()

        if not connection:
            self._send_json(400, {"ok": False, "result": "Field 'connection' is required"})
            return

        with _export_lock:
            if _export_jobs.get(connection, {}).get("status") == "running":
                self._send_json(409, {"ok": False, "result": "Export already running for this connection"})
                return
            _export_jobs[connection] = {"status": "running", "result": ""}

        import threading
        t = threading.Thread(target=_run_export_background, args=(connection, output_dir), daemon=True)
        t.start()

        self._send_json(200, {"ok": True, "result": "Export started in background. Check /export-status for progress."})


def main():
    global WORKSPACE_OVERRIDE, _export_lock
    import threading
    _export_lock = threading.Lock()

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--workspace", default="")
    args = ap.parse_args()
    WORKSPACE_OVERRIDE = args.workspace.strip()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Export host service listening on {args.host}:{args.port}")
    print(f"  BSL workspace: {current_workspace()}")
    print(f"  V8 path:       {V8_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()

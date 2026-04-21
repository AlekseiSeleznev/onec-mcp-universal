#!/usr/bin/env python3
# epf-build v1.1 — Build external data processor or report (EPF/ERF) from XML sources
# Cross-platform: Windows and Linux. Auto-detects installed 1C versions.
# Source: https://github.com/Nikolay-Shirokov/cc-1c-skills

import argparse
import glob
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile


def _is_windows():
    return platform.system() == "Windows"


def _v8_bin_name():
    return "1cv8.exe" if _is_windows() else "1cv8"


def find_all_v8_binaries():
    """Return dict {version_str: path} of all installed 1cv8 binaries."""
    result = {}
    if _is_windows():
        patterns = [r"C:\Program Files\1cv8\*\bin\1cv8.exe"]
    else:
        patterns = [
            "/opt/1cv8/x86_64/*/1cv8",
            "/opt/1cv8/*/1cv8",
        ]
    for pattern in patterns:
        for path in glob.glob(pattern):
            if os.path.isfile(path):
                # Extract version from path, e.g. .../8.3.27.1989/1cv8
                m = re.search(r'(\d+\.\d+\.\d+\.\d+)', path)
                ver = m.group(1) if m else path
                result[ver] = path
    return result


def resolve_v8path(v8path_arg):
    """Resolve path to 1cv8 binary. Returns (path, all_versions_dict)."""
    all_versions = find_all_v8_binaries()

    if not v8path_arg:
        if not all_versions:
            print(f"Error: {_v8_bin_name()} not found. Specify -V8Path", file=sys.stderr)
            sys.exit(1)
        # Pick the latest installed version
        latest_ver = sorted(all_versions.keys())[-1]
        return all_versions[latest_ver], all_versions

    # If it's a directory — append binary name
    if os.path.isdir(v8path_arg):
        candidate = os.path.join(v8path_arg, _v8_bin_name())
        if not os.path.isfile(candidate):
            # Also try without .exe on Linux
            candidate = os.path.join(v8path_arg, "1cv8")
        v8path_arg = candidate

    if not os.path.isfile(v8path_arg):
        print(f"Error: {_v8_bin_name()} not found at {v8path_arg}", file=sys.stderr)
        sys.exit(1)

    return v8path_arg, all_versions


def run_designer(v8path, arguments, out_file):
    """Run 1cv8 DESIGNER with given arguments. Returns (exit_code, log_content)."""
    cmd = [v8path] + arguments
    print(f"Running: {os.path.basename(v8path)} {' '.join(arguments)}")

    env = dict(os.environ)
    if not _is_windows():
        # On Linux 1cv8 needs display; use xvfb-run if available
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            cmd = [xvfb, "--auto-servernum", "--server-args=-screen 0 1024x768x24"] + cmd

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    exit_code = result.returncode

    log_content = ""
    if os.path.isfile(out_file):
        try:
            with open(out_file, "r", encoding="utf-8-sig") as f:
                log_content = f.read().strip()
        except Exception:
            pass

    return exit_code, log_content


def extract_server_version(log_content):
    """Extract server version from version mismatch error log."""
    m = re.search(r'\([\d.]+ - ([\d.]+)\)', log_content)
    return m.group(1) if m else None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Build external data processor or report (EPF/ERF) from XML sources",
        allow_abbrev=False,
    )
    parser.add_argument("-V8Path", default="", help="Path to 1cv8 binary or its directory")
    parser.add_argument("-InfoBasePath", default="", help="Path to file infobase")
    parser.add_argument("-InfoBaseServer", default="", help="1C server (for server infobase)")
    parser.add_argument("-InfoBaseRef", default="", help="Infobase name on server")
    parser.add_argument("-UserName", default="", help="1C user name")
    parser.add_argument("-Password", default="", help="1C user password")
    parser.add_argument("-SourceFile", required=True, help="Path to root XML source file")
    parser.add_argument("-OutputFile", required=True, help="Path to output EPF/ERF file")
    args = parser.parse_args()

    # --- Resolve V8Path ---
    v8path, all_versions = resolve_v8path(args.V8Path)

    # --- Auto-create stub database if no connection specified ---
    auto_created_base = None
    if not args.InfoBasePath and (not args.InfoBaseServer or not args.InfoBaseRef):
        source_dir = os.path.dirname(os.path.abspath(args.SourceFile))
        auto_base_path = os.path.join(tempfile.gettempdir(), f"epf_stub_db_{random.randint(0, 999999)}")
        stub_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stub-db-create.py")
        print("No database specified. Creating temporary stub database...")
        result = subprocess.run(
            [sys.executable, stub_script, "-SourceDir", source_dir, "-V8Path", v8path, "-TempBasePath", auto_base_path],
            capture_output=False,
        )
        if result.returncode != 0:
            print("Error: failed to create stub database", file=sys.stderr)
            sys.exit(1)
        args.InfoBasePath = auto_base_path
        auto_created_base = auto_base_path

    # --- Validate source file ---
    if not os.path.isfile(args.SourceFile):
        print(f"Error: source file not found: {args.SourceFile}", file=sys.stderr)
        sys.exit(1)

    # --- Ensure output directory exists ---
    out_dir = os.path.dirname(args.OutputFile)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # --- Temp dir ---
    temp_dir = os.path.join(tempfile.gettempdir(), f"epf_build_{random.randint(0, 999999)}")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # --- Build arguments ---
        def make_args(v8):
            arguments = ["DESIGNER"]
            if args.InfoBaseServer and args.InfoBaseRef:
                arguments += ["/S", f"{args.InfoBaseServer}/{args.InfoBaseRef}"]
            else:
                arguments += ["/F", args.InfoBasePath]
            if args.UserName:
                arguments.append(f"/N{args.UserName}")
            if args.Password:
                arguments.append(f"/P{args.Password}")
            arguments += ["/LoadExternalDataProcessorOrReportFromFiles", args.SourceFile, args.OutputFile]
            out_file = os.path.join(temp_dir, "build_log.txt")
            arguments += ["/Out", out_file, "/DisableStartupDialogs"]
            return arguments, out_file

        arguments, out_file = make_args(v8path)
        exit_code, log_content = run_designer(v8path, arguments, out_file)

        # --- Version mismatch: retry with matching client ---
        if exit_code != 0 and log_content:
            server_ver = extract_server_version(log_content)
            if server_ver and server_ver in all_versions and all_versions[server_ver] != v8path:
                alt_v8 = all_versions[server_ver]
                print(f"Version mismatch: server={server_ver}. Retrying with {alt_v8}")
                # Remove old output file if exists
                if os.path.isfile(out_file):
                    os.unlink(out_file)
                exit_code, log_content = run_designer(alt_v8, arguments, out_file)
            elif server_ver and server_ver not in all_versions:
                installed = ", ".join(sorted(all_versions.keys()))
                print(f"Version mismatch: server needs {server_ver}, installed: {installed}", file=sys.stderr)
                print(f"Install 1C client version {server_ver} to build against this server.", file=sys.stderr)

        # --- Result ---
        if exit_code == 0:
            print(f"Build completed successfully: {args.OutputFile}")
        else:
            print(f"Error building (code: {exit_code})", file=sys.stderr)

        if log_content:
            print("--- Log ---")
            print(log_content)
            print("--- End ---")

        sys.exit(exit_code)

    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if auto_created_base and os.path.exists(auto_created_base):
            shutil.rmtree(auto_created_base, ignore_errors=True)


if __name__ == "__main__":
    main()

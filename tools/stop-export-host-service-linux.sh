#!/usr/bin/env bash
set -euo pipefail

for pid in $(pgrep -f 'python3 .*export-host-service.py --port 8082' || true); do
  [ -n "$pid" ] || continue
  cmdline="$(tr '\0' ' ' <"/proc/${pid}/cmdline" 2>/dev/null || true)"
  case "$cmdline" in
    *python3*"export-host-service.py --port 8082"*)
      kill "$pid" 2>/dev/null || true
      ;;
  esac
done

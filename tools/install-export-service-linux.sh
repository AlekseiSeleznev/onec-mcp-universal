#!/usr/bin/env bash
# Installs tools/export-host-service.py as a user-level systemd service so
# BSL export runs on the host (using the host's 1C software license) instead
# of inside the Docker container (which corrupts developer/community licenses
# via hardware-fingerprint mismatch).
#
# Runs as the current user. No sudo required. On desktop machines the
# service starts at user login (the normal path). For headless/server use
# enable lingering once manually:
#   sudo loginctl enable-linger $USER
#
# Safe to re-run — idempotent.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_PY="${REPO_ROOT}/tools/export-host-service.py"
STOP_STALE_SH="${REPO_ROOT}/tools/stop-export-host-service-linux.sh"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="${UNIT_DIR}/onec-export-service.service"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/onec-export"

if [ ! -f "$SERVICE_PY" ]; then
  echo "[!] ERROR: $SERVICE_PY not found." >&2
  exit 1
fi

if [ ! -f "$STOP_STALE_SH" ]; then
  echo "[!] ERROR: $STOP_STALE_SH not found." >&2
  exit 1
fi

# Detect latest available 1C platform version on the host
detect_v8() {
  local base="/opt/1cv8/x86_64"
  if [ ! -d "$base" ]; then
    echo ""
    return
  fi
  # newest first
  for d in $(ls -1d "${base}"/*/ 2>/dev/null | sort -rV); do
    d="${d%/}"
    if [ -x "${d}/1cv8" ]; then
      echo "$d"
      return
    fi
  done
}

V8_PATH="${V8_PATH:-$(detect_v8)}"
if [ -z "$V8_PATH" ]; then
  echo "[!] 1C platform not found under /opt/1cv8/x86_64/."
  echo "    Install the full 1C platform, then re-run this script."
  echo "    Skipping service install."
  exit 0
fi

mkdir -p "$UNIT_DIR" "$LOG_DIR"
chmod +x "$STOP_STALE_SH"

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=1C BSL export host service (onec-mcp-universal)
Documentation=https://github.com/AlekseiSeleznev/onec-mcp-universal
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
# 1cv8 DESIGNER needs an X display. Reuse the user's logged-in session;
# with 'loginctl enable-linger' the service runs even when not logged in
# (xvfb-run takes over if no real display is available).
Environment=DISPLAY=:0
Environment=XAUTHORITY=%h/.Xauthority
Environment=V8_PATH=${V8_PATH}
ExecStartPre=/usr/bin/bash ${STOP_STALE_SH}
ExecStart=/usr/bin/python3 ${SERVICE_PY} --port 8082
Restart=on-failure
RestartSec=5
StandardOutput=append:${LOG_DIR}/service.log
StandardError=append:${LOG_DIR}/service.log

[Install]
WantedBy=default.target
EOF

echo "[+] Wrote ${UNIT_FILE}"
echo "    V8_PATH=${V8_PATH}"
echo "    BSL_WORKSPACE=dynamic (.env / request-driven)"

# Reload + enable + start
if systemctl --user daemon-reload 2>/dev/null; then
  systemctl --user enable --now onec-export-service.service
  echo "[+] Enabled and started onec-export-service.service (user scope)."
else
  echo "[!] 'systemctl --user' unavailable — service file written but not started."
  echo "    Start manually with: systemctl --user enable --now onec-export-service"
fi

# Lingering is left to the operator. On a desktop the service starts at login
# (the normal path). On a headless/server machine enable it once:
#   sudo loginctl enable-linger $USER
if loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  echo "[i] Lingering is enabled — service will start at boot without login."
else
  echo "[i] Lingering is disabled — service will start when you log in."
  echo "    For headless/server use, enable with:  sudo loginctl enable-linger $USER"
fi

# Health check
sleep 1
if curl -s -m 3 http://localhost:8082/health >/dev/null 2>&1; then
  echo "[+] Health check: http://localhost:8082/health OK"
else
  echo "[!] Health check failed — see ${LOG_DIR}/service.log"
fi

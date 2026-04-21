#!/usr/bin/env bash
set -euo pipefail

# ── onec-mcp-universal setup ─────────────────────────────────────
# One-command setup: creates .env (with auto-detected 1C platform),
# creates empty volume placeholders, builds Docker images,
# starts all containers, and registers the MCP server in Codex.
# Works on Linux, macOS, and Windows (Git Bash / WSL).

cd "$(dirname "$0")"

DEFAULT_PORT=8080
NAME="onec-universal"
ENV_PORT_KEY="GW_PORT"
WITH_BSL_GRAPH=0

for arg in "$@"; do
  case "$arg" in
    --with-bsl-graph)
      WITH_BSL_GRAPH=1
      ;;
    -h|--help)
      cat <<'EOF'
Usage: ./setup.sh [--with-bsl-graph]

  --with-bsl-graph   Also build and start the optional local bsl-graph backend
EOF
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $arg" >&2
      echo "Run ./setup.sh --help for usage." >&2
      exit 1
      ;;
  esac
done

# ── Helpers ──────────────────────────────────────────────────────
env_val() { grep "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2-; }

# Append KEY=VAL to .env only if the key is not already present (uncommented).
ensure_env() {
  local key="$1" val="$2"
  if [ ! -f .env ]; then return 0; fi
  if grep -qE "^${key}=" .env; then return 0; fi
  echo "${key}=${val}" >> .env
  echo "[+] .env: set ${key}=${val}"
}

generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
    return
  fi
  if command -v python >/dev/null 2>&1; then
    python -c 'import secrets; print(secrets.token_hex(32))'
    return
  fi
  od -An -N 32 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n'
}

ensure_secret_env() {
  local key="$1"
  if [ ! -f .env ]; then return 0; fi
  if grep -qE "^${key}=" .env; then return 0; fi
  local secret
  secret="$(generate_secret)"
  echo "${key}=${secret}" >> .env
  echo "[+] .env: generated ${key}=<hidden>"
}

# Portable sed -i (macOS needs '' arg)
sed_inplace() {
  if [ "$OS" = "macos" ]; then
    sed -i '' "$@"
  else
    sed -i "$@"
  fi
}

set_env() {
  local key="$1" val="$2"
  if [ ! -f .env ]; then return 0; fi
  if grep -qE "^${key}=" .env; then
    sed_inplace "s|^${key}=.*|${key}=${val}|" .env
  else
    echo "${key}=${val}" >> .env
  fi
  echo "[+] .env: set ${key}=${val}"
}

set_env_if_missing_or_matching() {
  local key="$1" desired="$2"
  shift 2
  local current
  current="$(env_val "$key" .env 2>/dev/null || true)"
  if [ -z "${current:-}" ]; then
    set_env "$key" "$desired"
    return
  fi
  for candidate in "$@"; do
    if [ "$current" = "$candidate" ]; then
      set_env "$key" "$desired"
      return
    fi
  done
}

workspace_default() {
  if [ "$OS" = "windows" ] && command -v pwd >/dev/null 2>&1; then
    local native_pwd
    native_pwd="$(pwd -W 2>/dev/null || true)"
    if [ -n "${native_pwd:-}" ]; then
      native_pwd="${native_pwd//\\//}"
      printf '%s/bsl-projects' "${native_pwd%/}"
      return
    fi
  fi
  printf '%s/bsl-projects' "$PWD"
}

# ── Detect OS early (needed for error messages) ─────────────────
OS="linux"
case "$(uname -s)" in
  Darwin*)                OS="macos"   ;;
  MINGW*|MSYS*|CYGWIN*)  OS="windows" ;;
esac
echo "✓ OS: ${OS}"

# ── 1. Prerequisites ─────────────────────────────────────────────
if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git not found."
  if [ "$OS" = "windows" ]; then
    echo "       Install Git for Windows: https://gitforwindows.org/"
  elif [ "$OS" = "macos" ]; then
    echo "       Install via: xcode-select --install (or brew install git)"
  else
    echo "       Install via: sudo apt install -y git (or your distro's package manager)"
  fi
  exit 1
fi
echo "✓ git found"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker not found."
  if [ "$OS" = "windows" ]; then
    echo "       Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    echo "       Enable WSL2 backend in Settings → General"
  elif [ "$OS" = "macos" ]; then
    echo "       Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
  else
    echo "       Install via: curl -fsSL https://get.docker.com | sh"
    echo "       Then: sudo usermod -aG docker \$USER && newgrp docker"
  fi
  exit 1
fi
echo "✓ docker found"

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose V2 not found (need 'docker compose', not 'docker-compose')."
  echo "       Install: https://docs.docker.com/compose/install/"
  exit 1
fi
echo "✓ docker compose v2 found"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running."
  if [ "$OS" = "windows" ] || [ "$OS" = "macos" ]; then
    echo "       Start Docker Desktop from your taskbar or Applications."
  else
    echo "       Start it: sudo systemctl start docker"
    echo "       Enable auto-start: sudo systemctl enable docker"
  fi
  exit 1
fi
echo "✓ docker daemon is running"

if ! command -v codex >/dev/null 2>&1; then
  echo "[!] Codex CLI not found — MCP will not be registered automatically."
  echo "    Install Codex, then re-run ./setup.sh for automatic MCP registration."
fi

# Windows-only: check Python for export-host-service
if [ "$OS" = "windows" ]; then
  if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Python 3 not found — BSL export feature will not work."
    echo "    Install Python 3.10+: https://www.python.org/downloads/"
  else
    echo "✓ python found (needed for BSL export service)"
  fi
fi

# ── 2. OS-specific compose override ────────────────────────────
if [ "$OS" != "linux" ]; then
  if [ -f docker-compose.windows.yml ] && [ ! -f docker-compose.override.yml ]; then
    cp docker-compose.windows.yml docker-compose.override.yml
    echo "[+] Created docker-compose.override.yml for ${OS} (bridge network)"
  fi
fi

# ── 3. Create empty volume placeholder directories ──────────────
# These prevent Docker errors when host paths (1C platform, licenses, /home) don't exist.
mkdir -p data/empty-platform data/empty-licenses data/empty-home data/empty-root
echo "✓ Volume placeholder directories created"

# ── 4. Create .env ──────────────────────────────────────────────
PLATFORM_DETECTED=0
if [ ! -f .env ]; then
  cp .env.example .env

  # Auto-detect 1C platform path on Linux
  if [ "$OS" = "linux" ] && [ -d /opt/1cv8/x86_64 ]; then
    PLATFORM_DIR=$(ls -1d /opt/1cv8/x86_64/*/ 2>/dev/null | sort -V | tail -1 | sed 's:/$::' || true)
    if [ -n "${PLATFORM_DIR:-}" ] && [ -f "${PLATFORM_DIR}/1cv8" ]; then
      sed_inplace "s|^PLATFORM_PATH=.*|PLATFORM_PATH=${PLATFORM_DIR}|" .env
      sed_inplace "s|^# HOST_PLATFORM_PATH=.*|HOST_PLATFORM_PATH=/opt/1cv8|" .env
      echo "[+] Detected 1C platform: ${PLATFORM_DIR}"
      PLATFORM_DETECTED=1
    fi
  fi

  # Also mount /var/1C if it exists
  if [ "$OS" = "linux" ] && [ -d /var/1C ]; then
    sed_inplace "s|^# ONEC_LICENSES_PATH=.*|ONEC_LICENSES_PATH=/var/1C|" .env 2>/dev/null || \
      echo "ONEC_LICENSES_PATH=/var/1C" >> .env
  fi

  # Adjust export host URL. The gateway routes BSL exports to this URL
  # instead of running 1cv8 inside the container — avoids the 1C software
  # license fingerprint-mismatch problem (see README / AGENTS.md).
  if [ "$OS" = "windows" ] || [ "$OS" = "macos" ]; then
    sed_inplace 's|^EXPORT_HOST_URL=.*|EXPORT_HOST_URL=http://host.docker.internal:8082|' .env 2>/dev/null || \
      echo "EXPORT_HOST_URL=http://host.docker.internal:8082" >> .env
    sed_inplace 's|^DOCKER_CONTROL_URL=.*|DOCKER_CONTROL_URL=http://docker-control:8091|' .env 2>/dev/null || \
      echo "DOCKER_CONTROL_URL=http://docker-control:8091" >> .env
  else
    # Linux: gateway uses host networking, so localhost reaches the host service.
    sed_inplace 's|^EXPORT_HOST_URL=.*|EXPORT_HOST_URL=http://localhost:8082|' .env 2>/dev/null || \
      echo "EXPORT_HOST_URL=http://localhost:8082" >> .env
    sed_inplace 's|^DOCKER_CONTROL_URL=.*|DOCKER_CONTROL_URL=http://localhost:8091|' .env 2>/dev/null || \
      echo "DOCKER_CONTROL_URL=http://localhost:8091" >> .env
  fi

  echo "[+] Created .env from .env.example"
else
  echo "[i] .env already exists, keeping it"
  # Re-detect 1C for COMPOSE_PROFILES — also fill missing platform keys
  if [ "$OS" = "linux" ] && [ -d /opt/1cv8/x86_64 ]; then
    PLATFORM_DIR=$(ls -1d /opt/1cv8/x86_64/*/ 2>/dev/null | sort -V | tail -1 | sed 's:/$::' || true)
    if [ -n "${PLATFORM_DIR:-}" ] && [ -f "${PLATFORM_DIR}/1cv8" ]; then
      PLATFORM_DETECTED=1
      echo "[+] Detected 1C platform: ${PLATFORM_DIR}"
      # Idempotent: update PLATFORM_PATH if present, add if missing
      if grep -q "^PLATFORM_PATH=" .env; then
        sed_inplace "s|^PLATFORM_PATH=.*|PLATFORM_PATH=${PLATFORM_DIR}|" .env
      else
        ensure_env PLATFORM_PATH "${PLATFORM_DIR}"
      fi
      # HOST_PLATFORM_PATH: add if missing (needed for container bind-mount)
      ensure_env HOST_PLATFORM_PATH "/opt/1cv8"
    fi
  fi
fi

# ── Dashboard folder browser: host filesystem mounts ──────────
# Idempotent — runs on every setup.sh invocation so a pre-existing .env
# missing these keys gets fixed up without manual editing.
if [ "$OS" = "linux" ]; then
  ensure_env HOSTFS_HOME "/home"
  ensure_env HOST_ROOT "/"
  ensure_env HOST_ROOT_PREFIX ""
  # Route BSL export through the host service so 1cv8 uses the host's real
  # license instead of running inside the container (see README / AGENTS.md).
  ensure_env EXPORT_HOST_URL "http://localhost:8082"
  ensure_env DOCKER_CONTROL_URL "http://localhost:8091"
  set_env_if_missing_or_matching DOCKER_CONTROL_URL "http://localhost:8091" \
    "http://docker-control:8091" "http://host.docker.internal:8091"
elif [ "$OS" = "windows" ] || [ "$OS" = "macos" ]; then
  # On Windows/macOS, Docker Desktop cannot bind-mount the real root. Mount the
  # user profile instead and tell the gateway to translate host paths through it.
  _home_native="${USERPROFILE:-$HOME}"
  # Git Bash normalizes backslashes; forward-slash form works in both .env and compose.
  _home_native="${_home_native//\\//}"
  # Strip trailing slash
  _home_native="${_home_native%/}"
  if [ -n "$_home_native" ]; then
    ensure_env HOSTFS_HOME "$_home_native"
    ensure_env HOST_ROOT "$_home_native"
    ensure_env HOST_ROOT_PREFIX "$_home_native"
  fi
  ensure_env EXPORT_HOST_URL "http://host.docker.internal:8082"
  ensure_env DOCKER_CONTROL_URL "http://docker-control:8091"
  set_env_if_missing_or_matching DOCKER_CONTROL_URL "http://docker-control:8091" \
    "http://host.docker.internal:8091" "http://localhost:8091"
fi

ensure_env TOOLKIT_ALLOW_DANGEROUS_WITH_APPROVAL "true"
ensure_env GATEWAY_RATE_LIMIT_ENABLED "true"
ensure_env GATEWAY_RATE_LIMIT_READ_RPM "120"
ensure_env GATEWAY_RATE_LIMIT_MUTATING_RPM "30"
ensure_secret_env DOCKER_CONTROL_TOKEN
ensure_secret_env ANONYMIZER_SALT

# ── Deterministic BSL workspace defaults ───────────────────────
WORKSPACE_DEFAULT="$(workspace_default)"
CURRENT_BSL_WORKSPACE="$(env_val "BSL_WORKSPACE" .env 2>/dev/null || true)"
CURRENT_BSL_HOST_WORKSPACE="$(env_val "BSL_HOST_WORKSPACE" .env 2>/dev/null || true)"

case "$CURRENT_BSL_WORKSPACE" in
  ""|"/home/user/1c-bsl-projects"|"/abs/path/to/bsl-projects"|"./bsl-projects"|"bsl-projects")
    set_env BSL_WORKSPACE "$WORKSPACE_DEFAULT"
    ;;
esac

case "$CURRENT_BSL_HOST_WORKSPACE" in
  ""|"/home/user/bsl-projects"|"/abs/path/to/bsl-projects"|"./bsl-projects"|"bsl-projects")
    set_env BSL_HOST_WORKSPACE "$(env_val "BSL_WORKSPACE" .env 2>/dev/null || printf '%s' "$WORKSPACE_DEFAULT")"
    ;;
esac

mkdir -p "$(env_val "BSL_WORKSPACE" .env 2>/dev/null || printf '%s' "$WORKSPACE_DEFAULT")"
echo "✓ BSL workspace directory is ready"

PORT=$(env_val "$ENV_PORT_KEY" .env 2>/dev/null || true)
PORT=${PORT:-$DEFAULT_PORT}
ENABLED_BACKENDS=$(env_val "ENABLED_BACKENDS" .env 2>/dev/null || true)
ENABLED_BACKENDS=${ENABLED_BACKENDS:-onec-toolkit,platform-context,bsl-lsp-bridge}

# ── Port availability check (portable: works on Linux, macOS, Windows Git Bash) ──
_port_in_use=0
if command -v ss >/dev/null 2>&1; then
  ss -tlnH 2>/dev/null | grep -q ":${PORT} " && _port_in_use=1
elif command -v netstat >/dev/null 2>&1; then
  netstat -tln 2>/dev/null | grep -q ":${PORT} " && _port_in_use=1
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "import socket; s=socket.socket(); s.settimeout(1); exit(0 if s.connect_ex(('127.0.0.1',${PORT}))==0 else 1)" 2>/dev/null && _port_in_use=1
fi
if [ "$_port_in_use" -eq 1 ]; then
  EXISTING_GW=$(docker inspect --format='{{.State.Status}}' onec-mcp-gw 2>/dev/null || echo "")
  if [ "$EXISTING_GW" != "running" ]; then
    echo "[!] WARNING: Port ${PORT} appears to be in use by another process."
    echo "    Change GW_PORT in .env to use a different port, then re-run."
  fi
fi

# ── 5. Build local LSP image when enabled ─────────────────────
if echo "$ENABLED_BACKENDS" | tr ',' '\n' | grep -qx "bsl-lsp-bridge"; then
  echo "[*] Building local LSP image (Java 21 compatible)..."
  ./tools/build-lsp-image.sh
fi

# ── 6. Build & start ───────────────────────────────────────────
COMPOSE_PROFILES_LIST=()

# Enable platform-context profile if 1C platform was detected
if [ "$PLATFORM_DETECTED" -eq 1 ]; then
  COMPOSE_PROFILES_LIST+=(platform-context)
  echo "[*] platform-context profile enabled (1C detected)"
  # Update ENABLED_BACKENDS in .env to include platform-context
  if grep -q "^ENABLED_BACKENDS=" .env 2>/dev/null; then
    sed_inplace "s|^ENABLED_BACKENDS=.*|ENABLED_BACKENDS=onec-toolkit,platform-context,bsl-lsp-bridge|" .env
  else
    echo "ENABLED_BACKENDS=onec-toolkit,platform-context,bsl-lsp-bridge" >> .env
  fi
else
  echo "[*] 1C platform not detected — platform-context profile disabled"
  echo "    To enable platform-context later: install 1C platform, then re-run setup.sh"
fi

if [ "$WITH_BSL_GRAPH" -eq 1 ]; then
  COMPOSE_PROFILES_LIST+=(bsl-graph)
  echo "[*] bsl-graph profile enabled"
fi

if [ "${#COMPOSE_PROFILES_LIST[@]}" -gt 0 ]; then
  export COMPOSE_PROFILES
  COMPOSE_PROFILES="$(IFS=,; echo "${COMPOSE_PROFILES_LIST[*]}")"
  echo "[*] Building and starting containers with profiles: ${COMPOSE_PROFILES}"
else
  echo "[*] Building and starting core containers..."
fi

docker compose up -d --build --remove-orphans

# ── 7. Health check (curl → wget → python3 fallback) ───────────
echo "[*] Waiting for health (backends need ~30-60s)..."
HEALTHY=0
LOCAL_HEALTH_HOST="127.0.0.1"
_check_health() {
  if command -v curl >/dev/null 2>&1; then
    curl --max-time 5 -sf "http://${LOCAL_HEALTH_HOST}:${PORT}/health" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "http://${LOCAL_HEALTH_HOST}:${PORT}/health" >/dev/null 2>&1
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import urllib.request; urllib.request.urlopen('http://${LOCAL_HEALTH_HOST}:${PORT}/health', timeout=5)" 2>/dev/null
  else
    return 1
  fi
}
for i in $(seq 1 120); do
  if _check_health; then
    HEALTHY=1; break
  fi
  sleep 1
done

if [ "$HEALTHY" -eq 0 ]; then
  STATUS=$(docker inspect --format='{{.State.Health.Status}}' onec-mcp-gw 2>/dev/null || echo "unknown")
  if [ "$STATUS" = "healthy" ]; then HEALTHY=1; fi
fi

if [ "$HEALTHY" -eq 1 ]; then
  echo "[+] Gateway is healthy on port ${PORT}"
else
  echo "[!] Gateway not healthy after 120s. Check: docker compose logs"
  exit 1
fi

_check_docker_control_health() {
  if [ "$OS" = "linux" ]; then
    if command -v curl >/dev/null 2>&1; then
      curl --max-time 5 -sf "http://${LOCAL_HEALTH_HOST}:8091/health" >/dev/null 2>&1
    elif command -v wget >/dev/null 2>&1; then
      wget -qO- "http://${LOCAL_HEALTH_HOST}:8091/health" >/dev/null 2>&1
    elif command -v python3 >/dev/null 2>&1; then
      python3 -c "import urllib.request; urllib.request.urlopen('http://${LOCAL_HEALTH_HOST}:8091/health', timeout=5)" 2>/dev/null
    else
      return 1
    fi
    return $?
  fi

  docker exec onec-mcp-gw python -c "import urllib.request; urllib.request.urlopen('http://docker-control:8091/health', timeout=5)" >/dev/null 2>&1
}

if _check_docker_control_health; then
  if [ "$OS" = "linux" ]; then
    echo "[+] docker-control is reachable: http://${LOCAL_HEALTH_HOST}:8091/health"
  else
    echo "[+] docker-control is reachable via onec-mcp-gw: http://docker-control:8091/health"
  fi
else
  if [ "$OS" = "linux" ]; then
    echo "[!] docker-control is not reachable at http://${LOCAL_HEALTH_HOST}:8091/health"
  else
    echo "[!] docker-control is not reachable via onec-mcp-gw at http://docker-control:8091/health"
  fi
  exit 1
fi

if [ "$WITH_BSL_GRAPH" -eq 1 ]; then
  echo "[*] Waiting for bsl-graph health..."
  GRAPH_HEALTHY=0
  for i in $(seq 1 60); do
    if command -v curl >/dev/null 2>&1; then
      if curl --max-time 5 -sf "http://${LOCAL_HEALTH_HOST}:8888/health" >/dev/null 2>&1; then
        GRAPH_HEALTHY=1
        break
      fi
    elif command -v wget >/dev/null 2>&1; then
      if wget -qO- "http://${LOCAL_HEALTH_HOST}:8888/health" >/dev/null 2>&1; then
        GRAPH_HEALTHY=1
        break
      fi
    fi
    sleep 1
  done

  if [ "$GRAPH_HEALTHY" -eq 1 ]; then
    echo "[+] bsl-graph is reachable: http://${LOCAL_HEALTH_HOST}:8888/health"
  else
    echo "[!] bsl-graph did not become healthy after 60s"
    exit 1
  fi
fi

_check_export_health() {
  if command -v curl >/dev/null 2>&1; then
    curl --max-time 5 -sf "http://${LOCAL_HEALTH_HOST}:8082/health" >/dev/null 2>&1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "http://${LOCAL_HEALTH_HOST}:8082/health" >/dev/null 2>&1
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import urllib.request; urllib.request.urlopen('http://${LOCAL_HEALTH_HOST}:8082/health', timeout=5)" 2>/dev/null
  elif command -v python >/dev/null 2>&1; then
    python -c "import urllib.request; urllib.request.urlopen('http://${LOCAL_HEALTH_HOST}:8082/health', timeout=5)" 2>/dev/null
  else
    return 1
  fi
}

# ── 8. Register in Codex / print generic MCP instructions ──────
if command -v codex >/dev/null 2>&1; then
  codex mcp remove "$NAME" >/dev/null 2>&1 || true
  codex mcp add "$NAME" --url "http://localhost:${PORT}/mcp"
  echo "[+] Registered '${NAME}' in Codex"
  echo ""
  echo "[*] Current MCP servers:"
  codex mcp list 2>/dev/null || true
  echo ""
  echo "Done! Run 'codex mcp list' to verify."
else
  echo ""
  echo "[i] Codex CLI not found. Register this MCP endpoint manually in your client:"
  echo "    http://localhost:${PORT}/mcp"
  echo "    For Codex: codex mcp add ${NAME} --url http://localhost:${PORT}/mcp"
fi

# ── 9. Install skills for Codex / compatible local skill runners ──
if [ -d "skills" ]; then
  if [ "$OS" = "windows" ]; then
    if command -v powershell.exe >/dev/null 2>&1; then
      PS_SCRIPT="$(pwd)/install-skills.ps1"
      PS_SCRIPT_WIN=$(cygpath -w "$PS_SCRIPT" 2>/dev/null || echo "$PS_SCRIPT")
      powershell.exe -ExecutionPolicy Bypass -File "$PS_SCRIPT_WIN"
    else
      echo "[!] PowerShell not found — run install-skills.ps1 manually to install skills"
    fi
  else
    bash install-skills.sh
  fi
fi

# ── 10. Install export-host-service (host-side BSL export, protects license) ───
# Running 1cv8 DESIGNER inside the container copies license files and can invalidate
# 1C software (developer/community) licenses via hardware-fingerprint mismatch.
# The host service runs 1cv8 on the host directly and uses the real license.
if [ "$OS" = "windows" ]; then
  if [ -f tools/install-export-service-windows.ps1 ] && command -v powershell.exe >/dev/null 2>&1; then
    if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
      echo "[*] Installing BSL export service as Windows Scheduled Task (auto-start at logon)..."
      PS_SCRIPT="$(pwd)/tools/install-export-service-windows.ps1"
      PS_SCRIPT_WIN=$(cygpath -w "$PS_SCRIPT" 2>/dev/null || echo "$PS_SCRIPT")
      powershell.exe -ExecutionPolicy Bypass -File "$PS_SCRIPT_WIN" || {
        echo "[!] Could not register Scheduled Task. To install manually:"
        echo "    powershell -ExecutionPolicy Bypass -File tools\\install-export-service-windows.ps1"
      }
    else
      echo "[!] Python not found — BSL export service NOT installed."
      echo "    Install Python 3.10+ and re-run setup.sh."
    fi
  fi
elif [ "$OS" = "linux" ]; then
  # Linux: install as user-level systemd service. Requires systemctl --user.
  if [ -f tools/install-export-service-linux.sh ]; then
    if [ -d /opt/1cv8/x86_64 ] && command -v systemctl >/dev/null 2>&1; then
      echo "[*] Installing BSL export host service (user systemd unit)..."
      bash tools/install-export-service-linux.sh || \
        echo "[!] Could not install host service — see error above."
    else
      echo "[i] Skipping host export service: 1C platform not installed, or systemd unavailable."
      echo "    When installed, run: bash tools/install-export-service-linux.sh"
    fi
  fi
fi

if _check_export_health; then
  echo "[+] export-host-service is reachable: http://${LOCAL_HEALTH_HOST}:8082/health"
else
  echo "[!] export-host-service is not reachable at http://${LOCAL_HEALTH_HOST}:8082/health"
  if [ "$OS" = "windows" ]; then
    echo "    Re-run: powershell -ExecutionPolicy Bypass -File tools\\install-export-service-windows.ps1"
  elif [ "$OS" = "linux" ]; then
    echo "    Re-run: bash tools/install-export-service-linux.sh"
  else
    echo "    Start manually: python3 tools/export-host-service.py --port 8082"
  fi
fi

echo ""
echo "Dashboard: http://localhost:${PORT}/dashboard"
echo ""
echo "Containers start automatically after system reboot via Docker (restart: always)."
echo "MCP endpoint: http://localhost:${PORT}/mcp"
if [ "$WITH_BSL_GRAPH" -eq 1 ]; then
  echo "BSL graph: http://localhost:8888/health"
else
  echo "Optional bsl-graph: docker compose --profile bsl-graph up -d --build"
fi
if [ "$OS" = "windows" ]; then
  echo ""
  echo "Windows note: Docker Desktop must be set to start at login (default)."
  echo "BSL export service is registered as Scheduled Task to auto-start at login."
fi

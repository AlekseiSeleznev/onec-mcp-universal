#!/usr/bin/env bash
set -u

cd "$(dirname "$0")"

DEFAULT_PORT=8080
FAILS=0
WARNS=0
PASSES=0
LOCAL_HEALTH_HOST="127.0.0.1"
OS="linux"
case "$(uname -s)" in
  Darwin*)                OS="macos"   ;;
  MINGW*|MSYS*|CYGWIN*)  OS="windows" ;;
esac

pass() { echo "[PASS] $*"; PASSES=$((PASSES + 1)); }
warn() { echo "[WARN] $*"; WARNS=$((WARNS + 1)); }
fail() { echo "[FAIL] $*"; FAILS=$((FAILS + 1)); }

env_val() {
  local key="$1" file="$2"
  [ -f "$file" ] || return 0
  awk -F= -v k="$key" '
    /^[[:space:]]*#/ { next }
    $1 == k { sub(/^[^=]*=/, "", $0); print $0; exit }
  ' "$file"
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl --max-time 5 -sf "$url" >/dev/null 2>&1
    return $?
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$url" >/dev/null 2>&1
    return $?
  fi
  return 1
}

http_status() {
  local url="$1" token="${2:-}"
  if command -v curl >/dev/null 2>&1; then
    local args=(--max-time 5 -s -o /dev/null -w '%{http_code}')
    if [ -n "$token" ]; then
      args+=(-H "Authorization: Bearer ${token}")
    fi
    curl "${args[@]}" "$url" 2>/dev/null || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    VERIFY_STATUS_URL="$url" VERIFY_STATUS_TOKEN="$token" python3 - <<'PY'
import sys, urllib.request, urllib.error
import os
url = os.environ.get("VERIFY_STATUS_URL", "")
token = os.environ.get("VERIFY_STATUS_TOKEN", "")
headers = {}
if token:
    headers["Authorization"] = f"Bearer {token}"
request = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        print(response.status)
except urllib.error.HTTPError as exc:
    print(exc.code)
except Exception:
    print("")
PY
    return 0
  fi
  echo ""
}

echo "== onec-mcp-universal verify =="

if [ ! -f ".env" ]; then
  warn ".env not found; using defaults"
fi

GW_PORT="$(env_val GW_PORT .env)"
GW_PORT="${GW_PORT:-$DEFAULT_PORT}"
ENABLED_BACKENDS="$(env_val ENABLED_BACKENDS .env)"
ENABLED_BACKENDS="${ENABLED_BACKENDS:-onec-toolkit,platform-context,bsl-lsp-bridge}"
DOCKER_CONTROL_TOKEN="$(env_val DOCKER_CONTROL_TOKEN .env)"
ANONYMIZER_SALT="$(env_val ANONYMIZER_SALT .env)"

if command -v docker >/dev/null 2>&1; then
  pass "docker command found"
else
  fail "docker command not found"
fi

if docker info >/dev/null 2>&1; then
  pass "docker daemon is running"
else
  fail "docker daemon is not running"
fi

GW_HEALTH_URL="http://${LOCAL_HEALTH_HOST}:${GW_PORT}/health"
if http_ok "$GW_HEALTH_URL"; then
  HEALTH_BODY="$(curl -s "$GW_HEALTH_URL" 2>/dev/null || true)"
  if echo "$HEALTH_BODY" | grep -q '"status":"ok"'; then
    pass "gateway health endpoint is OK (${GW_HEALTH_URL})"
  else
    warn "gateway health endpoint is reachable but response is unexpected"
  fi
else
  fail "gateway health endpoint is unreachable (${GW_HEALTH_URL})"
fi

if docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q '^onec-mcp-gw .*healthy'; then
  pass "container onec-mcp-gw is running and healthy"
elif docker ps --format '{{.Names}} {{.Status}}' 2>/dev/null | grep -q '^onec-mcp-gw '; then
  warn "container onec-mcp-gw is running but health is not healthy yet"
else
  fail "container onec-mcp-gw is not running"
fi

docker_control_health_ok() {
  if [ "$OS" = "linux" ]; then
    http_ok "http://${LOCAL_HEALTH_HOST}:8091/health"
    return $?
  fi
  docker exec onec-mcp-gw python -c "import http.client, sys; conn=http.client.HTTPConnection('docker-control', 8091, timeout=5); conn.request('GET', '/health'); resp=conn.getresponse(); sys.exit(0 if resp.status == 200 else 1)" >/dev/null 2>&1
}

docker_control_guard_status() {
  if [ "$OS" = "linux" ]; then
    http_status "http://${LOCAL_HEALTH_HOST}:8091/api/docker/system"
    return 0
  fi
  docker exec onec-mcp-gw python -c "import http.client; conn=http.client.HTTPConnection('docker-control', 8091, timeout=5); conn.request('GET', '/api/docker/system'); resp=conn.getresponse(); print(resp.status)" 2>/dev/null || true
}

if docker_control_health_ok; then
  if [ "$OS" = "linux" ]; then
    pass "docker-control is reachable (http://${LOCAL_HEALTH_HOST}:8091/health)"
  else
    pass "docker-control is reachable via onec-mcp-gw (http://docker-control:8091/health)"
  fi
else
  if [ "$OS" = "linux" ]; then
    fail "docker-control is unreachable (http://${LOCAL_HEALTH_HOST}:8091/health)"
  else
    fail "docker-control is unreachable via onec-mcp-gw (http://docker-control:8091/health)"
  fi
fi

if [ -n "${DOCKER_CONTROL_TOKEN:-}" ]; then
  pass "DOCKER_CONTROL_TOKEN is configured"
else
  fail "DOCKER_CONTROL_TOKEN is missing in .env"
fi

if [ -n "${ANONYMIZER_SALT:-}" ]; then
  pass "ANONYMIZER_SALT is configured"
else
  fail "ANONYMIZER_SALT is missing in .env"
fi

DOCKER_CONTROL_GUARD_STATUS="$(docker_control_guard_status)"
if [ "$DOCKER_CONTROL_GUARD_STATUS" = "401" ]; then
  pass "docker-control protected API rejects unauthenticated requests with 401"
else
  fail "docker-control protected API expected 401 without token, got '${DOCKER_CONTROL_GUARD_STATUS:-empty}'"
fi

if http_ok "http://${LOCAL_HEALTH_HOST}:8082/health"; then
  pass "export-host-service is reachable (http://${LOCAL_HEALTH_HOST}:8082/health)"
else
  fail "export-host-service is unreachable (http://${LOCAL_HEALTH_HOST}:8082/health)"
fi

if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx 'onec-bsl-graph'; then
  if http_ok "http://${LOCAL_HEALTH_HOST}:8888/health"; then
    pass "bsl-graph is reachable (http://${LOCAL_HEALTH_HOST}:8888/health)"
  else
    fail "bsl-graph container is running but health endpoint is unreachable"
  fi
else
  warn "bsl-graph profile is not running (optional)"
fi

if echo "$ENABLED_BACKENDS" | tr ',' '\n' | grep -qx 'onec-toolkit'; then
  if docker ps --format '{{.Names}}' | grep -qx 'onec-mcp-toolkit'; then
    pass "onec-toolkit backend container is running"
  else
    fail "onec-toolkit backend is enabled but onec-mcp-toolkit container is not running"
  fi
fi

if echo "$ENABLED_BACKENDS" | tr ',' '\n' | grep -qx 'platform-context'; then
  if docker ps --format '{{.Names}}' | grep -qx 'onec-mcp-platform'; then
    pass "platform-context backend container is running"
  else
    fail "platform-context backend is enabled but onec-mcp-platform container is not running"
  fi
fi

if echo "$ENABLED_BACKENDS" | tr ',' '\n' | grep -qx 'bsl-lsp-bridge'; then
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q '^mcp-lsp-bridge-bsl:'; then
    pass "bsl-lsp-bridge image is present"
  else
    warn "bsl-lsp-bridge is enabled, but image mcp-lsp-bridge-bsl is missing"
  fi
fi

if command -v codex >/dev/null 2>&1; then
  if codex mcp list 2>/dev/null | grep -q "onec-universal"; then
    pass "Codex MCP registration 'onec-universal' found"
  else
    warn "Codex CLI found, but MCP registration 'onec-universal' not found"
  fi
else
  warn "Codex CLI is not installed; MCP registration check skipped"
fi

echo
echo "Summary: PASS=${PASSES}, WARN=${WARNS}, FAIL=${FAILS}"
if [ "$FAILS" -gt 0 ]; then
  exit 1
fi
exit 0

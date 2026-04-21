#!/bin/bash
# onec-mcp-universal — host-mode starter (when Docker Hub is unavailable)
# Runs the gateway directly on the host Python while backends run as Docker containers.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── start backends ─────────────────────────────────────────────────────────────
start_container() {
  local name=$1; shift
  if docker ps -q --filter "name=^${name}$" | grep -q .; then
    echo "[${name}] already running"
  else
    echo "[${name}] starting..."
    docker start "${name}" 2>/dev/null || docker run -d --name "${name}" "$@"
  fi
}

start_container onec-mcp-toolkit \
  -p 6003:6003 \
  -e PORT=6003 -e TIMEOUT=180 -e RESPONSE_FORMAT=json -e ALLOW_DANGEROUS_WITH_APPROVAL=true \
  roctup/1c-mcp-toolkit-proxy:latest

start_container onec-mcp-platform \
  -p 8081:8080 \
  -v /opt/1cv8:/opt/1cv8:ro \
  ghcr.io/alkoleft/mcp-bsl-platform-context:latest \
  java -jar /app/mcp-bsl-context.jar --mode sse \
    --platform-path "${PLATFORM_PATH:-/opt/1cv8/x86_64/8.3.27.2074}" --port 8080

# wait for onec-toolkit
echo "Waiting for onec-toolkit..."
for i in $(seq 1 20); do
  curl -sf http://localhost:6003/health > /dev/null 2>&1 && break || sleep 2
done

# ── start gateway ──────────────────────────────────────────────────────────────
echo "Starting gateway on :8080..."
cd "${SCRIPT_DIR}/gateway"
exec env \
  ONEC_TOOLKIT_URL=http://localhost:6003/mcp \
  PLATFORM_CONTEXT_URL=http://localhost:8081/sse \
  LOG_LEVEL="${LOG_LEVEL:-INFO}" \
  ENABLED_BACKENDS="${ENABLED_BACKENDS:-onec-toolkit,platform-context,bsl-lsp-bridge}" \
  python3 -m gateway

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

IMAGE_TAG="${LSP_IMAGE_TAG:-mcp-lsp-bridge-bsl:latest}"
MCP_LSP_BRIDGE_REPO="${MCP_LSP_BRIDGE_REPO:-https://github.com/1cvibe/mcp-bsl-lsp-bridge.git}"
MCP_LSP_BRIDGE_REF="${BSL_LSP_BRIDGE_REF:-2b9ff1b823b679209b215e57bf5d7a47d4447a89}"
BSL_LS_VERSION="${BSL_LS_VERSION:-0.29.0}"

printf '[*] Building %s from %s@%s with BSL LS %s\n' \
  "$IMAGE_TAG" "$MCP_LSP_BRIDGE_REPO" "$MCP_LSP_BRIDGE_REF" "$BSL_LS_VERSION"

docker build \
  -t "$IMAGE_TAG" \
  --build-arg MCP_LSP_BRIDGE_REPO="$MCP_LSP_BRIDGE_REPO" \
  --build-arg MCP_LSP_BRIDGE_REF="$MCP_LSP_BRIDGE_REF" \
  --build-arg BSL_LS_VERSION="$BSL_LS_VERSION" \
  -f docker/lsp-bridge/Dockerfile \
  docker/lsp-bridge

printf '[+] Built %s\n' "$IMAGE_TAG"

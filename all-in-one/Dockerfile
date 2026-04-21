# ─── Stage 1: BSL Language Server components ──────────────────────────────────
# Build the local base image first:
#   ./tools/build-lsp-image.sh
FROM mcp-lsp-bridge-bsl:latest AS lsp

# ─── Stage 2: platform-context JAR ────────────────────────────────────────────
FROM ghcr.io/alkoleft/mcp-bsl-platform-context:latest AS platform

# ─── Final: base on onec-toolkit (Python 3.12, Debian 13) ────────────────────
FROM roctup/1c-mcp-toolkit-proxy:latest

# ── Java runtime (from LSP image) ─────────────────────────────────────────────
COPY --from=lsp /opt/java /opt/java
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=$PATH:/opt/java/openjdk/bin

# ── BSL Language Server + bridges (from LSP image) ────────────────────────────
COPY --from=lsp /opt/bsl-ls /opt/bsl-ls
COPY --from=lsp /usr/bin/lsp-session-manager /usr/bin/lsp-session-manager
COPY --from=lsp /usr/bin/mcp-lsp-bridge /usr/bin/mcp-lsp-bridge
COPY --from=lsp /etc/mcp-lsp-bridge /etc/mcp-lsp-bridge

# ── platform-context (from platform image) ────────────────────────────────────
COPY --from=platform /app/mcp-bsl-context.jar /opt/platform/mcp-bsl-context.jar

# ── Kerberos libs for ibcmd (export_bsl_sources tool) ────────────────────────
COPY all-in-one/libs/ /lib/x86_64-linux-gnu/

# ── Gateway Python code ────────────────────────────────────────────────────────
COPY gateway/requirements.txt /opt/gateway/requirements.txt
RUN pip install --no-cache-dir -r /opt/gateway/requirements.txt
COPY gateway/gateway /opt/gateway/gateway

# ── Process manager ───────────────────────────────────────────────────────────
COPY all-in-one/entrypoint.py /opt/entrypoint.py

# Ports:
#   8080 — MCP gateway (Codex / any MCP client connects here)
#   6003 — onec-toolkit HTTP (1C app server connects here to post results)
EXPOSE 8080 6003

HEALTHCHECK --interval=20s --timeout=5s --retries=5 --start-period=60s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=4)" || exit 1

CMD ["python3", "/opt/entrypoint.py"]

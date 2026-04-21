FROM golang:1.24.2-bookworm AS build

ARG MCP_LSP_BRIDGE_REPO=https://github.com/1cvibe/mcp-bsl-lsp-bridge.git
ARG MCP_LSP_BRIDGE_REF=2b9ff1b823b679209b215e57bf5d7a47d4447a89

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --filter=blob:none "$MCP_LSP_BRIDGE_REPO" /src \
  && git checkout "$MCP_LSP_BRIDGE_REF"

ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN go mod download
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /out/mcp-lsp-bridge .
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH go build -o /out/lsp-session-manager ./cmd/lsp-session-manager

FROM debian:bookworm-slim AS bsl-ls-downloader
RUN apt-get update \
  && apt-get install -y --no-install-recommends wget ca-certificates \
  && rm -rf /var/lib/apt/lists/*

ARG BSL_LS_VERSION=0.29.0
RUN mkdir -p /opt/bsl-ls \
  && BSL_LS_URL="https://github.com/1c-syntax/bsl-language-server/releases/download/v${BSL_LS_VERSION}/bsl-language-server-${BSL_LS_VERSION}-exec.jar" \
  && echo "Downloading BSL LS from: $BSL_LS_URL" \
  && wget -q -O /opt/bsl-ls/bsl-language-server.jar "$BSL_LS_URL"

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update \
  && apt-get install -y --no-install-recommends xz-utils ca-certificates procps netcat-openbsd locales \
  && rm -rf /var/lib/apt/lists/* \
  && sed -i '/ru_RU.UTF-8/s/^# //g' /etc/locale.gen \
  && sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen \
  && locale-gen

ARG S6_OVERLAY_VERSION=3.1.6.2
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz /tmp
ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz /tmp
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
  && tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz \
  && rm /tmp/s6-overlay-*.tar.xz

RUN useradd -m -s /bin/sh user
RUN mkdir -p /opt/bsl-ls
COPY --from=bsl-ls-downloader /opt/bsl-ls/bsl-language-server.jar /opt/bsl-ls/bsl-language-server.jar
RUN chown -R user:user /opt/bsl-ls

COPY --from=build /out/mcp-lsp-bridge /usr/bin/mcp-lsp-bridge
COPY --from=build /out/lsp-session-manager /usr/bin/lsp-session-manager
RUN java -jar /opt/bsl-ls/bsl-language-server.jar --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' > /opt/bsl-ls/VERSION || echo "unknown" > /opt/bsl-ls/VERSION

RUN mkdir -p /home/user/.config/mcp-lsp-bridge /home/user/.local/share/mcp-lsp-bridge/logs \
  && chown -R user:user /home/user/.config /home/user/.local

COPY lsp_config.json /home/user/.config/mcp-lsp-bridge/lsp_config.json
COPY bsl-ls.json /home/user/.config/mcp-lsp-bridge/bsl-ls.json
RUN mkdir -p /etc/mcp-lsp-bridge
COPY lsp_config.json /etc/mcp-lsp-bridge/lsp_config.json
COPY bsl-ls.json /etc/mcp-lsp-bridge/bsl-ls.json

COPY s6-rc.d/ /etc/s6-overlay/s6-rc.d/
RUN find /etc/s6-overlay/s6-rc.d -type f -exec sed -i 's/\r$//' {} \; \
  && find /etc/s6-overlay/s6-rc.d -name "run" -exec chmod +x {} \; \
  && find /etc/s6-overlay/s6-rc.d -name "finish" -exec chmod +x {} \;

ENV S6_KEEP_ENV=1
ENV S6_BEHAVIOUR_IF_STAGE2_FAILS=2
ENV S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0
ENV LANG=ru_RU.UTF-8
ENV LANGUAGE=ru_RU:ru
ENV LC_ALL=ru_RU.UTF-8

WORKDIR /home/user
ENTRYPOINT ["/init"]
CMD ["sleep", "infinity"]

FROM python:3.12-slim

# docker CLI for docker exec (BSL LSP backend)
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# ibcmd runtime dependencies (1C platform shared libs for Linux)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgssapi-krb5-2 \
        libssl3 \
        libcurl4 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ ./gateway/
COPY resources/ ./resources/

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "gateway"]

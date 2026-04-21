FROM python:3.12-slim

# 1C platform runtime deps + GUI libs for headless 1cv8 DESIGNER BSL export
RUN apt-get update && apt-get install -y --no-install-recommends \
        gosu \
        libgssapi-krb5-2 \
        libssl3 \
        libcurl4 \
        xvfb \
        xauth \
        libcups2 \
        libgtk-3-0 \
        libglu1-mesa \
        libwebkit2gtk-4.1-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway/ ./gateway/
COPY resources/ ./resources/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && useradd --create-home --uid 10001 --shell /bin/sh app \
    && chown -R app:app /app

ENV PYTHONUNBUFFERED=1 \
    HOME=/home/app

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["/usr/local/bin/entrypoint.sh"]

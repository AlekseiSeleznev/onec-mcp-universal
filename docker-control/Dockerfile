FROM python:3.12-slim

COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py /app/server.py

ENV PYTHONUNBUFFERED=1

EXPOSE 8091

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8091/health')" || exit 1

CMD ["python", "/app/server.py"]

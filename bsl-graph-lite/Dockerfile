FROM python:3.12-slim

WORKDIR /app

COPY server.py /app/server.py
COPY static/ /app/static/

ENV PORT=8888
ENV GRAPH_WORKSPACE=/workspace
ENV GRAPH_STATE_FILE=/data/graph.json
ENV GRAPH_RESCAN_SECONDS=300

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8888/health')" || exit 1

CMD ["python", "/app/server.py"]

# FinePrint: FalkorDB with the Hub graph baked in, plus the HTTP API, in one container.
FROM falkordb/falkordb:v4.22.1

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
    "fastapi>=0.115" "uvicorn>=0.30" "falkordb>=1.8" "anthropic>=0.70" "pydantic>=2"

COPY api /app/api
COPY data/derived /app/data/derived
COPY deploy/dump.rdb /var/lib/falkordb/data/dump.rdb
COPY db/udf /app/db/udf
COPY deploy/start.sh /app/start.sh

ENV BROWSER=0 \
    FALKORDB_ARGS="TIMEOUT_DEFAULT 30000 TIMEOUT_MAX 120000 MAX_QUEUED_QUERIES 50" \
    FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 PORT=8000
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/start.sh"]

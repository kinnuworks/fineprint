#!/bin/sh
# Start FalkorDB on localhost only, wait for the graph to load, then serve the API on $PORT.
redis-server --bind 127.0.0.1 --protected-mode yes --dir /var/lib/falkordb/data \
  --save "" --appendonly no \
  --loadmodule /var/lib/falkordb/bin/falkordb.so ${FALKORDB_ARGS} &
until redis-cli -h 127.0.0.1 GRAPH.RO_QUERY hub "RETURN 1" >/dev/null 2>&1; do sleep 2; done
# Load the lineage UDFs from source so the API never depends on what the snapshot carried.
redis-cli -h 127.0.0.1 -x GRAPH.UDF LOAD REPLACE lineage < /app/db/udf/lineage.js
cd /app/api && exec /opt/venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"

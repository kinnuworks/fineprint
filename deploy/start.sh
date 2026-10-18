#!/bin/sh
# Start FalkorDB on localhost only, wait for the graph to load, then serve the API on $PORT.
set -e
redis-server --bind 127.0.0.1 --protected-mode yes --dir /var/lib/falkordb/data \
  --save "" --appendonly no \
  --loadmodule /var/lib/falkordb/bin/falkordb.so ${FALKORDB_ARGS} &
# redis-cli exits 0 on an error reply too (LOADING while the snapshot loads), so check the output.
until redis-cli -h 127.0.0.1 GRAPH.RO_QUERY hub "RETURN 1" 2>/dev/null | grep -q '^1$'; do sleep 2; done
# Load the lineage UDFs from source so the API never depends on what the snapshot carried.
redis-cli -h 127.0.0.1 -x GRAPH.UDF LOAD REPLACE lineage < /app/db/udf/lineage.js
# Fulltext index on Model.id for /api/search. FalkorDB builds it in the background (about 40 s and
# 700 MB on 3.16M ids); search uses a CONTAINS scan until it is OPERATIONAL. FINEPRINT_FULLTEXT=0 skips it.
if [ "${FINEPRINT_FULLTEXT:-1}" = "1" ]; then
  redis-cli -h 127.0.0.1 GRAPH.QUERY hub \
    "CALL db.idx.fulltext.createNodeIndex('Model', 'id')" || true
fi
# Database users with random passwords for this boot (api/fineprint_core/acl.py): fp-hub-ro,
# fp-whatif, fp-admin, and fp-org-<slug> on demand. The default user is switched off afterwards,
# so every connection from here on goes through one of them.
cd /app/api
eval "$(FALKORDB_HOST=127.0.0.1 FALKORDB_PORT=6379 /opt/venv/bin/python -m fineprint_core.acl --lock-default)"
exec /opt/venv/bin/uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"

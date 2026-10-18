#!/bin/sh
# Rebuild every number in README.md and CLAIMS.md from the Hub dump.
# Needs: data/raw/models.parquet and datasets.parquet (huggingface.co/datasets/cfahlgren1/hub-stats),
# FalkorDB v4.22.1 on $FALKORDB_PORT (default 6379), redis-cli on the host (or alias it to `docker exec -i <container> redis-cli`),
# the project venv, and ANTHROPIC_API_KEY for the card-reading baseline in steps 16-17.
set -e
cd "$(dirname "$0")/.."
PY=.venv/bin/python
export FALKORDB_PORT="${FALKORDB_PORT:-6379}"
$PY -I scripts/headline.py                       # 1  parse the dump (DuckDB), edges and slim model table
$PY -I scripts/export_graph.py                   # 2  CSVs for the bulk loader
(cd data/bulk && ../../.venv/bin/falkordb-bulk-insert hub -n Model.csv -r FINETUNE_OF.csv -r ADAPTER_OF.csv \
   -r MERGE_OF.csv -r QUANTIZED_FROM.csv -d -j STRING --port "$FALKORDB_PORT")   # 3  lineage graph
redis-cli -p "$FALKORDB_PORT" -x GRAPH.UDF LOAD REPLACE lineage < db/udf/lineage.js   # 4  lineage UDFs
$PY -I scripts/enrich.py                         # 5  task and size for substitutes
$PY -I scripts/load_all_models.py                # 6  every Hub model with its effective license
$PY -I scripts/update_effective_licenses.py      # 7  named licenses behind empty or `other` tags
$PY -I scripts/load_datasets.py                  # 8  datasets and TRAINED_ON edges
$PY -I scripts/load_license_graph.py             # 8b License and Clause nodes, LICENSED_UNDER edges
$PY -I scripts/audit_graph.py                    # 9  in-graph audit: inherits and contested, every family
$PY -I scripts/headline_graph.py                 # 10 headline counts (Cypher)
$PY -I scripts/graph_mismatches.py               # 11 mismatch set from the graph
$PY -I scripts/unsloth_share.py                  # 12 Unsloth share and template signature
$PY -I scripts/relicense_points.py               # 13 relicensing points (Cypher + UDF)
$PY -I scripts/hub_api_comparison.py             # 14 Hub API calls vs one graph query
$PY -I scripts/what_if.py                        # 14b FLUX.1-dev relicensing what-if on a GRAPH.COPY
$PY -I scripts/clerk_cleanup.py                  # 15 drop Clerk edges that fail attribution checks
$PY -I eval/run_eval.py v2                       # 16 sealed evaluation, gold v2
$PY -I eval/run_eval.py v3                       # 17 sealed evaluation, gold v3

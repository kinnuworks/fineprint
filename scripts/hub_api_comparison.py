"""How many Hugging Face API calls a full descendant walk needs, against one FalkorDB query.

The Hub API lists a model's direct children (`filter=base_model:X`), 1,000 per page, so a
walk needs at least one call per descendant that is checked for children. Call latency is
the median of five live calls; the graph time is a live call to the lineage UDF.
"""
import collections
import json
import os
import statistics
import time
import urllib.request
from pathlib import Path

import duckdb
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "derived"
root = "meta-llama/Llama-3.1-8B"
kids = collections.defaultdict(set)
for c, p in duckdb.sql(f"SELECT child, parent FROM '{D / 'edges.parquet'}' WHERE child <> parent").fetchall():
    kids[p].add(c)
seen, frontier, calls = {root}, [root], 0
while frontier:
    nxt = []
    for m in frontier:
        n = len(kids.get(m, ()))
        calls += max(1, -(-n // 1000))
        for k in kids.get(m, ()):
            if k not in seen:
                seen.add(k)
                nxt.append(k)
    frontier = nxt
lat = []
for m in [root, "meta-llama/Llama-3.1-8B-Instruct", "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit",
          "NousResearch/Hermes-3-Llama-3.1-8B", "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"]:
    t = time.time()
    urllib.request.urlopen(f"https://huggingface.co/api/models?filter=base_model:{m}&limit=1000", timeout=60).read()
    lat.append(time.time() - t)
g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
graph = []
for _ in range(5):
    t = time.time()
    n = g.ro_query("MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64)", {"id": root}).result_set[0][0]["count"]
    graph.append(time.time() - t)
res = {"root": root, "descendants": len(seen) - 1, "graph_descendants": n, "hub_api_calls_needed": calls,
       "median_call_seconds": round(statistics.median(lat), 2),
       "estimated_sequential_minutes": round(calls * statistics.median(lat) / 60, 1),
       "graph_ms_median": round(statistics.median(graph) * 1000, 1)}
(D / "hub_api_comparison.json").write_text(json.dumps(res, indent=1))
print(res)

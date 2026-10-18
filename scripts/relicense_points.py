"""Relicensing points, computed in FalkorDB.

A relicensing point is a model that declares a permissive license directly on top of a parent
under a restricted license. Cypher finds them; the lineage UDF counts the mismatched models
below each one (models that inherit restricted terms and also declare a permissive license).
"""
import json
import os
import sys
import time
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
perm, restricted = sorted(PERMISSIVE), sorted(LICENSES)
t = time.time()
points = g.ro_query(
    """MATCH (c:Model)-[:FINETUNE_OF|ADAPTER_OF|MERGE_OF|QUANTIZED_FROM]->(p:Model)
       WHERE c.license IN $perm AND p.license IN $restricted
       RETURN c.id, collect(DISTINCT p.id), c.downloads, size([(k:Model)-[:FINETUNE_OF|ADAPTER_OF|MERGE_OF|QUANTIZED_FROM]->(c) | k])""",
    {"perm": perm, "restricted": restricted}, timeout=590000).result_set
find_seconds = time.time() - t

t = time.time()
out = []
for pid, parents, dl, n_children in points:
    below = below_dl = 0
    if n_children:
        r = g.ro_query(
            """MATCH (c:Model) WHERE c.id = $id
               WITH lineage.descendantIds([c]) AS ids
               UNWIND ids AS d MATCH (m:Model) WHERE m.id = d AND size(m.inherits) > 0 AND m.license IN $perm
               RETURN count(m), sum(m.downloads)""", {"id": pid, "perm": perm}, timeout=120000).result_set[0]
        below, below_dl = r[0], r[1] or 0
    out.append({"model": pid, "restricted_parents": parents, "own_downloads_30d": dl,
                "mismatched_models_below": below, "their_downloads_30d": below_dl})
count_seconds = time.time() - t
out.sort(key=lambda x: -x["mismatched_models_below"])
summary = {
    "computed_in": "FalkorDB",
    "relicensing_points": len(out),
    "points_with_mismatched_descendants": sum(1 for x in out if x["mismatched_models_below"]),
    "mismatched_models_below_some_point": None,
    "seconds": {"find_points": round(find_seconds, 2), "count_below": round(count_seconds, 2)},
    "top": out[:50],
}
# Distinct models below any point (a model can sit below several points).
ids = [x["model"] for x in out if x["mismatched_models_below"]]
below = set()
for i in range(0, len(ids), 500):
    r = g.ro_query("""MATCH (c:Model) WHERE c.id IN $ids WITH collect(c) AS cs
                      WITH lineage.descendantIds(cs) AS d UNWIND d AS x
                      MATCH (m:Model) WHERE m.id = x AND size(m.inherits) > 0 AND m.license IN $perm RETURN m.id""",
                   {"ids": ids[i:i + 500], "perm": perm}, timeout=590000).result_set
    below.update(x[0] for x in r)
summary["mismatched_models_below_some_point"] = len(below)
(ROOT / "data" / "derived" / "relicense_points.json").write_text(json.dumps(summary, indent=1))
print(json.dumps({k: v for k, v in summary.items() if k != "top"}, indent=1))
for x in out[:8]:
    print(x["mismatched_models_below"], x["model"], "<-", x["restricted_parents"][:2])

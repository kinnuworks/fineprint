"""Hub-wide audit computed inside FalkorDB.

1. For each restricted license family, a multi-source UDF walk from every model that
   carries it marks all descendants (m.inherits).
2. The same walk from every model trained on a non-commercial dataset marks contested
   terms (m.contested).
3. Walk timings go to data/derived/audit_walks.json; scripts/headline_graph.py reads the counts.
"""
import collections
import json
import sys
import time
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

g = FalkorDB(host="localhost", port=int(__import__("os").environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
B = 25000


def q(query, params=None, timeout=590000):
    return g.query(query, params or {}, timeout=timeout).result_set


def mark(prop, ids, value):
    for i in range(0, len(ids), B):
        q(f"UNWIND $ids AS id MATCH (m:Model) WHERE m.id = id "
          f"SET m.{prop} = CASE WHEN $v IN m.{prop} THEN m.{prop} ELSE m.{prop} + [$v] END",
          {"ids": ids[i:i + B], "v": value})


timings = {}
t = time.time()
q("MATCH (m:Model) SET m.inherits = [], m.contested = []")
timings["reset"] = time.time() - t

families = collections.defaultdict(list)
for key, lic in LICENSES.items():
    families[lic.family].append(key)

walk = {}
for fam, keys in families.items():
    t = time.time()
    rows = q("MATCH (r:Model) WHERE r.license IN $keys WITH collect(r) AS roots "
             "RETURN size(roots), lineage.descendantIds(roots)", {"keys": keys})
    n_roots, ids = rows[0]
    walk[fam] = {"roots": n_roots, "descendants": len(ids), "seconds": round(time.time() - t, 2)}
    mark("inherits", ids, fam)
    print(fam, walk[fam], flush=True)

nc_keys = [k for k, l in LICENSES.items() if not l.commercial]
t = time.time()
rows = q("MATCH (m:Model)-[:TRAINED_ON]->(d:Dataset) WHERE d.license IN $keys "
         "WITH collect(DISTINCT m) AS roots RETURN [r IN roots | r.id], lineage.descendantIds(roots)", {"keys": nc_keys})
trained, below = rows[0]
mark("contested", list(trained) + list(below), "Non-commercial dataset")
walk["Non-commercial dataset"] = {"roots": len(trained), "descendants": len(below), "seconds": round(time.time() - t, 2)}

(ROOT / "data" / "derived" / "audit_walks.json").write_text(json.dumps(walk, indent=1))
print(json.dumps(walk, indent=1))
# Headline counts are read separately by scripts/headline_graph.py; `clean` is computed at query
# time from m.license, m.inherits and m.contested.

"""Add license families to the in-graph audit without resetting it (see audit_graph.py)."""
import json
import os
import sys
import time
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES  # noqa: E402

g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
families = sys.argv[1:]
B = 25000
log = {}
for fam in families:
    keys = [k for k, l in LICENSES.items() if l.family == fam]
    t = time.time()
    n_roots, ids = g.query("MATCH (r:Model) WHERE r.license IN $keys WITH collect(r) AS roots "
                           "RETURN size(roots), lineage.descendantIds(roots)", {"keys": keys}, timeout=590000).result_set[0]
    walk = time.time() - t
    t = time.time()
    for i in range(0, len(ids), B):
        g.query("UNWIND $ids AS id MATCH (m:Model) WHERE m.id = id "
                "SET m.inherits = CASE WHEN $v IN m.inherits THEN m.inherits ELSE m.inherits + [$v] END",
                {"ids": ids[i:i + B], "v": fam}, timeout=590000)
    log[fam] = {"roots": n_roots, "descendants": len(ids), "walk_seconds": round(walk, 2), "mark_seconds": round(time.time() - t, 2)}
    print(fam, log[fam], flush=True)
path = ROOT / "data" / "derived" / "audit_walks.json"
prev = json.loads(path.read_text()) if path.exists() else {}
prev.update(log)
path.write_text(json.dumps(prev, indent=1))

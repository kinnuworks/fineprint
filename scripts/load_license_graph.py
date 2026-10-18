"""Put the license rules in the graph.

(:License {key, family, commercial})-[:IMPOSES]->(:Clause {code, obligation, quote, source, tier})
(:Model)-[:LICENSED_UNDER]->(:License) for every model under a license in the library.
api/fineprint_core/licenses.py is the seed; after this the Examiner reads obligations from the graph.
"""
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
for stmt in ("CREATE INDEX FOR (l:License) ON (l.key)", "CREATE INDEX FOR (c:Clause) ON (c.code)"):
    try:
        g.query(stmt)
    except Exception as e:
        print("index:", str(e)[:60])
g.query("MATCH (l:License) DETACH DELETE l")
g.query("MATCH (c:Clause) DETACH DELETE c")
lic_rows = [{"key": l.key, "family": l.family, "commercial": l.commercial, "permissive": False,
             "clauses": [asdict(c) for c in l.clauses]} for l in LICENSES.values()]
lic_rows += [{"key": k, "family": k, "commercial": True, "permissive": True, "clauses": []} for k in sorted(PERMISSIVE)]
g.query("""UNWIND $rows AS r
           CREATE (l:License {key: r.key, family: r.family, commercial: r.commercial, permissive: r.permissive})
           WITH l, r UNWIND r.clauses AS c
           MERGE (k:Clause {code: c.code})
             ON CREATE SET k.obligation = c.obligation, k.quote = c.quote, k.source = c.source, k.tier = c.tier
           CREATE (l)-[:IMPOSES]->(k)""", {"rows": lic_rows})
t = time.time()
keys = sorted(set(LICENSES) | PERMISSIVE)
for key in keys:
    g.query("""MATCH (l:License) WHERE l.key = $k
               MATCH (m:Model) WHERE m.license = $k
               CREATE (m)-[:LICENSED_UNDER]->(l)""", {"k": key}, timeout=590000)
n = g.ro_query("MATCH ()-[r:LICENSED_UNDER]->() RETURN count(r)").result_set[0][0]
print(f"licenses {len(lic_rows)}, LICENSED_UNDER edges {n}, {time.time() - t:.1f}s")

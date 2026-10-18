"""What if FLUX.1-dev were relicensed as Apache-2.0? Answered on a GRAPH.COPY of its family.

1. Copy the FLUX.1-dev family (FLUX.1-dev has no ancestors, so its descendants and the edges
   between them are the whole picture) from `hub` into its own graph, `family:flux1-dev`.
2. GRAPH.COPY that graph to `whatif:flux1-dev-apache` and relicense FLUX.1-dev in the copy.
3. Re-run the lineage walk on both graphs and count models that still sit below a model
   under the FLUX.1 [dev] Non-Commercial License.
"""
import json
import os
import time
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
ROOT_ID = "black-forest-labs/FLUX.1-dev"
NC = "flux-1-dev-non-commercial-license"
REL = ["FINETUNE_OF", "ADAPTER_OF", "MERGE_OF", "QUANTIZED_FROM"]
db = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379")))
hub = db.select_graph("hub")
timings = {}

t = time.time()
ids = hub.ro_query("MATCH (r:Model) WHERE r.id = $id RETURN lineage.descendantIds([r])", {"id": ROOT_ID}).result_set[0][0]
members = [ROOT_ID] + list(ids)
nodes, edges = [], []
for i in range(0, len(members), 5000):
    chunk = members[i:i + 5000]
    nodes += hub.ro_query("MATCH (m:Model) WHERE m.id IN $ids RETURN m.id, m.license, m.downloads", {"ids": chunk}).result_set
    edges += hub.ro_query("""MATCH (c:Model)-[r:FINETUNE_OF|ADAPTER_OF|MERGE_OF|QUANTIZED_FROM]->(p:Model)
                             WHERE c.id IN $ids RETURN c.id, type(r), p.id""", {"ids": chunk}).result_set
member_set = set(members)
edges = [e for e in edges if e[2] in member_set]
timings["extract"] = round(time.time() - t, 2)

for name in ("family:flux1-dev", "whatif:flux1-dev-apache"):
    try:
        db.select_graph(name).delete()
    except Exception:
        pass
fam = db.select_graph("family:flux1-dev")
t = time.time()
fam.query("CREATE INDEX FOR (m:Model) ON (m.id)")
for i in range(0, len(nodes), 20000):
    fam.query("UNWIND $rows AS r CREATE (:Model {id: r[0], license: r[1], downloads: r[2]})",
              {"rows": [list(n) for n in nodes[i:i + 20000]]})
for rel in REL:
    rows = [[c, p] for c, r, p in edges if r == rel]
    for i in range(0, len(rows), 20000):
        fam.query(f"UNWIND $rows AS r MATCH (c:Model) WHERE c.id = r[0] MATCH (p:Model) WHERE p.id = r[1] CREATE (c)-[:{rel}]->(p)",
                  {"rows": rows[i:i + 20000]})
timings["build_family_graph"] = round(time.time() - t, 2)

t = time.time()
db.execute_command("GRAPH.COPY", "family:flux1-dev", "whatif:flux1-dev-apache")
timings["graph_copy"] = round(time.time() - t, 3)
whatif = db.select_graph("whatif:flux1-dev-apache")
whatif.query("MATCH (m:Model) WHERE m.id = $id SET m.license = 'apache-2.0'", {"id": ROOT_ID})


def still_nc(g):
    rows = g.ro_query("""MATCH (r:Model) WHERE r.license = $nc WITH collect(r) AS roots
                         RETURN size(roots), lineage.descendantIds(roots)""", {"nc": NC}).result_set[0]
    below = set(rows[1])
    roots = {r[0] for r in g.ro_query("MATCH (r:Model) WHERE r.license = $nc RETURN r.id", {"nc": NC}).result_set}
    return {"models_under_nc_license": len(roots), "models_below_one": len(below), "affected_total": len(roots | below)}


t = time.time()
before, after = still_nc(fam), still_nc(whatif)
timings["walks"] = round(time.time() - t, 2)


result = {
    "scenario": "FLUX.1-dev relicensed as Apache-2.0, on a GRAPH.COPY of its family",
    "family_models": len(nodes), "family_edges": len(edges),
    "before": before, "after": after,
    "still_labelled_non_commercial_after": after["affected_total"],
    "why": "Most of these are LoRAs whose own cards copy the FLUX.1 [dev] Non-Commercial license label. Relicensing the base would not change those labels; each uploader would have to edit their card, so they would still read as non-commercial until relabelled.",
    "graphs": ["family:flux1-dev", "whatif:flux1-dev-apache"],
    "seconds": timings,
}
(ROOT / "data" / "derived" / "what_if_flux.json").write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))

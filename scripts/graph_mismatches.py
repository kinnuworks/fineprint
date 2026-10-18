"""Export the in-graph mismatch set (inherits restricted terms, declares permissive) for downstream scripts."""
import json
import os
import sys
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import PERMISSIVE  # noqa: E402

g = FalkorDB(host="localhost", port=int(os.environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
rows = g.ro_query("MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $p RETURN m.id, m.license, m.inherits, m.downloads",
                  {"p": sorted(PERMISSIVE)}, timeout=590000).result_set
with open(ROOT / "data" / "derived" / "graph_mismatches.jsonl", "w") as f:
    for mid, lic, inh, dl in rows:
        f.write(json.dumps({"id": mid, "declared": lic, "inherits": inh, "downloads_30d": dl}) + "\n")
print(len(rows))

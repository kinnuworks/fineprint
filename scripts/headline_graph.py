"""Hub-wide headline counts, read from the audited graph with Cypher.

Run after scripts/audit_graph.py has marked m.inherits and m.contested. Saves the
numbers with the query text and timings to data/derived/headline_graph.json.
"""
import json
import sys
import time
from pathlib import Path

from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

g = FalkorDB(host="localhost", port=int(__import__("os").environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")


def q(query, params=None):
    return g.ro_query(query, params or {}, timeout=590000).result_set


nc_families = sorted({l.family for l in LICENSES.values() if not l.commercial})
timings = {}
QUERIES = {
    "models_total": "MATCH (m:Model) WHERE m.missing = false RETURN count(m)",
    "inheriting_restricted": "MATCH (m:Model) WHERE size(m.inherits) > 0 RETURN count(m)",
    "inheriting_but_declare_permissive": "MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $perm RETURN count(m), sum(m.downloads)",
    "of_those_ship_license_file": "MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $perm AND m.has_license_file = true RETURN count(m)",
    "non_commercial_upstream_declare_permissive": "MATCH (m:Model) WHERE any(f IN m.inherits WHERE f IN $nc) AND m.license IN $perm RETURN count(m), sum(m.downloads)",
    "by_family": "MATCH (m:Model) WHERE m.license IN $perm UNWIND m.inherits AS f RETURN f, count(m) ORDER BY count(m) DESC",
    "inheriting_but_declare_permissive_10plus_downloads": "MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $perm AND m.downloads >= 10 RETURN count(m), sum(m.downloads)",
    "non_commercial_upstream_declare_permissive_10plus": "MATCH (m:Model) WHERE any(f IN m.inherits WHERE f IN $nc) AND m.license IN $perm AND m.downloads >= 10 RETURN count(m), sum(m.downloads)",
    "inheriting_restricted_10plus_downloads": "MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.downloads >= 10 RETURN count(m)",
    "contested_only": "MATCH (m:Model) WHERE size(m.contested) > 0 AND size(m.inherits) = 0 AND m.license IN $perm RETURN count(m)",
    "inheriting_downloads": "MATCH (m:Model) WHERE size(m.inherits) > 0 RETURN sum(m.downloads)",
}
params = {"perm": sorted(PERMISSIVE), "nc": nc_families}
numbers = {}
for name, query in QUERIES.items():
    t = time.time()
    res = q(query, params)
    numbers[name] = res if len(res) > 1 else res[0]
    timings[name] = round(time.time() - t, 3)
out = {"computed_in": "FalkorDB", "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
       "numbers": numbers, "queries": QUERIES, "seconds": timings}
(ROOT / "data" / "derived" / "headline_graph.json").write_text(json.dumps(out, indent=1, default=str))
print(json.dumps(numbers, indent=1, default=str))

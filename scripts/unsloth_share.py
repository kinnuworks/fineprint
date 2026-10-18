"""How many in-graph mismatches descend through an unsloth/* model, and how many carry Unsloth's card template tags."""
import collections
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "derived"
ids = [json.loads(l)["id"] for l in open(D / "graph_mismatches.jsonl")]
par = collections.defaultdict(set)
for c, p in duckdb.sql(f"SELECT child, parent FROM '{D / 'edges.parquet'}' WHERE child <> parent").fetchall():
    par[c].add(p)


def via_unsloth(m):
    seen, st = set(), [m]
    while st:
        x = st.pop()
        for p in par.get(x, ()):
            if p.lower().startswith("unsloth/"):
                return True
            if p not in seen:
                seen.add(p)
                st.append(p)
    return False


con = duckdb.connect()
con.sql("CREATE TABLE ids(id VARCHAR)")
con.executemany("INSERT INTO ids VALUES (?)", [(i,) for i in ids])
# The template writes these tags together with license: apache-2.0 (unsloth/save.py MODEL_CARD).
template = {r[0] for r in con.sql(f"""
    SELECT m.id FROM '{ROOT / 'data' / 'raw' / 'models.parquet'}' m JOIN ids USING (id)
    WHERE list_contains(m.tags, 'unsloth') AND list_contains(m.tags, 'text-generation-inference')
      AND list_contains(m.tags, 'license:apache-2.0')""").fetchall()}
n_via = sum(1 for m in ids if via_unsloth(m))
out = {"mismatched": len(ids), "via_unsloth": n_via, "share": round(n_via / len(ids), 3),
       "template_signature": len(template), "template_share": round(len(template) / len(ids), 3),
       "template_signature_rule": "tags unsloth + text-generation-inference + license:apache-2.0"}
(D / "unsloth_share.json").write_text(json.dumps(out, indent=1))
print(out)

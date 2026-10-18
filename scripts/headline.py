"""Hub-wide headline: models whose declared license differs from the terms
they inherit from their ancestors.

Reads data/raw/models.parquet (cfahlgren1/hub-stats) and writes
data/derived/edges.parquet, data/derived/models_slim.parquet and
data/derived/headline.json.
"""
import json
import collections
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "models.parquet"
OUT = ROOT / "data" / "derived"
OUT.mkdir(parents=True, exist_ok=True)

# Licenses whose terms reach derivatives. Values are the family label used in reports.
RESTRICTIVE = {
    "llama2": "Llama 2", "llama3": "Llama 3", "llama3.1": "Llama 3.1",
    "llama3.2": "Llama 3.2", "llama3.3": "Llama 3.3", "llama4": "Llama 4",
    "gemma": "Gemma",
    "cc-by-nc-4.0": "CC BY-NC", "cc-by-nc-sa-4.0": "CC BY-NC", "cc-by-nc-nd-4.0": "CC BY-NC",
    "cc-by-nc-2.0": "CC BY-NC", "cc-by-nc-3.0": "CC BY-NC", "cc-by-nc-sa-3.0": "CC BY-NC",
}
PERMISSIVE = {
    "apache-2.0", "mit", "bsd", "bsd-2-clause", "bsd-3-clause", "afl-3.0",
    "unlicense", "wtfpl", "cc0-1.0", "cc-by-4.0", "cc-by-sa-4.0", "isc", "zlib", "bsl-1.0",
}

con = duckdb.connect()
con.sql(f"""
CREATE TABLE m AS
SELECT id,
       downloads,
       downloadsAllTime,
       list_filter(tags, t -> starts_with(t, 'license:')) AS lic_tags,
       baseModels.relation AS relation,
       list_transform(baseModels.models, x -> x.id) AS parents
FROM '{RAW}'
""")
con.sql(f"""
COPY (SELECT id, downloads, downloadsAllTime,
             CASE WHEN len(lic_tags) > 0 THEN substr(lic_tags[1], 9) END AS license,
             relation, len(parents) AS n_parents
      FROM m) TO '{OUT / "models_slim.parquet"}' (FORMAT parquet)
""")
con.sql(f"""
COPY (SELECT id AS child, unnest(parents) AS parent, relation
      FROM m WHERE parents IS NOT NULL AND len(parents) > 0)
TO '{OUT / "edges.parquet"}' (FORMAT parquet)
""")

lic = dict(con.sql(f"SELECT id, license FROM '{OUT / 'models_slim.parquet'}'").fetchall())
dl = dict(con.sql(f"SELECT id, coalesce(downloads,0) FROM '{OUT / 'models_slim.parquet'}'").fetchall())
edges = con.sql(f"SELECT child, parent, relation FROM '{OUT / 'edges.parquet'}'").fetchall()

parents = collections.defaultdict(set)
rel_of = {}
for c, p, r in edges:
    if c != p:
        parents[c].add(p)
        rel_of[c] = r

# Inherited restrictive families, with the depth of the nearest ancestor carrying each.
memo: dict[str, dict[str, int]] = {}


def inherited(mid: str, stack: frozenset = frozenset()) -> dict[str, int]:
    if mid in memo:
        return memo[mid]
    out: dict[str, int] = {}
    for p in parents.get(mid, ()):
        if p in stack:
            continue
        fam = RESTRICTIVE.get(lic.get(p) or "")
        if fam:
            out[fam] = min(out.get(fam, 99), 1)
        for f, d in inherited(p, stack | {mid}).items():
            out[f] = min(out.get(f, 99), d + 1)
    memo[mid] = out
    return out


import sys
sys.setrecursionlimit(100000)

total_with_parents = len(parents)
multi_parent = sum(1 for c in parents if len(parents[c]) > 1)
mismatch = []
for mid in parents:
    inh = inherited(mid)
    if not inh:
        continue
    declared = lic.get(mid)
    if declared in PERMISSIVE:
        mismatch.append((mid, declared, inh, rel_of.get(mid), dl.get(mid, 0)))

inheriting = sum(1 for mid in parents if inherited(mid))
depth_hist = collections.Counter(min(i[2].values()) for i in mismatch)
fam_hist = collections.Counter(f for i in mismatch for f in i[2])
rel_hist = collections.Counter(i[3] for i in mismatch)
declared_hist = collections.Counter(i[1] for i in mismatch)
inh_dl = sum(dl.get(mid, 0) for mid in parents if inherited(mid))
mis_dl = sum(i[4] for i in mismatch)
max_depth = max((max(memo[m].values()) for m in memo if memo[m]), default=0)

result = {
    "models_total": len(lic),
    "models_with_declared_parents": total_with_parents,
    "multi_parent_models": multi_parent,
    "models_inheriting_restrictive_terms": inheriting,
    "of_those_declaring_permissive_license": len(mismatch),
    "share_by_count": round(len(mismatch) / max(inheriting, 1), 4),
    "downloads_30d_inheriting": inh_dl,
    "downloads_30d_mismatched": mis_dl,
    "share_by_downloads": round(mis_dl / max(inh_dl, 1), 4),
    "mismatch_by_nearest_depth": dict(sorted(depth_hist.items())),
    "max_inheritance_depth": max_depth,
    "mismatch_by_family": dict(fam_hist.most_common()),
    "mismatch_by_relation": dict(rel_hist.most_common()),
    "mismatch_by_declared_license": dict(declared_hist.most_common()),
    "top_by_downloads": [
        {"id": i[0], "declared": i[1], "inherits": sorted(i[2]), "relation": i[3], "downloads_30d": i[4]}
        for i in sorted(mismatch, key=lambda x: -x[4])[:40]
    ],
}
(OUT / "headline.json").write_text(json.dumps(result, indent=2))
with open(OUT / "mismatches.jsonl", "w") as f:
    for i in mismatch:
        f.write(json.dumps({"id": i[0], "declared": i[1], "inherits": i[2], "relation": i[3], "downloads_30d": i[4]}) + "\n")
print(json.dumps({k: v for k, v in result.items() if k != "top_by_downloads"}, indent=2))

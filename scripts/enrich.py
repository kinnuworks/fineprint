"""Add task, size and title facts to Model nodes, in batches.

task      pipeline tag from the Hub, inherited from the nearest ancestor when missing
params    parameter count (safetensors total), inherited from the nearest ancestor when missing
inherits  restricted license families found upstream
clean     declared license is permissive and nothing restricted is upstream
"""
import collections
import sys
from pathlib import Path

import duckdb
from falkordb import FalkorDB

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

D = ROOT / "data" / "derived"
con = duckdb.connect()
meta = {
    r[0]: (r[1], r[2])
    for r in con.sql(f"""
        SELECT id, pipeline_tag, safetensors.total
        FROM '{ROOT / 'data' / 'raw' / 'models.parquet'}'
        QUALIFY row_number() OVER (PARTITION BY id ORDER BY downloads DESC NULLS LAST) = 1
    """).fetchall()
}
lic = dict(con.sql(f"SELECT id, license FROM '{D / 'models_slim.parquet'}'").fetchall())
parents = collections.defaultdict(set)
for c, p in con.sql(f"SELECT child, parent FROM '{D / 'edges.parquet'}' WHERE child <> parent").fetchall():
    parents[c].add(p)
nodes = [r[0] for r in con.sql(f"SELECT DISTINCT id FROM (SELECT child id FROM '{D / 'edges.parquet'}' UNION SELECT parent FROM '{D / 'edges.parquet'}')").fetchall()]

sys.setrecursionlimit(200000)
memo: dict[str, frozenset] = {}
pmemo: dict[str, int | None] = {}
tmemo: dict[str, str] = {}


def task_of(m: str, stack=frozenset()) -> str:
    if m in tmemo:
        return tmemo[m]
    own = (meta.get(m) or (None, None))[0]
    if own:
        tmemo[m] = own
        return own
    for p in parents.get(m, ()):
        if p not in stack:
            v = task_of(p, stack | {m})
            if v:
                tmemo[m] = v
                return v
    tmemo[m] = ""
    return ""


def inherited(m: str, stack=frozenset()) -> frozenset:
    if m in memo:
        return memo[m]
    out = set()
    for p in parents.get(m, ()):
        if p in stack:
            continue
        if lic.get(p) in LICENSES:
            out.add(LICENSES[lic[p]].family)
        out |= inherited(p, stack | {m})
    memo[m] = frozenset(out)
    return memo[m]


def params(m: str, stack=frozenset()) -> int | None:
    if m in pmemo:
        return pmemo[m]
    own = (meta.get(m) or (None, None))[1]
    if own:
        pmemo[m] = own
        return own
    for p in parents.get(m, ()):
        if p not in stack:
            v = params(p, stack | {m})
            if v:
                pmemo[m] = v
                return v
    pmemo[m] = None
    return None


rows = []
for m in nodes:
    task = task_of(m)
    inh = sorted(inherited(m))
    declared = lic.get(m) or ""
    rows.append({
        "id": m,
        "task": task,
        "params": params(m) or 0,
        "inherits": inh,
        "clean": declared in PERMISSIVE and not inh,
    })

g = FalkorDB(host="localhost", port=int(__import__("os").environ.get("FALKORDB_PORT", "6379"))).select_graph("hub")
B = 20000
for i in range(0, len(rows), B):
    g.query(
        "UNWIND $rows AS r MATCH (m:Model) WHERE m.id = r.id "
        "SET m.task = r.task, m.params = r.params, m.inherits = r.inherits, m.clean = r.clean",
        {"rows": rows[i:i + B]}, timeout=600000,
    )
    print(f"{min(i + B, len(rows))}/{len(rows)}", flush=True)
try:
    g.query("CREATE INDEX FOR (m:Model) ON (m.task)")
except Exception as e:  # already indexed on a re-run
    print("index:", e)
print("clean:", sum(r["clean"] for r in rows), "with params:", sum(1 for r in rows if r["params"]))

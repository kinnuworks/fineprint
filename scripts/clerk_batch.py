"""Run the Clerk over the most-downloaded cards in the restricted families and record what changed."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.clerk import extract, record  # noqa: E402
from fineprint_core.examiner import examine  # noqa: E402
from fineprint_core.graph import ro  # noqa: E402

N = int(sys.argv[1]) if len(sys.argv) > 1 else 150
OUT = ROOT / "data" / "derived" / "clerk_run.jsonl"

MODE = sys.argv[2] if len(sys.argv) > 2 else "unclear"
if MODE == "inheriting":
    rows = ro("""MATCH (m:Model) WHERE m.missing = false AND size(m.inherits) > 0 AND m.downloads > 500
                 RETURN m.id ORDER BY m.downloads DESC LIMIT $n""", {"n": N})
    ids = [r[0] for r in rows]
else:
    # Popular models whose verdict is not settled by tags: no restricted terms found yet, permissive or no license.
    rows = ro("""MATCH (m:Model) WHERE m.missing = false AND size(m.inherits) = 0 AND m.downloads > 2000
                 AND NOT m.id STARTS WITH 'meta-llama/' AND NOT m.id STARTS WITH 'google/'
                 RETURN m.id ORDER BY m.downloads DESC LIMIT $n""", {"n": N * 6})
    ids = [r[0] for r in rows if examine(r[0])["verdict"] in ("UNKNOWN", "NO LIENS FOUND")][: N]
OUT = ROOT / "data" / "derived" / f"clerk_run_{MODE}.jsonl"


def run(mid):
    from fineprint_core.graph import hub
    hub().query("MATCH (m:Model)-[r]->() WHERE m.id = $id AND r.by = 'clerk' AND r.read_from = $id DELETE r", {"id": mid})
    before = examine(mid)["verdict"]
    try:
        claims = extract(mid)
    except Exception as e:  # card missing, network, API error
        return {"id": mid, "error": str(e)[:200]}
    written = record(mid, claims)
    after = examine(mid)
    return {
        "id": mid, "before": before, "after": after["verdict"], "edges_written": written,
        "claims": claims, "liens_after": [(l["family"], l["tier"], l["via"]) for l in after["liens"]],
    }


with ThreadPoolExecutor(max_workers=8) as pool, open(OUT, "w") as f:
    for res in pool.map(run, ids):
        f.write(json.dumps(res) + "\n")
        f.flush()
        print(res["id"], res.get("before"), "->", res.get("after"), res.get("edges_written", res.get("error", "")), flush=True)

"""Remove Clerk edges that fail the attribution rules, and the edges a manual check marked wrong.

Rules (same as clerk.record for new writes):
  1. An edge must sit on the model whose card was read, or on an original the card itself names.
  2. A third-party card never writes onto an official base model.
  3. The quote must mention the target.
Manual check: eval/clerk_precision.json lists every edge reviewed and why the wrong ones are wrong.
Only edges marked correct there stay; edges from later, unchecked runs are removed.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.clerk import OFFICIAL, _names_target  # noqa: E402
from fineprint_core.graph import hub  # noqa: E402

g = hub()
rows = g.ro_query("MATCH (m:Model)-[r]->(t) WHERE r.by = 'clerk' RETURN ID(r), m.id, type(r), t.id, r.quote, r.read_from").result_set
checked = json.loads((ROOT / "eval" / "clerk_precision.json").read_text())
correct = {(e["model"], e["rel"], e["target"]) for e in checked["edges"] if e["correct"]}
drop = []
for rid, mid, rel, target, quote, read_from in rows:
    # A claim about "the original" may sit on a model other than the one whose card was read only
    # when that model is a direct parent of the read model (clerk._subject applies the same rule).
    if mid != read_from:
        parent = g.ro_query("MATCH (c:Model)-[:QUANTIZED_FROM|FINETUNE_OF|ADAPTER_OF]->(p:Model) "
                            "WHERE c.id = $c AND p.id = $p RETURN count(p)", {"c": read_from, "p": mid}).result_set[0][0]
    misplaced = mid != read_from and not parent
    official = mid.lower().startswith(OFFICIAL) and not (read_from or "").lower().startswith(OFFICIAL)
    # Only edges that passed the manual check stay in the published graph.
    unchecked = (mid, rel, target) not in correct
    if misplaced or official or unchecked or not _names_target(quote or "", target):
        drop.append(rid)
ids = sorted(set(drop))
for i in range(0, len(ids), 500):
    g.query("MATCH (m:Model)-[r]->() WHERE r.by = 'clerk' AND ID(r) IN $ids DELETE r", {"ids": ids[i:i + 500]})
print(f"clerk edges: {len(rows)} before, {len(set(drop))} removed, {len(rows) - len(set(drop))} kept")

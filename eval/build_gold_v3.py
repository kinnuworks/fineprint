"""Gold v3: the same 120 models as v2, relabelled through the live Hub API with one rule decided
before scoring: a model with no declared license is UNKNOWN (no license grants no rights).
Everything else matches build_gold.py. Sealed with its SHA-256 before any system runs.
"""
import hashlib
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_gold as bg  # noqa: E402

HERE = Path(__file__).resolve().parent
v2 = json.loads((HERE / "gold_v2.json").read_text())
gold = []
for g in v2:
    lab = bg.label(g["id"])
    if lab is None:
        continue
    if not lab["declared"]:
        lab["verdict"] = "UNKNOWN"
    gold.append({**lab, "stratum": g["stratum"]})
blob = json.dumps(sorted(gold, key=lambda x: x["id"]), indent=1, sort_keys=True)
(HERE / "gold_v3.json").write_text(blob)
sha = hashlib.sha256(blob.encode()).hexdigest()
(HERE / "GOLD_V3_SHA256").write_text(f"{sha}  gold_v3.json  sealed {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
print("sealed", sha, len(gold))

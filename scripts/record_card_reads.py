"""Run the Clerk once on each demo model and save what it extracted.

The API loads data/derived/card_reads.json at startup, so the public demo replays these
recorded reads (marked "recorded" in the response) when no model key is configured or the
live call fails. The graph writes still happen live on every request.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
from app import READ_CARD_ALLOW  # noqa: E402
from fineprint_core.clerk import MODEL, extract  # noqa: E402

out_path = ROOT / "data" / "derived" / "card_reads.json"
reads = json.loads(out_path.read_text()) if out_path.exists() else {}
for mid in sorted(READ_CARD_ALLOW):
    if mid in reads and "--redo" not in sys.argv:
        continue
    t = time.time()
    claims = extract(mid)
    reads[mid] = {"claims": claims, "model": MODEL, "read_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "seconds": round(time.time() - t, 1)}
    print(mid, len(claims), "claims", reads[mid]["seconds"], "s")
out_path.write_text(json.dumps(reads, indent=1))

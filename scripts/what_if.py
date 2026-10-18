"""What if FLUX.1-dev were relicensed as Apache-2.0? Answered on a GRAPH.COPY of its family.

Runs the same code as GET /api/what-if (api/fineprint_core/whatif.py):
1. The FLUX.1-dev family (the root and its descendants, with the edges between them) is written
   once from `hub` to its own graph, `family:black-forest-labs-flux-1-dev`.
2. GRAPH.COPY makes a throwaway `whatif:<uuid>`, FLUX.1-dev is relicensed in the copy, the
   lineage walk runs on both graphs, and the copy is deleted.

Also pre-builds the family graphs for the other showcase roots, so the shipped dump carries them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from fineprint_core import whatif  # noqa: E402

SHOWCASE = ["black-forest-labs/FLUX.1-dev", "Qwen/Qwen2.5-3B", "meta-llama/Llama-3.2-1B",
            "facebook/nllb-200-distilled-600M"]

if __name__ == "__main__":
    out = {}
    for root in SHOWCASE:
        out[root] = whatif.simulate(root, "apache-2.0")
        print(json.dumps({k: out[root][k] for k in ("root", "family_models", "before", "after", "seconds")}))
    flux = out[SHOWCASE[0]]
    (ROOT / "data" / "derived" / "what_if_flux.json").write_text(json.dumps(flux, indent=1))

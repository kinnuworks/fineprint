"""Seed the demo ruleset `acme-legal` (graph `org:acme-legal`) with three rulings, then show
what they change. Rerunning replaces the ruleset. The `hub` graph is only read.

    FALKORDB_PORT=6380 .venv/bin/python -I scripts/seed_rulings.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

from fineprint_core import rulings  # noqa: E402
from fineprint_core.examiner import decide, examine  # noqa: E402

SLUG = "acme-legal"
SEED = [
    dict(scope="license", target="llama3.1", effect="approve", use="commercial",
         conditions="Ship the Llama 3.1 LICENSE with the product and show \"Built with Llama\"",
         note="Llama 3.1 Community License reviewed for our products. We stay far under 700M monthly users.",
         by="legal@acme (ticket LEG-31)"),
    dict(scope="license", target="qwen-research", effect="reject", use="any",
         note="Qwen Research License is off limits at Acme, research projects included.",
         by="legal@acme (ticket LEG-17)"),
    dict(scope="model", target="google/gemma-3-27b-it", effect="approve", use="commercial",
         conditions="Keep the Gemma Terms of Use and the NOTICE file in the release",
         note="google/gemma-3-27b-it approved by legal on 2026-10-18, ticket LEG-42.",
         by="legal@acme (ticket LEG-42)"),
]
SHOW = [
    ("meta-llama/Llama-3.1-8B-Instruct", "commercial"),
    ("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit", "noncommercial"),
    ("google/gemma-3-27b-it", "commercial"),
    ("google/gemma-2-9b-it", "commercial"),
]


def main() -> None:
    rulings.drop(SLUG)
    for r in SEED:
        made = rulings.create(SLUG, **r)
        print(f"{made['id']}  {made['effect']:7} {made['scope']:7} {made['target']}  ({made['use']})")
    print()
    for mid, use in SHOW:
        rep = examine(mid)
        out = rulings.apply(rep, decide(rep, use), use, SLUG)
        print(f"{mid} [{use}]: {out['org']['decision_before']} -> {out['decision']}. {out['why']}")


if __name__ == "__main__":
    main()

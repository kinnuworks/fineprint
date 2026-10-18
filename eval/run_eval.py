"""Score FinePrint and two baselines on the sealed gold set.

Systems:
  declared    the model's declared license alone (what a license scanner sees)
  one_hop     the declared license plus the direct parents' licenses (what a model page shows)
  card_llm    an LLM given the model card text, asked for the verdict and inherited families
  tool_agent  an LLM agent with live Hub API tools, up to 10 calls per model (eval/tool_agent.py)
  fineprint   the Examiner over the graph

  run_eval.py v3                      score every system (tool_agent only if its runs are stored)
  run_eval.py v3 --with-tool-agent    also run the tool agent for any gold model it has not seen
  run_eval.py v3 --merge              keep the other systems' stored results, rescore only tool_agent
"""
import hashlib
import json
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.clerk import MODEL, _client  # noqa: E402
from fineprint_core.examiner import examine  # noqa: E402
from fineprint_core.licenses import LICENSES, PERMISSIVE  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = {a for a in sys.argv[1:] if a.startswith("--")}
VERSION = ARGS[0] if ARGS else "v2"
OUT = HERE / {"v1": "results.json", "v2": "results_v2.json", "v3": "results_v3.json"}[VERSION]
GOLD, SEAL = {"v1": ("gold.json", "GOLD_SHA256"), "v2": ("gold_v2.json", "GOLD_V2_SHA256"),
              "v3": ("gold_v3.json", "GOLD_V3_SHA256")}[VERSION]
blob = (HERE / GOLD).read_text()
sealed = (HERE / SEAL).read_text().split()[0]
assert hashlib.sha256(blob.encode()).hexdigest() == sealed, "gold.json changed after sealing"
gold = json.loads(blob)
FAMILIES = sorted({l.family for l in LICENSES.values()})


def declared(g):
    lic = g["declared"] or ""
    if lic in LICENSES:
        return {"verdict": "LIENS", "families": [LICENSES[lic].family]}
    if lic in PERMISSIVE:
        return {"verdict": "NO LIENS FOUND", "families": []}
    return {"verdict": "UNKNOWN", "families": []}


class CardAnswer(BaseModel):
    verdict: Literal["NO LIENS FOUND", "LIENS", "CLOUDED", "UNKNOWN"]
    inherited_families: list[str]


CARD_PROMPT = (
    "You check open model licenses. From the model card below, decide which restricted license families "
    f"this model inherits from its upstream models (choose from: {', '.join(FAMILIES)}), and give a verdict: "
    "CLOUDED if the declared license is permissive but restricted terms come from upstream; LIENS if restricted "
    "terms apply and the declared license is consistent with them; NO LIENS FOUND if nothing restricted applies; "
    "UNKNOWN if you cannot tell."
)


def card_llm(g):
    try:
        card = urllib.request.urlopen(f"https://huggingface.co/{g['id']}/raw/main/README.md", timeout=20).read().decode("utf-8", "ignore")[:60000]
    except Exception:
        card = "(no model card)"
    r = _client().messages.parse(
        model=MODEL, max_tokens=16000,
        messages=[{"role": "user", "content": f"{CARD_PROMPT}\n\nModel id: {g['id']}\n\nModel card:\n{card}"}],
        output_format=CardAnswer,
    )
    a = r.parsed_output
    if a is None:
        return {"verdict": "UNKNOWN", "families": []}
    return {"verdict": a.verdict, "families": [f for f in a.inherited_families if f in FAMILIES]}


def one_hop(g):
    """What a model page shows: the declared license and the direct parent's license."""
    r = examine(g["id"], use_graph=False)
    fams = sorted({l["family"] for l in r["liens"] if l["tier"] == "contractual" and l["depth"] > 0})
    return {"verdict": r["verdict"], "families": fams}


def fineprint(g):
    r = examine(g["id"])
    fams = sorted({l["family"] for l in r["liens"] if l["tier"] == "contractual" and l["depth"] > 0})
    return {"verdict": r["verdict"], "families": fams}


import tool_agent as ta  # noqa: E402

_runs = ta.load_runs()["runs"]
RUN_AGENT = "--with-tool-agent" in FLAGS


def _finished(r):
    return r is not None and r["answered"] and not r["error"]


def tool_agent(g):
    """Stored run from eval/tool_agent_runs.json. With --with-tool-agent, runs the agent for models it
    has not finished. A model with no finished run gets None and is left out of tool_agent's score."""
    r = _runs.get(g["id"])
    if not _finished(r) and RUN_AGENT:
        r = ta.run_one(g["id"])
        _runs[g["id"]] = r
    if not _finished(r):
        return None
    return {"verdict": r["verdict"], "families": r["families"]}


SYSTEMS = {"declared": declared, "one_hop": one_hop, "card_llm": card_llm, "fineprint": fineprint}
if RUN_AGENT or any(_finished(_runs.get(g["id"])) for g in gold):
    SYSTEMS = {"declared": declared, "one_hop": one_hop, "card_llm": card_llm, "tool_agent": tool_agent,
               "fineprint": fineprint}
MERGE = "--merge" in FLAGS and OUT.exists()
previous = json.loads(OUT.read_text()) if MERGE else None
if MERGE:
    assert previous["gold_sha256"] == sealed, "stored results were scored on a different gold file"

results = {}
for name, fn in SYSTEMS.items():
    if MERGE and name != "tool_agent" and name in previous["systems"]:
        continue
    with ThreadPoolExecutor(max_workers=6 if name in ("card_llm", "tool_agent") else 1) as pool:
        results[name] = list(pool.map(fn, gold))
    print(name, "done", flush=True)
if "tool_agent" in results and RUN_AGENT:
    store = ta.load_runs()
    store["runs"].update(_runs)
    ta.RUNS.write_text(json.dumps(store, indent=1))


def score(pairs, with_families=True):
    """pairs: (gold item, prediction) where prediction has 'verdict' and, if with_families, 'families'."""
    by = defaultdict(lambda: [0, 0])
    fam_hit = fam_total = 0
    for g, p in pairs:
        ok = p["verdict"] == g["verdict"]
        bucket = "depth 2+" if g["max_depth"] >= 2 else ("depth 1" if g["max_depth"] == 1 else "no upstream terms")
        for k in ("all", g["stratum"], bucket):
            by[k][0] += ok
            by[k][1] += 1
        if with_families:
            for f in g["inherits"]:
                fam_total += 1
                fam_hit += f in p["families"]
    restricted = [(g, p) for g, p in pairs if g["verdict"] in ("CLOUDED", "LIENS")]
    false_clean = sum(1 for g, p in restricted if p["verdict"] == "NO LIENS FOUND")
    abstain = sum(1 for _, p in pairs if p["verdict"] == "UNKNOWN")
    committed = [(g, p) for g, p in pairs if p["verdict"] != "UNKNOWN"]
    out = {
        "verdict_accuracy": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by.items())},
        "inherited_family_recall": f"{fam_hit}/{fam_total}" if with_families else "n/a",
        "false_clean": f"{false_clean}/{len(restricted)}",
        "abstained_unknown": abstain,
        "accuracy_when_committed": f"{sum(1 for g, p in committed if g['verdict'] == p['verdict'])}/{len(committed)}",
    }
    return out


report = {"gold_sha256": sealed, "n": len(gold), "systems": {}}
for name in SYSTEMS:
    if name not in results:
        report["systems"][name] = previous["systems"][name]
        continue
    pairs = [(g, p) for g, p in zip(gold, results[name]) if p is not None]
    report["systems"][name] = score(pairs)
    if len(pairs) < len(gold):
        report["systems"][name]["scored_on"] = f"{len(pairs)} of {len(gold)} models (no finished run on the rest)"
old_rows = {r["id"]: r for r in previous["rows"]} if MERGE else {}


def _verdict(n, i, g):
    if n in results:
        p = results[n][i]
        return p["verdict"] if p is not None else None
    return old_rows[g["id"]][n]


report["rows"] = [{"id": g["id"], "gold": g["verdict"], **{n: _verdict(n, i, g) for n in SYSTEMS}}
                  for i, g in enumerate(gold)]
conservative = sum(1 for r in report["rows"] if r["gold"] == "NO LIENS FOUND" and r["fineprint"] == "UNKNOWN")
report["fineprint_unknown_where_gold_clean"] = conservative

if "tool_agent" in SYSTEMS and any(r["tool_agent"] is None for r in report["rows"]):
    # Same-subset comparison: every system scored on only the models the tool agent finished.
    gi = {g["id"]: g for g in gold}
    sub = [r for r in report["rows"] if r["tool_agent"] is not None]
    report["same_subset_as_tool_agent"] = {
        "n": len(sub),
        "missing_ids": [r["id"] for r in report["rows"] if r["tool_agent"] is None],
        "note": "Verdict metrics only (stored rows keep verdicts, not families).",
        "systems": {n: score([(gi[r["id"]], {"verdict": r[n]}) for r in sub], with_families=False) for n in SYSTEMS},
    }

if "tool_agent" in SYSTEMS:
    # Cost and latency: the agent's stored runs against one FinePrint lookup per model, timed now.
    import statistics
    import time
    every = [_runs[g["id"]] for g in gold if g["id"] in _runs]
    runs = [r for r in every if _finished(r)]
    tok = {k: sum(r["usage"][k] for r in every) for k in ("input", "cache_write", "cache_read", "output")}
    fp_ms = []
    for g in gold:
        t = time.perf_counter()
        examine(g["id"])
        fp_ms.append((time.perf_counter() - t) * 1000)
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]  # noqa: E731
    walls = [r["wall_s"] for r in runs]
    calls = [r["tool_calls"] for r in runs]
    report["tool_agent_cost"] = {
        "config": ta.load_runs().get("config"),
        "models_finished": len(runs),
        "models_attempted": len(every),
        "note": "tokens and cost cover every attempt, finished or not; calls and wall time cover finished runs",
        "hub_tool_calls_total": sum(calls),
        "hub_tool_calls_per_model": {"mean": round(statistics.mean(calls), 2), "median": statistics.median(calls),
                                     "max": max(calls), "hit_cap": sum(1 for c in calls if c >= ta.TOOL_CAP)},
        "llm_turns_total": sum(r["turns"] for r in runs),
        "tokens": tok,
        "cost_usd_at_5_25": round(ta.cost_usd(tok), 2),
        "wall_s_per_model": {"median": statistics.median(walls), "p90": q(walls, 0.9), "max": max(walls)},
        "errors": sorted({r["error"] for r in every if r["error"]}),
        "fineprint_ms_per_model": {"median": round(statistics.median(fp_ms), 1), "p90": round(q(fp_ms, 0.9), 1),
                                   "max": round(max(fp_ms), 1)},
    }
OUT.write_text(json.dumps(report, indent=1))
print(json.dumps(report["systems"], indent=1))
if "tool_agent_cost" in report:
    print(json.dumps(report["tool_agent_cost"], indent=1))

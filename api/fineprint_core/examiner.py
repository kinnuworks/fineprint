"""The Examiner: computes a model's verdict from its lineage. No LLM involved."""
from dataclasses import dataclass, asdict

from .graph import ro, LINEAGE_TYPES
from .hub_live import looks_derived, lookup
from .licenses import LICENSES, PERMISSIVE, UNKNOWN, recognized, restrictive

DISCLAIMER = "Flags with evidence, not legal advice. Lineage and licenses are as declared on the Hub."


@dataclass
class Lien:
    family: str
    license: str
    tier: str
    via: str
    depth: int
    clauses: list
    paths: list


def _model(model_id: str):
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN m.id, m.license, m.downloads, m.missing, m.unresolved_claims",
              {"id": model_id})
    if not rows:
        return None
    mid, lic, dl, missing, unresolved = rows[0]
    return {"id": mid, "license": lic or "", "downloads": dl or 0, "missing": bool(missing),
            "unresolved": int(unresolved or 0)}


def _ancestors(model_id: str) -> list[dict]:
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.ancestors(m, 64)", {"id": model_id})
    return list(rows[0][0]) if rows else []


def _datasets(model_ids: list[str]) -> list[dict]:
    rows = ro(
        """MATCH (m:Model)-[t:TRAINED_ON]->(d:Dataset) WHERE m.id IN $ids
           RETURN m.id, d.id, d.license, d.missing, t.source, t.quote""",
        {"ids": model_ids},
    )
    return [{"model": r[0], "dataset": r[1], "license": r[2] or "", "missing": bool(r[3]),
             "source": r[4] or "hub tag", "quote": r[5]} for r in rows]


def _dataset_paths(model_id: str, d: dict) -> list[dict]:
    """Route from the model to a dataset: up the lineage to the model that trained on it, then TRAINED_ON."""
    up = _paths(model_id, d["model"], k=1) if d["model"] != model_id else [
        {"models": [model_id], "licenses": [None], "relations": []}]
    path = up[0] if up else {"models": [model_id, d["model"]], "licenses": [None, None], "relations": ["LINEAGE"]}
    return [{"models": path["models"] + [d["dataset"]], "licenses": path["licenses"] + [d["license"]],
             "relations": path["relations"] + ["TRAINED_ON"], "source": d["source"], "quote": d["quote"]}]


def _paths(src: str, dst: str, k: int = 3) -> list[dict]:
    rows = ro(
        """MATCH (s:Model), (t:Model) WHERE s.id = $s AND t.id = $t
           CALL algo.SPpaths({sourceNode: s, targetNode: t, relTypes: $types,
                              relDirection: 'outgoing', pathCount: $k})
           YIELD path
           RETURN [n IN nodes(path) | n.id], [n IN nodes(path) | n.license], [r IN relationships(path) | type(r)]""",
        {"s": src, "t": dst, "types": LINEAGE_TYPES, "k": k},
    )
    out, seen = [], set()
    for ids, lics, rels in sorted(rows, key=lambda r: len(r[0])):
        key = (tuple(ids), tuple(rels))
        if key not in seen:
            seen.add(key)
            out.append({"models": ids, "licenses": lics, "relations": rels})
    return out


def _parents(model_id: str) -> list[dict]:
    rows = ro("""MATCH (m:Model)-[r]->(p:Model) WHERE m.id = $id
                 RETURN p.id, p.license, p.missing, type(r)""", {"id": model_id})
    return [{"id": r[0], "license": r[1] or "", "depth": 1, "missing": bool(r[2]), "child": model_id,
             "relation": r[3]} for r in rows]


def decide(report: dict, use: str = "commercial") -> dict:
    """ALLOW, CONDITIONS or BLOCK for a given use."""
    nc = [l for l in report.get("liens", []) if not LICENSES[l["license"]].commercial] if report.get("liens") else []
    nc_contract = [l for l in nc if l["tier"] == "contractual"]
    v = report["verdict"]
    if report.get("reason") == "Not on the Hub.":
        return {"decision": "N/A", "why": "No such public model."}
    if use == "commercial" and nc_contract:
        return {"decision": "BLOCK", "why": f"Non-commercial terms from {nc_contract[0]['via']} ({nc_contract[0]['family']})."}
    if use == "commercial" and nc:
        return {"decision": "CONDITIONS", "why": f"Trained on non-commercial data ({nc[0]['via']}); get legal review before commercial use."}
    if v == "UNKNOWN":
        return {"decision": "CONDITIONS", "why": "Lineage or license unknown; review before shipping."}
    if (report.get("coverage") is not None and report["coverage"] < 1.0) and v == "NO LIENS FOUND":
        return {"decision": "CONDITIONS", "why": "Part of the chain has no recognised license; review before shipping."}
    if report.get("unresolved_card_claims") and v == "NO LIENS FOUND":
        return {"decision": "CONDITIONS", "why": "The model card names a base model or dataset that isn't on the Hub; review it before shipping."}
    if v in ("CLOUDED", "LIENS"):
        n = sum(len(l["clauses"]) for l in report["liens"])
        return {"decision": "CONDITIONS", "why": f"{n} obligations to meet before shipping."}
    return {"decision": "ALLOW", "why": "Nothing restricted found upstream."}


OBLIGATIONS = """
MATCH (m:Model) WHERE m.id = $id
WITH lineage.ancestors(m, 64) AS anc
UNWIND anc AS a
MATCH (x:Model) WHERE x.id = a.id
WITH x, a
MATCH (x)-[:LICENSED_UNDER]->(l:License)-[:IMPOSES]->(c:Clause)
WHERE l.permissive = false
WITH l, c, a ORDER BY a.depth
RETURN l.key, l.family, l.commercial, head(collect(a.id)), min(a.depth),
       collect(DISTINCT {code: c.code, obligation: c.obligation, quote: c.quote, source: c.source, tier: c.tier})
"""


def _graph_obligations(model_id: str) -> dict[str, dict]:
    """Restricted licenses anywhere up the lineage and the clauses they impose, read from the graph."""
    out = {}
    for key, family, commercial, via, depth, clauses in ro(OBLIGATIONS, {"id": model_id}):
        out[key] = {"family": family, "commercial": commercial, "via": via, "depth": depth, "clauses": clauses}
    return out


def _own_clauses(key: str) -> list[dict]:
    rows = ro("""MATCH (l:License)-[:IMPOSES]->(c:Clause) WHERE l.key = $k
                 RETURN collect({code: c.code, obligation: c.obligation, quote: c.quote, source: c.source, tier: c.tier})""",
              {"k": key})
    return rows[0][0] if rows else []


def _unknown(model_id: str, reason: str, detail: str, **extra) -> dict:
    return {"model": model_id, "declared_license": extra.pop("declared", None), "verdict": "UNKNOWN",
            "reason": reason, "detail": detail, "coverage": 0.0, "ancestors": [], "liens": [],
            "datasets": [], "graph": True, "disclaimer": DISCLAIMER, **extra}


def _descendant_count(model_id: str) -> int:
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64)", {"id": model_id}, timeout=60000)
    return rows[0][0]["count"] if rows else 0


def examine(model_id: str, use_graph: bool = True) -> dict:
    m = _model(model_id)
    seed_bases: list[str] = []
    live = False
    if m is None:
        info = lookup(model_id)
        if info is None:
            return _unknown(model_id, "Not on the Hub.",
                            "Hugging Face has no public model with this id. Check the spelling, or the model is private or gated.")
        if "error" in info:
            return _unknown(model_id, "Hugging Face did not answer.", "Try again in a minute.")
        m = {"id": model_id, "license": info["license"] or "", "downloads": info["downloads"], "missing": False}
        seed_bases = [b for b in info["bases"] if b != model_id]
        live = True

    if m["missing"]:
        direct = ro("MATCH (c:Model)-[:FINETUNE_OF|ADAPTER_OF|MERGE_OF|QUANTIZED_FROM]->(m:Model) WHERE m.id = $id RETURN count(c)",
                    {"id": model_id})[0][0]
        n = _descendant_count(model_id)
        return _unknown(model_id, "Deleted from the Hub.",
                        f"This model is no longer on Hugging Face. {direct:,} models still declare it as their direct base, "
                        f"and {n:,} sit below it in total. Its license and lineage can no longer be checked.",
                        descendants=n, direct_children=direct)

    declared = m["license"]
    if use_graph:
        if live:
            ancestors = []
            for b in seed_bases:
                bm = _model(b)
                ancestors.append({"id": b, "license": (bm or {}).get("license", ""), "depth": 1,
                                  "missing": bool((bm or {}).get("missing")), "child": model_id, "relation": "BASE_MODEL"})
                for a in _ancestors(b) if bm else []:
                    ancestors.append({**a, "depth": a["depth"] + 1})
        else:
            ancestors = _ancestors(model_id)
    else:
        ancestors = _parents(model_id) if not live else []

    liens = []
    if use_graph and not live:
        # Obligations composed in the graph: lineage walk -> LICENSED_UNDER -> IMPOSES.
        for key, ob in sorted(_graph_obligations(model_id).items(), key=lambda kv: kv[1]["depth"]):
            liens.append(Lien(family=ob["family"], license=key, tier="contractual", via=ob["via"], depth=ob["depth"],
                              clauses=ob["clauses"], paths=_paths(model_id, ob["via"])))
    else:
        nearest: dict[str, dict] = {}
        for a in ancestors:
            lic = restrictive(a.get("license"))
            if lic and (lic.key not in nearest or a["depth"] < nearest[lic.key]["depth"]):
                nearest[lic.key] = a
        for key, a in sorted(nearest.items(), key=lambda kv: kv[1]["depth"]):
            lic = restrictive(key)
            liens.append(Lien(family=lic.family, license=key, tier="contractual", via=a["id"], depth=a["depth"],
                              clauses=[asdict(c) for c in lic.clauses], paths=[]))
    own = restrictive(declared)
    if own and own.key not in {l.license for l in liens}:
        liens.insert(0, Lien(family=own.family, license=own.key, tier="contractual", via=model_id, depth=0,
                             clauses=_own_clauses(own.key) or [asdict(c) for c in own.clauses], paths=[]))

    depth_of = {model_id: 0, **{a["id"]: a["depth"] for a in ancestors}}
    datasets = _datasets(list(depth_of)) if use_graph else []
    seen_ds = set()
    for d in sorted(datasets, key=lambda d: depth_of.get(d["model"], 0)):
        lic = restrictive(d["license"])
        if not lic or d["dataset"] in seen_ds:
            continue
        seen_ds.add(d["dataset"])
        liens.append(Lien(
            family=lic.family, license=lic.key, tier="contested", via=d["dataset"],
            depth=depth_of.get(d["model"], 0) + 1,
            clauses=[{**asdict(c), "tier": "contested"} for c in lic.clauses],
            paths=_dataset_paths(model_id, d),
        ))

    deleted = [a["id"] for a in ancestors if a.get("missing")]
    if not use_graph:
        coverage = None
    elif ancestors:
        known = [a for a in ancestors if recognized(a.get("license")) and not a.get("missing")]
        coverage = round(len(known) / len(ancestors), 3)
    else:
        coverage = 0.0 if looks_derived(model_id) else None
    contractual = [l for l in liens if l.depth > 0 and l.tier == "contractual"]
    unknown_up = [a for a in ancestors if not recognized(a.get("license")) and not a.get("missing")]

    other_family = own and contractual and all(l.family != own.family for l in contractual)
    if declared in PERMISSIVE and contractual:
        verdict, reason = "CLOUDED", "Declared license differs from upstream terms."
    elif other_family:
        verdict, reason = "CLOUDED", f"Declares {own.family} terms; upstream terms are {contractual[0].family}."
    elif liens:
        verdict, reason = "LIENS", ("Obligations carried down from upstream." if any(l.depth for l in liens)
                                    else "Obligations from this model's own license.")
    elif not use_graph and declared in UNKNOWN:
        verdict, reason = "UNKNOWN", "No declared license."
    elif not use_graph and not recognized(declared):
        verdict, reason = "UNKNOWN", f"License '{declared}' is not in FinePrint's library, so its terms aren't checked."
    elif not use_graph and unknown_up:
        a = unknown_up[0]
        verdict, reason = "UNKNOWN", (f"Upstream model {a['id']} uses '{a['license']}', which FinePrint's library doesn't cover."
                                      if a["license"] else f"Upstream model {a['id']} declares no license.")
    elif not use_graph:
        verdict, reason = "NO LIENS FOUND", "Direct parents only, as the model page shows; nothing restricted one hop up."
    elif not ancestors and looks_derived(model_id):
        verdict, reason = "UNKNOWN", "Lineage not declared. This looks like a derived model, but it names no base model."
    elif declared in UNKNOWN and not ancestors:
        verdict, reason = "UNKNOWN", "No declared license and no declared lineage."
    elif declared in UNKNOWN:
        verdict, reason = "UNKNOWN", "No declared license."
    elif not recognized(declared):
        verdict, reason = "UNKNOWN", f"License '{declared}' is not in FinePrint's library, so its terms aren't checked."
    elif deleted:
        verdict, reason = "UNKNOWN", "An ancestor was deleted from the Hub, so part of the chain can't be checked."
    elif unknown_up:
        a = unknown_up[0]
        verdict, reason = "UNKNOWN", (f"Upstream model {a['id']} uses '{a['license']}', which FinePrint's library doesn't cover."
                                      if a["license"] else f"Upstream model {a['id']} declares no license.")
    elif coverage is not None and coverage < 1.0:
        verdict, reason = "NO LIENS FOUND", "Nothing restricted found, but some ancestors have no declared license."
    elif not ancestors:
        verdict, reason = "NO LIENS FOUND", "No base model declared; treated as an original upload."
    else:
        verdict, reason = "NO LIENS FOUND", "No restrictive terms found anywhere upstream."

    return {
        "model": m["id"],
        "declared_license": declared or None,
        "downloads_30d": m["downloads"],
        "verdict": verdict,
        "reason": reason,
        "coverage": coverage,
        "ancestors": ancestors,
        "deleted_ancestors": deleted,
        "unresolved_card_claims": m.get("unresolved", 0),
        "liens": [asdict(l) for l in liens],
        "datasets": datasets,
        "graph": use_graph,
        "mode": "full lineage" if use_graph else "direct parents only",
        "source": "live Hub lookup" if live else "graph",
        "disclaimer": DISCLAIMER,
    }


def substitutes(model_id: str, k: int = 5, spread: float = 0.35) -> dict:
    """Most-downloaded original models of the same task and size whose whole chain is clean.

    Clean is computed in the graph (no restricted or contested terms anywhere upstream);
    size uses the model's own parameter count; quantized and adapter repos are left out;
    languages must overlap when both sides declare any.
    """
    rows = ro(
        """MATCH (m:Model) WHERE m.id = $id
           WITH m, m.params * (1 - $s) AS lo, m.params * (1 + $s) AS hi
           MATCH (c:Model) WHERE c.task = m.task AND c.task <> '' AND c.license IN $perm
                 AND size(c.inherits) = 0 AND size(c.contested) = 0
                 AND c.own_params >= lo AND c.own_params <= hi AND c.own_params > 0 AND c.id <> m.id
                 AND NOT (c)-[:QUANTIZED_FROM|ADAPTER_OF]->()
                 AND (size(m.languages) = 0 OR size(c.languages) = 0 OR any(l IN c.languages WHERE l IN m.languages))
           RETURN m.task, m.params, c.id, c.license, c.own_params, c.downloads, c.languages
           ORDER BY c.downloads DESC LIMIT """ + str(int(k) * 4),
        {"id": model_id, "s": spread, "perm": sorted(PERMISSIVE)},
    )
    rows = [r for r in rows if not looks_derived(r[2])][: int(k)]
    if not rows:
        return {"model": model_id, "substitutes": [], "note": "No clean model with the same task and a similar size."}
    task, size = rows[0][0], rows[0][1]
    return {
        "model": model_id, "task": task, "params": size,
        "substitutes": [{"id": r[2], "license": r[3], "params": r[4], "downloads_30d": r[5], "languages": r[6]} for r in rows],
    }

"""Org rulings: decisions a company's legal team records once, applied to every later check.

Each ruleset lives in its own FalkorDB graph, `org:<slug>`, so one org never sees another's
rulings and the public `hub` graph is never written. A graph holds `(:Ruling)` nodes; a newer
ruling on the same scope, target and use points at the one it replaces with `[:SUPERSEDES]`.

How rulings change a decision (fail closed):
- A reject on a license in the liens, the declared license, the model itself or any ancestor
  makes the decision BLOCK.
- An approve never lifts BLOCK. It lifts CONDITIONS to ALLOW only when every lien is covered by
  an approve for this use and nothing else caused CONDITIONS (full coverage, no UNKNOWN, no
  unresolved card claims, no deleted ancestors, no contested dataset terms).
"""
import re
import uuid
from datetime import datetime, timezone

from .graph import db, ro
from .licenses import ALIASES

SLUG_RE = re.compile(r"^[a-z0-9-]{3,40}$")
SCOPES = ("license", "model")
EFFECTS = ("approve", "reject")
USES = ("commercial", "non-commercial", "any")
MAX_RULINGS = 200
MAX_RULESETS = 200

_ready: set[str] = set()


class RulingError(ValueError):
    """Bad input for a ruling. The message is safe to show to the caller."""


def graph_name(slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        raise RulingError("ruleset must match ^[a-z0-9-]{3,40}$")
    return f"org:{slug}"


def _graph(slug: str):
    return db().select_graph(graph_name(slug))


def _exists(slug: str) -> bool:
    return graph_name(slug) in db().list_graphs()


def _setup(slug: str) -> None:
    if slug in _ready:
        return
    g = _graph(slug)
    for fn in (lambda: g.create_node_range_index("Ruling", "target"),
               lambda: g.create_node_range_index("Ruling", "id"),
               lambda: g.create_node_unique_constraint("Ruling", "id")):
        try:
            fn()
        except Exception:
            pass  # already there
    _ready.add(slug)


def norm_use(use: str | None) -> str:
    """The report API says 'noncommercial'; rulings say 'non-commercial'."""
    u = (use or "").strip().lower()
    return "non-commercial" if u in ("noncommercial", "non-commercial") else u


FIELDS = ("id", "scope", "target", "effect", "use", "conditions", "note", "by", "at")
RETURN = "RETURN " + ", ".join(f"r.{f}" for f in FIELDS)


def _row(row, superseded_by=None) -> dict:
    d = dict(zip(FIELDS, row))
    if superseded_by is not None:
        d["superseded_by"] = superseded_by
    return d


def list_rulings(slug: str) -> list[dict]:
    """Every ruling in the ruleset, newest first. Superseded ones carry `superseded_by`."""
    if not _exists(slug):
        return []
    rows = _graph(slug).ro_query(
        "MATCH (r:Ruling) OPTIONAL MATCH (n:Ruling)-[:SUPERSEDES]->(r) "
        + RETURN + ", n.id ORDER BY r.at DESC").result_set
    return [_row(r[:-1], r[-1]) for r in rows]


def active_for(slug: str, targets: list[str]) -> list[dict]:
    """Rulings in force on any of `targets` (index lookup on Ruling.target)."""
    if not targets or not _exists(slug):
        return []
    rows = _graph(slug).ro_query(
        "MATCH (r:Ruling) WHERE r.target IN $t AND NOT ()-[:SUPERSEDES]->(r) " + RETURN + " ORDER BY r.at DESC",
        {"t": sorted(set(targets))}).result_set
    return [_row(r) for r in rows]


def _check_target(scope: str, target: str) -> str:
    if scope == "license":
        key = ALIASES.get(target.lower(), target.lower())
        if not ro("MATCH (l:License) WHERE l.key = $k RETURN l.key", {"k": key}):
            raise RulingError(f"no License '{target}' in the hub graph")
        return key
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN m.id", {"id": target})
    if not rows:
        raise RulingError(f"no Model '{target}' in the hub graph")
    return rows[0][0]


def create(slug: str, scope: str, target: str, effect: str, use: str, note: str,
           conditions: str | None = None, by: str | None = None) -> dict:
    """Validate and record a ruling. Returns it, with `supersedes` listing replaced ruling ids."""
    graph_name(slug)
    scope, effect, use = (scope or "").strip().lower(), (effect or "").strip().lower(), norm_use(use)
    target, note = (target or "").strip(), (note or "").strip()
    conditions, by = (conditions or "").strip(), (by or "").strip()
    if scope not in SCOPES:
        raise RulingError(f"scope must be one of {SCOPES}")
    if effect not in EFFECTS:
        raise RulingError(f"effect must be one of {EFFECTS}")
    if use not in USES:
        raise RulingError(f"use must be one of {USES}")
    if not target or len(target) > 200:
        raise RulingError("target is required (a License key or a Model id)")
    if not note or len(note) > 500:
        raise RulingError("note is required, at most 500 characters")
    if len(conditions) > 500 or len(by) > 80:
        raise RulingError("conditions at most 500 characters, by at most 80")
    target = _check_target(scope, target)
    if not _exists(slug):
        orgs = [g for g in db().list_graphs() if g.startswith("org:")]
        if len(orgs) >= MAX_RULESETS:
            raise RulingError("too many rulesets on this server")
    elif _graph(slug).ro_query("MATCH (r:Ruling) RETURN count(r)").result_set[0][0] >= MAX_RULINGS:
        raise RulingError(f"a ruleset holds at most {MAX_RULINGS} rulings")
    _setup(slug)
    r = {"id": "r-" + uuid.uuid4().hex[:10], "scope": scope, "target": target, "effect": effect, "use": use,
         "conditions": conditions, "note": note, "by": by,
         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    g = _graph(slug)
    g.query("CREATE (:Ruling {id: $id, scope: $scope, target: $target, effect: $effect, use: $use, "
            "conditions: $conditions, note: $note, by: $by, at: $at})", r)
    rows = g.query("""MATCH (n:Ruling {id: $id}), (o:Ruling)
                      WHERE o.target = $target AND o.scope = $scope AND o.use = $use AND o.id <> $id
                            AND NOT ()-[:SUPERSEDES]->(o)
                      CREATE (n)-[:SUPERSEDES]->(o) RETURN o.id""", r).result_set
    return {**r, "supersedes": [x[0] for x in rows]}


def delete(slug: str, ruling_id: str) -> bool:
    """Remove one ruling. A ruling it had superseded comes back into force."""
    if not _exists(slug):
        return False
    res = _graph(slug).query("MATCH (r:Ruling {id: $id}) DETACH DELETE r", {"id": ruling_id})
    return res.nodes_deleted > 0


def drop(slug: str) -> None:
    """Delete the whole ruleset graph (tests and cleanup)."""
    if _exists(slug):
        _graph(slug).delete()
    _ready.discard(slug)


def _uses(ruling: dict, use: str) -> bool:
    return ruling["use"] in ("any", norm_use(use))


def apply(report: dict, decision: dict, use: str, slug: str) -> dict:
    """Apply ruleset `slug` to a report and its decision.

    Returns {"decision", "why", "org"}; `org` lists the rulings that changed the decision
    (`applied`) and the ones that matched but could not (`not_applied`), each with a reason.
    """
    before, why_before = decision["decision"], decision["why"]
    org = {"org": slug, "applied": [], "not_applied": [], "decision_before": before, "decision_after": before}
    if before == "N/A":
        return {**decision, "org": org}
    model = report["model"]
    ancestors = [a["id"] for a in report.get("ancestors") or []]
    liens = report.get("liens") or []
    lien_keys = {l["license"] for l in liens}
    lic_keys = lien_keys | ({report["declared_license"]} if report.get("declared_license") else set())
    found = [r for r in active_for(slug, [model, *ancestors, *lic_keys]) if _uses(r, use)]

    def matches(r: dict) -> str | None:
        if r["scope"] == "model" and r["target"] == model:
            return f"model {model} itself"
        if r["scope"] == "model" and r["effect"] == "reject" and r["target"] in ancestors:
            return f"ancestor {r['target']}"
        if r["scope"] == "license" and r["target"] in lien_keys:
            return f"license {r['target']} in the liens"
        if r["scope"] == "license" and r["effect"] == "reject" and r["target"] in lic_keys:
            return f"declared license {r['target']}"
        return None

    hits = [(r, m) for r in found if (m := matches(r))]
    rejects = sorted([h for h in hits if h[0]["effect"] == "reject"], key=lambda h: h[0]["scope"] != "model")
    approves = [h for h in hits if h[0]["effect"] == "approve"]

    if rejects:
        first = rejects[0][0]
        org["applied"] = [{**r, "why": f"Rejects {m}."} for r, m in rejects]
        org["not_applied"] = [{**r, "why": "A reject ruling takes precedence."} for r, _ in approves]
        org["decision_after"] = "BLOCK"
        return {"decision": "BLOCK", "why": first["note"], "org": org}

    if not approves:
        return {**decision, "org": org}
    blocker = None
    if before == "BLOCK":
        blocker = "Approvals never lift BLOCK; only a new reject or a change upstream can."
    elif before == "ALLOW":
        blocker = "Decision was already ALLOW."
    elif report.get("verdict") not in ("LIENS", "CLOUDED"):
        blocker = f"Verdict is {report.get('verdict')}; an approval only covers known liens."
    elif report.get("coverage") is None or report["coverage"] < 1.0:
        blocker = "Part of the chain has no recognised license."
    elif report.get("unresolved_card_claims"):
        blocker = "The model card names a base model or dataset that isn't on the Hub."
    elif report.get("deleted_ancestors"):
        blocker = "An ancestor was deleted from the Hub."
    elif any(l["tier"] != "contractual" for l in liens):
        blocker = "Contested terms from training data still need review."
    else:
        model_ok = any(r["scope"] == "model" for r, _ in approves)
        approved = {r["target"] for r, _ in approves if r["scope"] == "license"}
        left = sorted(lien_keys - approved)
        if not model_ok and left:
            blocker = f"No approval covers {', '.join(left)}."
    if blocker:
        org["not_applied"] = [{**r, "why": blocker} for r, _ in approves]
        return {"decision": before, "why": why_before, "org": org}

    org["applied"] = [{**r, "why": f"Approves {m}."} for r, m in approves]
    org["decision_after"] = "ALLOW"
    conds = "; ".join(dict.fromkeys(r["conditions"].rstrip(".") for r, _ in approves if r["conditions"]))
    why = (f"Approved by org rulings. Conditions: {conds}." if conds
           else f"Approved by org rulings: {approves[0][0]['note']}")
    return {"decision": "ALLOW", "why": why, "org": org}

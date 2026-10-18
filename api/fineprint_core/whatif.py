"""Live what-if: relicense a base model on a GRAPH.COPY of its family and re-walk the lineage.

1. The family is the root and every model below it, with the lineage edges between them. It is
   written once to `family:<slug>` and reused after that.
2. Each request copies it with GRAPH.COPY to `whatif:<uuid>`, sets the root's license on the
   copy, walks "models under the old license, and everything below them" on both graphs, and
   deletes the copy in a `finally`. The `hub` graph is never written.
"""
import re
import threading
import time
import uuid

from .graph import LINEAGE_TYPES, ro, whatif_db
from .licenses import LICENSES, PERMISSIVE

DEFAULT_ROOT = "black-forest-labs/FLUX.1-dev"
DEFAULT_LICENSE = "apache-2.0"
MAX_FAMILY = 120_000
CHUNK = 5000
MAX_CONCURRENT = 2

_running = threading.BoundedSemaphore(MAX_CONCURRENT)
_build_locks: dict[str, threading.Lock] = {}
_build_guard = threading.Lock()


def _non_commercial(key: str) -> bool:
    lic = LICENSES.get(key)
    return bool(lic is not None and getattr(lic, "commercial", True) is False)


class WhatIfError(ValueError):
    """Bad input; the message is safe to show. `status` is the HTTP code to answer with."""

    def __init__(self, msg: str, status: int = 422):
        super().__init__(msg)
        self.status = status


def slug(model_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model_id.lower()).strip("-")[:80]


def family_graph(model_id: str) -> str:
    return f"family:{slug(model_id)}"


def _exists(name: str) -> bool:
    # EXISTS instead of GRAPH.LIST: the fp-whatif user can only see its own key patterns.
    return bool(whatif_db().connection.exists(name))


def _complete(name: str) -> bool:
    """A family graph counts only once its (:Family) marker, written last, is there."""
    return _exists(name) and bool(
        whatif_db().select_graph(name).ro_query("MATCH (f:Family) RETURN count(f)").result_set[0][0])


def graph_copy(src: str, dst: str, wait: float = 30.0) -> None:
    """GRAPH.COPY forks the server. Redis runs one child at a time, so while a snapshot save is
    running the copy is refused with "could not fork"; wait and try again."""
    end = time.time() + wait
    while True:
        try:
            whatif_db().connection.execute_command("GRAPH.COPY", src, dst)
            return
        except Exception as e:
            if "could not fork" not in str(e) or time.time() > end:
                raise
            time.sleep(0.25)


def _root(model_id: str) -> tuple[str, str]:
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN m.id, m.license", {"id": model_id})
    if not rows:
        raise WhatIfError(f"no Model '{model_id}' in the hub graph", 404)
    mid, lic = rows[0]
    if (lic or "") not in LICENSES:
        raise WhatIfError(f"{mid} is under '{lic}', which is not a restricted license; "
                          "pick a root whose license carries terms down to derivatives")
    return mid, lic


def build_family(root_id: str) -> tuple[str, float, bool]:
    """Write `family:<slug>` from hub if it is not there yet. Returns (graph, seconds, cached)."""
    name = family_graph(root_id)
    with _build_guard:
        lock = _build_locks.setdefault(name, threading.Lock())
    with lock:
        if _complete(name):
            return name, 0.0, True
        t = time.time()
        ids = ro("MATCH (r:Model) WHERE r.id = $id RETURN lineage.descendantIds([r])", {"id": root_id},
                 timeout=120000)[0][0]
        members = [root_id] + list(ids)
        if len(members) > MAX_FAMILY:
            raise WhatIfError(f"{root_id} has {len(members):,} models in its family; the live what-if is capped "
                              f"at {MAX_FAMILY:,}")
        nodes, edges = [], []
        rel = "|".join(LINEAGE_TYPES)
        for i in range(0, len(members), CHUNK):
            chunk = members[i:i + CHUNK]
            nodes += ro("MATCH (m:Model) WHERE m.id IN $ids RETURN m.id, m.license, m.downloads",
                        {"ids": chunk}, timeout=120000)
            edges += ro(f"MATCH (c:Model)-[r:{rel}]->(p:Model) WHERE c.id IN $ids RETURN c.id, type(r), p.id",
                        {"ids": chunk}, timeout=120000)
        member_set = set(members)
        edges = [e for e in edges if e[2] in member_set]
        g = whatif_db().select_graph(name)
        if _exists(name):
            g.delete()  # left half-built by an earlier failure
        try:
            g.query("CREATE INDEX FOR (m:Model) ON (m.id)")
            for i in range(0, len(nodes), 20000):
                g.query("UNWIND $rows AS r CREATE (:Model {id: r[0], license: r[1], downloads: r[2]})",
                        {"rows": [list(n) for n in nodes[i:i + 20000]]}, timeout=120000)
            for t_ in LINEAGE_TYPES:
                rows = [[c, p] for c, r, p in edges if r == t_]
                for i in range(0, len(rows), 20000):
                    g.query(f"UNWIND $rows AS r MATCH (c:Model) WHERE c.id = r[0] MATCH (p:Model) WHERE p.id = r[1] "
                            f"CREATE (c)-[:{t_}]->(p)", {"rows": rows[i:i + 20000]}, timeout=120000)
            g.query("CREATE (:Family {root: $root, license: $lic, models: $n, edges: $e, built_at: timestamp()})",
                    {"root": root_id, "lic": next((n[1] for n in nodes if n[0] == root_id), None), "n": len(nodes), "e": len(edges)})
        except Exception:
            try:
                g.delete()
            except Exception:
                pass
            raise
        return name, round(time.time() - t, 3), False


def _walk(g, lic: str) -> dict:
    """Models labelled `lic`, and every model below at least one of them."""
    n, below = g.ro_query("MATCH (r:Model) WHERE r.license = $lic WITH collect(r) AS roots "
                          "RETURN size(roots), size(lineage.descendantIds(roots))", {"lic": lic},
                          timeout=120000).result_set[0]
    return {"models_under_restricted": n, "models_below_one": below, "affected_total": n + below}


def simulate(root_id: str | None = None, to_license: str | None = None) -> dict:
    root_id = (root_id or DEFAULT_ROOT).strip().removeprefix("https://huggingface.co/").strip("/")
    to_license = (to_license or DEFAULT_LICENSE).strip().lower()
    if to_license not in PERMISSIVE and to_license not in LICENSES:
        raise WhatIfError(f"unknown license '{to_license}'; use a key such as apache-2.0, mit or llama3.1")
    root_id, from_license = _root(root_id)
    if to_license == from_license:
        raise WhatIfError(f"{root_id} is already under {from_license}")
    if not _running.acquire(timeout=20):
        raise WhatIfError("two simulations are already running; try again in a few seconds", 429)
    try:
        return _simulate(root_id, from_license, to_license)
    finally:
        _running.release()


def _simulate(root_id: str, from_license: str, to_license: str) -> dict:
    t0 = time.time()
    fam_name, fam_s, cached = build_family(root_id)
    d = whatif_db()
    fam = d.select_graph(fam_name)
    info = fam.ro_query("MATCH (f:Family) RETURN f.models, f.edges").result_set
    models, edges = info[0] if info else (None, None)
    copy = f"whatif:{uuid.uuid4().hex[:12]}"
    seconds = {"family": fam_s}
    try:
        t = time.time()
        graph_copy(fam_name, copy)
        seconds["graph_copy"] = round(time.time() - t, 3)
        g = d.select_graph(copy)
        t = time.time()
        g.query("MATCH (m:Model) WHERE m.id = $id SET m.license = $lic", {"id": root_id, "lic": to_license})
        seconds["edit"] = round(time.time() - t, 3)
        t = time.time()
        before, after = _walk(fam, from_license), _walk(g, from_license)
        relabel = g.ro_query("MATCH (m:Model) WHERE m.license = $lic RETURN m.id, m.license, m.downloads "
                             "ORDER BY m.downloads DESC LIMIT 10", {"lic": from_license}).result_set
        seconds["walks"] = round(time.time() - t, 3)
    finally:
        t = time.time()
        try:
            d.connection.execute_command("GRAPH.DELETE", copy)
        except Exception:
            pass
        seconds["delete"] = round(time.time() - t, 3)
    seconds["total"] = round(time.time() - t0, 3)
    still = after["affected_total"]
    labelled = after["models_under_restricted"]
    why = (f"{labelled:,} models in the family still declare {from_license} on their own cards, and "
           f"{after['models_below_one']:,} more sit below one of them. Relicensing {root_id} does not change "
           "those labels; each uploader would have to edit their card.")
    return {
        "scenario": f"{root_id} relicensed as {to_license}, on a GRAPH.COPY of its family",
        "root": root_id, "from_license": from_license, "to_license": to_license,
        "family_models": models, "family_edges": edges,
        "before": before, "after": after,
        "still_labelled_restricted_after": still,
        # Older clients read this key; it is only true when the old license is non-commercial.
        **({"still_labelled_non_commercial_after": still} if _non_commercial(from_license) else {}),
        "relabel_needed": [{"id": r[0], "license": r[1], "downloads": r[2]} for r in relabel],
        "why": why,
        "graphs": {"family": fam_name, "copy": copy},
        "seconds": seconds,
        "cached_family": cached,
    }

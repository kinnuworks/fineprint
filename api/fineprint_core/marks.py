"""Keep the cached inheritance marks (m.inherits, m.contested) right after card edges change.

scripts/audit_graph.py sets them Hub-wide: m.inherits lists the license family of every
ancestor whose license is in LICENSES, and m.contested is ["Non-commercial dataset"] when the
model or any ancestor is trained on a dataset whose license is not commercial. When the Clerk
writes or removes lineage or TRAINED_ON edges, only the touched model and the models below it
can change, so this recomputes that subtree from the graph and writes back the rows that differ.

Parents outside the subtree keep their cached marks, which the edge change cannot affect.
The walk runs level by level on internal node ids (ID(n) = x is a direct seek), which is
several times faster here than resolving thousands of string ids through the Model.id index.
"""
import logging
import time

from .graph import LINEAGE_TYPES, hub
from .licenses import LICENSES

log = logging.getLogger("fineprint.marks")

MAX_SUBTREE = 5_000
BATCH = 5000
CONTESTED = "Non-commercial dataset"
FAMILY_ORDER = list(dict.fromkeys(lic.family for lic in LICENSES.values()))
FAMILY_OF = {k: lic.family for k, lic in LICENSES.items()}
NC_KEYS = sorted(k for k, lic in LICENSES.items() if not lic.commercial)
LINEAGE = "|".join(LINEAGE_TYPES)


def _ro(query: str, params: dict):
    return hub().ro_query(query, params, timeout=120000).result_set


def _chunks(items: list, n: int = BATCH):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _subtree(model_id: str) -> list[int] | None:
    """Internal ids of the model and every descendant, BFS order. None when above MAX_SUBTREE."""
    rows = _ro("MATCH (m:Model) WHERE m.id = $id RETURN ID(m)", {"id": model_id})
    if not rows:
        return []
    order = [rows[0][0]]
    seen = set(order)
    frontier = order
    while frontier:
        nxt = []
        for f in _chunks(frontier):
            for (c,) in _ro(f"UNWIND $f AS x MATCH (p) WHERE ID(p) = x MATCH (p)<-[:{LINEAGE}]-(c:Model) "
                            "RETURN DISTINCT ID(c)", {"f": f}):
                if c not in seen:
                    seen.add(c)
                    nxt.append(c)
        order.extend(nxt)
        if len(order) > MAX_SUBTREE:
            return None
        frontier = nxt
    return order


def refresh_marks(model_ids) -> dict:
    """Recompute inherits and contested for each model in `model_ids` and every descendant.

    Returns {"nodes", "updated", "seconds", "skipped"}. Subtrees above MAX_SUBTREE are skipped
    and logged; the Hub-wide audit script covers those.
    """
    t0 = time.time()
    out = {"nodes": 0, "updated": 0, "seconds": 0.0, "skipped": []}
    order: list[int] = []
    seen: set[int] = set()
    for rid in sorted({m for m in model_ids if m}):
        sub = _subtree(rid)
        if sub is None:
            log.warning("refresh_marks: %s has more than %d models below it; left to scripts/audit_graph.py",
                        rid, MAX_SUBTREE)
            out["skipped"].append(rid)
            continue
        for n in sub:
            if n not in seen:
                seen.add(n)
                order.append(n)
    if not order:
        out["seconds"] = round(time.time() - t0, 3)
        return out

    current, parents, trained = {}, {}, set()
    for ids in _chunks(order):
        for n, inh, con, nc, ps in _ro(
                "UNWIND $n AS x MATCH (c) WHERE ID(c) = x "
                "RETURN ID(c), c.inherits, c.contested, "
                "size([(c)-[:TRAINED_ON]->(d:Dataset) WHERE d.license IN $keys | 1]), "
                f"[(c)-[:{LINEAGE}]->(p:Model) | [ID(p), p.license, p.inherits, p.contested]]",
                {"n": ids, "keys": NC_KEYS}):
            current[n] = (inh or [], con or [])
            parents[n] = ps
            if nc:
                trained.add(n)

    # Fixed point over the subtree: marks only grow, so this settles; BFS order makes it quick.
    inherits: dict[int, set] = {n: set() for n in order}
    contested: dict[int, bool] = {n: n in trained for n in order}
    for _ in range(64):
        changed = False
        for n in order:
            fams, con = set(inherits[n]), contested[n]
            for p, lic, p_inh, p_con in parents.get(n, []):
                if lic in FAMILY_OF:
                    fams.add(FAMILY_OF[lic])
                if p in inherits:
                    fams |= inherits[p]
                    con = con or contested[p]
                else:
                    fams.update(p_inh or [])
                    con = con or bool(p_con)
            if fams != inherits[n] or con != contested[n]:
                inherits[n], contested[n], changed = fams, con, True
        if not changed:
            break

    rows = []
    for n in order:
        inh = [f for f in FAMILY_ORDER if f in inherits[n]]
        con = [CONTESTED] if contested[n] else []
        old = current.get(n)
        if old is None or set(old[0]) != set(inh) or list(old[1]) != con:
            rows.append({"n": n, "i": inh, "c": con})
    for batch in _chunks(rows):
        hub().query("UNWIND $rows AS r MATCH (m) WHERE ID(m) = r.n SET m.inherits = r.i, m.contested = r.c",
                    {"rows": batch})
    out.update(nodes=len(order), updated=len(rows), seconds=round(time.time() - t0, 3))
    return out

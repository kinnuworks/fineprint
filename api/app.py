"""FinePrint HTTP API."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Path as Path_, Query
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

import time

from fineprint_core.examiner import decide, examine
from fineprint_core.graph import fulltext_ready, ro

ROOT = Path(__file__).resolve().parent.parent
HEADLINE = ROOT / "data" / "derived" / "headline.json"
HEADLINE_GRAPH = ROOT / "data" / "derived" / "headline_graph.json"
RELICENSE = ROOT / "data" / "derived" / "relicense_points.json"
COMPARISON = ROOT / "data" / "derived" / "hub_api_comparison.json"

app = FastAPI(title="FinePrint", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])


@app.get("/api/health")
def health():
    """Fails closed: the graph must hold the license rules the code expects."""
    from fastapi.responses import JSONResponse
    from fineprint_core.licenses import LICENSES, PERMISSIVE
    try:
        n = ro("MATCH (m:Model) WHERE m.missing = false RETURN count(m)")[0][0]
        lic = ro("MATCH (l:License) RETURN count(l)")[0][0]
        linked = ro("MATCH (l:License {key: 'llama3.1'})<-[:LICENSED_UNDER]-(m) RETURN count(m)")[0][0]
    except Exception as e:
        return JSONResponse({"ok": False, "error": "graph unreachable", "detail": str(e)[:120]}, status_code=503)
    expected = len(LICENSES) + len(PERMISSIVE)
    ok = lic == expected and linked > 0 and n > 3_000_000
    body = {"ok": ok, "models": n, "license_nodes": lic, "license_nodes_expected": expected, "llama31_models": linked}
    return body if ok else JSONResponse(body, status_code=503)


@app.get("/api/stats")
def stats():
    """Hub-wide numbers computed in FalkorDB (headline_graph.json), plus the DuckDB cross-check."""
    g = json.loads(HEADLINE_GRAPH.read_text())
    n = g["numbers"]
    import datetime as _dt
    at = g.get("computed_at") or g.get("at") or _dt.datetime.fromtimestamp(
        HEADLINE_GRAPH.stat().st_mtime, _dt.timezone.utc).isoformat(timespec="seconds")
    out = {
        "computed_in": "FalkorDB",
        "computed_at": at,
        "computed_how": "scripts/headline_graph.py ran these queries in FalkorDB; this endpoint serves the saved result.",
        "models_total": n["models_total"][0],
        "inheriting_restricted": n["inheriting_restricted"][0],
        "inheriting_but_declare_permissive": n["inheriting_but_declare_permissive"][0],
        "their_downloads_30d": n["inheriting_but_declare_permissive"][1],
        "ship_license_file": n["of_those_ship_license_file"][0],
        "non_commercial_upstream_declare_permissive": n["non_commercial_upstream_declare_permissive"][0],
        "non_commercial_downloads_30d": n["non_commercial_upstream_declare_permissive"][1],
        "contested_only": n["contested_only"][0],
        "by_family": n["by_family"],
        "graph_audit": g,
    }
    if COMPARISON.exists():
        out["hub_api_comparison"] = json.loads(COMPARISON.read_text())
    if (ROOT / "data" / "derived" / "unsloth_share.json").exists():
        out["unsloth"] = json.loads((ROOT / "data" / "derived" / "unsloth_share.json").read_text())
    out["duckdb_cross_check"] = {"note": "Earlier count from the dump with Llama, Gemma and CC BY-NC only.",
                                 **{k: v for k, v in json.loads(HEADLINE.read_text()).items() if k != "top_by_downloads"}}
    return out


@app.get("/api/relicense-points")
def relicense_points(k: int = Query(25, ge=1, le=100)):
    d = json.loads(RELICENSE.read_text())
    return {**{x: d[x] for x in d if x != "top"}, "top": d["top"][:k]}


_lb_cache: dict = {}


@app.get("/api/load-bearing")
def load_bearing(k: int = Query(20, ge=1, le=100)):
    """PageRank over lineage edges: the base models most of the Hub stands on."""
    if "rows" not in _lb_cache or time.time() - _lb_cache["at"] > 3600:
        t = time.time()
        rows = ro("CALL algo.pageRank('Model', null) YIELD node, score "
                  "RETURN node.id, node.license, node.downloads, score ORDER BY score DESC LIMIT 25", timeout=120000)
        seconds = round(time.time() - t, 2)
        top = []
        for mid, lic, dl, score in rows:
            st = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64)", {"id": mid}, timeout=60000)[0][0]
            top.append({"id": mid, "license": lic, "downloads_30d": dl, "score": score,
                        "descendants": st["count"], "descendant_downloads_30d": st["downloads"]})
        _lb_cache.update(rows=top, at=time.time(), seconds=seconds)
    return {"seconds": _lb_cache["seconds"], "query": "CALL algo.pageRank('Model', null)",
            "note": "PageRank counts automated upload farms too; compare descendant_downloads_30d.",
            "top": _lb_cache["rows"][:k]}


RULESET = "^[a-z0-9-]{3,40}$"


def _decided(model_id: str, graph: bool, use: str, ruleset: str | None) -> dict:
    r = examine(model_id, use_graph=graph)
    d = decide(r, use)
    if ruleset:
        from fineprint_core.rulings import apply
        d = apply(r, d, use, ruleset)
    return {**r, "use": use, **d}


@app.get("/api/report/{org}/{name}")
def report(org: str, name: str, graph: bool = Query(True), use: str = Query("commercial", pattern="^(commercial|noncommercial)$"),
           ruleset: str | None = Query(None, pattern=RULESET)):
    """`org` here is the Hugging Face namespace. `ruleset` names the org rulings to apply."""
    return _decided(f"{org}/{name}", graph, use, ruleset)


@app.get("/api/report/{name}")
def report_single(name: str, graph: bool = Query(True), use: str = Query("commercial", pattern="^(commercial|noncommercial)$"),
                  ruleset: str | None = Query(None, pattern=RULESET)):
    return _decided(name, graph, use, ruleset)


class RulingIn(BaseModel):
    scope: str
    target: str
    effect: str
    use: str = "any"
    note: str
    conditions: str | None = None
    by: str | None = None


_ruling_calls: list[float] = []


def _ruling_write(ruleset: str) -> None:
    """Rate limit for ruling writes, and keep the shared demo ruleset read-only."""
    import os
    protected = {s.strip() for s in os.environ.get("FINEPRINT_PROTECTED_RULESETS", "acme-legal").split(",") if s.strip()}
    if ruleset in protected and os.environ.get("FINEPRINT_RULINGS_OPEN") != "1":
        raise HTTPException(403, f"Ruleset '{ruleset}' is the shared demo and is read-only here; use your own slug.")
    now = time.time()
    _ruling_calls[:] = [t for t in _ruling_calls if now - t < 60]
    if len(_ruling_calls) >= 20:
        raise HTTPException(429, "Too many ruling changes this minute; try again shortly.")
    _ruling_calls.append(now)


@app.post("/api/rulings/{ruleset}")
def create_ruling(body: RulingIn, ruleset: str = Path_(..., pattern=RULESET)):
    from fineprint_core import rulings
    _ruling_write(ruleset)
    try:
        return rulings.create(ruleset, **body.model_dump())
    except rulings.RulingError as e:
        raise HTTPException(422, str(e))


@app.get("/api/rulings/{ruleset}")
def list_rulings(ruleset: str = Path_(..., pattern=RULESET)):
    from fineprint_core import rulings
    rows = rulings.list_rulings(ruleset)
    return {"ruleset": ruleset, "graph": rulings.graph_name(ruleset), "count": len(rows), "rulings": rows}


@app.delete("/api/rulings/{ruleset}/{ruling_id}")
def delete_ruling(ruling_id: str, ruleset: str = Path_(..., pattern=RULESET)):
    from fineprint_core import rulings
    _ruling_write(ruleset)
    if not rulings.delete(ruleset, ruling_id):
        raise HTTPException(404, "no such ruling")
    return {"deleted": ruling_id}


@app.get("/api/descendants/{org}/{name}")
def descendants(org: str, name: str, k: int = Query(50, ge=1, le=500)):
    mid = f"{org}/{name}"
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64), lineage.topDescendants(m, $k)",
              {"id": mid, "k": k}, timeout=60000)
    if not rows:
        raise HTTPException(404, "not in graph")
    stats_, top = rows[0]
    return {"model": mid, "stats": stats_, "top": top}


def fulltext_query(q: str) -> str | None:
    """Turn free text into a RediSearch query on the Model.id fulltext index: every token must
    match, the last one as a prefix. Tokens are alphanumeric only, so nothing needs escaping."""
    import re
    toks = [t for t in re.split(r"[^a-z0-9]+", q.lower()) if t]
    if not toks:
        return None
    if len(toks[-1]) >= 2:
        toks[-1] += "*"
    return " ".join(toks[:12])


@app.get("/api/search")
def search(q: str = Query(..., min_length=2, max_length=200), limit: int = Query(10, ge=1, le=50)):
    """Exact id first (range index), then the fulltext index on Model.id, most downloaded first."""
    q = q.strip().removeprefix("https://huggingface.co/").strip("/")
    exact = ro("MATCH (m:Model) WHERE m.id = $q AND m.missing = false RETURN m.id, m.license, m.downloads", {"q": q})
    ftq = fulltext_query(q) if fulltext_ready() else None
    rows = []
    if ftq:
        try:
            rows = ro("CALL db.idx.fulltext.queryNodes('Model', $ft) YIELD node WITH node AS m "
                      "WHERE m.missing = false AND m.id <> $q "
                      "RETURN m.id, m.license, m.downloads ORDER BY m.downloads DESC LIMIT " + str(int(limit)),
                      {"ft": ftq, "q": q}, timeout=20000)
        except Exception:
            rows = None  # no fulltext index in this snapshot
    if not ftq or rows is None:
        rows = ro("MATCH (m:Model) WHERE m.id CONTAINS $q AND m.missing = false AND m.id <> $q "
                  "RETURN m.id, m.license, m.downloads ORDER BY m.downloads DESC LIMIT " + str(int(limit)), {"q": q},
                  timeout=20000)
    return [{"id": r[0], "license": r[1], "downloads": r[2]} for r in (exact + rows)[: int(limit)]]


@app.get("/api/substitutes/{org}/{name}")
def substitutes_route(org: str, name: str, k: int = Query(5, ge=1, le=20)):
    from fineprint_core.examiner import substitutes
    return substitutes(f"{org}/{name}", k=k)


_card_cache: dict[str, dict] = {}
# Clerk reads recorded by scripts/record_card_reads.py, replayed when the live model call fails.
CARD_READS = ROOT / "data" / "derived" / "card_reads.json"
_card_source: dict[str, str] = {}
_recorded: dict[str, dict] = json.loads(CARD_READS.read_text()) if CARD_READS.exists() else {}
_card_calls: list[float] = []
# Any model in the graph can be read. Live reads are capped per minute (all callers) and per day
# (per process, FINEPRINT_READCARD_DAILY). Past the daily cap, models with a recorded read replay it.
READ_CARD_PER_MINUTE = 6
READ_CARD_DAILY_DEFAULT = 300
_card_day: dict[str, object] = {"day": "", "count": 0}


def _drop_clerk_edges(scope: list[str], mid: str) -> None:
    """Delete the Clerk's edges read from `mid`'s card and restore the cached marks they changed."""
    from fineprint_core.graph import hub
    from fineprint_core.marks import refresh_marks
    rows = hub().query("MATCH (m:Model)-[r]->() WHERE m.id IN $ids AND r.by = 'clerk' AND r.read_from = $id "
                       "DELETE r RETURN DISTINCT m.id", {"ids": scope, "id": mid}).result_set
    if rows:
        refresh_marks([r[0] for r in rows])


@app.post("/api/read-card/{org}/{name}")
def read_card(org: str, name: str):
    """Run the Clerk on a model card and return the verdict before and after.

    Edges the Clerk wrote for this model earlier are removed first, so "before" is
    always the verdict from Hub tags alone. Extracted claims are cached per model.
    """
    from fineprint_core.clerk import extract, record
    from fineprint_core.graph import hub
    import os
    mid = f"{org}/{name}"
    if mid not in _card_cache and mid not in _recorded and not ro(
            "MATCH (m:Model) WHERE m.id = $id AND m.missing = false RETURN m.id", {"id": mid}):
        raise HTTPException(404, f"{mid} is not in the graph.")
    now = time.time()
    replay = False
    if mid not in _card_cache:
        _card_calls[:] = [t for t in _card_calls if now - t < 60]
        if len(_card_calls) >= READ_CARD_PER_MINUTE:
            raise HTTPException(429, "Too many card reads this minute; try again shortly.")
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        if _card_day["day"] != today:
            _card_day.update(day=today, count=0)
        try:
            daily = int(os.environ.get("FINEPRINT_READCARD_DAILY", READ_CARD_DAILY_DEFAULT))
        except ValueError:
            daily = READ_CARD_DAILY_DEFAULT
        if int(_card_day["count"]) >= daily:
            if mid not in _recorded:
                raise HTTPException(429, f"This deployment has used its {daily} live card reads for today (UTC). "
                                         "Models already read today still work; try others tomorrow.")
            replay = True
        _card_calls.append(now)
    scope = [mid] + [r[0] for r in ro("MATCH (c:Model)-[]->(p:Model) WHERE c.id = $id RETURN p.id", {"id": mid})]
    _drop_clerk_edges(scope, mid)
    before = examine(mid)["verdict"]
    cached = mid in _card_cache
    source = _card_source.get(mid, "cache") if cached else "live"
    if not cached:
        try:
            if replay:
                raise RuntimeError("daily live read cap reached")
            _card_day["count"] = int(_card_day["count"]) + 1
            _card_cache[mid] = extract(mid)
        except Exception as e:
            if mid not in _recorded:
                raise HTTPException(502, f"could not read the card: {str(e)[:120]}")
            # The live call failed or was capped (no key, quota, outage): replay the recorded read.
            _card_cache[mid] = _recorded[mid]["claims"]
            source = "recorded"
        _card_source[mid] = source
    claims = _card_cache[mid]
    written = int(record(mid, claims))
    after = examine(mid)
    # The public demo puts the graph back afterwards, so every visitor starts from the Hub tags alone.
    if os.environ.get("FINEPRINT_READCARD_KEEP") != "1":
        _drop_clerk_edges(scope, mid)
    after = {**after, "use": "commercial", **decide(after, "commercial")}
    return {"model": mid, "before": before, "after": after["verdict"], "edges_written": written,
            "claims": claims, "report": after, "cached": cached, "source": source,
            "recorded_at": _recorded.get(mid, {}).get("read_at") if source == "recorded" else None, "kept": os.environ.get("FINEPRINT_READCARD_KEEP") == "1"}


_whatif_calls: list[float] = []


@app.get("/api/what-if")
def what_if(root: str | None = Query(None, max_length=200), license: str = Query("apache-2.0", max_length=60)):
    """Relicense `root` as `license` on a fresh GRAPH.COPY of its family, re-walk, delete the copy."""
    from fineprint_core import whatif
    now = time.time()
    _whatif_calls[:] = [t for t in _whatif_calls if now - t < 60]
    if len(_whatif_calls) >= 10:
        raise HTTPException(429, "Too many simulations this minute; try again shortly.")
    _whatif_calls.append(now)
    try:
        return whatif.simulate(root, license)
    except whatif.WhatIfError as e:
        raise HTTPException(e.status, str(e))

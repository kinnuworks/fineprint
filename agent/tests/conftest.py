"""Shared fixtures: a fake FinePrint API served through httpx.MockTransport."""
from __future__ import annotations

import copy

import httpx
import pytest

from fineprint import client, hub_guard as guard_mod

GEMMA_CLAUSES = [
    {"code": "gemma-3.1-1", "obligation": "Pass Gemma's use restrictions on as an enforceable term, and tell recipients.",
     "quote": "include the use restrictions referenced in Section 3.2 as an enforceable provision",
     "source": "https://ai.google.dev/gemma/terms", "tier": "contractual"},
    {"code": "gemma-3.1-4", "obligation": 'Ship a "Notice" file pointing to the Gemma Terms of Use.',
     "quote": 'must be accompanied by a "Notice" text file', "source": "https://ai.google.dev/gemma/terms",
     "tier": "contractual"},
]
LLAMA_CLAUSES = [
    {"code": "llama3.1-1bi-a", "obligation": "Ship a copy of the license agreement with the model.",
     "quote": "provide a copy of this Agreement with any such Llama Materials",
     "source": "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/main/LICENSE", "tier": "contractual"},
    {"code": "llama3.1-1bi-c", "obligation": 'Start the model name with "Llama".',
     "quote": 'include "Llama" at the beginning of any such AI model name',
     "source": "https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct/blob/main/LICENSE", "tier": "contractual"},
]
DISCLAIMER = "Flags with evidence, not legal advice. Lineage and licenses are as declared on the Hub."

REPORTS = {
    "QCRI/Fanar-2-27B-Instruct": {
        "model": "QCRI/Fanar-2-27B-Instruct", "declared_license": "apache-2.0", "downloads_30d": 193149,
        "verdict": "CLOUDED", "reason": "Declared license differs from upstream terms.", "coverage": 1.0,
        "ancestors": [{"id": "google/gemma-3-27b-pt", "license": "gemma", "depth": 1}],
        "liens": [{"family": "Gemma", "license": "gemma", "tier": "contractual", "via": "google/gemma-3-27b-pt",
                   "depth": 1, "clauses": GEMMA_CLAUSES,
                   "paths": [{"models": ["QCRI/Fanar-2-27B-Instruct", "google/gemma-3-27b-pt"],
                              "licenses": ["apache-2.0", "gemma"], "relations": ["FINETUNE_OF"]}]}],
        "graph": True, "disclaimer": DISCLAIMER,
    },
    "Qwen/Qwen2.5-7B-Instruct": {
        "model": "Qwen/Qwen2.5-7B-Instruct", "declared_license": "apache-2.0", "downloads_30d": 7045027,
        "verdict": "NO LIENS FOUND", "reason": "No restrictive terms found anywhere upstream.", "coverage": 1.0,
        "ancestors": [{"id": "Qwen/Qwen2.5-7B", "license": "apache-2.0", "depth": 1}],
        "liens": [], "graph": True, "disclaimer": DISCLAIMER,
    },
    "acme/Llama-3.1-8B-tuned": {
        "model": "acme/Llama-3.1-8B-tuned", "declared_license": "llama3.1", "downloads_30d": 10,
        "verdict": "LIENS", "reason": "Obligations carried down from upstream.", "coverage": 1.0,
        "ancestors": [{"id": "meta-llama/Llama-3.1-8B-Instruct", "license": "llama3.1", "depth": 1},
                      {"id": "meta-llama/Llama-3.1-8B", "license": "llama3.1", "depth": 2}],
        "liens": [{"family": "Llama 3.1", "license": "llama3.1", "tier": "contractual",
                   "via": "meta-llama/Llama-3.1-8B-Instruct", "depth": 1, "clauses": LLAMA_CLAUSES,
                   "paths": [{"models": ["acme/Llama-3.1-8B-tuned", "meta-llama/Llama-3.1-8B-Instruct"],
                              "licenses": ["llama3.1", "llama3.1"], "relations": ["ADAPTER_OF"]},
                             {"models": ["acme/Llama-3.1-8B-tuned", "acme/merge", "meta-llama/Llama-3.1-8B-Instruct"],
                              "licenses": ["llama3.1", None, "llama3.1"], "relations": ["MERGE_OF", "FINETUNE_OF"]}]}],
        "graph": True, "disclaimer": DISCLAIMER,
    },
}

REPORTS["acme/nc-tuned"] = {
    "model": "acme/nc-tuned", "declared_license": "apache-2.0", "downloads_30d": 5,
    "verdict": "CLOUDED", "reason": "Declared license differs from upstream terms.", "coverage": 1.0,
    "ancestors": [{"id": "acme/nc-base", "license": "cc-by-nc-4.0", "depth": 1}],
    "liens": [{"family": "CC BY-NC", "license": "cc-by-nc-4.0", "tier": "contractual", "via": "acme/nc-base",
               "depth": 1, "clauses": [
                   {"code": "cc-by-nc-4.0-nc", "obligation": "Non-commercial use only.", "quote": "NonCommercial",
                    "source": "https://creativecommons.org/licenses/by-nc/4.0/legalcode", "tier": "contractual"}],
               "paths": [{"models": ["acme/nc-tuned", "acme/nc-base"], "licenses": ["apache-2.0", "cc-by-nc-4.0"],
                          "relations": ["FINETUNE_OF"]}]}],
    "graph": True, "disclaimer": DISCLAIMER,
}
REPORTS["acme/no-license"] = {
    "model": "acme/no-license", "declared_license": None, "verdict": "UNKNOWN",
    "reason": "No declared license and no declared lineage.", "coverage": 1.0, "ancestors": [], "liens": [],
    "graph": True, "disclaimer": DISCLAIMER,
}
NONCOMMERCIAL = {"cc-by-nc-4.0"}


def decide(r: dict, use: str) -> dict:
    """Same rules as api/fineprint_core/examiner.py decide(), for the fake."""
    nc = [l for l in r.get("liens", []) if l["license"] in NONCOMMERCIAL and l["tier"] == "contractual"]
    if r.get("reason") == "Not on the Hub.":
        return {"decision": "N/A", "why": "No such public model."}
    if use == "commercial" and nc:
        return {"decision": "BLOCK", "why": f"Non-commercial terms from {nc[0]['via']} ({nc[0]['family']})."}
    if r["verdict"] == "UNKNOWN":
        return {"decision": "CONDITIONS", "why": "Lineage or license unknown; review before shipping."}
    if r["verdict"] in ("CLOUDED", "LIENS"):
        n = sum(len(l["clauses"]) for l in r["liens"])
        return {"decision": "CONDITIONS", "why": f"{n} obligations to meet before shipping."}
    return {"decision": "ALLOW", "why": "Nothing restricted found upstream."}


DESCENDANTS = {
    "QCRI/Fanar-2-27B-Instruct": {
        "model": "QCRI/Fanar-2-27B-Instruct", "stats": {"count": 4, "deepest": 1, "downloads": 796},
        "top": [{"id": "mradermacher/Fanar-2-27B-Instruct-i1-GGUF", "license": "apache-2.0", "downloads": 347, "depth": 1},
                {"id": "someone/Fanar-gemma-tagged", "license": "gemma", "downloads": 20, "depth": 1}],
    },
}


LOAD_BEARING = {"seconds": 5.59, "query": "CALL algo.pageRank('Model', null)",
                "note": "PageRank counts automated upload farms too; compare descendant_downloads_30d.",
                "top": [{"id": "black-forest-labs/FLUX.1-dev", "license": "flux-1-dev-non-commercial-license",
                         "downloads_30d": 648212, "score": 0.00861445628106594, "descendants": 43699,
                         "descendant_downloads_30d": 1487043},
                        {"id": "Qwen/Qwen1.5-0.5B", "license": "tongyi-qianwen-research", "downloads_30d": 38131,
                         "score": 0.0064245, "descendants": 32564, "descendant_downloads_30d": 138858}]}
RELICENSE = {"computed_in": "FalkorDB", "relicensing_points": 38489, "points_with_mismatched_descendants": 2438,
             "mismatched_models_below_some_point": 9386, "seconds": {"find_points": 9.42, "count_below": 4.91},
             "top": [{"model": "CultriX/NeuralTrix-7B-dpo", "restricted_parents": ["mlabonne/OmniBeagle-7B"],
                      "own_downloads_30d": 105, "mismatched_models_below": 1243, "their_downloads_30d": 148462.0},
                     {"model": "Gille/StrangeMerges_11-7B-slerp", "restricted_parents": ["mlabonne/NeuralBeagle14-7B"],
                      "own_downloads_30d": 58, "mismatched_models_below": 1231, "their_downloads_30d": 137210.0}]}
WHAT_IF = {"scenario": "FLUX.1-dev relicensed as Apache-2.0, on a GRAPH.COPY of its family",
           "family_models": 43700, "family_edges": 43702,
           "before": {"models_under_nc_license": 27453, "models_below_one": 16247, "affected_total": 43700},
           "after": {"models_under_nc_license": 27452, "models_below_one": 140, "affected_total": 27592},
           "still_non_commercial_after": 27592,
           "why": "LoRAs and fine-tunes that declare the license themselves keep it.",
           "graphs": ["family:flux1-dev", "whatif:flux1-dev-apache"],
           "seconds": {"extract": 3.31, "graph_copy": 5.102}}
STATS = {"computed_in": "FalkorDB", "models_total": 3161594, "inheriting_restricted": 242170,
         "inheriting_but_declare_permissive": 48975, "their_downloads_30d": 5879953.0, "ship_license_file": 346,
         "by_family": [["Gemma", 11215]], "graph_audit": {"numbers": {"models_total": [3161594]}}}


def unknown(mid: str) -> dict:
    return {"model": mid, "verdict": "UNKNOWN", "reason": "Not on the Hub.",
            "detail": "Hugging Face has no public model with this id.",
            "liens": [], "ancestors": [], "coverage": 0.0, "disclaimer": DISCLAIMER}


def fake_apply(r: dict, use: str, rulings: list[dict], slug: str) -> None:
    """A small stand-in for api/fineprint_core/rulings.py apply(): license-scope rulings only."""
    keys = {l["license"] for l in r.get("liens", [])}
    u = "non-commercial" if use == "noncommercial" else use
    hit = [x for x in rulings if x["target"] in keys and x["use"] in ("any", u)]
    before = r["decision"]
    rejects = [x for x in hit if x["effect"] == "reject"]
    approved = {x["target"] for x in hit if x["effect"] == "approve"}
    applied = []
    if rejects:
        r.update(decision="BLOCK", why=rejects[0]["note"])
        applied = rejects
    elif before == "CONDITIONS" and keys and keys <= approved and r.get("coverage") == 1.0:
        r.update(decision="ALLOW", why="Approved by org rulings.")
        applied = [x for x in hit if x["effect"] == "approve"]
    r["org"] = {"org": slug, "applied": [{**x, "why": "matched"} for x in applied], "not_applied": [],
                "decision_before": before, "decision_after": r["decision"]}


class FakeApi:
    """Routes like api/app.py. `substitutes` is None to mimic the endpoint not existing yet."""

    def __init__(self):
        self.calls: list[str] = []
        self.uses: list[str] = []
        self.missing: set[str] = set()
        self.last_url = None
        self.with_decision = True  # False mimics an API from before `decision` existed
        self.substitutes = None
        self.down = False
        self.rulings: dict[str, list[dict]] = {}
        self.rulesets: list[str | None] = []
        self.org_support = True  # False mimics an API from before org rulings

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        self.last_url = request.url
        if path in self.missing:
            return httpx.Response(404, json={"detail": "Not Found"})
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        if path.startswith("/api/report/"):
            mid = path[len("/api/report/"):]
            use = request.url.params.get("use", "commercial")
            self.uses.append(use)
            if use not in ("commercial", "noncommercial"):
                return httpx.Response(422, json={"detail": "bad use"})
            r = copy.deepcopy(REPORTS.get(mid) or unknown(mid))
            if self.with_decision:
                r.update(use=use, **decide(r, use))
            rs = request.url.params.get("ruleset")
            self.rulesets.append(rs)
            if rs and self.with_decision and self.org_support:
                fake_apply(r, use, self.rulings.get(rs, []), rs)
            return httpx.Response(200, json=r)
        if path.startswith("/api/rulings/") and self.org_support:
            rs = path[len("/api/rulings/"):]
            if request.method == "POST":
                import json as _json
                body = _json.loads(request.content)
                if rs == "acme-legal":
                    return httpx.Response(403, json={"detail": "Ruleset 'acme-legal' is the shared demo and is read-only here."})
                if body["scope"] == "license" and body["target"] not in {"llama3.1", "gemma", "cc-by-nc-4.0"}:
                    return httpx.Response(422, json={"detail": f"no License '{body['target']}' in the hub graph"})
                rows = self.rulings.setdefault(rs, [])
                made = {**body, "id": f"r-{len(rows) + 1}", "at": "2026-10-18T10:00:00+00:00", "supersedes": []}
                rows.insert(0, made)
                return httpx.Response(200, json=made)
            rows = self.rulings.get(rs, [])
            return httpx.Response(200, json={"ruleset": rs, "graph": f"org:{rs}", "count": len(rows), "rulings": rows})
        if path.startswith("/api/descendants/"):
            mid = path[len("/api/descendants/"):]
            if mid not in DESCENDANTS:
                return httpx.Response(404, json={"detail": "not in graph"})
            return httpx.Response(200, json=DESCENDANTS[mid])
        k = int(request.url.params.get("k", 20))
        if path == "/api/load-bearing":
            return httpx.Response(200, json={**LOAD_BEARING, "top": LOAD_BEARING["top"][:k]})
        if path == "/api/relicense-points":
            return httpx.Response(200, json={**RELICENSE, "top": RELICENSE["top"][:k]})
        if path == "/api/what-if":
            return httpx.Response(200, json=WHAT_IF)
        if path == "/api/stats":
            return httpx.Response(200, json=STATS)
        if path == "/api/search":
            q = request.url.params.get("q", "")
            rows = [{"id": m, "license": r.get("declared_license"), "downloads": r.get("downloads_30d", 0)}
                    for m, r in REPORTS.items() if q.lower() in m.lower()]
            rows.sort(key=lambda r: -(r["downloads"] or 0))
            return httpx.Response(200, json=rows[: int(request.url.params.get("limit", 10))])
        if path.startswith("/api/substitutes/") and self.substitutes is not None:
            return httpx.Response(200, json=self.substitutes)
        return httpx.Response(404, json={"detail": "Not Found"})

    def report_calls(self) -> int:
        return sum(1 for c in self.calls if c.startswith("/api/report/"))


@pytest.fixture
def fake_api():
    fake = FakeApi()
    api = client.Api(base="http://fineprint.test", transport=httpx.MockTransport(fake.handler))
    client.set_api(api)
    fake.api = api
    yield fake
    client.set_api(None)


@pytest.fixture(autouse=True)
def _clean_guard(monkeypatch):
    monkeypatch.delenv("FINEPRINT_ALLOW", raising=False)
    monkeypatch.delenv("FINEPRINT_GUARD", raising=False)
    monkeypatch.delenv("FINEPRINT_USE", raising=False)
    monkeypatch.delenv("FINEPRINT_RULESET", raising=False)
    yield
    guard_mod.unguard()

"""Org rulings: separate graph per ruleset, applied fail closed. Needs FalkorDB with the hub graph.

Uses throwaway rulesets and drops them afterwards.
"""
import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from fineprint_core import rulings as R
from fineprint_core.examiner import decide, examine
from fineprint_core.graph import db, ro

LLAMA = "meta-llama/Llama-3.1-8B-Instruct"
QWEN_RES = "unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit"


def _slug() -> str:
    return "t-" + uuid.uuid4().hex[:10]


@pytest.fixture
def slugs():
    made = []

    def new():
        s = _slug()
        made.append(s)
        return s

    yield new
    for s in made:
        R.drop(s)


@pytest.fixture(scope="module")
def llama():
    return examine(LLAMA)


def _apply(report, use, slug):
    return R.apply(report, decide(report, use), use, slug)


def test_approve_lifts_conditions_when_every_lien_is_covered(slugs, llama):
    s = slugs()
    assert decide(llama, "commercial")["decision"] == "CONDITIONS"
    R.create(s, "license", "llama3.1", "approve", "commercial", "Approved.", conditions="Ship LICENSE")
    out = _apply(llama, "commercial", s)
    assert out["decision"] == "ALLOW" and "Ship LICENSE" in out["why"]
    assert out["org"]["decision_before"] == "CONDITIONS" and out["org"]["decision_after"] == "ALLOW"
    assert [r["target"] for r in out["org"]["applied"]] == ["llama3.1"]
    # The approval was for commercial use only.
    assert _apply(llama, "noncommercial", s)["decision"] == "CONDITIONS"


def test_approve_does_not_lift_when_coverage_below_one(slugs, llama):
    s = slugs()
    R.create(s, "license", "llama3.1", "approve", "any", "Approved.")
    r = {**copy.deepcopy(llama), "coverage": 0.5}
    out = _apply(r, "commercial", s)
    assert out["decision"] == "CONDITIONS" and not out["org"]["applied"]
    assert "no recognised license" in out["org"]["not_applied"][0]["why"]


def test_approve_does_not_lift_unknown_or_unresolved_or_contested(slugs, llama):
    s = slugs()
    R.create(s, "license", "llama3.1", "approve", "any", "Approved.")
    R.create(s, "model", LLAMA, "approve", "any", "This exact model is approved.")
    unknown = {**copy.deepcopy(llama), "verdict": "UNKNOWN"}
    unresolved = {**copy.deepcopy(llama), "unresolved_card_claims": 2}
    contested = copy.deepcopy(llama)
    contested["liens"].append({**contested["liens"][0], "tier": "contested", "via": "some/dataset"})
    deleted = {**copy.deepcopy(llama), "deleted_ancestors": ["gone/model"]}
    for r in (unknown, unresolved, contested, deleted):
        out = _apply(r, "commercial", s)
        assert out["decision"] == "CONDITIONS", r
        assert out["org"]["decision_after"] == "CONDITIONS" and out["org"]["not_applied"]


def test_approve_must_cover_every_lien(slugs, llama):
    s = slugs()
    R.create(s, "license", "llama3.1", "approve", "any", "Approved.")
    r = copy.deepcopy(llama)
    r["liens"].append({**r["liens"][0], "license": "gemma", "family": "Gemma"})
    out = _apply(r, "commercial", s)
    assert out["decision"] == "CONDITIONS" and "gemma" in out["org"]["not_applied"][0]["why"]


def test_model_approve_applies_only_to_that_model(slugs, llama):
    s = slugs()
    R.create(s, "model", "google/gemma-3-27b-it", "approve", "commercial", "LEG-42")
    assert _apply(examine("google/gemma-3-27b-it"), "commercial", s)["decision"] == "ALLOW"
    assert _apply(examine("google/gemma-2-9b-it"), "commercial", s)["decision"] == "CONDITIONS"


def test_approve_never_lifts_block(slugs):
    s = slugs()
    R.create(s, "license", "qwen-research", "approve", "any", "Approved anyway.")
    R.create(s, "model", QWEN_RES, "approve", "any", "Approved anyway.")
    out = _apply(examine(QWEN_RES), "commercial", s)
    assert out["org"]["decision_before"] == "BLOCK" and out["decision"] == "BLOCK"


def test_reject_blocks_even_non_commercial(slugs):
    s = slugs()
    rep = examine(QWEN_RES)
    assert decide(rep, "noncommercial")["decision"] == "CONDITIONS"
    R.create(s, "license", "qwen-research", "reject", "any", "Never use Qwen Research.")
    out = _apply(rep, "noncommercial", s)
    assert out["decision"] == "BLOCK" and out["why"] == "Never use Qwen Research."
    assert out["org"]["applied"][0]["effect"] == "reject"


def test_reject_on_an_ancestor_blocks(slugs, llama):
    s = slugs()
    anc = llama["ancestors"][0]["id"]
    R.create(s, "model", anc, "reject", "commercial", "Do not build on this base.")
    assert _apply(llama, "commercial", s)["decision"] == "BLOCK"
    assert _apply(llama, "noncommercial", s)["decision"] == "CONDITIONS"


def test_reject_beats_approve(slugs, llama):
    s = slugs()
    R.create(s, "license", "llama3.1", "approve", "any", "Approved.")
    R.create(s, "model", LLAMA, "reject", "any", "Pulled after audit.")
    out = _apply(llama, "commercial", s)
    assert out["decision"] == "BLOCK" and out["org"]["not_applied"]


def test_rulesets_are_isolated(slugs, llama):
    a, b = slugs(), slugs()
    R.create(a, "license", "llama3.1", "approve", "any", "Approved in A.")
    assert _apply(llama, "commercial", a)["decision"] == "ALLOW"
    out = _apply(llama, "commercial", b)
    assert out["decision"] == "CONDITIONS" and not out["org"]["applied"] and not out["org"]["not_applied"]
    assert R.list_rulings(b) == []
    assert f"org:{a}" in db().list_graphs()


def test_hub_graph_has_no_rulings(slugs):
    s = slugs()
    R.create(s, "license", "llama3.1", "approve", "any", "Approved.")
    assert ro("MATCH (r:Ruling) RETURN count(r)")[0][0] == 0


def test_new_ruling_supersedes_old_one_and_delete_restores_it(slugs, llama):
    s = slugs()
    old = R.create(s, "license", "llama3.1", "approve", "commercial", "Approved.")
    new = R.create(s, "license", "llama3.1", "reject", "commercial", "Withdrawn.")
    assert new["supersedes"] == [old["id"]]
    assert _apply(llama, "commercial", s)["decision"] == "BLOCK"
    listed = {r["id"]: r for r in R.list_rulings(s)}
    assert listed[old["id"]]["superseded_by"] == new["id"]
    assert R.delete(s, new["id"])
    assert _apply(llama, "commercial", s)["decision"] == "ALLOW"


def test_validation():
    s = _slug()
    with pytest.raises(R.RulingError):
        R.create("Bad Slug", "license", "llama3.1", "approve", "any", "x")
    with pytest.raises(R.RulingError, match="no License"):
        R.create(s, "license", "not-a-license", "approve", "any", "x")
    with pytest.raises(R.RulingError, match="no Model"):
        R.create(s, "model", "not-a-real-org/not-a-real-model", "reject", "any", "x")
    with pytest.raises(R.RulingError, match="note"):
        R.create(s, "license", "llama3.1", "approve", "any", "")
    assert f"org:{s}" not in db().list_graphs()  # nothing written on a bad request
    assert R.norm_use("noncommercial") == "non-commercial"


def test_api_round_trip(slugs, monkeypatch):
    import app as api_app
    monkeypatch.setattr(api_app, "_ruling_calls", [])
    c = TestClient(api_app.app)
    s = slugs()
    org, name = LLAMA.split("/")
    plain = c.get(f"/api/report/{org}/{name}").json()
    assert plain["decision"] == "CONDITIONS" and "org" not in plain
    r = c.post(f"/api/rulings/{s}", json={"scope": "license", "target": "Llama-3.1", "effect": "approve",
                                          "use": "commercial", "note": "Approved.", "conditions": "Ship LICENSE"})
    assert r.status_code == 200 and r.json()["target"] == "llama3.1"
    rep = c.get(f"/api/report/{org}/{name}?ruleset={s}").json()
    assert rep["decision"] == "ALLOW" and rep["org"]["decision_before"] == "CONDITIONS"
    assert c.get(f"/api/rulings/{s}").json()["count"] == 1
    assert c.post(f"/api/rulings/{s}", json={"scope": "license", "target": "nope", "effect": "approve",
                                             "note": "x"}).status_code == 422
    assert c.get(f"/api/report/{org}/{name}?ruleset=BAD_SLUG").status_code == 422
    assert c.post("/api/rulings/acme-legal", json={"scope": "license", "target": "llama3.1",
                                                   "effect": "reject", "note": "x"}).status_code == 403
    assert c.delete(f"/api/rulings/{s}/{r.json()['id']}").status_code == 200
    assert c.delete(f"/api/rulings/{s}/{r.json()['id']}").status_code == 404

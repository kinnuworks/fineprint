"""Live what-if on GRAPH.COPY. Needs FalkorDB with the hub graph."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fineprint_core import whatif
from fineprint_core.graph import db, ro

FLUX = "black-forest-labs/FLUX.1-dev"
SAVED = Path(__file__).resolve().parents[2] / "data" / "derived" / "what_if_flux.json"


@pytest.fixture(scope="module")
def client():
    from app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def flux():
    return whatif.simulate(FLUX, "apache-2.0")


def _whatif_graphs():
    return [g for g in db().list_graphs() if g.startswith("whatif:")]


def test_copy_is_deleted_afterwards(flux):
    assert flux["graphs"]["copy"].startswith("whatif:")
    assert flux["graphs"]["copy"] not in db().list_graphs()
    assert _whatif_graphs() == []


def test_hub_is_untouched(flux):
    assert ro("MATCH (m:Model) WHERE m.id = $id RETURN m.license", {"id": FLUX})[0][0] == "flux-1-dev-non-commercial-license"


def test_flux_numbers_match_the_saved_run(flux):
    saved = json.loads(SAVED.read_text())
    assert flux["family_models"] == saved["family_models"] == 43700
    assert flux["family_edges"] == saved["family_edges"]
    assert flux["after"]["affected_total"] == saved["after"]["affected_total"] == 27592
    assert flux["before"]["affected_total"] == 43700
    assert flux["still_labelled_restricted_after"] == flux["still_labelled_non_commercial_after"] == 27592
    assert flux["after"]["models_under_restricted"] == flux["before"]["models_under_restricted"] - 1
    assert len(flux["relabel_needed"]) == 10
    assert all(r["license"] == "flux-1-dev-non-commercial-license" for r in flux["relabel_needed"])
    assert set(flux["seconds"]) == {"family", "graph_copy", "edit", "walks", "delete", "total"}


def test_endpoint_default_root_keeps_old_url_working(client):
    r = client.get("/api/what-if")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["root"] == FLUX and d["to_license"] == "apache-2.0" and d["cached_family"] is True
    assert d["still_labelled_non_commercial_after"] == 27592
    assert _whatif_graphs() == []


def test_other_root_and_license(client):
    d = client.get("/api/what-if", params={"root": "meta-llama/Llama-3.2-1B", "license": "mit"}).json()
    assert d["from_license"] == "llama3.2" and d["to_license"] == "mit"
    assert d["after"]["affected_total"] < d["before"]["affected_total"] == d["family_models"]
    assert ro("MATCH (m:Model) WHERE m.id = 'meta-llama/Llama-3.2-1B' RETURN m.license")[0][0] == "llama3.2"


@pytest.mark.parametrize("params,code", [
    ({"license": "not-a-license"}, 422),
    ({"root": "google-bert/bert-base-uncased"}, 422),  # already permissive
    ({"root": FLUX, "license": "flux-1-dev-non-commercial-license"}, 422),  # no change
    ({"root": "nobody/no-such-model-xyz"}, 404),
])
def test_bad_input(client, params, code):
    r = client.get("/api/what-if", params=params)
    assert r.status_code == code, r.text
    assert r.json()["detail"]


def test_family_cap(monkeypatch):
    monkeypatch.setattr(whatif, "MAX_FAMILY", 100)
    with pytest.raises(whatif.WhatIfError, match="capped"):
        whatif.build_family("google/gemma-2-2b")
    assert "family:google-gemma-2-2b" not in db().list_graphs()

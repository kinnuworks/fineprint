"""Card reading is open to any model in the graph, with a per-minute and a daily cap. Needs FalkorDB.

The live model call is replaced with a stub, so no API key is used.
"""
import pytest
from fastapi.testclient import TestClient

RECORDED = "QCRI/Fanar-2-27B-Instruct"
OTHER = "meta-llama/Llama-3.1-8B-Instruct"


@pytest.fixture
def client(monkeypatch):
    import app as api_app
    from fineprint_core import clerk
    calls = []
    monkeypatch.setattr(clerk, "extract", lambda mid: calls.append(mid) or [])
    monkeypatch.setattr(clerk, "record", lambda mid, claims: 0)
    for name, value in (("_card_cache", {}), ("_card_source", {}), ("_card_calls", []),
                        ("_card_day", {"day": "", "count": 0})):
        monkeypatch.setattr(api_app, name, value)
    monkeypatch.delenv("FINEPRINT_READCARD_DAILY", raising=False)
    c = TestClient(api_app.app)
    c.live_calls = calls
    return c


def _post(c, mid):
    org, name = mid.split("/")
    return c.post(f"/api/read-card/{org}/{name}")


def test_any_model_in_graph_is_readable(client):
    r = _post(client, OTHER)
    assert r.status_code == 200 and r.json()["source"] == "live"
    assert client.live_calls == [OTHER]
    assert _post(client, OTHER).json()["cached"] is True  # second read is from the cache
    assert client.live_calls == [OTHER]


def test_unknown_model_is_404(client):
    assert _post(client, "nobody/no-such-model-xyz").status_code == 404
    assert client.live_calls == []


def test_daily_cap(client, monkeypatch):
    monkeypatch.setenv("FINEPRINT_READCARD_DAILY", "1")
    assert _post(client, OTHER).status_code == 200
    r = _post(client, "meta-llama/Llama-3.2-1B")
    assert r.status_code == 429 and "live card reads for today" in r.json()["detail"]
    assert _post(client, OTHER).status_code == 200  # cached reads still work
    r = _post(client, RECORDED)  # past the cap, a recorded read is replayed without a live call
    assert r.status_code == 200 and r.json()["source"] == "recorded"
    assert client.live_calls == [OTHER]


def test_per_minute_limit(client):
    ids = [r[0] for r in __import__("fineprint_core.graph", fromlist=["ro"]).ro(
        "MATCH (m:Model) WHERE m.missing = false RETURN m.id ORDER BY m.downloads DESC LIMIT 7")]
    codes = [_post(client, mid).status_code for mid in ids]
    assert codes[:6] == [200] * 6 and codes[6] == 429

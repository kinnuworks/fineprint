"""Search: exact id first, then the Model.id fulltext index (or the CONTAINS scan without it)."""
from fastapi.testclient import TestClient

from app import app, fulltext_query
from fineprint_core import graph

client = TestClient(app)


def test_fulltext_query_tokens():
    assert fulltext_query("Qwen2.5-3B") == "qwen2 5 3b*"
    assert fulltext_query("meta-llama/Llama-3.2-1") == "meta llama llama 3 2 1"
    assert fulltext_query("--") is None


def test_exact_id_comes_first():
    rows = client.get("/api/search", params={"q": "meta-llama/Llama-3.2-1B", "limit": 5}).json()
    assert rows[0]["id"] == "meta-llama/Llama-3.2-1B"
    assert len({r["id"] for r in rows}) == len(rows)


def test_search_works_with_and_without_the_index(monkeypatch):
    on = client.get("/api/search", params={"q": "Llama-3.2-1B-Instruct", "limit": 5}).json()
    monkeypatch.setattr(graph, "_fulltext", {"ready": False, "checked": 1e18})
    off = client.get("/api/search", params={"q": "Llama-3.2-1B-Instruct", "limit": 5}).json()
    for rows in (on, off):
        assert rows and all("llama-3.2-1b-instruct" in r["id"].lower() for r in rows)

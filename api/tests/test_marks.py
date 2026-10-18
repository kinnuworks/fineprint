"""Cached marks (m.inherits, m.contested) follow card edges as they are written and removed. Needs FalkorDB.

A clean Apache-2.0 fine-tune with two quantized descendants gets a test Clerk edge to a
Llama 3.2 base; the family must show up on the model and below it, then go away again.
"""
from fineprint_core.graph import hub
from fineprint_core.marks import refresh_marks

MODEL = "neongeckocom/NeonLLM-Base"
CHILD = "mradermacher/NeonLLM-Base-GGUF"
LLAMA = "meta-llama/Llama-3.2-1B"
FAMILY = "Llama 3.2"


def _marks(ids):
    rows = hub().ro_query("UNWIND $ids AS i MATCH (m:Model) WHERE m.id = i RETURN m.id, m.inherits, m.contested",
                          {"ids": ids}).result_set
    return {r[0]: (sorted(r[1] or []), sorted(r[2] or [])) for r in rows}


def _drop_test_edge():
    hub().query("MATCH (m:Model)-[r:FINETUNE_OF]->(p:Model) WHERE m.id = $m AND p.id = $p "
                "AND r.by = 'clerk' AND r.read_from = $m DELETE r", {"m": MODEL, "p": LLAMA})


def test_marks_follow_clerk_edges():
    import app as api_app
    before = _marks([MODEL, CHILD])
    assert set(before) == {MODEL, CHILD}
    assert FAMILY not in before[MODEL][0] and FAMILY not in before[CHILD][0]
    try:
        hub().query("MATCH (m:Model) WHERE m.id = $m MATCH (p:Model) WHERE p.id = $p "
                    "CREATE (m)-[:FINETUNE_OF {source: 'card', quote: 'test', by: 'clerk', read_from: $m}]->(p)",
                    {"m": MODEL, "p": LLAMA})
        out = refresh_marks([MODEL])
        assert out["nodes"] >= 2 and not out["skipped"]
        now = _marks([MODEL, CHILD])
        assert FAMILY in now[MODEL][0]
        assert FAMILY in now[CHILD][0]
        assert now[MODEL][1] == before[MODEL][1]  # no dataset edge changed, contested stays

        # The read-card path removes the Clerk edges and restores the marks.
        api_app._drop_clerk_edges([MODEL], MODEL)
        assert _marks([MODEL, CHILD]) == before
    finally:
        _drop_test_edge()
        refresh_marks([MODEL])
    assert _marks([MODEL, CHILD]) == before


def test_large_subtree_is_skipped(monkeypatch):
    from fineprint_core import marks
    monkeypatch.setattr(marks, "MAX_SUBTREE", 1)
    out = refresh_marks([MODEL])
    assert out["skipped"] == [MODEL] and out["updated"] == 0

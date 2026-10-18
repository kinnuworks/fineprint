"""Examiner and lineage tests against the live graph (FalkorDB on localhost:6379).

The oracle tests rebuild lineage with networkx from the same Hub dump and compare.
"""
import random
from pathlib import Path

import duckdb
import networkx as nx
import pytest

from fineprint_core.examiner import examine, substitutes
from fineprint_core.graph import ro

ROOT = Path(__file__).resolve().parents[2]
EDGES = ROOT / "data" / "derived" / "edges.parquet"


@pytest.fixture(scope="module")
def oracle():
    g = nx.DiGraph()
    for child, parent in duckdb.sql(f"SELECT child, parent FROM '{EDGES}' WHERE child <> parent").fetchall():
        g.add_edge(child, parent)
    return g


def udf_ancestors(model_id):
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.ancestors(m, 64)", {"id": model_id})
    return {a["id"] for a in rows[0][0]} if rows else set()


def udf_descendant_count(model_id):
    rows = ro("MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64)", {"id": model_id}, timeout=60000)
    return rows[0][0]["count"]


def test_ancestors_match_oracle_on_random_models(oracle):
    rng = random.Random(20261018)
    sample = rng.sample([n for n in oracle.nodes if oracle.out_degree(n) > 0], 200)
    mismatches = []
    for m in sample:
        expected = nx.descendants(oracle, m)  # child -> parent edges, so descendants are ancestors
        got = udf_ancestors(m)
        # Clerk-written edges can only add ancestors, never remove them.
        if not expected <= got:
            mismatches.append((m, expected - got))
    assert not mismatches, mismatches[:5]


@pytest.mark.parametrize("root", ["meta-llama/Llama-3.1-8B", "google/gemma-3-27b-pt", "Qwen/Qwen2.5-7B"])
def test_descendant_counts_match_oracle(oracle, root):
    expected = len(nx.ancestors(oracle, root))
    assert udf_descendant_count(root) >= expected
    assert udf_descendant_count(root) - expected < 50  # only Clerk edges may add a few


def test_multi_type_walk_regression():
    # FalkorDB 4.22.1 follows only the last type of a multi-type UDF traversal;
    # the walk queries one type at a time. Fanar's only edge is FINETUNE_OF.
    assert "google/gemma-3-27b-pt" in udf_ancestors("QCRI/Fanar-2-27B-Instruct")


@pytest.mark.parametrize("model_id, verdict", [
    ("QCRI/Fanar-2-27B-Instruct", "CLOUDED"),
    ("meta-llama/Llama-3.1-8B-Instruct", "LIENS"),
    ("Qwen/Qwen2.5-7B-Instruct", "NO LIENS FOUND"),
    ("not-a-real-org/not-a-real-model", "UNKNOWN"),
])
def test_verdicts(model_id, verdict):
    assert examine(model_id)["verdict"] == verdict


def test_clouded_lien_cites_clauses_and_paths():
    r = examine("mradermacher/Llama3.3-8B-Instruct-Thinking-Heretic-Uncensored-Claude-4.5-Opus-High-Reasoning-i1-GGUF")
    assert r["verdict"] == "CLOUDED"
    lien = r["liens"][0]
    assert lien["family"] == "Llama 3.3" and lien["depth"] == 2
    assert any("Llama" in c["obligation"] for c in lien["clauses"])
    assert lien["paths"] and lien["paths"][0]["models"][-1] == lien["via"]


def test_graph_off_hides_inherited_terms():
    mid = "mradermacher/Llama3.3-8B-Instruct-Thinking-Heretic-Uncensored-Claude-4.5-Opus-High-Reasoning-i1-GGUF"
    assert examine(mid, use_graph=True)["verdict"] == "CLOUDED"
    assert examine(mid, use_graph=False)["verdict"] == "NO LIENS FOUND"


def test_contested_dataset_lien():
    r = examine("HuggingFaceTB/SmolVLM2-500M-Video-Instruct")
    assert r["verdict"] == "LIENS"
    assert any(l["tier"] == "contested" and l["family"] == "CC BY-NC" for l in r["liens"])


def test_substitutes_are_clean_and_similar():
    s = substitutes("QCRI/Fanar-2-27B-Instruct")
    assert s["substitutes"]
    for c in s["substitutes"]:
        assert examine(c["id"])["verdict"] == "NO LIENS FOUND"
        assert 0.65 * s["params"] <= c["params"] <= 1.35 * s["params"]


# Regressions from judging rounds: none of these may come back as ALLOW for commercial use.
@pytest.mark.parametrize("model_id, decision", [
    ("dx8152/Flux2-Klein-9B-Consistency", "BLOCK"),
    ("AstraMindAI/xtts2-gpt", "BLOCK"),
    ("plainhub/mobileclip-s2-tflite", "BLOCK"),
    ("RedHatAI/Llama-4-Scout-17B-16E-Instruct-FP8-block", "CONDITIONS"),
    ("chaudhrysuleman/medgemma-1.5-4b-it-leukemia-lora", "CONDITIONS"),
    ("typhoon-ai/typhoon-ocr-3b", "BLOCK"),
    ("ggml-org/Qwen2.5-VL-3B-Instruct-GGUF", "BLOCK"),
    ("ifmylove2011/girlslike", "BLOCK"),
    ("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit", "BLOCK"),
    ("black-forest-labs/FLUX.1-dev", "BLOCK"),
])
def test_no_false_allow(model_id, decision):
    from fineprint_core.examiner import decide
    assert decide(examine(model_id), "commercial")["decision"] == decision


def test_unrecognised_ancestor_never_allows():
    from fineprint_core.examiner import decide
    from fineprint_core.licenses import recognized
    rows = ro("""MATCH (c:Model)-[:FINETUNE_OF|ADAPTER_OF|QUANTIZED_FROM]->(p:Model)
                 WHERE c.license IN ['apache-2.0','mit'] AND p.license <> '' AND p.missing = false
                   AND NOT p.license IN ['apache-2.0','mit','other'] AND c.downloads > 100
                 RETURN c.id, p.license LIMIT 400""")
    picked = [r[0] for r in rows if not recognized(r[1])][:15]
    assert picked
    for mid in picked:
        assert decide(examine(mid), "commercial")["decision"] != "ALLOW", mid


def test_obligations_query_is_fast():
    import time
    t = time.perf_counter()
    examine("mradermacher/Goetia-24B-v1.4-heretic-GGUF")
    assert time.perf_counter() - t < 1.5


def test_one_hop_mode_still_fails_closed():
    r = examine("conradlocke/krea2-identity-edit", use_graph=False)
    assert r["verdict"] == "UNKNOWN"

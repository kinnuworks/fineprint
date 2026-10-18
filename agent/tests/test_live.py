"""Live checks against a running FinePrint API. Run with `pytest -m live`."""
import io
from pathlib import Path

import pytest

import fineprint
from fineprint import cli, client, mcp_server

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def live_api():
    client.set_api(None)
    try:
        client.get_api().search("Qwen", limit=1)
    except client.ApiUnavailable as e:
        pytest.skip(str(e))


@pytest.mark.parametrize("model_id,decision", [
    ("black-forest-labs/FLUX.1-dev", "BLOCK"),
    ("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit", "BLOCK"),
    ("mlabonne/NeuralBeagle14-7B", "BLOCK"),
    ("Qwen/Qwen2.5-7B-Instruct", "ALLOW"),
    ("QCRI/Fanar-2-27B-Instruct", "CONDITIONS"),
])
def test_commercial_decisions(model_id, decision):
    rep = client.get_api().report(model_id, use="commercial")
    assert rep["decision"] == decision, rep.get("why")
    assert rep["why"]


def test_fanar_is_clouded():
    rep = client.get_api().report("QCRI/Fanar-2-27B-Instruct")
    assert rep["verdict"] == "CLOUDED"
    assert rep["declared_license"] == "apache-2.0"
    assert any(l["license"] == "gemma" for l in rep["liens"])


def test_qwen_has_no_liens():
    rep = client.get_api().report("Qwen/Qwen2.5-7B-Instruct")
    assert rep["verdict"] == "NO LIENS FOUND"
    assert rep["liens"] == []


def test_noncommercial_use_lifts_flux_block():
    rep = client.get_api().report("black-forest-labs/FLUX.1-dev", use="noncommercial")
    assert rep["decision"] != "BLOCK"


def test_demo_repo_fails_ci():
    demo = Path(__file__).resolve().parents[2] / "demo"
    if not demo.is_dir():
        pytest.skip("no demo/ directory")
    assert cli.main(["check", str(demo), "--use", "commercial"]) == 1


def test_mcp_tools_live():
    out = mcp_server.check_model("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit")
    assert out.startswith("Decision for commercial use: BLOCK.")
    assert "google/gemma-3-27b-pt" in mcp_server.explain_path("QCRI/Fanar-2-27B-Instruct")
    assert "descendants" in mcp_server.downstream("QCRI/Fanar-2-27B-Instruct", k=3)
    assert "license: gemma" in mcp_server.draft_remediation("QCRI/Fanar-2-27B-Instruct")
    assert mcp_server.find_clean_substitute("QCRI/Fanar-2-27B-Instruct")


def test_cli_live(tmp_path):
    (tmp_path / "a.py").write_text('from_pretrained("QCRI/Fanar-2-27B-Instruct")\n'
                                   'from_pretrained("Qwen/Qwen2.5-7B-Instruct")\n')
    assert cli.main(["check", str(tmp_path)]) == 0  # CONDITIONS only
    assert cli.main(["check", str(tmp_path), "--strict"]) == 2
    (tmp_path / "b.py").write_text('from_pretrained("black-forest-labs/FLUX.1-dev")\n')
    assert cli.main(["check", str(tmp_path)]) == 1


def test_guard_blocks_live():
    hub = pytest.importorskip("huggingface_hub")
    fineprint.guard("block", stream=io.StringIO())
    with pytest.raises(fineprint.FinePrintBlocked):
        hub.hf_hub_download("black-forest-labs/FLUX.1-dev", "model_index.json")
    hub_report = fineprint.check("QCRI/Fanar-2-27B-Instruct")  # CONDITIONS: no raise
    assert hub_report["decision"] == "CONDITIONS"


def test_algorithm_tools_live():
    lb = mcp_server.load_bearing(k=5)
    assert lb.startswith("Load-bearing base models by PageRank") and "upload farms" in lb
    assert "1. " in lb and "descendants" in lb
    rp = mcp_server.relicense_points(k=3)
    assert "relicense points:" in rp and "3. " in rp
    wi = mcp_server.what_if()
    assert "FLUX.1-dev" in wi and "| bound by flux-1-dev-non-commercial-license terms in total | 43,700 | 27,592 |" in wi
    wi = mcp_server.what_if(root="meta-llama/Llama-3.2-1B", license="mit")
    assert "| declare llama3.2 |" in wi and "GRAPH.COPY" in wi
    st = mcp_server.hub_stats()
    assert "- models on the Hub:" in st
    se = mcp_server.search_models("Qwen2.5-7B-Instruct", limit=3, use="commercial")
    assert "Qwen/Qwen2.5-7B-Instruct [apache-2.0]" in se and "ALLOW" in se


def test_fail_closed_live(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text('from_pretrained("Qwen/Qwen2.5-7B-Instruct")\n')
    assert cli.main(["check", str(tmp_path), "--fail-closed"]) == 0  # API up: only decisions matter
    monkeypatch.setenv("FINEPRINT_API", "http://127.0.0.1:9")
    client.set_api(None)
    assert cli.main(["check", str(tmp_path)]) == 3
    assert cli.main(["check", str(tmp_path), "--fail-closed"]) == 1

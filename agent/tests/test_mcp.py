import asyncio
import os
import sys
from pathlib import Path

import pytest

from fineprint import mcp_server as srv

FANAR = "QCRI/Fanar-2-27B-Instruct"
QWEN = "Qwen/Qwen2.5-7B-Instruct"
LLAMA = "acme/Llama-3.1-8B-tuned"
TOOLS = {"check_model", "explain_path", "downstream", "draft_remediation", "find_clean_substitute",
         "search_models", "load_bearing", "relicense_points", "what_if", "hub_stats",
         "record_ruling", "list_rulings"}
TAKES_MODEL_ID = {"check_model", "explain_path", "downstream", "draft_remediation", "find_clean_substitute"}


def test_check_model_decision_first(fake_api):
    out = srv.check_model("acme/nc-tuned")
    assert out.startswith("Decision for commercial use: BLOCK. Non-commercial terms from acme/nc-base (CC BY-NC).")
    out = srv.check_model("acme/nc-tuned", use="noncommercial")
    assert out.startswith("Decision for noncommercial use: CONDITIONS.")
    assert fake_api.uses[-1] == "noncommercial"
    with pytest.raises(srv.ToolError):
        srv.check_model(FANAR, use="resale")


def test_check_model_clouded(fake_api):
    out = srv.check_model(FANAR)
    lines = out.splitlines()
    assert lines[0] == "Decision for commercial use: CONDITIONS. 2 obligations to meet before shipping."
    assert lines[1] == f"{FANAR}: CLOUDED. Declared license differs from upstream terms."
    assert "Declared license: apache-2.0" in out
    assert "Gemma (gemma), contractual, inherited from google/gemma-3-27b-pt at depth 1" in out
    assert "[gemma-3.1-1]" in out and "https://ai.google.dev/gemma/terms" in out
    assert "not legal advice" in out


def test_check_model_clean_and_unknown(fake_api):
    assert srv.check_model(QWEN).startswith("Decision for commercial use: ALLOW.")
    out = srv.check_model("nobody/nothing")
    assert out.startswith("Decision for commercial use: N/A. No such public model.")
    out = srv.check_model("acme/no-license")
    assert "CONDITIONS" in out and "not a pass" in out


def test_explain_path_lists_every_path(fake_api):
    out = srv.explain_path(LLAMA)
    assert "arrives from meta-llama/Llama-3.1-8B-Instruct at depth 1 by 2 paths" in out
    assert "1. acme/Llama-3.1-8B-tuned [llama3.1] --adapter of--> meta-llama/Llama-3.1-8B-Instruct [llama3.1]" in out
    assert ("2. acme/Llama-3.1-8B-tuned [llama3.1] --merge of--> acme/merge [none declared] "
            "--fine-tune of--> meta-llama/Llama-3.1-8B-Instruct [llama3.1]") in out


def test_explain_path_without_liens(fake_api):
    out = srv.explain_path(QWEN)
    assert "No lien reaches this model" in out and "Qwen/Qwen2.5-7B [apache-2.0]" in out


def test_downstream(fake_api):
    out = srv.downstream(FANAR, k=5)
    assert out.startswith(f"{FANAR}: 4 descendants, deepest chain 1, 796 downloads")
    assert "mradermacher/Fanar-2-27B-Instruct-i1-GGUF [apache-2.0] depth 1, 347 downloads" in out
    assert "1 of these 2 declare a permissive license." in out
    assert any(c.startswith("/api/descendants/") for c in fake_api.calls)


def test_bad_model_id_is_a_tool_error(fake_api):
    with pytest.raises(srv.ToolError, match="not a Hugging Face model id"):
        srv.check_model("not a model")


def test_downstream_not_in_graph(fake_api):
    assert "not in graph" in srv.downstream("nobody/nothing", k=3)


def test_draft_remediation_clouded(fake_api):
    out = srv.draft_remediation(FANAR)
    assert "Draft text only. FinePrint does not post" in out
    assert "Gemma is provided under and subject to the Gemma Terms of Use" in out
    assert "license: gemma\nbase_model:\n- google/gemma-3-27b-pt" in out
    assert "differs from upstream terms" in out
    assert "- [ ] Ship a \"Notice\" file pointing to the Gemma Terms of Use. (gemma, clause gemma-3.1-4)" in out
    assert "violation" not in out.lower()


def test_draft_remediation_clean_and_unknown(fake_api):
    assert "no NOTICE or license change is suggested" in srv.draft_remediation(QWEN)
    assert "base_model:" in srv.draft_remediation("nobody/nothing")


def test_find_clean_substitute_not_available(fake_api):
    out = srv.find_clean_substitute(FANAR)
    assert "not available yet" in out


def test_find_clean_substitute_when_endpoint_exists(fake_api):
    fake_api.substitutes = {"model": FANAR, "task": "text-generation", "params": 27_000_000_000, "substitutes": [
        {"id": "Qwen/Qwen2.5-32B-Instruct", "license": "apache-2.0", "params": 32_500_000_000,
         "downloads_30d": 1000}]}
    out = srv.find_clean_substitute(FANAR, k=3)
    assert out.startswith(f"Clean substitutes for {FANAR} (text-generation, 27.0B params):")
    assert "- Qwen/Qwen2.5-32B-Instruct [apache-2.0], 32.5B params, 1,000 downloads (30 days)" in out
    assert fake_api.calls[-1] == f"/api/substitutes/{FANAR}"
    fake_api.substitutes = {"model": FANAR, "substitutes": [], "note": "No clean model with the same task."}
    assert srv.find_clean_substitute(FANAR).endswith("No clean model with the same task.")


def test_load_bearing(fake_api):
    out = srv.load_bearing(k=1)
    assert out.startswith("Load-bearing base models by PageRank over lineage edges (top 1):")
    assert ("1. black-forest-labs/FLUX.1-dev [flux-1-dev-non-commercial-license] score 0.00861, 43,699 descendants "
            "with 1,487,043 downloads (30 days); own downloads 648,212") in out
    assert "Qwen1.5" not in out
    assert "PageRank counts automated upload farms too" in out
    assert "algo.pageRank" in out
    assert "k=1" in str(fake_api.last_url)


def test_relicense_points(fake_api):
    out = srv.relicense_points(k=2)
    assert "- relicense points: 38,489" in out
    assert ("1. CultriX/NeuralTrix-7B-dpo (restricted parent: mlabonne/OmniBeagle-7B): 1,243 mismatched models below "
            "with 148,462 downloads (30 days); own downloads 105") in out
    assert "Declared license differs from upstream terms" in out


def test_what_if(fake_api):
    out = srv.what_if()
    assert out.startswith("What if: black-forest-labs/FLUX.1-dev relicensed as apache-2.0, on a GRAPH.COPY")
    assert "| bound by flux-1-dev-non-commercial-license terms in total | 43,700 | 27,592 |" in out
    assert "| declare flux-1-dev-non-commercial-license | 27,453 | 27,452 |" in out
    assert "- city96/FLUX.1-dev-gguf [flux-1-dev-non-commercial-license], 194,092 downloads" in out
    assert "copied family:black-forest-labs-flux-1-dev to whatif:0123abcd with GRAPH.COPY" in out
    assert fake_api.what_if_params == {"root": "black-forest-labs/FLUX.1-dev", "license": "apache-2.0"}
    srv.what_if(root="meta-llama/Llama-3.2-1B", license="mit")
    assert fake_api.what_if_params == {"root": "meta-llama/Llama-3.2-1B", "license": "mit"}


def test_what_if_renders_older_api_shape():
    from fineprint import render
    out = render.what_if({"scenario": "old", "before": {"models_under_nc_license": 2, "affected_total": 3},
                          "after": {"models_under_nc_license": 1, "affected_total": 1},
                          "graphs": ["family:flux1-dev", "whatif:flux1-dev-apache"]})
    assert "| declare the non-commercial license | 2 | 1 |" in out
    assert "whatif:flux1-dev-apache" in out


def test_hub_stats_top_level_only(fake_api):
    out = srv.hub_stats()
    assert "- models on the Hub: 3,161,594" in out
    assert "- their downloads (30 days): 5,879,953" in out
    assert "Gemma" not in out and "graph_audit" not in out


def test_search_models(fake_api):
    out = srv.search_models("acme")
    assert out.splitlines()[0] == "Models matching 'acme', most downloaded first:"
    assert "- acme/Llama-3.1-8B-tuned [llama3.1], 10 downloads" in out
    assert fake_api.report_calls() == 0
    out = srv.search_models("acme", limit=5, use="commercial")
    assert "- acme/nc-tuned [apache-2.0], 5 downloads: BLOCK. Non-commercial terms from acme/nc-base" in out
    assert "acme/Llama-3.1-8B-tuned [llama3.1], 10 downloads: CONDITIONS." in out
    assert srv.search_models("zzzz") == "No models match 'zzzz'."


def test_algorithm_tools_raise_when_api_down(fake_api):
    fake_api.down = True
    for fn in (srv.load_bearing, srv.relicense_points, srv.what_if, srv.hub_stats):
        with pytest.raises(srv.ToolError, match="not reachable"):
            fn()
    with pytest.raises(srv.ToolError, match="not reachable"):
        srv.search_models("qwen")


def test_algorithm_tool_on_older_api(fake_api):
    fake_api.missing = {"/api/what-if"}
    with pytest.raises(srv.ToolError, match="does not offer that yet"):
        srv.what_if()


def test_tools_raise_clear_error_when_api_down(fake_api):
    fake_api.down = True
    for fn in (srv.check_model, srv.explain_path, srv.draft_remediation, srv.find_clean_substitute):
        with pytest.raises(srv.ToolError, match="not reachable"):
            fn(FANAR)
    with pytest.raises(srv.ToolError, match="not reachable"):
        srv.downstream(FANAR, k=3)


def test_tool_schemas():
    tools = asyncio.run(srv.mcp.list_tools())
    by_name = {t.name: t for t in tools}
    assert set(by_name) == TOOLS
    def schema(t):
        return t.model_dump(by_alias=True)["inputSchema"]

    for t in tools:
        assert t.description and len(t.description) < 300
        if t.name in TAKES_MODEL_ID:
            assert "model_id" in schema(t)["properties"]
            assert schema(t)["required"] == ["model_id"]
    assert schema(by_name["search_models"])["required"] == ["q"]
    assert schema(by_name["load_bearing"])["properties"]["k"]["default"] == 10
    assert schema(by_name["relicense_points"])["properties"]["k"]["maximum"] == 100
    wi = schema(by_name["what_if"])["properties"]
    assert wi["root"]["default"] == "black-forest-labs/FLUX.1-dev" and wi["license"]["default"] == "apache-2.0"
    use = schema(by_name["check_model"])["properties"]["use"]
    assert use["enum"] == ["commercial", "noncommercial"] and use["default"] == "commercial"
    k = schema(by_name["downstream"])["properties"]["k"]
    assert k["default"] == 10 and k["minimum"] == 1 and k["maximum"] == 100


def test_stdio_server_lists_tools_and_reports_api_down():
    """Start `python -m fineprint.mcp_server` as a subprocess and talk to it over stdio."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    src = str(Path(srv.__file__).resolve().parents[1])
    env = {**os.environ, "FINEPRINT_API": "http://127.0.0.1:9", "PYTHONPATH": src}

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "fineprint.mcp_server"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {t.name for t in (await s.list_tools()).tools}
                res = await s.call_tool("check_model", {"model_id": FANAR})
                return names, res

    names, res = asyncio.run(asyncio.wait_for(run(), 60))
    assert names == TOOLS
    assert getattr(res, "is_error", None) or getattr(res, "isError", None)
    assert "not reachable" in res.content[0].text


def test_record_ruling_then_check_model_applies_it(fake_api):
    out = srv.record_ruling("my-team", "license", "cc-by-nc-4.0", "approve", "commercial",
                            "Approved for the pilot.", conditions="Credit the dataset authors")
    assert out.startswith("Recorded in ruleset my-team: approve license cc-by-nc-4.0 for commercial use")
    assert "Conditions: Credit the dataset authors." in out
    # Approvals never lift BLOCK.
    assert srv.check_model("acme/nc-tuned", ruleset="my-team").startswith("Decision for commercial use: BLOCK.")
    srv.record_ruling("my-team", "license", "llama3.1", "reject", "any", "Llama is off limits.")
    out = srv.check_model(LLAMA, ruleset="my-team")
    assert out.startswith("Decision for commercial use: BLOCK. Llama is off limits.")
    assert "Org rulings (my-team): CONDITIONS -> BLOCK" in out
    assert fake_api.rulesets[-1] == "my-team"
    # Without a ruleset nothing changes.
    assert srv.check_model(LLAMA).startswith("Decision for commercial use: CONDITIONS.")
    assert fake_api.rulesets[-1] is None


def test_check_model_ruleset_from_env(fake_api, monkeypatch):
    fake_api.rulings["env-team"] = [{"id": "r-1", "scope": "license", "target": "llama3.1", "effect": "approve",
                                     "use": "any", "note": "OK", "conditions": "", "by": "", "at": ""}]
    monkeypatch.setenv("FINEPRINT_RULESET", "env-team")
    out = srv.check_model(LLAMA)
    assert out.startswith("Decision for commercial use: ALLOW.")
    assert "Org rulings (env-team): CONDITIONS -> ALLOW" in out


def test_list_rulings(fake_api):
    assert srv.list_rulings("my-team") == "Ruleset my-team: no rulings yet."
    srv.record_ruling("my-team", "license", "gemma", "approve", "any", "Gemma terms reviewed.")
    out = srv.list_rulings("my-team")
    assert "Ruleset my-team (graph org:my-team): 1 ruling" in out and "approve license gemma" in out


def test_record_ruling_errors(fake_api):
    with pytest.raises(srv.ToolError, match="no License"):
        srv.record_ruling("my-team", "license", "not-a-license", "approve", "any", "x")
    with pytest.raises(srv.ToolError, match="read-only"):
        srv.record_ruling("acme-legal", "license", "llama3.1", "approve", "any", "x")
    with pytest.raises(srv.ToolError, match="ruleset must match"):
        srv.record_ruling("Bad Slug", "license", "llama3.1", "approve", "any", "x")
    with pytest.raises(srv.ToolError, match="ruleset must match"):
        srv.check_model(LLAMA, ruleset="Bad Slug")
    fake_api.org_support = False
    out = srv.check_model(LLAMA, ruleset="my-team")
    assert out.startswith("Note: ruleset my-team was not applied")
    with pytest.raises(srv.ToolError, match="no org rulings"):
        srv.list_rulings("my-team")
    fake_api.down = True
    with pytest.raises(srv.ToolError, match="not reachable"):
        srv.list_rulings("my-team")


def test_ruling_tool_schemas():
    tools = {t.name: t.model_dump(by_alias=True)["inputSchema"] for t in asyncio.run(srv.mcp.list_tools())}
    rec = tools["record_ruling"]
    assert rec["required"] == ["ruleset", "scope", "target", "effect", "use", "note"]
    assert rec["properties"]["effect"]["enum"] == ["approve", "reject"]
    assert rec["properties"]["use"]["enum"] == ["commercial", "non-commercial", "any"]
    assert "ruleset" in tools["check_model"]["properties"]
    assert tools["check_model"]["required"] == ["model_id"]

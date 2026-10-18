# Claims and where they come from

Every number in the README, the script or query that produces it, and the file it lands in. `scripts/reproduce.sh` runs them in order.

| Claim | Value | Produced by | Output |
|---|---|---|---|
| Public models in the graph | 3,161,594 | `scripts/load_all_models.py`; `MATCH (m:Model) WHERE m.missing = false RETURN count(m)` | `data/derived/headline_graph.json` |
| Lineage edges | 927,431 | `scripts/export_graph.py` + bulk loader | loader log |
| License rules in the graph | 47 License nodes, 1,055,181 LICENSED_UNDER edges | `scripts/load_license_graph.py` | live |
| Dataset links / datasets | 386,483 / 66,243 | `scripts/load_datasets.py` | loader log |
| Models inheriting restricted terms | 242,170 | `scripts/audit_graph.py`, `scripts/audit_add_families.py` (UDF walk), then Cypher in `scripts/headline_graph.py` | `data/derived/headline_graph.json` (`inheriting_restricted`) |
| Of those, declaring a permissive license | 48,975 (5.88M downloads in 30 days) | `scripts/headline_graph.py` | `inheriting_but_declare_permissive` |
| Of those, with 10+ downloads | 25,627 | `scripts/headline_graph.py` | `inheriting_but_declare_permissive_10plus_downloads` |
| Of those, shipping any license or notice file | 346 | `scripts/headline_graph.py` (`m.has_license_file`, from repo file lists) | `of_those_ship_license_file` |
| Non-commercial upstream, permissive declared | 11,442 (2.85M downloads) | `scripts/headline_graph.py` | `non_commercial_upstream_declare_permissive` |
| Most depended-on model by PageRank | `black-forest-labs/FLUX.1-dev` | `GET /api/load-bearing` (`CALL algo.pageRank('Model', null)`) | live |
| Mismatches carrying Unsloth's template tags | 26,406 of 48,975 (54%) | `scripts/graph_mismatches.py`, `scripts/unsloth_share.py` | `data/derived/unsloth_share.json` |
| Unsloth template hardcodes apache-2.0 | `unsloth/save.py` `MODEL_CARD`, commit 72d0d2d | source read | [link](https://github.com/unslothai/unsloth/blob/72d0d2dbf33fd16c7ed1c6f909276aa33fa1f6b4/unsloth/save.py) |
| Relicensing points / with mismatches below / models below | 38,489 / 2,438 / 9,386 | `scripts/relicense_points.py` (Cypher + UDF) | `data/derived/relicense_points.json` |
| Hub API calls for Llama-3.1-8B's descendants vs graph | 21,653 calls (about 3.7 h) vs 70 ms | `scripts/hub_api_comparison.py` | `data/derived/hub_api_comparison.json` |
| FLUX.1-dev relicensed as Apache-2.0 (what-if) | 27,592 of 43,700 still labelled non-commercial | `GET /api/what-if` and `scripts/what_if.py` (family graph, GRAPH.COPY per request, re-walk, GRAPH.DELETE); `api/tests/test_whatif.py` | `data/derived/what_if_flux.json`, live |
| Other what-if roots (relicensed as apache-2.0) | Qwen/Qwen2.5-3B 8,483 → 6,974; meta-llama/Llama-3.2-1B 3,846 → 2,887; facebook/nllb-200-distilled-600M 677 → 449 | `GET /api/what-if?root=...` | live |
| What-if timings | see README "Queries and algorithms" | `seconds` in the `GET /api/what-if` response | live |
| ACL isolation | org user cannot write `hub` or read another org; `fp-hub-ro` cannot run GRAPH.QUERY (NOPERM) | `api/fineprint_core/acl.py`; `api/tests/test_acl.py` | live |
| Fulltext search | `queryNodes` on Model.id, median 48 ms vs 278 ms for the CONTAINS scan over ten queries | `api/app.py` `search`; index built with `db.idx.fulltext.createNodeIndex` | live |
| SD 1.5 direct children after deletion | 3,373 | `MATCH (c:Model)-[]->(m:Model {id:'runwayml/stable-diffusion-v1-5'}) RETURN count(c)` | live |
| Eval, said clean when it isn't | FinePrint 0 of 69; card LLM 8; one hop 19; declared 33 | `eval/run_eval.py v2` | `eval/results_v2.json` |
| Eval accuracy | v2 80/120, v3 103/120 | `eval/run_eval.py v2`, `eval/run_eval.py v3` | `eval/results_v2.json`, `eval/results_v3.json` |
| Restricted terms two or more hops up | FinePrint 19/19, card LLM 7/19 (v2) | `eval/run_eval.py v2` | `eval/results_v2.json` |
| Eval, LLM agent with Hub API tools | all 120 models; said clean when it isn't 5 of 69 (all GGUFs of merge trees); correct v2 92/120, v3 91/120; 2+ hops 14/19; merges 6/15 | `eval/tool_agent.py`, then `eval/run_eval.py v2 --merge`, `eval/run_eval.py v3 --merge` | `eval/tool_agent_runs.json`, `eval/results_v2.json`, `eval/results_v3.json` |
| Hub agent cost per model vs FinePrint | 471 Hub calls (mean 3.9, 8 hit the cap), median 11.5 s per model; $4.79 for the run (1.64M input tokens, mostly cache reads, 98K output); FinePrint median 9 ms, no model calls | `eval/run_eval.py v2 --merge` | `tool_agent_cost` in `eval/results_v2.json` |
| Clerk precision | 41 of 48 edges correct | manual check | `eval/clerk_precision.json` |
| Org rulings flip decisions (demo ruleset `acme-legal`) | `meta-llama/Llama-3.1-8B-Instruct` commercial CONDITIONS to ALLOW; `unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit` non-commercial CONDITIONS to BLOCK; `google/gemma-3-27b-it` commercial CONDITIONS to ALLOW, `google/gemma-2-9b-it` stays CONDITIONS | `scripts/seed_rulings.py`; `api/tests/test_rulings.py` | live (`org:acme-legal`) |
| FalkorDB UDF bug | `types` list follows only its last entry | repro | `docs/upstream/falkordb-udf-types-last-only.md` |

Gold files and seals: `eval/gold_v2.json` + `eval/GOLD_V2_SHA256`, `eval/gold_v3.json` + `eval/GOLD_V3_SHA256`. The scorer refuses to run if a gold file does not match its seal.

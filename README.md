# FinePrint

Every fine-tune comes with fine print.

FinePrint reads the obligations an open AI model inherited from its family tree. Give it any model on the Hugging Face Hub and it walks every ancestor model and every training dataset in a FalkorDB graph of the whole Hub, collects the terms each one carries, and answers ALLOW, CONDITIONS or BLOCK for the way you plan to use it.

Track: Agents That Act on Connected Data.

Live site: [fineprint-plum.vercel.app](https://fineprint-plum.vercel.app) (API: [api-production-9f25.up.railway.app](https://api-production-9f25.up.railway.app/api/health)) · Demo video: _added at upload_ · Five-minute path: [JUDGES.md](JUDGES.md) · Every number: [CLAIMS.md](CLAIMS.md)

## What the graph found

All 3,161,594 public models on Hugging Face (Oct 18 2026) are nodes in one FalkorDB graph, with 927,431 lineage edges and 386,483 links to 66,243 training datasets. Each number below comes from a script listed in [CLAIMS.md](CLAIMS.md), and the headline counts are Cypher queries whose text and timings are saved in [data/derived/headline_graph.json](data/derived/headline_graph.json).

- 242,170 models inherit restricted terms (Llama, Gemma, Qwen, FLUX, Mistral, OpenRAIL, DeepSeek, CC BY-NC and named non-commercial or research licenses) through the base models they declare.
- 48,975 of them declare a permissive license such as apache-2.0 or MIT, with 5.88M downloads in the last 30 days. 25,627 of those have at least 10 downloads, so this is not a pile of abandoned uploads. Only 346 of the 48,975 ship any license or notice file.
- 11,442 of them say commercial use is fine while an ancestor's license is non-commercial (FLUX.1 [dev], Qwen Research, CC BY-NC, Mistral Research and others), with 2.85M downloads in 30 days.
- By PageRank over lineage, the most depended-on model on the Hub is `black-forest-labs/FLUX.1-dev`, which is non-commercial. PageRank also rewards automated upload farms (the next two, Qwen 1.5 models, have tens of thousands of near-empty adapters), so `/api/load-bearing` returns descendant counts and downloads next to the score.
- 26,406 of the 48,975 (54%) carry the exact tag set Unsloth's model card template writes together with `license: apache-2.0` ([`unsloth/save.py`, `MODEL_CARD`, at commit 72d0d2d](https://github.com/unslothai/unsloth/blob/72d0d2dbf33fd16c7ed1c6f909276aa33fa1f6b4/unsloth/save.py)). The template sets that license whatever the base model's license is. A proposed fix is in [docs/upstream/unsloth-card-license.patch](docs/upstream/unsloth-card-license.patch). It covers the library and Unsloth Studio's export cards, and Unsloth's own card and export tests pass with it (110 tests across the library and Studio, six of them new).
- 38,489 models declare a permissive license directly on top of a restricted parent. Below 2,438 of them sit 9,386 mismatched models that inherited the wrong label rather than writing it ([data/derived/relicense_points.json](data/derived/relicense_points.json), computed in FalkorDB).
- `runwayml/stable-diffusion-v1-5` was deleted from the Hub; 3,373 models still declare it as their direct base.
- What if Black Forest Labs relicensed FLUX.1-dev as Apache-2.0? On a `GRAPH.COPY` of the 43,700-model family, 27,592 would still be labelled non-commercial: 27,452 LoRAs and fine-tunes copy the FLUX.1 [dev] Non-Commercial label onto their own cards, and each uploader would have to edit theirs ([scripts/what_if.py](scripts/what_if.py), `GET /api/what-if`).

These are differences between a declared license and upstream terms, not legal findings.

## Try it in 60 seconds

1. Open `kenpath/svara-tts-v1`, a text-to-speech model with 103k downloads in 30 days that says apache-2.0. FinePrint finds Llama 3.2 terms three hops up (adapter, fine-tune, fine-tune), lists them with the license text, and draws the path.
2. Flip to "direct parents only", which is what the model page shows. The same model looks clean.
3. Open `ifmylove2011/girlslike`, an apache-2.0 LoRA on FLUX.1-dev. For commercial use the answer is BLOCK, because FLUX.1 [dev] terms apply to every derivative. Switch to non-commercial use and it becomes CONDITIONS.
4. Open `unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit`: Unsloth's own repo, apache-2.0 on top of a Qwen Research model. BLOCK for commercial use.
5. Open `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`. It declares MIT and names no base model in its tags, so FinePrint says UNKNOWN. Press "read the card": the agent quotes "DeepSeek-R1-Distill-Llama-8B is derived from Llama3.1-8B-Base", resolves Llama-3.1-8B in the graph, and the verdict becomes CLOUDED with Llama 3.1 terms. The demo puts the graph back afterwards so every visitor sees the same starting point.
6. Take any Hugging Face model URL and replace `huggingface.co` with the FinePrint domain.

## Verdicts and decisions

| Verdict | Meaning |
|---|---|
| NO LIENS FOUND | Nothing restricted upstream, with a coverage score for how much of the chain is known |
| LIENS | Obligations carried down from upstream, each tied to the clause that creates it |
| CLOUDED | The declared license differs from upstream terms |
| UNKNOWN | No declared license, no declared lineage for a model that looks derived, a deleted ancestor, or not on the Hub |

Liens are contractual (the license says so) or contested (legally unsettled, such as a non-commercial dataset's terms reaching trained weights). For a given use, commercial or not, FinePrint answers BLOCK when a contractual lien is non-commercial, CONDITIONS when obligations or open questions remain, and ALLOW otherwise.

## How it works

```
Hub dump: 3.16M models, 66k datasets  ->  DuckDB parse of base_model, dataset and license tags
                                       ->  FalkorDB: bulk load, then MERGE of every model
Audit (in FalkorDB)   a multi-source UDF walk from every restricted model marks all descendants;
                      Cypher counts the results
Examiner (rules)      ancestor walk, liens with clauses, k-shortest proof paths, decision for the use
Clerk (LLM)           reads a model card, extracts stated lineage with a quote, resolves names in the
                      graph, writes typed edges marked source='card'
Agent tools           MCP server, a download guard for huggingface_hub, a CLI that fails a build
```

The LLM never writes Cypher and never decides a verdict. Every claim it makes must quote the card word for word and resolve to a node that already exists, or it is reported as "not in graph".

## Org rulings

A legal team rules once on a license or a model, and every later check for that org applies the ruling. Each org has its own FalkorDB graph, `org:<slug>`, of `(:Ruling)` nodes (range index on `target`; a newer ruling points `[:SUPERSEDES]` at the one it replaces), so orgs never see each other's rulings and `hub` is never written. A reject on a license in the liens, on the model or on any ancestor gives BLOCK. An approve lifts CONDITIONS to ALLOW only when it covers every lien and nothing else is open (coverage below 100%, UNKNOWN, unresolved card claims, contested dataset terms), and it never lifts BLOCK. The report's `org` section lists each ruling that applied, with the decision before and after. Agents record rulings with the MCP tool `record_ruling` and pass `ruleset` to `check_model`; the CLI and guard take `--ruleset` or `FINEPRINT_RULESET`.

```bash
curl -X POST localhost:8000/api/rulings/my-team -H 'content-type: application/json' \
  -d '{"scope":"license","target":"llama3.1","effect":"approve","use":"commercial",
       "note":"Llama 3.1 terms reviewed, LEG-31","conditions":"Ship LICENSE and show Built with Llama"}'
curl 'localhost:8000/api/report/meta-llama/Llama-3.1-8B-Instruct?ruleset=my-team'   # CONDITIONS -> ALLOW
```

`scripts/seed_rulings.py` builds the read-only demo ruleset `acme-legal`.

## Graph model

```
(:Model {id, license, license_tag, license_name, downloads, task, own_params, languages,
         has_license_file, inherits, contested, missing})
(:Dataset {id, license, missing, downloads})

(:Model)-[:FINETUNE_OF]->(:Model)
(:Model)-[:ADAPTER_OF]->(:Model)
(:Model)-[:MERGE_OF]->(:Model)        a merge has two or more of these
(:Model)-[:QUANTIZED_FROM]->(:Model)
(:Model)-[:TRAINED_ON {source, quote, by, read_from}]->(:Dataset)

(:License {key, family, commercial, permissive})-[:IMPOSES]->(:Clause {code, obligation, quote, source, tier})
(:Model)-[:LICENSED_UNDER]->(:License)         1,055,181 edges
```

`license` is the effective license: the declared tag, or the named license behind `license: other` (123,135 models use that form, including 43,164 under FLUX.1 [dev]).

## Queries and algorithms

Lineage walks run inside FalkorDB as JavaScript UDFs ([db/udf/lineage.js](db/udf/lineage.js)). A variable-length Cypher match enumerates paths, and with merges the number of paths explodes; the UDF visits each model once.

```cypher
MATCH (m:Model) WHERE m.id = $id RETURN lineage.ancestors(m, 64)
MATCH (m:Model) WHERE m.id = $id RETURN lineage.descendantStats(m, 64)

// Hub-wide audit: mark everything below every model under a restricted license
MATCH (r:Model) WHERE r.license IN $keys WITH collect(r) AS roots
RETURN lineage.descendantIds(roots)
```

The obligations a model inherits, composed in one query: the lineage walk, then each ancestor's license, then the clauses that license imposes.

```cypher
MATCH (m:Model) WHERE m.id = $id
WITH lineage.ancestors(m, 64) AS anc
UNWIND anc AS a
MATCH (x:Model)-[:LICENSED_UNDER]->(l:License)-[:IMPOSES]->(c:Clause)
WHERE x.id = a.id AND l.permissive = false
WITH l, c, a ORDER BY a.depth
RETURN l.family, l.commercial, head(collect(a.id)) AS via, min(a.depth) AS depth,
       collect(DISTINCT c.obligation) AS obligations
```

Every route by which a lien reaches a model, shortest first:

```cypher
MATCH (s:Model), (t:Model) WHERE s.id = $s AND t.id = $t
CALL algo.SPpaths({sourceNode: s, targetNode: t,
                   relTypes: ['FINETUNE_OF','ADAPTER_OF','MERGE_OF','QUANTIZED_FROM'],
                   relDirection: 'outgoing', pathCount: 3})
YIELD path
RETURN [n IN nodes(path) | n.id], [r IN relationships(path) | type(r)]
```

The headline count:

```cypher
MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $permissive
RETURN count(m), sum(m.downloads)
```

What-if on a copy (`scripts/what_if.py`): the FLUX.1-dev family is written to its own graph, copied, and the copy is edited and re-walked.

```
GRAPH.COPY family:flux1-dev whatif:flux1-dev-apache
MATCH (m:Model) WHERE m.id = 'black-forest-labs/FLUX.1-dev' SET m.license = 'apache-2.0'   // on the copy
MATCH (r:Model) WHERE r.license = $nc WITH collect(r) AS roots RETURN lineage.descendantIds(roots)
```

Load-bearing models (`GET /api/load-bearing`):

```cypher
CALL algo.pageRank('Model', null) YIELD node, score
RETURN node.id, node.license, score ORDER BY score DESC LIMIT 20
```

Clean substitutes of the same task, size and language, with nothing restricted upstream (`GET /api/substitutes/...`):

```cypher
MATCH (m:Model) WHERE m.id = $id
MATCH (c:Model) WHERE c.task = m.task AND c.license IN $permissive
  AND size(c.inherits) = 0 AND size(c.contested) = 0
  AND c.own_params >= m.params * 0.65 AND c.own_params <= m.params * 1.35
  AND NOT (c)-[:QUANTIZED_FROM|ADAPTER_OF]->()
RETURN c.id, c.license, c.own_params, c.downloads ORDER BY c.downloads DESC LIMIT 5
```

## Why a graph

The Hugging Face API lists a model's direct children, 1,000 per page. Finding all 21,639 descendants of Llama-3.1-8B that way takes 21,653 calls, about 3.7 hours at the measured 0.61 s per call; FalkorDB returns the same set in 70 ms ([scripts/hub_api_comparison.py](scripts/hub_api_comparison.py)). A Python BFS over an in-memory edge list is also fast once the edges are loaded; what the graph adds is one store that holds lineage, datasets, licenses and the Clerk's evidence together, serves single-model checks and Hub-wide audits from the same data, and takes new edges without a rebuild.

## Measured

| Operation | Time |
|---|---|
| Verdict for one model (warm) | 3 to 70 ms |
| Ancestor walk | about 3 ms |
| All descendants of Llama-3.1-8B (21,639 models, 14 levels) | 70 ms |
| Audit walk, all Qwen Research descendants (73,794 models) | 0.4 s |
| Headline count over 3.16M models | about 1 s |
| PageRank over 3.16M models | 1 to 2 s |
| Relicensing points, found and counted | 18 s |
| Clerk reading one card | about 8 s |

## Evaluation

120 models in seven strata: clouded two or more hops up, clouded one hop up, consistent liens, clean, FLUX.1-dev derivatives, merges, and a random sample of recently updated models. Gold labels come from a separate script that walks lineage through the live Hugging Face API, not our dump or graph ([eval/build_gold.py](eval/build_gold.py)), hashed before any system ran. [eval/run_eval.py](eval/run_eval.py) refuses to score if a gold file changed. No candidates were dropped. Candidates were drawn with a fixed seed. The two clouded strata come from FinePrint's own mismatch list (built from the dump), so they lean toward cases the graph already finds. The other five come from Hub API listings: children of Llama-3.1-8B-Instruct, children of Qwen2.5-7B-Instruct, the first 400 FLUX.1-dev children, the 500 most downloaded merges, and the 1,000 most recently modified models. Every candidate was then labelled only by the live-API walk.

Two gold versions are published. v2 ([eval/GOLD_V2_SHA256](eval/GOLD_V2_SHA256)) labels a model with no declared license as clean. v3 ([eval/GOLD_V3_SHA256](eval/GOLD_V3_SHA256)) relabels the same models with one rule changed: no declared license means UNKNOWN, because no license grants no rights. v3 was written after v2 had been scored, and both are reported.

The column that matters for shipping is "said clean when it isn't": the system answered NO LIENS FOUND for a model whose gold label carries restricted terms.

| System | Said clean when it isn't (v2) | Correct (v2) | Correct (v3) | Restricted terms 2+ hops up (v2) | Inherited families found | Time per model |
|---|---|---|---|---|---|---|
| Declared license alone | 33 of 69 | 43/120 | 77/120 | 0/19 | 23/69 | |
| Direct parents only (the model page) | 19 of 69 | 75/120 | 84/120 | 0/19 | 48/69 | one API call |
| LLM reading the model card | 8 of 69 | 82/120 | 88/120 | 7/19 | 55/69 | |
| LLM agent with Hub API tools | 5 of 69 | 92/120 | 91/120 | 14/19 | 64/69 | median 11 s, 3 to 10 Hub calls |
| FinePrint | 0 of 69 | 80/120 | 103/120 | 19/19 | 69/69 | median 9 ms, one graph query |

FinePrint abstains (UNKNOWN) on 36 models: 29 declare no license, and the rest have an upstream license outside the library or a derived name with no declared base. When it commits to an answer it is right 80 times out of 84 on v2. The gold labels apply the same license rules through an independent data path, so they measure how far the alternatives fall behind rather than legal truth. Both LLM baselines use the same model as the Clerk. Rows: [eval/results_v2.json](eval/results_v2.json), [eval/results_v3.json](eval/results_v3.json).

### The strongest baseline: an LLM agent with Hub API tools

[eval/tool_agent.py](eval/tool_agent.py) gives an LLM the live Hub API and lets it trace lineage itself. Its tools are `model_info`, `model_card` (first 6,000 characters), `dataset_info` and `list_models`, with at most 10 calls per model. The prompt tells it to follow `base_model` up as far as it goes, check every branch of a merge, and check ancestor and dataset licenses. It never sees the graph. Every Hub response is cached in `eval/cache/hub_tool/`, so a rerun replays the same tool results. Per-model runs, traces and token counts are in [eval/tool_agent_runs.json](eval/tool_agent_runs.json).

It is a strong baseline, and on v2 it is more accurate than FinePrint: 92 against 80. Most of that gap is the 29 models with no declared license, where FinePrint answers UNKNOWN and v2 counts that as wrong. On v3, which treats no license as UNKNOWN, FinePrint leads 103 to 91.

The agent's misses are the ones a graph is for. It called a restricted model clean five times, and all five are GGUF quantizations of merge trees (for example `MaziyarPanahi/T3qm7xExperiment26-7B-GGUF`, where the CC BY-NC ancestor is 9 hops up). Its call budget runs out before it reaches the restricted ancestor, or it meets a gated repo and stops. It got 6 of 15 merges right and 14 of 19 models with terms two or more hops up. FinePrint walks the whole tree in one UDF call and found 19 of 19.

What it costs. The agent made 471 Hub calls across the 120 models (mean 3.9, 8 hit the cap of 10) and took a median 11.5 seconds per model (90th percentile 22 s, six running at once). The run used 1.64M input tokens, mostly cache reads, and 98K output tokens, $4.79 at $5/$25 per million. FinePrint answered the same 120 models with no model calls, median 9 ms. The agent's answer also depends on what the Hub serves at that moment: a gated or deleted ancestor is a dead end for it.

Other cases worth reading:

- `bartowski/TQ2.5-14B-Aletheia-v1-GGUF`: every declared ancestor is apache-2.0, but one card says it was distilled from Llama 3.1 405B outputs, so the agent answered CLOUDED. The gold walk only follows declared base models and says clean. FinePrint is also wrong here (LIENS).
- `florianvoss/LFM2-VL-3B-Autoround-a16w4` traces to LiquidAI's LFM Open License, which has a revenue threshold. The agent called it LIENS; gold says clean because that license is not in the gold's restricted list. This one is arguably a gap in the gold labels, not an agent error.

The Clerk was checked by hand: of 48 edges it wrote from 133 popular cards, 41 were correct (85%). The seven wrong ones (calibration sets recorded as training data, a quant pointed at the wrong size) are listed with reasons in [eval/clerk_precision.json](eval/clerk_precision.json) and removed by [scripts/clerk_cleanup.py](scripts/clerk_cleanup.py).

## A FalkorDB bug we hit

In FalkorDB v4.22.1, `getNeighbors` and `graph.traverse` in a UDF follow only the last type in a `types` list. The UDFs work around it by traversing one type at a time. Repro: [docs/upstream/falkordb-udf-types-last-only.md](docs/upstream/falkordb-udf-types-last-only.md).

## Tests

- `api/tests`: 40 tests against the live graph: a networkx oracle that rebuilds lineage independently and checks the UDF on 200 random models and three large families, regression tests for every false ALLOW a reviewer found, a fail-closed check on models below unrecognised licenses, a latency test on a merge-heavy model, and 14 org rulings tests (fail-closed approvals, rejects, isolation between rulesets, no Ruling nodes in `hub`).
- `agent/tests`: 91 unit tests (guard, CLI, twelve MCP tools, hook, fail-closed, org rulings) and 14 live tests.
- `eval/`: the sealed evaluation above.

## Run it

Every number in this README can be rebuilt with [scripts/reproduce.sh](scripts/reproduce.sh). The steps:

```bash
docker run -d --name fineprint-db -p 6379:6379 -p 3000:3000 \
  -v fineprint-data:/var/lib/falkordb/data falkordb/falkordb:v4.22.1
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python duckdb pyarrow falkordb networkx fastapi uvicorn anthropic falkordb-bulk-loader pytest

# data: models.parquet and datasets.parquet from huggingface.co/datasets/cfahlgren1/hub-stats into data/raw/
.venv/bin/python scripts/headline.py
.venv/bin/python scripts/export_graph.py
(cd data/bulk && ../../.venv/bin/falkordb-bulk-insert hub -n Model.csv -r FINETUNE_OF.csv -r ADAPTER_OF.csv -r MERGE_OF.csv -r QUANTIZED_FROM.csv -d -j STRING)
docker exec -i fineprint-db redis-cli -x GRAPH.UDF LOAD REPLACE lineage < db/udf/lineage.js
.venv/bin/python scripts/enrich.py
.venv/bin/python scripts/load_all_models.py
.venv/bin/python scripts/update_effective_licenses.py
.venv/bin/python scripts/load_datasets.py
.venv/bin/python scripts/audit_graph.py
.venv/bin/python scripts/audit_add_families.py <families>   # see reproduce.sh
.venv/bin/python scripts/headline_graph.py
cd api && ../.venv/bin/uvicorn app:app --port 8000
```

Web front end: [web/README.md](web/README.md). Agent tools: [agent/README.md](agent/README.md).

## Limits

Lineage and licenses are what uploaders declare. A missing `base_model` means FinePrint cannot see the parent, and the coverage score and the UNKNOWN verdict say so. Each license is reduced to a short list of clauses linked to its full text; licenses not in the library (some custom community licenses) are treated as unknown, not as permissive. FinePrint flags differences with evidence; it is not legal advice.

## Data and credits

Model and dataset metadata: [cfahlgren1/hub-stats](https://huggingface.co/datasets/cfahlgren1/hub-stats) (Apache-2.0). License texts are quoted briefly and linked.

## AI assistance

This project was built with help from an AI coding assistant, as Rule 11 of the hackathon requires us to disclose. The design, the data work and every number above were checked by the author, who can explain any part of it.

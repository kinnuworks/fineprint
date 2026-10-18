# 48,975 Hugging Face models say apache-2.0. Their family trees say otherwise.

A Hugging Face model page shows you one hop of history: the license the uploader typed, and maybe the base model they fine-tuned. The terms that actually travel with a model come from every model above it. If you fine-tune a fine-tune of Llama 3.2, the Llama 3.2 agreement comes along, whatever your card says.

I wanted to know how often the label on a model disagrees with the terms it inherited. Answering that for one model is a few API calls. Answering it for the whole Hub is a graph problem, so I put the whole Hub in a graph.

## The data

The public `cfahlgren1/hub-stats` dataset has a daily snapshot of every model and dataset on the Hub. On October 18 2026 that was 3,161,594 models. I parsed it with DuckDB and loaded it into FalkorDB:

- every model as a `Model` node, with its license, task, size and downloads;
- 927,431 lineage edges, typed as `FINETUNE_OF`, `ADAPTER_OF`, `MERGE_OF` or `QUANTIZED_FROM` from the `base_model` tags;
- 386,483 `TRAINED_ON` edges to 66,243 datasets;
- 47 `License` nodes, each linked to the clauses it imposes, with the quote and the source URL for every clause.

A license on Hugging Face is often just `other`. 123,135 models use that form and put the real name in `license_name`. 43,164 of them are under FLUX.1 [dev], which is non-commercial. If you only read the tag, you miss all of them.

## The finding

242,170 models sit below a model under restricted terms: Llama, Gemma, Qwen, FLUX, Mistral, OpenRAIL, DeepSeek, CC BY-NC, and licenses that say non-commercial or research-only in their name.

48,975 of those declare a permissive license, apache-2.0 or MIT or similar. They had 5.88 million downloads in the 30 days before the snapshot. More than half of them (25,627) have at least 10 downloads, so these are models people use. Only 346 ship any license or notice file.

11,442 of the 48,975 say commercial use is fine while an ancestor's license says it isn't.

The count is one Cypher query once every model is marked with what it inherits:

```cypher
MATCH (m:Model) WHERE size(m.inherits) > 0 AND m.license IN $permissive
RETURN count(m), sum(m.downloads)
```

The marking is the interesting part. For each restricted license, a JavaScript UDF inside FalkorDB starts from every model under that license and walks down to every descendant. All 73,794 descendants of Qwen Research models take 0.4 seconds.

## Where the wrong labels come from

54% of the 48,975 carry one exact set of tags: `unsloth`, `text-generation-inference`, `license:apache-2.0`. That's the model card template in Unsloth's `save.py`, which writes `license: apache-2.0` on every upload whatever the base model's license is. People fine-tune Llama or Qwen with Unsloth, press push, and the card says apache.

Nobody did anything wrong on purpose. It's a default in a template, multiplied across tens of thousands of uploads. I wrote a patch that reads the license from the base model (following Unsloth's own mirrors up to the original) and falls back to `other` when it can't. It covers both the library and Unsloth Studio, and Unsloth's own card and export tests pass with it.

The graph also finds where a wrong label starts. 38,489 models declare a permissive license directly on top of a restricted parent. Below 2,438 of them sit 9,386 more models that copied the wrong label from their parent rather than writing it.

## Why a graph and not the API

The Hugging Face API lists a model's direct children, 1,000 per page. Finding all 21,639 descendants of Llama-3.1-8B that way takes 21,653 calls, about 3.7 hours at the 0.61 seconds per call I measured. FalkorDB returns the same set in 70 ms.

A Python BFS over an edge list in memory would also be fast. What the graph gave me was one store holding lineage, datasets, licenses and clauses together, which serves a single model check and a Hub-wide audit from the same data and takes new edges without a rebuild. The obligations a model inherits come out of one query: walk the ancestors, follow each one's `LICENSED_UNDER` edge, collect the clauses.

```cypher
MATCH (m:Model) WHERE m.id = $id
WITH lineage.ancestors(m, 64) AS anc
UNWIND anc AS a
MATCH (x:Model)-[:LICENSED_UNDER]->(l:License)-[:IMPOSES]->(c:Clause)
WHERE x.id = a.id AND l.permissive = false
RETURN l.family, min(a.depth), collect(DISTINCT c.obligation)
```

`algo.SPpaths` then gives the three shortest routes by which a license reaches a model, which is the proof shown on screen. PageRank over lineage says the most depended-on model on the whole Hub is `black-forest-labs/FLUX.1-dev`, which is non-commercial.

One more question I could only ask with a graph: what if Black Forest Labs relicensed FLUX.1-dev as Apache-2.0 tomorrow? FinePrint copies the 43,700-model family with `GRAPH.COPY`, changes the license on the copy, walks it again and deletes the copy, in about half a second per request. 27,592 models would still be labelled non-commercial, because their own cards copied the FLUX label and each uploader would have to edit theirs.

## The tool: FinePrint

All of this became FinePrint. Give it a model id and a use (commercial or not) and it answers ALLOW, CONDITIONS or BLOCK, with every inherited clause, the license text it comes from, and the path through the family tree.

It fails closed. If any part of the chain is unknown, if an ancestor's license isn't one it recognises, or if the card makes a claim it couldn't resolve, it won't say ALLOW.

Some models don't declare their base in tags at all. `deepseek-ai/DeepSeek-R1-Distill-Llama-8B` says MIT and names no base model, so the tags alone give UNKNOWN. An LLM agent reads the card, quotes "DeepSeek-R1-Distill-Llama-8B is derived from Llama3.1-8B-Base", finds `meta-llama/Llama-3.1-8B` in the graph, and writes a typed edge marked with its source and quote. The rules then see Llama 3.1 terms. The LLM never writes a query and never decides a verdict. It only adds evidence the rules can check, and every claim must quote the card word for word.

The same decision runs in places where developers already are:

- an MCP server, so a coding agent can check a model, find a clean substitute of the same task and size, and draft the notice file;
- `fineprint.guard()`, which stops a `from_pretrained` download of a blocked model before the weights arrive;
- `fineprint check`, a CLI that fails a CI build when a repo pulls in a model that is blocked for its use.

## Does it work?

I built a sealed test set of 120 models across seven groups (restricted terms two or more hops up, one hop up, clean, FLUX derivatives, merges, a random sample and so on). The gold labels came from a separate script that walks lineage through the live Hugging Face API, not through my dump or graph, and the file was hashed before any system ran.

The number I care about is how often a system calls a restricted model clean, because that is the mistake that ships. Reading the declared license alone did it 33 times out of 69. Looking at direct parents, which is what the model page shows, did it 19 times. An LLM reading the model card did it 8 times.

The strongest baseline was an LLM agent with the live Hub API as tools, allowed 10 calls per model, told to follow every base model up and check every license. It was good. It got more models right than FinePrint on one version of the labels (92 against 80), mostly because FinePrint answers UNKNOWN for models that declare no license at all. But it still called a restricted model clean 5 times, and all five were quantized copies of merge trees where the restricted ancestor sat many hops up. It ran out of calls, or hit a gated repo, before it got there. It needed a median 11 seconds and about 4 Hub calls per model.

FinePrint called a restricted model clean 0 times, found the restricted terms in all 19 cases where they sit two or more hops up, and answered in a median 9 ms with no model calls. It says UNKNOWN when it doesn't know, which costs some answers and is the right trade for this kind of tool.

## What it isn't

These are differences between a declared license and upstream terms, not legal findings. Some of these models may have permission I can't see. Whether a non-commercial dataset's terms reach the weights trained on it is legally unsettled, and FinePrint marks those as contested and does not treat them as settled. The point is to show the question before you ship, with the evidence attached.

## Thanks

FalkorDB for the database and the hackathon, and `cfahlgren1/hub-stats` for the daily Hub snapshot that made a Hub-wide count possible. Along the way I hit a FalkorDB UDF bug: a `types` list in `graph.traverse` follows only its last type. The repro is in the repo.

Every number in this post comes from a script listed in the repo's CLAIMS.md, and the whole thing rebuilds from one `reproduce.sh`.

## Links

- Try it: https://fineprint-plum.vercel.app
- Code: https://github.com/kinnuworks/fineprint
- Demo video: https://youtu.be/GyyAkWWM_AA

Built for Graph Hacks: Context for AI Agents (WeMakeDevs x FalkorDB). I used an AI coding assistant while building it; the README says how.

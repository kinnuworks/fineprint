# Five minutes with FinePrint

Live site: [fineprint-plum.vercel.app](https://fineprint-plum.vercel.app) (API: [api-production-9f25.up.railway.app](https://api-production-9f25.up.railway.app/api/health)) · Video: _added at upload_ · Every number: [CLAIMS.md](CLAIMS.md)

## Minute 1: the number

Open the site. 48,975 Hugging Face models declare apache-2.0, MIT or another permissive license while a model they were built on carries restricted terms. 11,442 of them sit below a non-commercial license. Only 346 ship a license file. All counts are Cypher queries over one FalkorDB graph of all 3.16M models.

## Minute 2: a model the page says is fine

Open `kenpath/svara-tts-v1` (text-to-speech, 103k downloads in 30 days, says apache-2.0). FinePrint shows Llama 3.2 terms three hops up and the clauses that come with them. Switch to "Direct parents only", which is what the model page shows: it looks clean.

## Minute 3: block for commercial use

Open `ifmylove2011/girlslike`, a FLUX LoRA that says apache-2.0. Commercial use: BLOCK. Non-commercial: CONDITIONS. Below the verdict are clean models of the same task and size.

## Minute 4: the agent reads a card

Open `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`, which declares MIT. Hub tags alone: UNKNOWN (it names no base model). Press "Read the card". The agent quotes "DeepSeek-R1-Distill-Llama-8B is derived from Llama3.1-8B-Base", resolves `meta-llama/Llama-3.1-8B` in the graph, and the verdict becomes CLOUDED with Llama 3.1 terms. The LLM never writes Cypher and never decides a verdict.

## Minute 5: it acts in code

```bash
pip install "fineprint-agent @ git+https://github.com/kinnuworks/fineprint#subdirectory=agent"
FINEPRINT_API=https://api-production-9f25.up.railway.app fineprint check demo --use commercial   # exits 1: BLOCK on a Qwen Research model
```

The same decision drives the MCP server for coding agents and `fineprint.guard()`, which stops a `from_pretrained` download before the weights arrive. See [agent/README.md](agent/README.md).

## If you have one more minute

- Org rulings: open `meta-llama/Llama-3.1-8B-Instruct` and pick "Org rulings: acme-legal". The company's stored approval of the Llama 3.1 terms turns CONDITIONS into ALLOW, and the panel shows which ruling did it. Each company's rulings live in their own FalkorDB graph (`org:acme-legal`), and an agent records new ones through the `record_ruling` MCP tool.
- [eval/results_v2.json](eval/results_v2.json): on 120 sealed models, FinePrint never called a restricted model clean (0 of 69); an LLM reading the card did so 8 times.
- `GET /api/what-if`: relicense FLUX.1-dev as Apache-2.0 on a `GRAPH.COPY` of its family, and 27,592 of 43,700 models are still labelled non-commercial, because their own cards copied the label.
- [docs/upstream/](docs/upstream/): the FalkorDB UDF bug we hit, and a fix for the card template behind 54% of the mismatches.

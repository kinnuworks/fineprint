# fineprint (agent tools)

Tools that let code and coding agents ask FinePrint about a Hugging Face model before using it:

- an MCP server with twelve tools: five per-model tools (`check_model`, `explain_path`, `downstream`, `draft_remediation`, `find_clean_substitute`), five that expose FalkorDB graph algorithms and Hub-wide numbers (`search_models`, `load_bearing`, `relicense_points`, `what_if_flux`, `hub_stats`), and two for org rulings (`record_ruling`, `list_rulings`),
- `fineprint.guard()`, which checks every `huggingface_hub` download (and so every `from_pretrained`) first,
- a `fineprint` CLI that scans a repo for model ids and prints a markdown table, with exit codes for CI and hooks.

Everything here calls the FinePrint HTTP API. Only `record_ruling` writes, and only to the org's own graph `org:<ruleset>`, never to `hub`. Nothing posts to the Hub. Set the API base URL with `FINEPRINT_API` (default `http://localhost:8000`).

Every tool acts on the API's **decision** for an intended use, `commercial` (default) or `noncommercial`:

| Decision | Meaning | CLI exit | Guard in block mode |
|---|---|---|---|
| `ALLOW` | nothing restricted found upstream | 0 | downloads, quietly |
| `CONDITIONS` | obligations to meet before shipping (attribution, license copy, naming), or lineage unknown | 0, or 2 with `--strict` | downloads, prints the obligations |
| `BLOCK` | not usable for this use, for example non-commercial terms upstream and `use=commercial` | 1 | raises `FinePrintBlocked` |
| `N/A` | no such public model on the Hub | 0 | downloads (the Hub answers for itself) |

Each decision comes with a one-line `why`. The verdict (`NO LIENS FOUND`, `LIENS`, `CLOUDED` meaning the declared license differs from upstream terms, `UNKNOWN`) is still shown as the explanation, but it no longer sets exit codes on its own: a `CLOUDED` model with only attribution-style obligations is `CONDITIONS`, not `BLOCK`. Set the use with `--use`, `use=`, or `FINEPRINT_USE`. Results are evidence from Hub declarations, not legal advice.

## Install

```bash
uv pip install --python .venv/bin/python -e "agent[dev]"   # from the repo root
```

The import package is `fineprint`. The API uses a separate package, `fineprint_core`, so the two never clash.

## MCP server

```bash
python -m fineprint.mcp_server      # stdio transport; or the `fineprint-mcp` script
```

| Tool | Arguments | Returns |
|---|---|---|
| `check_model` | `model_id`, `use` (`commercial` default, or `noncommercial`), `ruleset` (optional, default `FINEPRINT_RULESET`) | decision and why first, then the org rulings that changed it, verdict, declared license, liens, obligations with clause text and source |
| `explain_path` | `model_id` | every lineage path by which each upstream license reaches the model |
| `downstream` | `model_id`, `k` (1-100, default 10) | descendant count, deepest chain, downloads, top k descendants |
| `draft_remediation` | `model_id` | draft NOTICE, LICENSE guidance, model-card YAML and a clause checklist (text only) |
| `find_clean_substitute` | `model_id`, `k` (1-20, default 5) | same-task, similar-size models with no liens upstream, from `/api/substitutes/{org}/{name}` |
| `search_models` | `q`, `limit` (1-50, default 10), `use` (optional) | model ids matching `q`, exact id first, then by downloads (`/api/search`); with `use`, each result's decision and why |
| `load_bearing` | `k` (1-100, default 10) | FalkorDB PageRank over lineage edges (`/api/load-bearing`): the base models most of the Hub stands on, with descendants and their 30-day downloads. PageRank also counts automated upload farms, so read it next to the download numbers |
| `relicense_points` | `k` (1-100, default 10) | models that declared a permissive license directly on a parent with restricted terms, ranked by mismatched models below them (`/api/relicense-points`) |
| `what_if_flux` | none | FLUX.1-dev relicensed as Apache-2.0 on a `GRAPH.COPY` of its family: before and after counts of models bound by non-commercial terms (`/api/what-if`) |
| `record_ruling` | `ruleset`, `scope` (`license` or `model`), `target` (license key or model id), `effect` (`approve` or `reject`), `use` (`commercial`, `non-commercial`, `any`), `note`, `conditions` (optional) | the saved ruling; later `check_model` calls with that ruleset apply it |
| `list_rulings` | `ruleset` | every ruling in the ruleset, newest first, with superseded ones marked |
| `hub_stats` | none | top-level Hub-wide numbers from `/api/stats` (models, how many inherit restricted terms, how many of those declare a permissive license, downloads, LICENSE files) |

The algorithm tools take no `use`, because the endpoints behind them are not per use. `search_models` takes one to add decisions.

`model_id` takes `org/name` or a `huggingface.co` URL. If the API is down, tools return an MCP error that says so. If the API is older and sends no `decision`, the tools fall back to ALLOW for `NO LIENS FOUND` and CONDITIONS for any other verdict, so they never block without the API's decision.

### Org rulings

When a user's legal team rules on a license or a model, the agent saves it with `record_ruling` and passes the same `ruleset` to `check_model` from then on. A reject makes matching models BLOCK. An approve lifts CONDITIONS to ALLOW only when it covers every lien and nothing else is open, and it never lifts BLOCK. The report lists each ruling that applied and the decision before and after. The CLI takes `--ruleset SLUG`, and the guard reads `FINEPRINT_RULESET` (or `fineprint.guard(ruleset=...)`). The demo ruleset `acme-legal` is read-only on the API; use your own slug to write.

### Register it with your coding agent

Most MCP clients read a JSON file with an `mcpServers` map. For a project-level `.mcp.json` at the repo root:

```json
{
  "mcpServers": {
    "fineprint": {
      "command": "/absolute/path/to/Graph Hacks./.venv/bin/python",
      "args": ["-m", "fineprint.mcp_server"],
      "env": { "FINEPRINT_API": "http://localhost:8000" }
    }
  }
}
```

Use an absolute path to the venv's Python so the client starts the server with `fineprint` installed. Clients that use a different file (for example a user-level settings file) take the same `command`, `args` and `env` block.

## Download guard

```python
import fineprint
fineprint.guard("block")          # or "warn"; "off" removes it. use="commercial" by default

from transformers import AutoModelForCausalLM
AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit")
# fineprint.FinePrintBlocked: FinePrint blocked the download of
# unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit for commercial use:
# Non-commercial terms from Qwen/Qwen2.5-3B-Instruct (Qwen Research).
# Verdict: CLOUDED. Declared license: apache-2.0. Upstream terms: qwen-research via Qwen/Qwen2.5-3B-Instruct (depth 1).
# Obligations: ...
```

- `warn` prints the decision and why (plus verdict, upstream license and obligations) to stderr for `CONDITIONS` and `BLOCK` models, then downloads. `ALLOW` and `N/A` are quiet.
- `block` raises `fineprint.FinePrintBlocked` when the decision is `BLOCK`, and warns for `CONDITIONS`. The exception has `.model_id`, `.decision`, `.why` and `.report`. It derives from `BaseException` (like `KeyboardInterrupt`) so that library code which catches `Exception` and falls back to cached files cannot swallow it; catch it by name.
- `fineprint.guard("block", use="noncommercial")` or `FINEPRINT_USE=noncommercial` for research and other non-commercial work.
- Each model is checked once per process and use. Dataset and Space downloads are not checked.
- If the API cannot be reached, the guard fails open by default: it prints a `WARNING` line and lets the download go ahead. With `fail_closed=True` or `FINEPRINT_FAIL_CLOSED=1` it raises `FinePrintBlocked` instead, in both `warn` and `block` mode, and asks the API again on the next download. Models in the allow list still pass.
- Allow a specific model with `fineprint.guard("block", allow=["org/name"])` or `FINEPRINT_ALLOW=org/name,org/other`.

It works by replacing `hf_hub_download` and `snapshot_download` in `huggingface_hub` and in every loaded module that imported them (transformers keeps its own copy). Recent transformers versions serve files that are already in the local cache without calling either function, so the guard also wraps `transformers.utils.hub.cached_files`, either right away or when transformers is first imported. Call `guard()` before the first `from_pretrained`. `fineprint.unguard()` puts everything back.

### Turn it on from the environment

```bash
export FINEPRINT_GUARD=block      # block | warn | off (unset means warn)
export FINEPRINT_USE=commercial   # commercial | noncommercial (unset means commercial)
export FINEPRINT_FAIL_CLOSED=1    # block when the API is unreachable (unset means fail open, with a warning)
export FINEPRINT_RULESET=acme-legal  # apply this org's recorded rulings (unset means none)
python -c "import fineprint.autoguard; import train"
```

Or add `import fineprint.autoguard` at the top of an entry point. `fineprint.guard()` with no mode also reads `FINEPRINT_GUARD`.

## CLI

```bash
fineprint check [PATH] [--use commercial|noncommercial] [--ruleset SLUG] [--strict] [--fail-closed] [--json]
fineprint report MODEL_ID [--use commercial|noncommercial] [--ruleset SLUG] [--fail-closed] [--json] [--no-graph] [--strict]
```

`check` scans `.py`, `.ipynb`, `.yaml`, `.yml`, `.json` and `.toml` files for `from_pretrained("...")`, `hf_hub_download(...)` and `snapshot_download(...)` (positional or `repo_id=`), keys such as `model: org/name`, `model_name_or_path`, `base_model` (including YAML lists) and `model="org/name"` keyword arguments. It skips `.git`, virtualenvs, `node_modules` and build folders, and ignores strings that point at local directories.

`--use` defaults to `FINEPRINT_USE`, then `commercial`. Rows are sorted `BLOCK` first. Output for `fineprint check demo` (the repo-level `demo/`):

```text
## FinePrint check: 1 model in demo, commercial use

| Model | Decision | Why | Verdict | Declared license | Upstream terms | Found in |
|---|---|---|---|---|---|---|
| unsloth/Qwen2.5-3B-Instruct-unsloth-bnb-4bit | BLOCK | Non-commercial terms from Qwen/Qwen2.5-3B-Instruct (Qwen Research). | CLOUDED | apache-2.0 | qwen-research via Qwen/Qwen2.5-3B-Instruct (depth 1) | app.py:4, app.py:5 |

BLOCK: 1

Result: fail. At least one model is BLOCK for commercial use.
```

`demo/.github/workflows/fineprint.yml` runs the same command in CI and adds the table to the job summary.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | nothing to stop on |
| 1 | at least one `BLOCK` (models in `FINEPRINT_ALLOW` do not count), or, with `--fail-closed` / `FINEPRINT_FAIL_CLOSED=1`, at least one model that could not be checked |
| 2 | at least one `CONDITIONS`, only with `--strict` |
| 3 | the API could not be reached for any model (fail-open default; a `WARNING` goes to stderr) |
| 64 | bad usage |

## Hook: check before Python runs

`hooks/fineprint-pre-python.sh` is a PreToolUse-style hook. It reads the hook JSON on stdin, and when `.tool_input.command` runs Python (`python`, `uv run`, `pytest`, `jupyter`, `torchrun`, ...) it runs `fineprint check`. On exit 1, a `BLOCK` model (or 2, `CONDITIONS`, with `FINEPRINT_HOOK_STRICT=1`), it exits 2 with the table on stderr, which blocks the command and shows the table to your coding agent. If the check cannot run (API down, `fineprint` missing or crashing) it prints a `WARNING` and lets the command run; with `FINEPRINT_FAIL_CLOSED=1` it blocks instead. `FINEPRINT_USE` sets the use, as for the CLI.

For a coding agent that reads hooks from `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "agent/hooks/fineprint-pre-python.sh" }
        ]
      }
    ]
  }
}
```

The path is relative to the project root, where hooks usually run. Other runners that pass the command on stdin as JSON can call the same script. Set `FINEPRINT_BIN` if `fineprint` is not on `PATH` for the hook (for example `FINEPRINT_BIN=/abs/path/.venv/bin/fineprint`).

## Tests

```bash
cd agent
../.venv/bin/python -m pytest                 # unit tests, mocked API
../.venv/bin/python -m pytest -m live         # needs the API on FINEPRINT_API
../.venv/bin/python tests/smoke_mcp.py        # starts the stdio server and lists its tools
```

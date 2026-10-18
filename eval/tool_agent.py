"""Baseline: an LLM agent that calls the live Hugging Face Hub API itself.

This is the realistic alternative to FinePrint: give a strong model the Hub API and let it
trace lineage on its own. It never touches the graph. Tools:

  model_info(repo_id)    GET https://huggingface.co/api/models/{id}, trimmed
  model_card(repo_id)    https://huggingface.co/{id}/raw/main/README.md, truncated
  dataset_info(repo_id)  GET https://huggingface.co/api/datasets/{id}, trimmed
  list_models(search)    GET https://huggingface.co/api/models?search=...  (to resolve a name to an id)
  answer(...)            the final, structured verdict

At most TOOL_CAP Hub calls per model. Every HTTP response is cached on disk under
eval/cache/hub_tool/ (keyed by URL), so reruns are free and give the same tool results.
Per-model results land in eval/tool_agent_runs.json; run_eval.py scores them.

  .venv/bin/python eval/tool_agent.py --limit 5     # pilot
  .venv/bin/python eval/tool_agent.py               # every gold model not yet in the runs file
"""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "api"))
from fineprint_core.clerk import _api_key  # noqa: E402
from fineprint_core.licenses import LICENSES  # noqa: E402

MODEL = "claude-opus-5-5"
EFFORT = os.environ.get("TOOL_AGENT_EFFORT", "high")
TOOL_CAP = int(os.environ.get("TOOL_AGENT_CAP", "10"))
CARD_CHARS = int(os.environ.get("TOOL_AGENT_CARD_CHARS", "6000"))
CACHE = HERE / "cache" / "hub_tool"
RUNS = HERE / "tool_agent_runs.json"
FAMILIES = sorted({l.family for l in LICENSES.values()})
VERDICTS = ["NO LIENS FOUND", "LIENS", "CLOUDED", "UNKNOWN"]
# USD per million tokens used for the cost guard (input, output). Cache writes 1.25x input, reads 0.1x.
PRICE_IN, PRICE_OUT = 5.0, 25.0


# ---------------------------------------------------------------- Hub access with a disk cache

def hub_get(url: str) -> tuple[int, str]:
    """GET a Hub URL anonymously. Returns (status, body). Cached on disk by URL, errors included."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if path.exists():
        d = json.loads(path.read_text())
        return d["status"], d["body"]
    status, body = 0, ""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fineprint-eval-baseline"})
            with urllib.request.urlopen(req, timeout=30) as r:
                status, body = r.status, r.read().decode("utf-8", "ignore")
            break
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
            if e.code in (401, 403, 404, 410):
                break
            time.sleep(2 * (attempt + 1))
        except Exception as e:  # network error: do not cache
            status, body = 0, f"network error: {e}"
            time.sleep(2 * (attempt + 1))
    if status:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"url": url, "status": status, "body": body}))
        tmp.replace(path)
    return status, body


def _quote(repo_id: str) -> str:
    return urllib.parse.quote(repo_id.strip().strip("/"), safe="/")


def _error(status: int, what: str) -> str:
    if status in (401, 403):
        return f"HTTP {status}: {what} is gated or private; it cannot be read anonymously."
    if status == 404:
        return f"HTTP 404: {what} does not exist on the Hub (deleted, renamed, or a typo)."
    return f"HTTP {status}: could not fetch {what}."


def model_info(repo_id: str) -> str:
    status, body = hub_get(f"https://huggingface.co/api/models/{_quote(repo_id)}")
    if status != 200:
        return _error(status, f"model {repo_id}")
    d = json.loads(body)
    card = d.get("cardData") or {}
    keep = {k: card[k] for k in ("license", "license_name", "license_link", "base_model", "base_model_relation",
                                 "datasets", "extra_gated_prompt") if k in card}
    if isinstance(keep.get("extra_gated_prompt"), str):
        keep["extra_gated_prompt"] = keep["extra_gated_prompt"][:600]
    tags = d.get("tags") or []
    files = [s.get("rfilename", "") for s in d.get("siblings") or []]
    out = {
        "id": d.get("id"),
        "pipeline_tag": d.get("pipeline_tag"),
        "library_name": d.get("library_name"),
        "gated": d.get("gated"),
        "cardData": keep,
        "tags": tags[:80],
        "license_files": [f for f in files if any(w in f.lower() for w in ("license", "notice", "use_policy"))][:10],
    }
    return json.dumps(out)


def model_card(repo_id: str) -> str:
    status, body = hub_get(f"https://huggingface.co/{_quote(repo_id)}/raw/main/README.md")
    if status != 200:
        return _error(status, f"the model card of {repo_id}")
    text = body if len(body) <= CARD_CHARS else body[:CARD_CHARS] + f"\n...[truncated, {len(body)} chars total]"
    return text or "(empty model card)"


def dataset_info(repo_id: str) -> str:
    status, body = hub_get(f"https://huggingface.co/api/datasets/{_quote(repo_id)}")
    if status != 200:
        return _error(status, f"dataset {repo_id}")
    d = json.loads(body)
    card = d.get("cardData") or {}
    return json.dumps({
        "id": d.get("id"),
        "gated": d.get("gated"),
        "cardData": {k: card[k] for k in ("license", "license_name", "license_link") if k in card},
        "license_tags": [t for t in d.get("tags") or [] if t.startswith("license:")],
    })


def list_models(search: str, limit: int = 10) -> str:
    limit = max(1, min(int(limit or 10), 20))
    url = f"https://huggingface.co/api/models?search={urllib.parse.quote(search)}&limit={limit}&sort=downloads"
    status, body = hub_get(url)
    if status != 200:
        return _error(status, f"a search for {search!r}")
    rows = json.loads(body)
    return json.dumps([{"id": m.get("id"), "license": [t[8:] for t in m.get("tags") or [] if t.startswith("license:")]}
                       for m in rows])


IMPL = {
    "model_info": lambda a: model_info(a["repo_id"]),
    "model_card": lambda a: model_card(a["repo_id"]),
    "dataset_info": lambda a: dataset_info(a["repo_id"]),
    "list_models": lambda a: list_models(a["search"], a.get("limit", 10)),
}


def _repo_tool(name: str, desc: str) -> dict:
    return {"name": name, "description": desc, "strict": True, "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["repo_id"],
        "properties": {"repo_id": {"type": "string", "description": "Hub id, e.g. meta-llama/Llama-3.1-8B"}}}}


TOOLS = [
    _repo_tool("model_info", "Hub metadata for a model: declared license (cardData.license, license_name), "
               "base_model (its declared parents), base_model_relation, datasets, tags, and license files in the repo."),
    _repo_tool("model_card", f"The model's README.md text (first {CARD_CHARS} characters)."),
    _repo_tool("dataset_info", "Hub metadata for a dataset, including its declared license."),
    {"name": "list_models", "description": "Search Hub models by name, sorted by downloads. Use it to turn a model name "
     "mentioned in a card into a Hub id.", "strict": True, "input_schema": {
        "type": "object", "additionalProperties": False, "required": ["search", "limit"],
        "properties": {"search": {"type": "string"}, "limit": {"type": "integer", "description": "1 to 20"}}}},
    {"name": "answer", "description": "Give the final verdict. Call it exactly once, as your last action.",
     "strict": True, "input_schema": {
        "type": "object", "additionalProperties": False,
        "required": ["verdict", "inherited_families", "declared_license", "chain", "reason"],
        "properties": {
            "verdict": {"type": "string", "enum": VERDICTS},
            "inherited_families": {"type": "array", "items": {"type": "string", "enum": FAMILIES},
                                   "description": "Restricted license families that reach this model from upstream models."},
            "declared_license": {"type": "string", "description": "This model's own declared license, or 'none'."},
            "chain": {"type": "string", "description": "The lineage you traced, e.g. 'a/b (mit) <- c/d (llama3.1)'."},
            "reason": {"type": "string", "description": "One or two sentences."}}}},
]

SYSTEM = f"""You check whether a Hugging Face model can be used commercially, given the license terms it inherits from the models it was built on.

You have tools that call the live Hugging Face Hub API. Work like a careful engineer doing license due diligence:

1. Call model_info on the model you are asked about. Note its declared license (cardData.license; when that is "other", read license_name and license_link).
2. Trace its lineage upward. cardData.base_model lists the model's declared parents. Call model_info on each parent, then on that parent's parents, and keep going up until you reach models with no base_model. Fine-tunes, adapters (LoRA), merges and quantized copies all stay bound by the license terms of the models they derive from, however many levels up those models are. A merge has several parents; check each branch.
3. If base_model is missing or vague, the model card or the tags may name the base (for example "fine-tuned from Llama 3 8B"). Read the card with model_card, and resolve a name to a Hub id with list_models if needed.
4. Note the license of every ancestor. Datasets listed in cardData.datasets can be checked with dataset_info, but a dataset license governs the data; count it only if its terms clearly bind models trained on it.
5. Call answer.

Restricted licenses are those with non-commercial, research-only or other use restrictions, or custom terms with obligations: Llama 2/3/3.1/3.2/3.3/4 community licenses, Gemma terms, Qwen and Qwen Research licenses, CC BY-NC variants, FLUX.1 [dev] non-commercial, Mistral Research and Non-Production licenses, DeepSeek model license, OpenRAIL variants, and similar. Permissive licenses include apache-2.0, mit, bsd, cc-by-4.0, cc0-1.0, unlicense.

Report the restricted families that reach this model from upstream models, choosing from: {', '.join(FAMILIES)}.

Verdict:
- CLOUDED: the declared license is permissive, but restricted terms come from upstream.
- LIENS: restricted terms apply and the declared license is consistent with them.
- NO LIENS FOUND: nothing restricted applies.
- UNKNOWN: you cannot tell.

You may make at most {TOOL_CAP} Hub tool calls for this model (parallel calls count one each). Spend them on the lineage. When you have enough, or the budget is used up, call answer."""


# ---------------------------------------------------------------- the agent loop

_client_lock = threading.Lock()
_client_obj = None


def client() -> anthropic.Anthropic:
    global _client_obj
    with _client_lock:
        if _client_obj is None:
            key = _api_key()
            if not key:
                raise RuntimeError("No API key found (ANTHROPIC_API_KEY, .env, or Keychain).")
            _client_obj = anthropic.Anthropic(api_key=key, max_retries=5, timeout=600)
        return _client_obj


def cost_usd(u: dict) -> float:
    return (u["input"] * PRICE_IN + u["cache_write"] * PRICE_IN * 1.25 + u["cache_read"] * PRICE_IN * 0.1
            + u["output"] * PRICE_OUT) / 1e6


def run_one(model_id: str) -> dict:
    t0 = time.time()
    usage = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    trace, calls, turns, nudges, final = [], 0, 0, 0, None
    messages = [{"role": "user", "content": f"Model: {model_id}\n\nCan this model be used commercially? "
                                            "Trace its lineage with the tools, then call answer."}]
    error = None
    try:
        while turns < TOOL_CAP + 6:
            turns += 1
            r = client().messages.create(
                model=MODEL, max_tokens=16000,
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                tools=TOOLS, messages=messages,
                cache_control={"type": "ephemeral"},
                output_config={"effort": EFFORT},
            )
            u = r.usage
            usage["input"] += u.input_tokens or 0
            usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
            usage["output"] += u.output_tokens or 0
            messages.append({"role": "assistant", "content": r.content})
            uses = [b for b in r.content if b.type == "tool_use"]
            ans = next((b for b in uses if b.name == "answer"), None)
            if ans is not None:
                final = dict(ans.input)
                break
            if r.stop_reason == "refusal":
                error = "refusal"
                break
            if not uses:
                nudges += 1
                if nudges > 2:
                    break
                messages.append({"role": "user", "content": "Call the answer tool now with your verdict."})
                continue
            results = []
            for b in uses:
                if calls >= TOOL_CAP:
                    out, err = f"Tool budget of {TOOL_CAP} calls is used up. Call answer now.", True
                else:
                    calls += 1
                    try:
                        out, err = IMPL[b.name](b.input), False
                    except Exception as e:
                        out, err = f"tool error: {e}", True
                    trace.append({"tool": b.name, "args": b.input})
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out, "is_error": err})
            messages.append({"role": "user", "content": results})
    except anthropic.APIError as e:
        msg = (getattr(e, "body", None) or {}).get("error", {}).get("message", "") if isinstance(getattr(e, "body", None), dict) else ""
        error = f"{type(e).__name__}: {getattr(e, 'status_code', '')} {msg[:120]}".strip()
    final = final or {}
    verdict = final.get("verdict") if final.get("verdict") in VERDICTS else "UNKNOWN"
    return {
        "id": model_id,
        "verdict": verdict,
        "families": [f for f in final.get("inherited_families", []) if f in FAMILIES],
        "declared_license": final.get("declared_license"),
        "chain": final.get("chain"),
        "reason": final.get("reason"),
        "answered": bool(final),
        "error": error,
        "tool_calls": calls,
        "turns": turns,
        "trace": trace,
        "usage": usage,
        "cost_usd": round(cost_usd(usage), 4),
        "wall_s": round(time.time() - t0, 2),
    }


def load_runs() -> dict:
    if RUNS.exists():
        return json.loads(RUNS.read_text())
    return {"config": {}, "runs": {}}


def gold_ids() -> list[str]:
    ids = []
    for f in ("gold_v2.json", "gold_v3.json"):
        for g in json.loads((HERE / f).read_text()):
            if g["id"] not in ids:
                ids.append(g["id"])
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--redo-errors", action="store_true")
    args = ap.parse_args()

    data = load_runs()
    cfg = {"model": MODEL, "effort": EFFORT, "tool_cap": TOOL_CAP, "card_chars": CARD_CHARS}
    if data["runs"] and data.get("config") != cfg:
        print("warning: config differs from the stored runs", data.get("config"), "->", cfg, flush=True)
    data["config"] = cfg
    todo = [i for i in gold_ids() if i not in data["runs"]
            or (args.redo_errors and (data["runs"][i]["error"] or not data["runs"][i]["answered"]))]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(todo)} models to run, {len(data['runs'])} already stored", flush=True)
    lock = threading.Lock()

    def work(mid):
        res = run_one(mid)
        with lock:
            data["runs"][mid] = res
            RUNS.write_text(json.dumps(data, indent=1))
            u = res["usage"]
            print(f"{res['verdict']:15s} calls={res['tool_calls']:2d} in={u['input'] + u['cache_write'] + u['cache_read']:6d} "
                  f"out={u['output']:5d} ${res['cost_usd']:.3f} {res['wall_s']:5.1f}s {mid}"
                  + (f"  ERROR {res['error']}" if res["error"] else ""), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, todo))
    runs = list(data["runs"].values())
    tot = {k: sum(r["usage"][k] for r in runs) for k in ("input", "cache_write", "cache_read", "output")}
    print("stored runs:", len(runs), "tokens:", tot, f"cost ${cost_usd(tot):.2f}", flush=True)


if __name__ == "__main__":
    main()

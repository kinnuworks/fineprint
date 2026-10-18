"""Live Hugging Face lookups for models the graph has never seen (new uploads, typos)."""
import json
import re
import time
import urllib.error
import urllib.request

_cache: dict[str, tuple[float, dict | None]] = {}
TTL = 3600

# Repo names that almost always mean "derived from something else".
DERIVATIVE = re.compile(
    r"(gguf|awq|gptq|exl2|exl3|fp8|nvfp4|mxfp4|int4|int8|bnb|4bit|8bit|mlx|lora|qlora|adapter|"
    r"-ft\b|finetun|merge|abliterat|heretic|uncensored|quant|q4_k|q5_k|q8_0)",
    re.I,
)


# A restricted family's name in the repo id, for repos that declare no base model.
FAMILY_HINT = re.compile(r"(llama|gemma|qwen|mistral|mixtral|codestral|flux|distill)", re.I)
OFFICIAL_PREFIX = ("meta-llama/", "google/", "qwen/", "mistralai/", "black-forest-labs/")


def looks_derived(model_id: str) -> bool:
    if DERIVATIVE.search(model_id):
        return True
    return bool(FAMILY_HINT.search(model_id.split("/")[-1])) and not model_id.lower().startswith(OFFICIAL_PREFIX)


def lookup(model_id: str) -> dict | None:
    """{'license', 'bases', 'downloads'} for a public model, None if the Hub has no such model."""
    hit = _cache.get(model_id)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/models/{model_id}", timeout=10) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        result = None if e.code in (401, 404) else {"error": e.code}
        _cache[model_id] = (time.time(), result)
        return result
    except Exception:
        return {"error": "unreachable"}
    card = d.get("cardData") or {}
    lic = card.get("license") if isinstance(card.get("license"), str) else None
    lic = lic or next((t[8:] for t in d.get("tags", []) if t.startswith("license:")), "")
    bases = card.get("base_model") or []
    bases = [bases] if isinstance(bases, str) else [b for b in bases if isinstance(b, str)]
    result = {"license": lic, "bases": bases, "downloads": d.get("downloads") or 0}
    _cache[model_id] = (time.time(), result)
    return result

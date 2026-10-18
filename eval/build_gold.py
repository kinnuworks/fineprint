"""Build the gold set from the live Hugging Face API, independently of the dump and the graph.

Picks a stratified sample of models, walks each one's base_model chain through
https://huggingface.co/api/models/<id>, and labels the restricted license families
found upstream. Writes eval/gold.json and its SHA-256 to eval/GOLD_SHA256 before any
system is scored.
"""
import hashlib
import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESTRICTED = {
    "llama2": "Llama 2", "llama3": "Llama 3", "llama3.1": "Llama 3.1", "llama3.2": "Llama 3.2",
    "llama3.3": "Llama 3.3", "llama4": "Llama 4", "gemma": "Gemma",
    "cc-by-nc-4.0": "CC BY-NC", "cc-by-nc-sa-4.0": "CC BY-NC", "cc-by-nc-nd-4.0": "CC BY-NC",
    "flux-1-dev-non-commercial-license": "FLUX.1 [dev] Non-Commercial", "qwen-research": "Qwen Research",
    "tongyi-qianwen-research": "Qwen Research", "qwen": "Qwen", "tongyi-qianwen": "Qwen",
    "mnpl": "Mistral Non-Production", "mrl": "Mistral Research", "research-only": "Research only",
    "gemma-terms-of-use": "Gemma",
}
PERMISSIVE = {"apache-2.0", "mit", "bsd-3-clause", "bsd-2-clause", "afl-3.0", "cc-by-4.0", "unlicense", "cc0-1.0"}
_cache: dict[str, dict | None] = {}


def info(mid: str) -> dict | None:
    if mid in _cache:
        return _cache[mid]
    url = f"https://huggingface.co/api/models/{mid}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                d = json.load(r)
            break
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                _cache[mid] = None
                return None
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    else:
        _cache[mid] = None
        return None
    card = d.get("cardData") or {}
    lic = card.get("license") if isinstance(card.get("license"), str) else None
    if not lic:
        lic = next((t[8:] for t in d.get("tags", []) if t.startswith("license:")), None)
    if lic == "other" and isinstance(card.get("license_name"), str):
        lic = card["license_name"].strip().lower()
    bases = card.get("base_model") or []
    bases = [bases] if isinstance(bases, str) else [b for b in bases if isinstance(b, str)]
    _cache[mid] = {"license": lic, "bases": bases}
    return _cache[mid]


def walk(mid: str) -> dict:
    """Breadth-first walk up the declared base models; nearest depth per restricted family."""
    seen, frontier, families, depth = {mid}, [mid], {}, 0
    while frontier and depth < 40:
        depth += 1
        nxt = []
        for m in frontier:
            i = info(m)
            for b in (i or {}).get("bases", []):
                if b in seen:
                    continue
                seen.add(b)
                bi = info(b)
                fam = RESTRICTED.get((bi or {}).get("license") or "")
                if fam and fam not in families:
                    families[fam] = depth
                nxt.append(b)
        frontier = nxt
    return families


def label(mid: str) -> dict | None:
    i = info(mid)
    if i is None:
        return None
    fams = walk(mid)
    own = RESTRICTED.get(i["license"] or "")
    if i["license"] in PERMISSIVE and fams:
        verdict = "CLOUDED"
    elif fams or own:
        verdict = "LIENS"
    else:
        verdict = "NO LIENS FOUND"
    return {"id": mid, "declared": i["license"], "inherits": fams, "verdict": verdict,
            "max_depth": max(fams.values()) if fams else 0}


def candidates() -> dict[str, list[str]]:
    """Sample candidates by stratum from the mismatch list and the public API."""
    rng = random.Random(1018)
    mis = [json.loads(l) for l in open(ROOT / "data" / "derived" / "mismatches.jsonl")]
    deep = [m["id"] for m in mis if min(m["inherits"].values()) >= 2]
    shallow = [m["id"] for m in mis if min(m["inherits"].values()) == 1]
    out = {"clouded_deep": rng.sample(deep, 40), "clouded_shallow": rng.sample(shallow, 30)}
    for stratum, base, lim in (("flux_nc", "black-forest-labs/FLUX.1-dev", 400),):
        url = f"https://huggingface.co/api/models?filter=base_model:{base}&limit={lim}"
        out[stratum] = rng.sample([m["id"] for m in json.load(urllib.request.urlopen(url, timeout=60))], 60)
    url = "https://huggingface.co/api/models?filter=merge&limit=500&sort=downloads"
    out["merges"] = rng.sample([m["id"] for m in json.load(urllib.request.urlopen(url, timeout=60))], 60)
    url = "https://huggingface.co/api/models?limit=1000&sort=lastModified"
    out["random_recent"] = rng.sample([m["id"] for m in json.load(urllib.request.urlopen(url, timeout=60))], 80)
    for stratum, base in (("liens", "meta-llama/Llama-3.1-8B-Instruct"), ("clean", "Qwen/Qwen2.5-7B-Instruct")):
        url = f"https://huggingface.co/api/models?filter=base_model:{base}&limit=200"
        ids = [m["id"] for m in json.load(urllib.request.urlopen(url, timeout=30))]
        out[stratum] = rng.sample(ids, min(40, len(ids)))
    return out


if __name__ == "__main__":
    quota = {"clouded_deep": 15, "clouded_shallow": 15, "liens": 15, "clean": 15,
             "flux_nc": 15, "merges": 15, "random_recent": 30}
    gold, dropped = [], []
    for stratum, ids in candidates().items():
        got = 0
        for mid in ids:
            if got >= quota[stratum]:
                break
            lab = label(mid)
            if lab is None:
                continue
            want = {"clouded_deep": "CLOUDED", "clouded_shallow": "CLOUDED", "liens": "LIENS", "clean": "NO LIENS FOUND"}.get(stratum)
            if stratum.startswith("clouded") and lab["verdict"] != want:
                dropped.append({"id": mid, "stratum": stratum, "live_api_verdict": lab["verdict"]})
                continue
            gold.append({**lab, "stratum": stratum})
            got += 1
        print(stratum, got, flush=True)
    blob = json.dumps(sorted(gold, key=lambda g: g["id"]), indent=1, sort_keys=True)
    (HERE / "gold_v2.json").write_text(blob)
    (HERE / "gold_v2_dropped.json").write_text(json.dumps(dropped, indent=1))
    sha = hashlib.sha256(blob.encode()).hexdigest()
    (HERE / "GOLD_V2_SHA256").write_text(f"{sha}  gold_v2.json  sealed {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n")
    print("sealed", sha, len(gold))

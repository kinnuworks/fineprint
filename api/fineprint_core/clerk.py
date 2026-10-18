"""The Clerk: reads a model card and records lineage the card states but the Hub tags leave out.

Every claim needs a quote that appears word for word in the card, and every name
must resolve to a model or dataset already in the graph. Anything else is reported
as "not in graph" and never written.
"""
import os
import re
import urllib.request
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .graph import fulltext_ready, hub, ro

MODEL = os.environ.get("FINEPRINT_CLERK_MODEL", "claude-opus-5-5")
KEYCHAIN_SERVICE = "fineprint-anthropic"


ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _api_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment, else the project .env, else the macOS Keychain."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip('"').strip("'")
    try:
        import subprocess
        out = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _client() -> anthropic.Anthropic:
    key = _api_key()
    if not key:
        raise RuntimeError(f"No Anthropic key: set ANTHROPIC_API_KEY or add Keychain item '{KEYCHAIN_SERVICE}'.")
    base = os.environ.get("FINEPRINT_ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    return anthropic.Anthropic(api_key=key, base_url=base)

SYSTEM = (
    "You read Hugging Face model cards and list the lineage the card states in its text. Kinds: "
    "finetuned_from (trained or fine-tuned from a base model), quantized_from (this is a quantized or "
    "converted copy of a model), merged_from (one of the parents in a merge), adapter_of (a LoRA or "
    "adapter on a base model), trained_on (a dataset), generated_by (a model whose outputs made the "
    "training data). Say whether each statement is about this repository itself or about the original "
    "model it was converted from (cards of quantized repos usually describe the original). Only list "
    "what the card says, and copy the exact sentence or phrase that says it. Use Hugging Face ids "
    "(org/name) when the card gives them or links to them; otherwise give the name as written."
)

Kind = Literal["finetuned_from", "quantized_from", "merged_from", "adapter_of", "trained_on", "generated_by"]
EDGE = {"finetuned_from": "FINETUNE_OF", "quantized_from": "QUANTIZED_FROM", "merged_from": "MERGE_OF",
        "adapter_of": "ADAPTER_OF", "trained_on": "TRAINED_ON"}


class Claim(BaseModel):
    kind: Kind
    about: Literal["this_repo", "original_model"] = Field(
        description="this_repo if the sentence describes this repository; original_model if it describes the model this repo was converted from")
    name: str = Field(description="Hugging Face id if given, else the name as written in the card")
    quote: str = Field(description="Exact text copied from the card that states this")


class Extraction(BaseModel):
    claims: list[Claim]


def fetch_card(model_id: str) -> str:
    url = f"https://huggingface.co/{model_id}/raw/main/README.md"
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")


def _body(card: str) -> str:
    if card.startswith("---"):
        parts = card.split("---", 2)
        return parts[2] if len(parts) == 3 else card
    return card


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _resolve(name: str, label: str) -> str | None:
    name = name.strip().strip("/").removeprefix("https://huggingface.co/").removeprefix("datasets/")
    rows = ro(f"MATCH (n:{label}) WHERE n.id = $id RETURN n.id", {"id": name})
    if rows:
        return rows[0][0]
    if "/" not in name and len(name) >= 4:
        rows = None
        toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
        if label == "Model" and toks and fulltext_ready():
            # Candidates from the fulltext index on Model.id (every token of the name), then the
            # same exact "ends with /name" test the full scan used.
            try:
                rows = ro("CALL db.idx.fulltext.queryNodes('Model', $ft) YIELD node WITH node AS n "
                          "WHERE n.id ENDS WITH $tail RETURN n.id, n.downloads ORDER BY n.downloads DESC LIMIT 2",
                          {"ft": " ".join(toks[:12]), "tail": "/" + name})
            except Exception:
                rows = None  # no fulltext index in this snapshot
        if rows is None:
            rows = ro(f"MATCH (n:{label}) WHERE n.id ENDS WITH $tail RETURN n.id, n.downloads "
                      "ORDER BY n.downloads DESC LIMIT 2", {"tail": "/" + name})
        if len(rows) == 1 or (len(rows) == 2 and (rows[0][1] or 0) > 10 * (rows[1][1] or 0)):
            return rows[0][0]
    return None


def extract(model_id: str, card: str | None = None) -> list[dict]:
    card = card if card is not None else fetch_card(model_id)
    body = _body(card)[:60000]
    client = _client()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Model: {model_id}\n\nCard:\n{body}"}],
        output_format=Extraction,
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return []
    out = []
    norm_body = _norm(body)
    for c in response.parsed_output.claims:
        if _norm(c.quote) not in norm_body:
            out.append({**c.model_dump(), "status": "quote not found in card"})
            continue
        label = "Dataset" if c.kind == "trained_on" else "Model"
        target = _resolve(c.name, label)
        out.append({**c.model_dump(), "target": target, "status": "resolved" if target else "not in graph"})
    return out


OFFICIAL = ("meta-llama/", "google/", "mistralai/", "qwen/", "black-forest-labs/", "microsoft/", "deepseek-ai/",
            "nvidia/", "openai/", "stabilityai/", "tiiuae/", "01-ai/", "allenai/", "ibm-granite/", "huggingfacetb/")


def _subject(model_id: str, about: str, claims: list[dict]) -> str | None:
    """Which model a claim belongs to.

    Claims about "the original model" go to the original only when this card itself names it
    (a resolved quantized_from claim) and that original is a direct parent in the Hub tags.
    Third-party cards never write onto an official base model. Returns None to skip the claim.
    """
    if about != "original_model":
        return model_id
    named = [c["target"] for c in claims if c.get("kind") == "quantized_from" and c.get("status") == "resolved"]
    if not named:
        return None
    original = named[0]
    if original.lower().startswith(OFFICIAL) and not model_id.lower().startswith(OFFICIAL):
        return None
    rows = ro("MATCH (m:Model)-[:QUANTIZED_FROM|FINETUNE_OF|ADAPTER_OF]->(p:Model) WHERE m.id = $id AND p.id = $p RETURN count(p)",
              {"id": model_id, "p": original})
    return original if rows and rows[0][0] else None


def _names_target(quote: str, target: str) -> bool:
    """The quote has to mention the thing it is evidence for."""
    q = quote.lower()
    tail = target.split("/")[-1].lower()
    return target.lower() in q or tail in q or tail.replace("-", " ") in q


def record(model_id: str, claims: list[dict]) -> int:
    """Write resolved claims as typed edges marked with their source. Returns edges written."""
    g = hub()
    written = 0
    unresolved = 0
    for c in claims:
        if c.get("status") != "resolved":
            unresolved += c.get("status") == "not in graph"
            continue
        edge = EDGE.get(c["kind"])
        subject = _subject(model_id, c.get("about", "this_repo"), claims)
        if not edge or subject is None or c["target"] in (model_id, subject):
            continue
        if not _names_target(c["quote"], c["target"]):
            continue
        label = "Dataset" if edge == "TRAINED_ON" else "Model"
        # Skip if the Hub tags already state this exact edge.
        exists = ro(f"MATCH (m:Model)-[r:{edge}]->(t:{label}) WHERE m.id = $m AND t.id = $t RETURN count(r)",
                    {"m": subject, "t": c["target"]})[0][0]
        if exists:
            continue
        res = g.query(f"MATCH (m:Model) WHERE m.id = $m MATCH (t:{label}) WHERE t.id = $t "
                      f"CREATE (m)-[r:{edge} {{source: 'card', quote: $q, by: 'clerk', read_from: $rf}}]->(t)",
                      {"m": subject, "t": c["target"], "q": c["quote"][:500], "rf": model_id})
        written += res.relationships_created
    g.query("MATCH (m:Model) WHERE m.id = $id SET m.unresolved_claims = $n", {"id": model_id, "n": unresolved})
    return written

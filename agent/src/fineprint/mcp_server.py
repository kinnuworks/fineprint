"""FinePrint MCP server (stdio). Run with `python -m fineprint.mcp_server`.

Every tool calls the FinePrint HTTP API (FINEPRINT_API, default http://localhost:8000).
Only record_ruling writes, and only to the org's own graph (org:<ruleset>), never to the hub graph.
"""
from __future__ import annotations

import logging
from typing import Annotated, Literal

from pydantic import Field

from . import render
from .client import ApiUnavailable, NotFound, get_api, resolve_ruleset

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

INSTRUCTIONS = (
    "FinePrint reads the license obligations a Hugging Face model inherits through its declared "
    "lineage (base models, adapters, merges, quantizations). Call check_model before recommending, "
    "downloading or shipping a model, with use='commercial' or 'noncommercial'. Act on its decision: "
    "ALLOW (nothing restricted upstream), CONDITIONS (obligations to meet first), BLOCK (do not use "
    "for this use, for example non-commercial terms upstream), N/A (no such public model). The verdict "
    "(NO LIENS FOUND, LIENS, CLOUDED meaning declared license differs from upstream terms, UNKNOWN) "
    "explains it. When the user's legal team rules on a license or a model, save it with record_ruling "
    "and pass the same ruleset to check_model; the org's rulings then apply to every later check. "
    "Results are evidence from Hub declarations, not legal advice."
)

mcp = _Server("fineprint", instructions=INSTRUCTIONS)

ModelId = Annotated[str, Field(description="Hugging Face model id, e.g. 'Qwen/Qwen2.5-7B-Instruct', or its huggingface.co URL")]


Use = Annotated[Literal["commercial", "noncommercial"],
                Field(description="Intended use. Non-commercial terms upstream make commercial use BLOCK.")]


Ruleset = Annotated[str | None, Field(
    description="Org ruleset slug (e.g. 'acme-legal') whose recorded rulings apply; defaults to FINEPRINT_RULESET")]


def _report(model_id: str, use: str | None = None, ruleset: str | None = None) -> dict:
    try:
        return get_api().report(model_id, use=use, ruleset=ruleset)
    except ValueError as e:
        raise ToolError(str(e)) from e
    except ApiUnavailable as e:
        raise ToolError(f"{e}. Start the FinePrint API or set FINEPRINT_API.") from e


@mcp.tool()
def check_model(model_id: ModelId, use: Use = "commercial", ruleset: Ruleset = None) -> str:
    """Decision for the intended use (ALLOW, CONDITIONS or BLOCK) and why, with any org rulings
    applied, then the verdict, inherited licenses and the obligations with clause text."""
    rep = _report(model_id, use, ruleset)
    out = render.summary(rep)
    try:
        rs = resolve_ruleset(ruleset)
    except ValueError:
        rs = None
    if rs and "org" not in rep:
        out = (f"Note: ruleset {rs} was not applied; this FinePrint API has no org rulings.\n") + out
    return out


def _write(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ValueError as e:  # bad input, or the API refused it (Rejected)
        raise ToolError(str(e)) from e
    except ApiUnavailable as e:
        raise ToolError(f"{e}. Start the FinePrint API or set FINEPRINT_API.") from e
    except NotFound as e:
        raise ToolError(f"This FinePrint API has no org rulings ({e.detail}).") from e


Slug = Annotated[str, Field(pattern=r"^[a-z0-9-]{3,40}$", description="Org ruleset slug, e.g. 'acme-legal'")]


@mcp.tool()
def record_ruling(
    ruleset: Slug,
    scope: Annotated[Literal["license", "model"], Field(description="Rule on a license key or one model id")],
    target: Annotated[str, Field(description="License key (e.g. 'llama3.1', 'qwen-research') or model id")],
    effect: Annotated[Literal["approve", "reject"], Field(description="approve can lift CONDITIONS; reject blocks")],
    use: Annotated[Literal["commercial", "non-commercial", "any"], Field(description="Which use the ruling covers")],
    note: Annotated[str, Field(min_length=1, max_length=500, description="The ruling in legal's words, with ticket")],
    conditions: Annotated[str | None, Field(max_length=500, description="What must be done to rely on it")] = None,
) -> str:
    """Save a legal ruling to the org's own graph so every later check_model with this ruleset
    applies it. A reject makes matching models BLOCK; an approve never lifts BLOCK."""
    r = _write(get_api().record_ruling, ruleset, scope, target, effect, use, note, conditions, "agent")
    out = f"Recorded in ruleset {ruleset}: {render.ruling_line(r)}"
    if r.get("supersedes"):
        out += f"\nSupersedes {', '.join(r['supersedes'])}."
    return out


@mcp.tool()
def list_rulings(ruleset: Slug) -> str:
    """Every ruling recorded in the org's ruleset, newest first, including superseded ones."""
    return render.rulings(_write(get_api().rulings, ruleset))


@mcp.tool()
def explain_path(model_id: ModelId) -> str:
    """Every lineage path by which each upstream license reaches the model, one path per line,
    with the relation (fine-tune, adapter, merge, quantized) and license at every hop."""
    return render.paths(_report(model_id))


@mcp.tool()
def downstream(
    model_id: ModelId,
    k: Annotated[int, Field(ge=1, le=100, description="How many top descendants to list")] = 10,
) -> str:
    """Models built on this one: total count, deepest chain, total downloads, and the top k
    descendants by downloads with their declared licenses."""
    api = get_api()
    try:
        data = api.descendants(model_id, k)
    except ValueError as e:
        raise ToolError(str(e)) from e
    except NotFound as e:
        return f"{model_id}: {e.detail}. No descendant data."
    except ApiUnavailable as e:
        raise ToolError(f"{e}. Start the FinePrint API or set FINEPRINT_API.") from e
    try:
        rep = api.report(model_id)
    except (ApiUnavailable, NotFound):
        rep = None
    return render.downstream(model_id, data, rep)


@mcp.tool()
def draft_remediation(model_id: ModelId) -> str:
    """Draft text for the model's repo owner: a NOTICE file, LICENSE guidance, corrected model-card
    YAML (license, base_model) and a clause checklist. Returns text only; posts nothing."""
    return render.remediation(_report(model_id))


@mcp.tool()
def find_clean_substitute(
    model_id: ModelId,
    k: Annotated[int, Field(ge=1, le=20, description="How many substitutes to list")] = 5,
) -> str:
    """Models with the same task and a similar size whose whole upstream chain has no liens,
    ranked by downloads. Says so plainly if the backend does not offer substitutes."""
    try:
        data = get_api().substitutes(model_id, k)
    except ValueError as e:
        raise ToolError(str(e)) from e
    except ApiUnavailable as e:
        raise ToolError(f"{e}. Start the FinePrint API or set FINEPRINT_API.") from e
    except NotFound as e:
        if e.detail == "Not Found":
            return ("Clean substitutes are not available yet: this FinePrint API has no "
                    "/api/substitutes endpoint. Use check_model on candidate models instead.")
        return f"{model_id}: {e.detail}"
    return render.substitutes(model_id, data)


def _call(fn, *args):
    try:
        return fn(*args)
    except ApiUnavailable as e:
        raise ToolError(f"{e}. Start the FinePrint API or set FINEPRINT_API.") from e
    except NotFound as e:
        raise ToolError(f"This FinePrint API does not offer that yet ({e.detail}).") from e


@mcp.tool()
def search_models(
    q: Annotated[str, Field(min_length=2, description="Part of a model id, e.g. 'Qwen2.5-7B' or 'gemma-3'")],
    limit: Annotated[int, Field(ge=1, le=50, description="How many results")] = 10,
    use: Annotated[Literal["commercial", "noncommercial"] | None,
                   Field(description="If set, also give each result's decision for this use")] = None,
) -> str:
    """Find Hugging Face model ids in the graph, exact id first, then most downloaded.
    With `use`, each result also gets its ALLOW / CONDITIONS / BLOCK decision."""
    api = get_api()
    rows = _call(api.search, q, limit)
    decisions = None
    if use:
        from concurrent.futures import ThreadPoolExecutor

        def one(mid):
            try:
                return mid, api.report(mid, use=use)
            except (ApiUnavailable, NotFound, ValueError) as e:
                return mid, {"verdict": "ERROR", "why": str(e)}

        with ThreadPoolExecutor(max_workers=8) as pool:
            decisions = dict(pool.map(one, [r.get("id") for r in rows]))
    return render.search(q, rows, decisions)


@mcp.tool()
def load_bearing(k: Annotated[int, Field(ge=1, le=100, description="How many models")] = 10) -> str:
    """Base models most of the Hub stands on: FalkorDB PageRank over lineage edges, with each
    model's descendant count and their downloads. PageRank also counts automated upload farms."""
    return render.load_bearing(_call(get_api().load_bearing, k))


@mcp.tool()
def relicense_points(k: Annotated[int, Field(ge=1, le=100, description="How many points")] = 10) -> str:
    """Models that declared a permissive license directly on a parent with restricted terms,
    ranked by how many mismatched models sit below them."""
    return render.relicense_points(_call(get_api().relicense_points, k))


@mcp.tool()
def what_if_flux() -> str:
    """Counterfactual on a GRAPH.COPY of the FLUX.1-dev family: if FLUX.1-dev were Apache-2.0,
    how many models would still be bound by non-commercial terms. Before and after counts."""
    return render.what_if(_call(get_api().what_if))


@mcp.tool()
def hub_stats() -> str:
    """Hub-wide headline numbers computed in FalkorDB: models, how many inherit restricted terms,
    how many of those declare a permissive license, their downloads, and how many ship a LICENSE file."""
    return render.hub_stats(_call(get_api().stats))


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    mcp.run("stdio")


if __name__ == "__main__":
    main()

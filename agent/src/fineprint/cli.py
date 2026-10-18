"""`fineprint check [PATH | MODEL_ID ...]` and `fineprint report MODEL_ID`.

`check` takes folders, files, or Hugging Face model ids. An argument that is not an existing
path and looks like `org/name` (or a huggingface.co URL) is checked as a model id.

The API's decision for the chosen use (--use, else FINEPRINT_USE, else commercial) sets the
exit code: 0 nothing to stop on, 1 at least one BLOCK, 2 CONDITIONS with --strict,
3 the API could not be reached for any model, 64 bad usage. With --fail-closed (or
FINEPRINT_FAIL_CLOSED=1) any model that could not be checked exits 1 instead.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from . import render
from .client import (USES, ApiUnavailable, NotFound, fail_closed, get_api, normalize_model_id, resolve_ruleset,
                     resolve_use)
from .scan import scan

EXIT_OK, EXIT_BLOCK, EXIT_CONDITIONS, EXIT_UNREACHABLE, EXIT_USAGE = 0, 1, 2, 3, 64
ORDER = {"BLOCK": 0, "CONDITIONS": 1, "ERROR": 2, "ALLOW": 3, "N/A": 4}


def _check_one(mid: str, use: str, ruleset: str | None = None) -> dict:
    try:
        return get_api().report(mid, use=use, ruleset=ruleset)
    except ApiUnavailable as e:
        return {"model": mid, "decision": "ERROR", "verdict": "ERROR", "why": str(e), "_unreachable": True}
    except (NotFound, ValueError) as e:
        return {"model": mid, "decision": "ERROR", "verdict": "ERROR", "why": str(e)}


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _places(places: list[str], n: int = 3) -> str:
    shown = ", ".join(places[:n])
    return shown + (f" (+{len(places) - n} more)" if len(places) > n else "")


def allowed() -> set[str]:
    return {x.strip() for x in os.environ.get("FINEPRINT_ALLOW", "").split(",") if x.strip()}


def table(rows: list[tuple[dict, list[str]]]) -> str:
    out = ["| Model | Decision | Why | Verdict | Declared license | Upstream terms | Found in |",
           "|---|---|---|---|---|---|---|"]
    ok = allowed()
    for rep, places in rows:
        dec = render.decision(rep)
        if rep.get("model") in ok and dec in ("BLOCK", "CONDITIONS"):
            dec = f"{dec} (allowed)"
        upstream = "" if rep.get("verdict") == "ERROR" else render.upstream_terms(rep)
        out.append("| " + " | ".join(_cell(x) for x in (
            rep.get("model"), dec, render.why(rep), rep.get("verdict"),
            rep.get("declared_license") or "none declared", upstream, _places(places))) + " |")
    return "\n".join(out)


def exit_code(reports: list[dict], strict: bool, closed: bool = False) -> int:
    ok = allowed()
    decisions = [render.decision(r) for r in reports if r.get("model") not in ok]
    if "BLOCK" in decisions:
        return EXIT_BLOCK
    if closed and any(r.get("_unreachable") for r in reports if r.get("model") not in ok):
        return EXIT_BLOCK
    if strict and "CONDITIONS" in decisions:
        return EXIT_CONDITIONS
    checked = [r for r in reports if r.get("model") not in ok]
    if checked and all(r.get("_unreachable") for r in checked):
        return EXIT_UNREACHABLE
    return EXIT_OK


def _as_model_id(arg: str) -> str | None:
    """`arg` as a model id when it is not an existing path and looks like org/name; else None."""
    if os.path.exists(arg):
        return None
    try:
        mid = normalize_model_id(arg)
    except ValueError:
        return None
    return mid if "/" in mid else None


def _collect(targets: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Model ids to check with where each was found, plus the arguments that were neither."""
    found: dict[str, list[str]] = {}
    bad: list[str] = []
    for t in targets:
        mid = _as_model_id(t)
        if mid:
            found.setdefault(mid, []).append("command line")
        elif os.path.exists(t):
            for m, hit in scan(t).items():
                found.setdefault(m, []).extend(hit.places)
        else:
            bad.append(t)
    return found, bad


def cmd_check(args) -> int:
    targets = args.path or ["."]
    hits, bad = _collect(targets)
    if bad:
        print(f"fineprint: no such file or folder, and not a model id like org/name: {', '.join(bad)}",
              file=sys.stderr)
        return EXIT_USAGE
    where = ", ".join(targets)
    if not hits:
        print(f"No Hugging Face model ids found under {where}.")
        return EXIT_OK
    ids = list(hits)
    with ThreadPoolExecutor(max_workers=8) as pool:
        reports = list(pool.map(lambda m: _check_one(m, args.use, args.ruleset), ids))
    rows = sorted(((rep, hits[mid]) for mid, rep in zip(ids, reports)),
                  key=lambda r: ORDER.get(render.decision(r[0]), 5))
    code = exit_code(reports, args.strict, args.fail_closed)
    unchecked = [r for r in reports if r.get("_unreachable")]
    if unchecked and not args.fail_closed:
        print(f"fineprint: WARNING: {len(unchecked)} of {len(reports)} models were not checked "
              f"(FinePrint API not reachable at {get_api().base}). Failing open; use --fail-closed "
              "or FINEPRINT_FAIL_CLOSED=1 to fail instead.", file=sys.stderr)
    if args.json:
        print(json.dumps([{**{k: v for k, v in rep.items() if not k.startswith("_")},
                           "decision": render.decision(rep), "found_in": places} for rep, places in rows], indent=2))
        return code

    counts: dict[str, int] = {}
    for r in reports:
        d = render.decision(r)
        counts[d] = counts.get(d, 0) + 1
    rs = f", org rulings {args.ruleset}" if args.ruleset else ""
    print(f"## FinePrint check: {len(ids)} model{'s' if len(ids) != 1 else ''} in {where}, {args.use} use{rs}")
    print()
    print(table(rows))
    print()
    changed = [(rep, line) for rep, _ in rows for line in render.org_lines(rep)[:1]
               if (rep.get("org") or {}).get("applied")]
    if changed:
        print("Org rulings applied:")
        for rep, line in changed:
            first = rep["org"]["applied"][0]
            print(f"- {rep.get('model')}: {line.split(': ', 1)[1]}. {first.get('effect')} {first.get('target')} "
                  f"[{first.get('id')}]: {first.get('note')}")
        print()
    print(", ".join(f"{d}: {counts[d]}" for d in sorted(counts, key=lambda d: ORDER.get(d, 5))))
    print()
    if code == EXIT_BLOCK and "BLOCK" not in counts:
        print(f"Result: fail (fail-closed). {len(unchecked)} model{'s' if len(unchecked) != 1 else ''} "
              f"could not be checked: FinePrint API not reachable at {get_api().base}.")
    elif code == EXIT_BLOCK:
        print(f"Result: fail. At least one model is BLOCK for {args.use} use.")
    elif code == EXIT_CONDITIONS:
        print("Result: fail (--strict). Some models have CONDITIONS to meet before shipping.")
    elif counts.get("CONDITIONS"):
        print("Result: pass with conditions. Run `fineprint report MODEL_ID` for the obligations.")
    elif code == EXIT_UNREACHABLE:
        print(f"Result: not checked. FinePrint API not reachable at {get_api().base}. "
              "Failing open (exit 3); use --fail-closed to exit 1.")
    else:
        print("Result: pass.")
    if code not in (EXIT_UNREACHABLE, EXIT_BLOCK) and unchecked:
        print(f"WARNING: {len(unchecked)} models were not checked (FinePrint API not reachable at "
              f"{get_api().base}). They did not fail this check.")
    print()
    print(render.DISCLAIMER)
    return code


def cmd_report(args) -> int:
    try:
        mid = normalize_model_id(args.model_id)
    except ValueError as e:
        print(f"fineprint: {e}", file=sys.stderr)
        return EXIT_USAGE
    try:
        rep = get_api().report(mid, graph=not args.no_graph, use=args.use, ruleset=args.ruleset)
    except ApiUnavailable as e:
        if args.fail_closed:
            print(f"fineprint: {e}. Fail-closed: treating {mid} as BLOCK.", file=sys.stderr)
            return EXIT_BLOCK
        print(f"fineprint: WARNING: {e}. Not checked (exit 3); use --fail-closed to exit 1.", file=sys.stderr)
        return EXIT_UNREACHABLE
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(render.summary(rep))
        if rep.get("liens"):
            print()
            print("Paths")
            print(render.paths(rep).split("\n", 2)[-1])
    return exit_code([rep], args.strict)


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would exit 2, which means CONDITIONS here
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _use_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--use", choices=USES, default=None,
                   help="intended use; decides BLOCK vs CONDITIONS (default: FINEPRINT_USE, else commercial)")
    p.add_argument("--ruleset", default=None, metavar="SLUG",
                   help="apply this org's recorded rulings (default: FINEPRINT_RULESET, else none)")
    p.add_argument("--fail-closed", action="store_true", default=None,
                   help="exit 1 if the API cannot be reached (default: FINEPRINT_FAIL_CLOSED, else fail open)")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="fineprint", description="Check the license terms Hugging Face models "
                                "inherit through their lineage, using the FinePrint API (FINEPRINT_API).")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    c = sub.add_parser("check", help="check model ids found in folders or files, or given directly")
    c.add_argument("path", nargs="*", metavar="PATH_OR_MODEL_ID",
                   help="folders or files to scan (default: .), or model ids like org/name")
    _use_arg(c)
    c.add_argument("--strict", action="store_true", help="exit 2 if any model is CONDITIONS")
    c.add_argument("--json", action="store_true", help="print JSON instead of a markdown table")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("report", help="full report for one model")
    r.add_argument("model_id")
    _use_arg(r)
    r.add_argument("--json", action="store_true")
    r.add_argument("--no-graph", action="store_true", help="ask the API for the graph-off answer")
    r.add_argument("--strict", action="store_true", help="exit 2 if the model is CONDITIONS")
    r.set_defaults(fn=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(args, "fail_closed"):
        args.fail_closed = fail_closed(args.fail_closed)
    if hasattr(args, "use"):
        try:
            args.use = resolve_use(args.use)
        except ValueError as e:
            print(f"fineprint: {e} (from FINEPRINT_USE)", file=sys.stderr)
            return EXIT_USAGE
    if hasattr(args, "ruleset"):
        try:
            args.ruleset = resolve_ruleset(args.ruleset)
        except ValueError as e:
            print(f"fineprint: {e}", file=sys.stderr)
            return EXIT_USAGE
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())

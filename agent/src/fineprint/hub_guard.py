"""Download guard: check a model with FinePrint before huggingface_hub downloads it.

`guard("warn")` prints FinePrint's decision (ALLOW | CONDITIONS | BLOCK) and why for any
model that is not ALLOW; `guard("block")` also raises FinePrintBlocked when the decision is
BLOCK. The decision depends on the use: commercial (default) or noncommercial. transformers' from_pretrained downloads through
hf_hub_download and snapshot_download, so it is covered too; newer transformers versions
serve already-cached files without calling either, so the guard also wraps
transformers.utils.hub.cached_files (now, or when transformers is first imported).
If the API cannot be reached the guard prints one line and lets the download go ahead.
"""
from __future__ import annotations

import functools
import importlib.abc
import os
import sys
import threading
from typing import Any, Callable, TextIO

from . import render
from .client import (Api, ApiUnavailable, NotFound, fail_closed, get_api, normalize_model_id, resolve_ruleset,
                     resolve_use)

MODES = ("warn", "block", "off")
_NAMES = ("hf_hub_download", "snapshot_download")
_HUB_MODULES = ("huggingface_hub", "huggingface_hub.file_download", "huggingface_hub._snapshot_download",
                "huggingface_hub.hf_api")


class FinePrintBlocked(BaseException):
    """Raised in block mode when FinePrint's decision for the chosen use is BLOCK.

    Derives from BaseException, like KeyboardInterrupt, so library code that catches
    Exception (transformers does, then falls back to cached files) cannot swallow it.
    Catch it by name: `except fineprint.FinePrintBlocked`.
    """

    def __init__(self, model_id: str, report: dict):
        self.model_id = model_id
        self.report = report
        self.decision = render.decision(report)
        self.why = render.why(report)
        use = report.get("use") or "commercial"
        lines = [f"FinePrint blocked the download of {model_id} for {use} use: {self.why}", *render.org_lines(report)]
        if report.get("verdict") != "NOT CHECKED":
            lines.append(f"Verdict: {report.get('verdict')}. Declared license: "
                         f"{report.get('declared_license') or 'none declared'}. "
                         f"Upstream terms: {render.upstream_terms(report)}.")
        obs = render.obligations(report)
        if obs:
            lines.append("Obligations:")
            lines += [f"  - {ob} ({lic})" for lic, _, ob in obs]
        lines.append(f"To allow it anyway: FINEPRINT_ALLOW={model_id} or fineprint.guard(allow=[{model_id!r}]). "
                     "For non-commercial work: FINEPRINT_USE=noncommercial.")
        lines.append(render.DISCLAIMER)
        super().__init__("\n".join(lines))


class _State:
    def __init__(self):
        self.mode = "off"
        self.use: str | None = None
        self.ruleset: str | None = None
        self.fail_closed: bool | None = None
        self.allow: set[str] = set()
        self.api: Api | None = None
        self.stream: TextIO | None = None
        self.cache: dict[tuple[str, str, str | None], dict | None] = {}
        self.patched: list[tuple[Any, str, Callable]] = []
        self.originals: dict[str, Callable] = {}
        self.lock = threading.Lock()


_state = _State()


def _out() -> TextIO:
    return _state.stream or sys.stderr


def _say(msg: str) -> None:
    print(msg, file=_out())


def _notice(report: dict) -> str:
    mid = report.get("model")
    use = report.get("use") or "commercial"
    lines = [f"fineprint: {mid} for {use} use: {render.decision(report)}. {render.why(report)}".rstrip(),
             *[f"  {x}" for x in render.org_lines(report)],
             f"  verdict {report.get('verdict')}; declared {report.get('declared_license') or 'none'}; "
             f"upstream: {render.upstream_terms(report)}"]
    obs = render.obligations(report)
    if obs:
        lines.append("  obligations:")
        lines += [f"  - {ob} ({lic})" for lic, _, ob in obs]
    lines.append("  details: fineprint report " + str(mid))
    return "\n".join(lines)


def _allowed(mid: str) -> bool:
    env = {x.strip() for x in os.environ.get("FINEPRINT_ALLOW", "").split(",") if x.strip()}
    return mid in _state.allow or mid in env


def _unchecked(mid: str, use: str, err: Exception) -> dict:
    return {"model": mid, "use": use, "decision": "BLOCK", "verdict": "NOT CHECKED", "liens": [],
            "why": f"FinePrint could not check this model ({err}) and fail-closed mode is on."}


def _blocks(mid: str, report: dict | None) -> bool:
    return (report is not None and _state.mode == "block" and render.decision(report) == "BLOCK"
            and not _allowed(mid))


def check(repo_id: str) -> dict | None:
    """Run the check the guard runs. Returns the report, or None if it could not be fetched.
    Raises FinePrintBlocked in block mode when the decision is BLOCK."""
    try:
        mid = normalize_model_id(repo_id)
    except ValueError:
        return None  # local paths and odd ids are not ours to judge
    use = resolve_use(_state.use)
    ruleset = resolve_ruleset(_state.ruleset)
    key = (mid, use, ruleset)
    with _state.lock:
        cached = key in _state.cache
        report = _state.cache.get(key)
    if not cached:
        api = _state.api or get_api()
        try:
            report = api.report(mid, use=use, ruleset=ruleset)
        except (ApiUnavailable, NotFound) as e:
            if fail_closed(_state.fail_closed) and not _allowed(mid):
                # Not cached, so the next download asks the API again.
                raise FinePrintBlocked(mid, _unchecked(mid, use, e)) from None
            _say(f"fineprint: WARNING: could not check {mid} ({e}). Download goes ahead unchecked "
                 "(fail-open). Set FINEPRINT_FAIL_CLOSED=1 to block instead.")
            report = None
        except ValueError:
            report = None
        with _state.lock:
            first = key not in _state.cache
            _state.cache[key] = report
        if first and report is not None and render.decision(report) in ("CONDITIONS", "BLOCK") \
                and not _blocks(mid, report):
            _say(_notice(report))
    if _blocks(mid, report):
        raise FinePrintBlocked(mid, report)
    return report


def _repo_args(args: tuple, kwargs: dict) -> tuple[str | None, str | None]:
    repo_id = kwargs.get("repo_id", args[0] if args else None)
    return repo_id, kwargs.get("repo_type")


def _wrap(name: str, original: Callable) -> Callable:
    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        if _state.mode != "off":
            repo_id, repo_type = _repo_args(args, kwargs)
            if isinstance(repo_id, str) and repo_type in (None, "model"):
                check(repo_id)
        return original(*args, **kwargs)

    wrapper.__fineprint_original__ = original  # type: ignore[attr-defined]
    return wrapper


def _patch() -> bool:
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        _say("fineprint: huggingface_hub is not installed; guard has nothing to patch.")
        return False
    import importlib
    for m in _HUB_MODULES:
        try:
            importlib.import_module(m)
        except ImportError:
            pass
    hub = sys.modules["huggingface_hub"]
    for name in _NAMES:
        if name in _state.originals:
            continue
        fn = getattr(hub, name, None)
        if fn is None:
            continue
        _state.originals[name] = getattr(fn, "__fineprint_original__", fn)
    wrappers = {name: _wrap(name, orig) for name, orig in _state.originals.items()}
    # Replace every module-level reference to the originals (huggingface_hub re-exports them,
    # and transformers and others keep their own `from huggingface_hub import ...` copies).
    for mod in list(sys.modules.values()):
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        for name, orig in _state.originals.items():
            if d.get(name) is orig:
                setattr(mod, name, wrappers[name])
                _state.patched.append((mod, name, orig))
    return True


def _patch_transformers(hub_mod) -> None:
    """Check the repo id before transformers resolves files, cached or not."""
    fn = getattr(hub_mod, "cached_files", None)
    if fn is None or hasattr(fn, "__fineprint_original__"):
        return

    @functools.wraps(fn)
    def cached_files(*args, **kwargs):
        if _state.mode != "off":
            repo = kwargs.get("path_or_repo_id", args[0] if args else None)
            if isinstance(repo, str) and kwargs.get("repo_type") in (None, "model") and not os.path.isdir(repo):
                check(repo)
        return fn(*args, **kwargs)

    cached_files.__fineprint_original__ = fn  # type: ignore[attr-defined]
    setattr(hub_mod, "cached_files", cached_files)
    _state.patched.append((hub_mod, "cached_files", fn))


class _TransformersHook(importlib.abc.MetaPathFinder):
    """Patches transformers.utils.hub right after it is first imported."""

    target = "transformers.utils.hub"

    def find_spec(self, name, path, target=None):
        if name != self.target:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                break
        else:
            return None
        loader = spec.loader
        if loader is None or not hasattr(loader, "exec_module"):
            return spec
        original_exec = loader.exec_module

        def exec_module(module):
            original_exec(module)
            _patch_transformers(module)

        loader.exec_module = exec_module
        return spec


_hook = _TransformersHook()


def _cover_transformers() -> None:
    mod = sys.modules.get(_TransformersHook.target)
    if mod is not None:
        _patch_transformers(mod)
    elif _hook not in sys.meta_path:
        sys.meta_path.insert(0, _hook)


def guard(mode: str | None = None, *, use: str | None = None, ruleset: str | None = None,
          allow: list[str] | None = None,
          fail_closed: bool | None = None, api: Api | None = None, stream: TextIO | None = None) -> None:
    """Check every Hugging Face model download with FinePrint first.

    mode: "warn" prints the decision and why, "block" also raises FinePrintBlocked when the
    decision is BLOCK, "off" removes the guard. Defaults to FINEPRINT_GUARD, then "warn".
    use: "commercial" or "noncommercial". Defaults to FINEPRINT_USE, then "commercial".
    ruleset: org ruleset slug whose recorded rulings apply. Defaults to FINEPRINT_RULESET, then none.
    allow: model ids that are never blocked (FINEPRINT_ALLOW adds more, comma separated).
    fail_closed: if True, raise FinePrintBlocked when the API cannot be reached, in either mode.
    Defaults to FINEPRINT_FAIL_CLOSED; otherwise the download goes ahead with a warning.
    """
    mode = (mode or os.environ.get("FINEPRINT_GUARD") or "warn").strip().lower()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if mode == "off":
        unguard()
        return
    if use is not None:
        resolve_use(use)  # validate now, not at the first download
    resolve_ruleset(ruleset)
    _state.use = use
    _state.ruleset = ruleset
    _state.fail_closed = fail_closed
    _state.allow = {normalize_model_id(a) for a in (allow or [])}
    _state.api = api
    _state.stream = stream
    if _patch():
        _cover_transformers()
        if mode != _state.mode:
            _state.cache.clear()  # notices are per mode, so show them again
        _state.mode = mode


def unguard() -> None:
    """Restore the original huggingface_hub functions and clear the cache."""
    for mod, name, orig in reversed(_state.patched):
        setattr(mod, name, orig)
    _state.patched.clear()
    _state.originals.clear()
    if _hook in sys.meta_path:
        sys.meta_path.remove(_hook)
    _state.cache.clear()
    _state.mode = "off"


def status() -> str:
    return _state.mode


FinePrintBlocked.__module__ = "fineprint"

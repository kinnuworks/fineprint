"""Small HTTP client for the FinePrint API. Every tool in this package goes through it."""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

DEFAULT_API = "http://localhost:8000"

_ID_PART = r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}"
MODEL_ID_RE = re.compile(rf"^(?:{_ID_PART}/)?{_ID_PART}$")
_URL_PREFIX = re.compile(r"^(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/", re.I)


USES = ("commercial", "noncommercial")
DECISIONS = ("BLOCK", "CONDITIONS", "ALLOW", "N/A")


def resolve_use(use: str | None = None) -> str:
    """`use`, else FINEPRINT_USE, else commercial. Raise ValueError for anything else."""
    u = (use or os.environ.get("FINEPRINT_USE") or "commercial").strip().lower()
    if u not in USES:
        raise ValueError(f"use must be one of {USES}, got {u!r}")
    return u


RULESET_RE = re.compile(r"^[a-z0-9-]{3,40}$")


def resolve_ruleset(ruleset: str | None = None) -> str | None:
    """`ruleset`, else FINEPRINT_RULESET, else None (no org rulings). Raise ValueError if malformed."""
    r = (ruleset if ruleset is not None else os.environ.get("FINEPRINT_RULESET") or "").strip().lower()
    if not r:
        return None
    if not RULESET_RE.match(r):
        raise ValueError(f"ruleset must match ^[a-z0-9-]{{3,40}}$, got {r!r}")
    return r


def fail_closed(flag: bool | None = None) -> bool:
    """`flag`, else FINEPRINT_FAIL_CLOSED (1/true/yes/on). Default False: fail open."""
    if flag is not None:
        return bool(flag)
    return os.environ.get("FINEPRINT_FAIL_CLOSED", "").strip().lower() in ("1", "true", "yes", "on")


class ApiUnavailable(RuntimeError):
    """The FinePrint API could not be reached or returned a server error."""


class NotFound(LookupError):
    """The API answered 404. `detail` is the API's own message."""

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def base_url() -> str:
    return os.environ.get("FINEPRINT_API", DEFAULT_API).rstrip("/")


def normalize_model_id(model_id: str) -> str:
    """Accept 'org/name', 'name', or a huggingface.co URL. Raise ValueError otherwise."""
    s = (model_id or "").strip().strip("/")
    s = _URL_PREFIX.sub("", s)
    parts = [p for p in s.split("/") if p]
    if len(parts) > 2:
        parts = parts[:2]  # drop /tree/main, /blob/... and similar suffixes
    s = "/".join(parts)
    if not MODEL_ID_RE.match(s):
        raise ValueError(f"not a Hugging Face model id: {model_id!r}")
    return s


class Rejected(ValueError):
    """The API refused the request (bad input, read-only ruleset, rate limit). The message says why."""


class Api:
    def __init__(self, base: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float | None = None):
        self.base = (base or base_url()).rstrip("/")
        t = timeout if timeout is not None else float(os.environ.get("FINEPRINT_TIMEOUT", "10"))
        self._http = httpx.Client(base_url=self.base, transport=transport, timeout=t,
                                  headers={"user-agent": "fineprint-agent/0.1"})

    def _get(self, path: str, params: dict | None = None, timeout: float | None = None) -> Any:
        return self._send("GET", path, params=params, timeout=timeout)

    def _send(self, method: str, path: str, params: dict | None = None, json: Any = None,
              timeout: float | None = None) -> Any:
        try:
            kw = {"timeout": timeout} if timeout is not None else {}
            r = self._http.request(method, path, params=params, json=json, **kw)
        except httpx.HTTPError as e:
            raise ApiUnavailable(f"FinePrint API not reachable at {self.base} ({type(e).__name__})") from e
        if r.status_code == 404:
            try:
                detail = r.json().get("detail", "Not Found")
            except ValueError:
                detail = "Not Found"
            raise NotFound(str(detail))
        if r.status_code in (403, 422, 429):
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = None
            if not isinstance(detail, str):
                detail = f"HTTP {r.status_code}"
            raise Rejected(detail)
        if r.status_code >= 400:
            raise ApiUnavailable(f"FinePrint API at {self.base} returned HTTP {r.status_code} for {path}")
        try:
            return r.json()
        except ValueError as e:
            raise ApiUnavailable(f"FinePrint API at {self.base} returned non-JSON for {path}") from e

    def report(self, model_id: str, graph: bool = True, use: str | None = None, ruleset: str | None = None) -> dict:
        """Verdict plus `decision` (ALLOW | CONDITIONS | BLOCK | N/A) and `why` for the given use.

        With a ruleset (or FINEPRINT_RULESET), the org's rulings are applied and the report gets
        an `org` section listing them."""
        mid = normalize_model_id(model_id)
        params = {"graph": "true" if graph else "false", "use": resolve_use(use)}
        rs = resolve_ruleset(ruleset)
        if rs:
            params["ruleset"] = rs
        return self._get(f"/api/report/{mid}", params)

    def rulings(self, ruleset: str) -> dict:
        rs = resolve_ruleset(ruleset)
        if not rs:
            raise ValueError("ruleset is required")
        return self._get(f"/api/rulings/{rs}")

    def record_ruling(self, ruleset: str, scope: str, target: str, effect: str, use: str, note: str,
                      conditions: str | None = None, by: str | None = None) -> dict:
        """Write one ruling to the org's own graph (`org:<ruleset>`). Never touches the hub graph."""
        rs = resolve_ruleset(ruleset)
        if not rs:
            raise ValueError("ruleset is required")
        body = {"scope": scope, "target": target, "effect": effect, "use": use, "note": note,
                "conditions": conditions, "by": by}
        return self._send("POST", f"/api/rulings/{rs}", json=body)

    def descendants(self, model_id: str, k: int = 10) -> dict:
        mid = normalize_model_id(model_id)
        if "/" not in mid:
            raise NotFound("descendants need an org/name model id")
        return self._get(f"/api/descendants/{mid}", {"k": int(k)}, timeout=90.0)

    def substitutes(self, model_id: str, k: int = 5) -> Any:
        mid = normalize_model_id(model_id)
        if "/" not in mid:
            raise NotFound("substitutes need an org/name model id")
        return self._get(f"/api/substitutes/{mid}", {"k": int(k)}, timeout=60.0)

    def search(self, q: str, limit: int = 10) -> list:
        return self._get("/api/search", {"q": q, "limit": int(limit)})

    def stats(self) -> dict:
        return self._get("/api/stats")

    def load_bearing(self, k: int = 10) -> dict:
        """PageRank over lineage edges. The first call after an API restart computes it (seconds)."""
        return self._get("/api/load-bearing", {"k": int(k)}, timeout=180.0)

    def relicense_points(self, k: int = 10) -> dict:
        return self._get("/api/relicense-points", {"k": int(k)}, timeout=60.0)

    def what_if(self, root: str | None = None, license: str = "apache-2.0") -> dict:
        """Relicense `root` on a live GRAPH.COPY of its family (the API's default root is FLUX.1-dev)."""
        params = {"license": license}
        if root:
            params["root"] = root
        return self._get("/api/what-if", params, timeout=120.0)


_default: Api | None = None
_override: Api | None = None


def get_api() -> Api:
    """The shared client. Tests replace it with set_api()."""
    global _default
    if _override is not None:
        return _override
    if _default is None or _default.base != base_url():
        _default = Api()
    return _default


def set_api(api: Api | None) -> None:
    """Use `api` for every tool call; None goes back to the FINEPRINT_API default."""
    global _override
    _override = api

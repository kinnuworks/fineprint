"""Find Hugging Face model ids referenced in a repo."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

EXTENSIONS = {".py", ".ipynb", ".yaml", ".yml", ".json", ".toml"}
SKIP_DIRS = {".git", ".hg", ".venv", "venv", "env", "node_modules", "__pycache__", ".mypy_cache",
             ".pytest_cache", ".ruff_cache", ".tox", ".nox", "site-packages", "dist", "build",
             ".ipynb_checkpoints", ".next", ".cache"}
MAX_BYTES = 2_000_000

_PART = r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}"
_ID = rf"{_PART}(?:/{_PART})?"
_Q = r"[\"']"

PATTERNS = [
    # from_pretrained("org/name") and from_pretrained(pretrained_model_name_or_path="org/name")
    re.compile(rf"from_pretrained\(\s*(?:pretrained_model_name_or_path\s*=\s*)?{_Q}({_ID}){_Q}"),
    # hf_hub_download("org/name", ...) / snapshot_download("org/name")
    re.compile(rf"(?:hf_hub_download|snapshot_download)\(\s*{_Q}({_ID}){_Q}"),
    # hf_hub_download(..., repo_id="org/name", ...)
    re.compile(rf"(?:hf_hub_download|snapshot_download)\([^)]*?repo_id\s*=\s*{_Q}({_ID}){_Q}", re.S),
]
# model: org/name, "model_name_or_path": "org/name", model="org/name", base_model = "org/name".
# Needs a slash so plain words are not taken for ids.
KEY_PATTERN = re.compile(
    rf"[\"']?\b[\w-]*(?:model|repo_id|tokenizer)[\w-]*[\"']?\s*[:=]\s*{_Q}?({_PART}/{_PART}){_Q}?(?=[\s,}}\])#]|$)",
    re.I | re.M,
)
# YAML list under base_model:
BASE_LIST = re.compile(r"^base_model:\s*\n((?:\s*-\s*\S+\s*\n?)+)", re.M)

FILE_SUFFIXES = (".json", ".bin", ".safetensors", ".pt", ".pth", ".ckpt", ".py", ".txt", ".yaml", ".yml",
                 ".toml", ".csv", ".parquet", ".md", ".onnx", ".gguf", ".h5", ".msgpack", ".model", ".jsonl")
LOCAL_FIRST = {"data", "datasets", "models", "model", "outputs", "output", "checkpoints", "checkpoint", "ckpt",
               "tmp", "src", "configs", "config", "results", "runs", "logs", "cache", "weights", "artifacts",
               "home", "usr", "mnt", "content", "drive", "workspace", "path", "your-org", "your_org",
               "org", "user", "username", "my-org"}


@dataclass
class Hit:
    model_id: str
    places: list[str] = field(default_factory=list)


def _plausible(mid: str, root: Path, here: Path) -> bool:
    if "{" in mid or mid.startswith((".", "-")) or ".." in mid:
        return False
    low = mid.lower()
    if low.endswith(FILE_SUFFIXES):
        return False
    parts = mid.split("/")
    if len(parts) == 2 and parts[0].lower() in LOCAL_FIRST:
        return False
    if len(parts) == 1 and (low in {"auto", "none", "true", "false", "main"} or low.isdigit()):
        return False
    try:
        if (here.parent / mid).exists() or (root / mid).exists():
            return False  # a local directory, not a Hub id
    except OSError:
        pass
    return True


def _notebook_text(raw: str) -> str:
    try:
        nb = json.loads(raw)
    except ValueError:
        return raw
    cells = nb.get("cells") if isinstance(nb, dict) else None
    if not isinstance(cells, list):
        return raw
    chunks = []
    for c in cells:
        if isinstance(c, dict) and c.get("cell_type") == "code":
            src = c.get("source", "")
            chunks.append("".join(src) if isinstance(src, list) else str(src))
    return "\n".join(chunks)


def scan_text(text: str, path: Path, root: Path) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []

    def add(mid: str, pos: int):
        if _plausible(mid, root, path):
            found.append((mid, text.count("\n", 0, pos) + 1))

    for pat in PATTERNS:
        for m in pat.finditer(text):
            add(m.group(1), m.start(1))
    for m in KEY_PATTERN.finditer(text):
        add(m.group(1), m.start(1))
    for m in BASE_LIST.finditer(text):
        for item in re.finditer(rf"-\s*[\"']?({_PART}/{_PART})", m.group(1)):
            add(item.group(1), m.start(1) + item.start(1))
    return found


def iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if p.suffix.lower() in EXTENSIONS:
                yield p


def scan(path: str | os.PathLike = ".") -> dict[str, Hit]:
    """Model ids found under `path`, each with 'file:line' places. Ordered by first sighting."""
    root = Path(path).resolve()
    base = root if root.is_dir() else root.parent
    hits: dict[str, Hit] = {}
    for p in iter_files(root):
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _notebook_text(raw) if p.suffix.lower() == ".ipynb" else raw
        rel = os.path.relpath(p, base)
        seen_here = set()
        for mid, line in scan_text(text, p, base):
            place = f"{rel}:{line}" if p.suffix.lower() != ".ipynb" else rel
            if (mid, place) in seen_here:
                continue
            seen_here.add((mid, place))
            hits.setdefault(mid, Hit(mid)).places.append(place)
    return hits

"""jcodemunch_config.py — keep ~/.code-index/config.jsonc on the workflow's keys.

The file lives outside ~/.claude, so a copied or fresh install keeps jcodemunch's stock
defaults (tool_surface "counter" = 6 menu tools; every get_context_bundle / plan_turn
directive then resolves to nothing). Required keys come from manifest.json
`jcodemunch_config.keys`. Writes go only through `jcodemunch-mcp config set` (its own
comment-preserving, validating editor); this module only reads the JSONC.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

import deps  # noqa: E402  (puts hooks/ on sys.path)
from lib import platform as plat  # noqa: E402

NAME = "jcodemunch-config"
_STRING = r'"(?:\\.|[^"\\])*"'
_COMMENTS = re.compile(_STRING + r"|//[^\n]*|/\*.*?\*/", re.S)
_TRAILING_COMMAS = re.compile(_STRING + r"|,(?=\s*[}\]])")


def config_path() -> Path:
    return Path(os.environ.get("CODE_INDEX_PATH") or Path.home() / ".code-index") / "config.jsonc"


def load_jsonc(text: str) -> dict:
    """Parse JSONC: drop // and /* */ comments and trailing commas, never inside strings."""
    def keep(m):
        return m.group(0) if m.group(0).startswith('"') else ""
    return json.loads(_TRAILING_COMMAS.sub(keep, _COMMENTS.sub(keep, text)))


def required() -> dict:
    keys = (deps._load_manifest().get("jcodemunch_config") or {}).get("keys") or {}
    home = str(Path.home())
    return {k: [home if x == "{HOME}" else x for x in v] if isinstance(v, list) else v
            for k, v in keys.items()}


def changes(current: dict, want: dict) -> dict:
    """Keys to write: scalars that differ; lists missing members (existing members kept)."""
    out = {}
    for key, val in want.items():
        have = current.get(key)
        if isinstance(val, list):
            have = have if isinstance(have, list) else []
            if missing := [x for x in val if x not in have]:
                out[key] = have + missing
        elif have != val:
            out[key] = val
    return out


def _current(p: Path) -> dict:
    return load_jsonc(p.read_text(encoding="utf-8-sig"))


def gaps(path: Path | None = None) -> list[str] | None:
    """None if the config is absent, else the sorted keys not at the required value."""
    p = path or config_path()
    if not p.is_file():
        return None
    try:
        return sorted(changes(_current(p), required()))
    except (OSError, ValueError):
        return ["<unparseable config.jsonc>"]


def configure(*, dry_run: bool = False) -> tuple[str, str]:
    exe = shutil.which("jcodemunch-mcp")
    if not exe:
        return NAME, "SKIP(jcodemunch-mcp not installed)"
    p = config_path()
    if not p.is_file():
        if dry_run:
            return NAME, f"WOULD-INIT {p}"
        plat.run([exe, "config", "--init"], timeout=60, stdin_devnull=True)
    try:
        todo = changes(_current(p), required())
    except (OSError, ValueError) as exc:
        return NAME, f"FAIL(read {p}: {type(exc).__name__})"
    if not todo:
        return NAME, "PRESENT (compliant)"
    if dry_run:
        return NAME, f"WOULD-SET {sorted(todo)}"
    shutil.copy2(p, p.with_name(p.name + ".bak-installer"))  # recoverable copy first
    bad = [k for k, v in todo.items()
           if plat.run([exe, "config", "set", k, json.dumps(v)], timeout=60,
                       stdin_devnull=True).returncode != 0]
    return NAME, f"FAIL(set {bad})" if bad else f"OK(set {sorted(todo)})"

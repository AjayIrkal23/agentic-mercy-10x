"""skills_index.py — the one reader of the skills index.

The tracked `hooks/skills-index.json` holds local skills only (`plugin_count` 0), so it is the same on
every machine and no install dirties it. Installed plugin skills are per machine: they go to the
gitignored sidecar `<root>/state/skills-index.plugins.json` (written by scripts/build_skills_index.py).
`load()` merges both. The sidecar sits next to the checkout, not under CLAUDE_HOOK_STATE_DIR, so an
isolated test state never hides the plugin skills of the tree it reads.
"""
from __future__ import annotations

import json
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent
SIDECAR_NAME = "skills-index.plugins.json"


def tracked_path(hooks_dir: Path | None = None) -> Path:
    return Path(hooks_dir or _HOOKS) / "skills-index.json"


def sidecar_path(hooks_dir: Path | None = None) -> Path:
    return Path(hooks_dir or _HOOKS).parent / "state" / SIDECAR_NAME


def _read(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def load(hooks_dir: Path | None = None) -> dict:
    """{"_meta", "aliases", "skills"}: tracked local skills + sidecar plugin skills; {} when neither exists."""
    idx = _read(tracked_path(hooks_dir))
    side = _read(sidecar_path(hooks_dir))
    plug = side.get("skills") if isinstance(side.get("skills"), dict) else {}
    if not plug:
        return idx
    out = dict(idx)
    skills = dict(idx.get("skills") or {}) if isinstance(idx.get("skills"), dict) else {}
    for k, v in plug.items():
        skills.setdefault(k, v)  # a local entry never loses to a plugin entry of the same name
    out["skills"] = dict(sorted(skills.items()))
    meta = dict(idx.get("_meta") or {}) if isinstance(idx.get("_meta"), dict) else {}
    meta["plugin_count"] = len(plug)
    out["_meta"] = meta
    return out


def skills(hooks_dir: Path | None = None) -> dict:
    s = load(hooks_dir).get("skills")
    return s if isinstance(s, dict) else {}


__all__ = ["SIDECAR_NAME", "tracked_path", "sidecar_path", "load", "skills"]

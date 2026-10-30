"""oomguard_config.py — ~/.claude/oomguard.local.json (gitignored user overrides) with defaults.

Shared by hooks/tools/memwatch.py, installer/oomguard_setup.py and scripts/restore_sessions.py.
Every reader takes an optional ``p`` path seam, never raises and falls back to ``DEFAULTS``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001 - fail-open: the plain ~/.claude path below
    _plat = None

DEFAULTS = {"restore_enabled": True, "shed_mode": "own-builders", "memory_high": "12G",
            "kill_policy": {"enabled": True}, "protected_extra": [], "victims_extra": []}
_MODES = {"none", "own-builders", "known-heavy"}
_SIZE_RE = re.compile(r"^\d+[KMGT]?$")
_KP_KEYS = ("enabled", "stage_holdoff_s", "emergency_mb", "idle_min")


def path() -> Path:
    base = _plat.claude_dir() if _plat is not None else Path("~/.claude").expanduser()
    return base / "oomguard.local.json"


def load(p: Path | str | None = None) -> dict:
    try:
        data = json.loads(Path(p or path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def restore_enabled(p=None) -> bool:
    """Only a literal ``false`` disables the restore."""
    return load(p).get("restore_enabled") is not False


def shed_mode(p=None) -> str:
    v = load(p).get("shed_mode")
    return v if v in _MODES else DEFAULTS["shed_mode"]


def memory_high(p=None) -> str:
    v = str(load(p).get("memory_high") or "")
    return v if _SIZE_RE.match(v) else DEFAULTS["memory_high"]


def kill_policy(p=None) -> dict:
    out = dict(DEFAULTS["kill_policy"])
    kp = load(p).get("kill_policy")
    if isinstance(kp, dict):
        out.update({k: v for k, v in kp.items() if k in _KP_KEYS})
    out["enabled"] = out.get("enabled") is not False
    return out


def _strs(p, key: str) -> list[str]:
    v = load(p).get(key)
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def protected_extra(p=None) -> list[str]:
    return _strs(p, "protected_extra")


def victims_extra(p=None) -> list[str]:
    return _strs(p, "victims_extra")


__all__ = ["DEFAULTS", "path", "load", "restore_enabled", "shed_mode", "memory_high", "kill_policy",
           "protected_extra", "victims_extra"]

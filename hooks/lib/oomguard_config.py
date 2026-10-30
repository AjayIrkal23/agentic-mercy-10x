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

# memory_high "" = unset: bin/claude and bin/claude-tmux derive the scope cap, memory_cap_mb()
DEFAULTS = {"restore_enabled": True, "shed_mode": "own-builders", "memory_high": "",
            "kill_policy": {"enabled": True}, "protected_extra": [], "victims_extra": [], "linger": True}
# index-lifecycle's MB floor is tuned for a ~30 GB box and scales by ram_factor() (FI-3); memwatch's tiers
# are percent of MemTotal (F7). Bigger boxes keep the shipped numbers (factor capped at 1).
REF_MEM_TOTAL_MB = 30000
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
    """The local ``memory_high`` (``8G``, ``16384M``); "" when unset or malformed (RAM-derived)."""
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


def linger_wanted(p=None) -> bool:
    """Only a literal ``false`` opts out of ``loginctl enable-linger`` at install."""
    return load(p).get("linger") is not False


def mem_total_mb() -> int:
    """MemTotal in MB from /proc/meminfo; 0 when unknown (Windows, no /proc)."""
    try:
        return int((_plat.mem_probe() or {}).get("mem_total_mb") or 0) if _plat is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def ram_factor(total_mb: int | None = None) -> float:
    """min(1, MemTotal / REF_MEM_TOTAL_MB); 1.0 when MemTotal is unknown."""
    t = mem_total_mb() if total_mb is None else int(total_mb or 0)
    return 1.0 if t <= 0 else min(1.0, t / REF_MEM_TOTAL_MB)


DESKTOP_RESERVE_MB = 4096  # F7 (user, 2026-10-30): what the desktop apps keep on any box


def memory_cap_mb(total_mb: int | None = None) -> int:
    """The one memory cap rule (F7): MemTotal minus 4 GiB, never below half of MemTotal; 0 when unknown.
    Scope MemoryHigh (bin/claude, bin/claude-tmux repeat it in bash) and the machine-wide
    CLAUDE_CODE_TOOL_MEMORY_LIMIT (settings_install.machine_sizes): 15650 MB -> 11554, 30669 MB -> 26573."""
    t = mem_total_mb() if total_mb is None else int(total_mb or 0)
    return 0 if t <= 0 else max(t - DESKTOP_RESERVE_MB, t // 2)


def scale_mb(value, floor=0, factor=None) -> int:
    """A shipped MB threshold scaled to this machine's RAM, never below ``floor``."""
    f = ram_factor() if factor is None else factor
    return max(int(floor), int(round(float(value) * f)))


def tiers_override(p=None) -> dict:
    """``tiers.warn`` / ``tiers.crit`` numbers from the local file (absolute, never scaled)."""
    t = load(p).get("tiers")
    out: dict = {}
    if isinstance(t, dict):
        for lvl in ("warn", "crit"):
            v = t.get(lvl)
            if isinstance(v, dict):
                out[lvl] = {k: int(x) for k, x in v.items()
                            if isinstance(x, (int, float)) and not isinstance(x, bool)}
    return out


__all__ = ["DEFAULTS", "REF_MEM_TOTAL_MB", "path", "load", "restore_enabled", "shed_mode", "memory_high",
           "kill_policy", "protected_extra", "victims_extra", "linger_wanted", "mem_total_mb",
           "ram_factor", "scale_mb", "tiers_override", "DESKTOP_RESERVE_MB", "memory_cap_mb"]

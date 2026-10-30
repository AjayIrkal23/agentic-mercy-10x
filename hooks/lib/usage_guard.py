"""usage_guard.py — step subagents down while the 5-hour window is nearly used up (MERGE-PLAN R3.3).

Input: the newest state/session-bridge/<sid>.json (written by scripts/statusline.py from the statusLine
rate_limits) younger than policy usage_guard.max_age_s. Hysteresis: on at >= on_pct (80), off below
off_pct (70) or once resets_at has passed. state/usage-guard.json is rewritten only when `active` flips,
and a flip regenerates the saved workflows (scripts/build_workflows.py, detached) when that script
exists. Numbers come from model-policy.json `usage_guard` and `tiers.<tier>.usage_guard`; every error
-> inactive. Never raises.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore

STATE_NAME = "usage-guard.json"
BRIDGE_DIR = "session-bridge"
_DEF = {"on_pct": 80.0, "off_pct": 70.0, "max_age_s": 600.0}
_ORDER = ["haiku", "sonnet", "opus", "fable"]
_LIT_UG = {"pro": {"ceiling": "haiku", "judge": "haiku"}, "max5": {"ceiling": "sonnet", "judge": "sonnet"},
           "max20": {"ceiling": "sonnet", "judge": "sonnet"}}
_LIT_UG["api"] = _LIT_UG["max5"]
_POLICY_PATH = Path(__file__).resolve().parents[1] / "model-policy.json"
_INACTIVE = {"active": False, "pct": None, "resets_at": None, "flipped": False}


def _policy() -> dict:
    try:
        with open(_POLICY_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _load(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _epoch(stamp) -> float | None:
    """Seconds, milliseconds (> 1e11) or ISO-8601 (Z or offset) -> epoch seconds; else None."""
    n = _num(stamp)
    if n is not None:
        return n / 1000.0 if n > 1e11 else n
    if isinstance(stamp, str) and stamp.strip():
        try:
            return datetime.fromisoformat(stamp.strip().replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _state_dir() -> Path:
    """state dir without plat.state_dir()'s mkdir (reads must not create it; atomic_write does on write)."""
    env = os.environ.get("CLAUDE_HOOK_STATE_DIR")
    if env:
        return Path(env).expanduser()
    return (_plat.claude_dir() if _plat else Path("~/.claude").expanduser()) / "state"


def _newest_bridge(max_age: float) -> dict | None:
    """Newest readable *.json under state/session-bridge by mtime, None when none is younger than max_age.
    Freshness is wall-clock (file mtimes); `now` in state() only drives the resets_at comparison."""
    now = time.time()
    try:
        files = sorted(((p.stat().st_mtime, p) for p in (_state_dir() / BRIDGE_DIR).glob("*.json")), reverse=True)
    except OSError:
        return None
    for mtime, p in files:
        if now - mtime > max_age:
            return None
        d = _load(p)
        if d is not None:
            return d
    return None


def _tier() -> str:
    try:
        from lib import plan_tier  # noqa: PLC0415

        return plan_tier.read()["tier"]
    except Exception:  # noqa: BLE001
        return "max20"


def _builder_path() -> Path | None:
    # A test run isolates state (CLAUDE_HOOK_STATE_DIR): a builder spawned from it would render the
    # live workflows from the test's tier, so the default lookup is off there (tests patch this).
    if os.environ.get("CLAUDE_HOOK_STATE_DIR") or _plat is None:
        return None
    return _plat.claude_dir() / "scripts" / "build_workflows.py"


def _spawn(cmd: list) -> None:
    if _plat is not None:
        _plat.spawn_detached(cmd)


def _regenerate() -> None:
    try:
        b = _builder_path()
        if b is not None and b.is_file():
            _spawn([_plat.python_exe() if _plat else "python3", str(b)])
    except Exception:  # noqa: BLE001
        pass


def state(now: float | None = None) -> dict:
    """{"active","pct","resets_at","flipped"}; writes state/usage-guard.json on a flip only."""
    try:
        now = time.time() if now is None else now
        raw = _policy().get("usage_guard") or {}
        cfg = dict(_DEF)
        cfg.update({k: float(v) for k, v in raw.items() if k in _DEF and _num(v) is not None})
        prev = _load(_state_dir() / STATE_NAME) or {}
        was = bool(prev.get("active"))
        b = _newest_bridge(cfg["max_age_s"])
        pct = _num(b.get("five_hour_pct")) if b else None
        resets = _epoch(b.get("five_hour_resets_at")) if b and pct is not None else _epoch(prev.get("resets_at"))
        if pct is None:  # no fresh reading: carry the stored flag while the window lasts
            active = was and resets is not None and now < resets
        elif resets is not None and now >= resets:  # the window reset: the counter is stale
            active = False
        elif pct >= cfg["on_pct"]:
            active = True
        elif pct < cfg["off_pct"]:
            active = False
        else:
            active = was
        flipped = active != was
        if flipped:
            body = {"schema": 1, "active": active, "five_hour_pct": pct, "resets_at": resets,
                    "since": now if active else prev.get("since"), "tier": _tier()}
            if _plat is not None:
                _plat.atomic_write(_state_dir() / STATE_NAME, json.dumps(body, sort_keys=True) + "\n")
            _regenerate()
        return {"active": active, "pct": pct, "resets_at": resets if (pct is not None or active) else None,
                "flipped": flipped}
    except Exception:  # noqa: BLE001
        return dict(_INACTIVE)


def step_down(model: str, role: str, tier: str, policy: dict | None = None) -> str:
    """The model while the guard is active. Judges take tiers.<tier>.usage_guard.judge when that is
    lower (the guard never raises a model); everyone else moves one step down the model order and is
    clamped to usage_guard.ceiling; fable lands on sonnet first (then the clamp). Unknown model
    strings pass through."""
    t = tier if tier in _LIT_UG else "api"
    pol = _policy() if policy is None else policy
    ug = ((pol.get("tiers") or {}).get(t) or {}).get("usage_guard")
    ug = ug if isinstance(ug, dict) and ug.get("ceiling") else _LIT_UG[t]
    if model not in _ORDER:
        return model
    if role == "judge":
        j = str(ug.get("judge") or "sonnet")
        return j if j in _ORDER and _ORDER.index(j) < _ORDER.index(model) else model
    down = "sonnet" if model == "fable" else _ORDER[max(0, _ORDER.index(model) - 1)]
    ceil = str(ug.get("ceiling") or "sonnet")
    if ceil not in _ORDER:
        return down
    return down if _ORDER.index(down) <= _ORDER.index(ceil) else ceil


__all__ = ["state", "step_down"]

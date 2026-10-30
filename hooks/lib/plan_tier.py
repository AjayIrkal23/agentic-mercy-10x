"""plan_tier.py — which Claude plan this machine runs on, and what that allows (MERGE-PLAN R3.3).

detect() is the ONLY code in the workbench that opens ~/.claude/.credentials.json. It reads two keys
(claudeAiOauth.subscriptionType, claudeAiOauth.rateLimitTier; fallback ~/.claude.json
oauthAccount.organizationRateLimitTier) with .get() and never iterates, copies, hashes or logs the file.
read() returns state/plan-tier.json and never detects (missing -> max20, today's behaviour).
Ceilings and render overrides come from model-policy.json `tiers`, with literal fallbacks.
Everything fails soft: no function here raises.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001 - keep importable from installer/render.py
    _plat = None  # type: ignore

TIERS = ("pro", "max5", "max20", "api")
STATE_NAME = "plan-tier.json"
STALE_S = 24 * 3600
_POLICY_PATH = Path(__file__).resolve().parents[1] / "model-policy.json"
# fail-open literals = the policy's tier essentials (pinned by tests/test_plan_tier.py)
_LIT = {"pro": {"ceiling": "sonnet", "main": "sonnet", "subagent_env": "haiku", "fallback": ["haiku"]},
        "max5": {"ceiling": "opus", "main": "sonnet", "subagent_env": "sonnet", "fallback": ["haiku"]},
        "max20": {"ceiling": "fable", "main": "opus", "subagent_env": "sonnet", "fallback": ["sonnet", "haiku"]}}
_LIT["api"] = _LIT["max5"]
_ORDER = ["haiku", "sonnet", "opus", "fable"]
_STATE_KEYS = ("schema", "tier", "source", "detected_at", "detail", "main", "notice", "notice_ts")


def _policy() -> dict:
    """model-policy.json, {} on any error (no cache: callers are short-lived processes)."""
    try:
        with open(_POLICY_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def _order() -> list:
    o = _policy().get("model_order")
    return o if isinstance(o, list) and o else _ORDER


def _tier_block(tier: str) -> dict:
    t = tier if tier in TIERS else "api"
    blk = (_policy().get("tiers") or {}).get(t)
    return blk if isinstance(blk, dict) and "ceiling" in blk else dict(_LIT[t])


def _load_json(path: Path) -> dict | None:
    """A dict from a JSON file, or None. Never raises (tests monkeypatch it)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _paths(home: Path | None) -> tuple[list[Path], list[Path]]:
    """(credential candidates, claude.json candidates). Real machine: exactly the two known files.
    Explicit home (tests, render --home): the same layout under it, plus the dot-free fixture
    spelling, because .gitignore drops dotfile fixtures."""
    if home is None:
        cdir = _plat.claude_dir() if _plat else Path("~/.claude").expanduser()
        return [cdir / ".credentials.json"], [Path.home() / ".claude.json", cdir / ".claude.json"]
    h = Path(home)
    return [h / ".claude" / ".credentials.json", h / "credentials.json"], [h / ".claude.json", h / "claude.json"]


def _map(sub: object, rate: object) -> str | None:
    sub = sub.lower() if isinstance(sub, str) else ""
    rate = rate.lower() if isinstance(rate, str) else ""
    if sub == "pro":
        return "pro"
    if sub == "max":
        return "max20" if "_20x" in rate else "max5"  # unknown max tier -> max5
    if sub:
        return "api"  # team, enterprise, anything else
    return None


def main_model(tier: str) -> str:
    """The tier's main-session model (`tiers.<tier>.main`): bin/claude passes it as --model."""
    return str(_tier_block(tier).get("main") or _LIT.get(tier, _LIT["api"])["main"] or "sonnet")


def detect(home: Path | None = None) -> dict:
    """Live detection. {"schema","tier","source","detected_at","detail","main"}; detail holds only the
    plan strings, main = main_model(tier)."""
    d = _detect(home)
    d["main"] = main_model(d["tier"])
    return d


def _detect(home: Path | None) -> dict:
    now = time.time()
    creds, cjs = _paths(home)
    for p in creds:
        d = _load_json(p)
        if d is None:
            continue
        oauth = d.get("claudeAiOauth")
        oauth = oauth if isinstance(oauth, dict) else {}
        sub, rate = oauth.get("subscriptionType"), oauth.get("rateLimitTier")
        tier = _map(sub, rate)
        if tier:
            return {"schema": 1, "tier": tier, "source": "credentials", "detected_at": now,
                    "detail": f"{sub}/{rate if isinstance(rate, str) and rate else '-'}"[:60]}
    for p in cjs:
        d = _load_json(p)
        if d is None:
            continue
        acct = d.get("oauthAccount")
        acct = acct if isinstance(acct, dict) else {}
        rate = acct.get("organizationRateLimitTier")
        if isinstance(rate, str) and rate:
            r = rate.lower()
            tier = ("max20" if "_20x" in r else "max5" if "_5x" in r or "max" in r
                    else "pro" if "pro" in r else "api")
            return {"schema": 1, "tier": tier, "source": "claude.json", "detected_at": now, "detail": rate[:60]}
    return {"schema": 1, "tier": "api", "source": "none", "detected_at": now, "detail": "no subscription file"}


def state_dir_ro() -> Path:
    """plat.state_dir() without its mkdir side effect: a read must not create the dir
    (scripts/model-mode.py show; atomic_write creates the parent when writing)."""
    env = os.environ.get("CLAUDE_HOOK_STATE_DIR")
    if env:
        return Path(env).expanduser()
    return (_plat.claude_dir() if _plat else Path("~/.claude").expanduser()) / "state"


def state_path() -> Path:
    return state_dir_ro() / STATE_NAME


def read() -> dict:
    """The state file as written; never detects. Missing/invalid -> max20 (same fallback as
    scripts/build_workflows.py). Adds `stale` (> 24 h) and, when fallen back, `missing`."""
    d = _load_json(state_path())
    if not d or d.get("tier") not in TIERS:
        return {"schema": 1, "tier": "max20", "source": "none", "detected_at": 0, "missing": True, "stale": False}
    out = {k: d.get(k) for k in _STATE_KEYS if k in d}
    ts = out.get("detected_at")
    out["stale"] = not isinstance(ts, (int, float)) or (time.time() - float(ts)) > STALE_S
    return out


def _fallback_write(path: Path, body: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        return True
    except OSError:
        return False


def write_state(d: dict, path: Path | None = None) -> bool:
    body = json.dumps({k: d[k] for k in _STATE_KEYS if k in d}, sort_keys=True) + "\n"
    target = path or state_path()
    return bool(_plat.atomic_write(target, body)) if _plat else _fallback_write(target, body)


def update_state(new: dict, path: Path | None = None) -> dict:
    """Write a fresh detect() result. Sets `notice` only when a previous file held a different
    tier; a quiet detect clears it. -> {"changed": bool, "previous": tier|None, "ok": bool}."""
    prev = _load_json(path or state_path()) or {}
    old = prev.get("tier")
    changed = old in TIERS and old != new.get("tier")
    d = {k: new[k] for k in ("schema", "tier", "source", "detected_at", "detail", "main") if k in new}
    if changed:
        d["notice"] = (f"plan tier changed: {old} -> {new.get('tier')} ({new.get('source')}); "
                       "routing ceilings follow the new tier")
        d["notice_ts"] = new.get("detected_at")
    return {"changed": bool(changed), "previous": old if old in TIERS else None, "ok": write_state(d, path)}


def notice_line() -> str:
    """The one-line tier-change notice, "" when the last detect did not change the tier."""
    n = (_load_json(state_path()) or {}).get("notice")
    return n if isinstance(n, str) and "oken" not in n else ""


def ceiling(tier: str) -> str:
    c = _tier_block(tier).get("ceiling")
    return str(c) if isinstance(c, str) and c else _LIT.get(tier, _LIT["api"])["ceiling"]


def cap(model: str, tier: str) -> str:
    """Clamp ``model`` to the tier ceiling; models outside the order pass through."""
    order, c = _order(), ceiling(tier)
    if model not in order or c not in order:
        return model
    return model if order.index(model) <= order.index(c) else c


def render_overrides(tier: str) -> dict:
    """Tier-derived settings keys for installer/render.py; settings.user.json still wins."""
    blk = _tier_block(tier)
    lit = _LIT[tier if tier in TIERS else "api"]
    fb = blk.get("fallback") if isinstance(blk.get("fallback"), list) else lit["fallback"]
    return {"model": str(blk.get("main") or lit["main"]),
            "env": {"CLAUDE_CODE_SUBAGENT_MODEL": str(blk.get("subagent_env") or lit["subagent_env"])},
            "fallbackModel": [str(m) for m in fb]}


__all__ = ["TIERS", "detect", "read", "write_state", "update_state", "notice_line", "state_path",
           "ceiling", "cap", "render_overrides"]

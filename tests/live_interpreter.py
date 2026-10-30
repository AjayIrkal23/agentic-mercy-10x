"""Decouple the suite from the interpreter that rendered the live ``settings.json`` (A7v2-03).

``statusLine.command`` pins an absolute python.exe (``detect._python_exe``: the interpreter running the
render). A test that renders or runs the doctor against the checkout's own ``settings.json`` then fails
under any other Python (the CI Windows leg runs 3.12, the file says 3.14). ``pin`` makes the render
compute the interpreter the live file already holds, or an injected one; everything else is still compared.
It also runs the doctor's `hook-command` / `statusline` rows with the real home: the POSIX render says
`${HOME}/.claude/...`, which a sandboxed HOME would point at an empty dir (exit 2).
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "installer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "installer"))
_REAL_HOME = {k: os.environ[k] for k in ("HOME", "USERPROFILE") if k in os.environ}  # read at import, before any sandbox


def live_interpreter() -> str | None:
    """First word of the live ``statusLine.command``; None without a settings.json (fresh checkout / CI)."""
    try:
        command = json.loads((_ROOT / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"]
        return shlex.split(command, posix=True)[0]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None


def pin(monkeypatch, exe: str | None = None) -> None:
    """Make ``detect._python_exe`` answer ``exe`` (default: the live file's interpreter) and run the
    doctor's hook rows with the real home."""
    exe = exe or live_interpreter()
    if exe:
        import detect  # type: ignore
        monkeypatch.setattr(detect, "_python_exe", lambda: exe)
    import doctor_hook  # type: ignore
    shell = doctor_hook._shell
    monkeypatch.setattr(doctor_hook, "_shell", lambda command, payload, env: shell(command, payload, {**env, **_REAL_HOME}))


def pin_tier(home: Path, monkeypatch) -> Path:
    """Pin this machine's plan tier in a sandbox HOME (FIX-r2 S3): the live settings.json carries its tier
    keys, so a render that fell back (or re-detected `api` from an empty HOME) would not match it. Copies
    state/plan-tier.json into ``home/.claude/state`` (CLAUDE_HOOK_STATE_DIR) and gives the sandbox the two
    plan strings only (no token) so the doctor's session-start re-detection lands on the same tier."""
    state = Path(home) / ".claude" / "state"
    state.mkdir(parents=True, exist_ok=True)
    try:
        pin_ = json.loads((_ROOT / "state" / "plan-tier.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pin_ = {"schema": 1, "tier": "max20", "source": "credentials", "detail": "max/default_claude_max_20x"}
    (state / "plan-tier.json").write_text(json.dumps(pin_), encoding="utf-8")
    sub, _, rate = str(pin_.get("detail") or "").partition("/")
    if pin_.get("source") == "credentials" and sub:
        (Path(home) / ".claude" / ".credentials.json").write_text(
            json.dumps({"claudeAiOauth": {"subscriptionType": sub, "rateLimitTier": "" if rate == "-" else rate}}),
            encoding="utf-8")
    elif pin_.get("source") == "claude.json" and pin_.get("detail"):
        (Path(home) / ".claude.json").write_text(
            json.dumps({"oauthAccount": {"organizationRateLimitTier": pin_["detail"]}}), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    return state

"""gate_mode.py — directive 31 (ask-or-advise): an ``ask`` downgrades to a logged advisory when nobody
is there to answer it.

``decide(payload, want="ask") -> (decision, reason)``; reasons: subagent | restored | unattended |
workflow | interactive. ``deny`` is never downgraded. ``once_per_file(sid, gate, path)`` is True the
first time a (session, gate, path) triple is seen. Other packages import this with
``try/except ImportError`` and fall back to ``"ask"``: keep both signatures exact. Never raises.
"""
from __future__ import annotations

import json
import os
import re

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(s: str) -> str:
    out = _UNSAFE.sub("_", str(s))[:120].strip(".")
    return out or "unknown"


def _ledger_restored(sid: str) -> bool:
    try:
        d = json.loads((_plat.state_dir() / "live-sessions" / f"{_safe(sid)}.json").read_text(encoding="utf-8"))
        return isinstance(d, dict) and d.get("restored") is True
    except Exception:  # noqa: BLE001
        return False


def decide(payload, want: str = "ask", *, environ=None) -> tuple[str, str]:
    if want != "ask":
        return want, ("deny-never-downgraded" if want == "deny" else "interactive")
    p = payload if isinstance(payload, dict) else {}
    env = os.environ if environ is None else environ
    ti = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
    if p.get("agent_id") or p.get("agent_type"):
        return "advise", "subagent"
    sid = str(p.get("session_id") or "")
    if sid and _ledger_restored(sid):
        return "advise", "restored"
    if env.get("CLAUDE_WORKBENCH_UNATTENDED") == "1":
        return "advise", "unattended"
    if p.get("workflow_id") or ti.get("workflow_id"):
        return "advise", "workflow"
    return "ask", "interactive"


def once_per_file(sid: str, gate: str, path: str) -> bool:
    """True the first time ``path`` is seen for (sid, gate); the set lives in
    ``state/<sid>.<gate>.once.json``. A state error answers True (fail-open: say it again)."""
    if _plat is None:
        return True
    seen = {"first": False}

    def _fn(d: dict) -> dict:
        paths = d.get("paths") if isinstance(d.get("paths"), list) else []
        if path not in paths:
            paths.append(path)
            seen["first"] = True
        d["paths"] = paths
        return d

    try:
        _plat.locked_update(_plat.state_dir() / f"{_safe(sid)}.{_safe(gate)}.once.json", _fn, default={"paths": []})
    except Exception:  # noqa: BLE001
        return True
    return seen["first"]


__all__ = ["decide", "once_per_file"]

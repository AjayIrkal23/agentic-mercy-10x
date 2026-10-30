#!/usr/bin/env python3
"""memwatch-brake.py — PreToolUse gate on Agent|Task|Workflow|Bash|PowerShell|mcp__playwright__browser_navigate.

Reads state/mem-pressure.json (one open, no subprocess). warn -> one advisory line per tier value per
session; crit -> permissionDecision ask with the numbers, or an advisory when lib/gate_mode says the
session is unattended (directive 31; telemetry row ``ask_downgraded``). Bash/PowerShell only count when
the command matches HEAVY_RE. Stale (> 30 s) or missing state = ok = {}. Always exit 0, always JSON.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

HEAVY_RE = re.compile(r"\b(vitest|jest|playwright|graphify|tsc|pytest)\b|\bnpm\s+(run\s+)?(test|build)\b")
HEAVY_TOOLS = {"Agent", "Task", "Workflow", "mcp__playwright__browser_navigate"}
SHELL_TOOLS = {"Bash", "PowerShell"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(s: str) -> str:
    return _UNSAFE.sub("_", s)[:120].strip(".") or "unknown"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _line(st) -> str:
    gb = (st.mem_available_mb or 0) / 1024
    sw = 100 - (st.swap_free_pct if st.swap_free_pct is not None else 100)
    return f"memory {st.level}: {gb:.1f} GB free, swap {sw:.0f} %"


def _usage_guard(plat) -> str:
    try:
        d = json.loads((plat.state_dir() / "usage-guard.json").read_text(encoding="utf-8"))
        return "; usage guard active" if isinstance(d, dict) and d.get("active") is True else ""
    except Exception:  # noqa: BLE001
        return ""


def _out(obj: dict) -> int:
    print(json.dumps(obj))
    return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except ValueError:
        return _out({})
    if not isinstance(payload, dict):
        return _out({})
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool in SHELL_TOOLS:
        if not HEAVY_RE.search(str(ti.get("command") or "")):
            return _out({})
    elif tool not in HEAVY_TOOLS:
        return _out({})
    from lib import memwatch_state as mws
    from lib import platform as plat
    st = mws.read(stale_s=30)
    if st.level == "ok":
        return _out({})
    sid = _safe(str(payload.get("session_id") or "unknown"))
    marker = plat.state_dir() / f"{sid}.brake-tier"
    if st.level == "warn":
        if _read(marker) == "warn":
            return _out({})
        plat.atomic_write(marker, "warn")
        text = _line(st) + _usage_guard(plat) + "; do not fan out agents or start vitest/playwright/graphify until it clears"
        return _out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}})
    plat.atomic_write(marker, "crit")
    try:
        from lib import gate_mode
        decision, why = gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001
        decision, why = "ask", "interactive"
    reason = (_line(st) + f"; `{tool}` would add pressure (the sentinel is shedding builders and may kill the "
              "biggest hog). Proceed anyway?")
    if decision == "ask":
        return _out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                            "permissionDecisionReason": reason}})
    try:
        from lib import hook_telemetry
        hook_telemetry.record("PreToolUse", "memwatch-brake", decision="ask_downgraded", reason=why, session=sid,
                              tool=tool)
    except Exception:  # noqa: BLE001
        pass
    return _out({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                 reason + f" (ask downgraded: {why}; unattended session, continuing)"}})


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 - a gate never blocks on its own error
        print("{}")
        sys.exit(0)

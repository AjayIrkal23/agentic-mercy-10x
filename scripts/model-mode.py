#!/usr/bin/env python3
"""Set/clear/show the subagent model mode for the CURRENT repo (per-repo, not global).

Usage (run from inside the repo):
  model-mode.py haiku | sonnet | opus | fable   # pin this model for THIS repo only (capped to the plan tier)
  model-mode.py clear | off | smart              # remove this repo's pin -> smart routing
  model-mode.py show | status                    # this repo's pin, the global flags, plan tier, usage guard

Global kill-switch (every repo, wins over the per-repo pin; capped to the plan tier too):
  touch ~/.claude/state/<mode>-only-mode   /   rm ~/.claude/state/<mode>-only-mode
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(_HOOKS))
try:
    from lib import model_mode as mm
except Exception as exc:  # pragma: no cover
    print(f"model-mode: cannot load helper ({exc})", file=sys.stderr)
    raise SystemExit(1)

_CLEAR = ("clear", "off", "smart", "none", "reset", "auto")


def _tier_rows() -> list[str]:
    try:
        from lib import plan_tier, usage_guard

        t = plan_tier.read()
        tier = f"{t['tier']} ({t.get('source', 'none')}; ceiling {plan_tier.ceiling(t['tier'])})"
        u = usage_guard.state()
        if u.get("active"):
            until = time.strftime("%H:%M", time.localtime(u["resets_at"])) if u.get("resets_at") else "reset"
            pct = f"{u['pct']:.0f}% " if u.get("pct") is not None else ""
            usage = f"active {pct}until {until}"
        else:
            usage = "inactive"
    except Exception:  # noqa: BLE001
        tier, usage = "(unknown)", "inactive"
    return [f"plan tier           : {tier}", f"usage guard         : {usage}"]


def main(argv: list[str]) -> int:
    arg = argv[0].lower() if argv else "show"
    cwd = os.getcwd()
    key = mm.repo_key(cwd)

    if arg in mm.MODES:
        if not mm.set_mode(cwd, arg):
            print("[model-mode] could not write the mode file", file=sys.stderr)
            return 1
        why = mm.cap_reason(arg)
        if why:
            print(f"[model-mode] {why}")
        else:
            print(f"[model-mode] {key} -> {arg}  (this repo only; other repos unaffected)")
        return 0
    if arg in _CLEAR:
        mm.set_mode(cwd, None)
        print(f"[model-mode] {key} pin cleared -> smart routing")
        return 0
    if arg in ("show", "status"):
        try:  # the guards' flag files: <claude_dir>/<session_flags.dir>/, not state_dir() (P7)
            policy = json.loads((_HOOKS / "model-policy.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            policy = {}
        flags = mm.global_flags(policy)
        pin = mm.forced_mode(cwd)
        print(f"repo key            : {key}")
        print(f"this-repo pin       : {pin or '(none)'}")
        print(f"global kill-switch  : {', '.join(flags) or '(none)'}")
        for row in _tier_rows():
            print(row)
        print(f"EFFECTIVE (guards)  : {flags[0] if flags else (pin or 'smart routing')}")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

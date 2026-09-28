#!/usr/bin/env python3
"""Set/clear/show the subagent model mode for the CURRENT repo (per-repo, not global).

Usage (run from inside the repo):
  model-mode.py sonnet | opus | fable   # pin this model for THIS repo only
  model-mode.py clear | off | smart      # remove this repo's pin -> smart routing
  model-mode.py show | status            # show this repo's pin + the global flags

Global kill-switch (every repo, wins over the per-repo pin):
  touch ~/.claude/state/<mode>-only-mode   /   rm ~/.claude/state/<mode>-only-mode
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
try:
    from lib import model_mode as mm
    from lib import platform as _plat
except Exception as exc:  # pragma: no cover
    print(f"model-mode: cannot load helper ({exc})", file=sys.stderr)
    raise SystemExit(1)

_CLEAR = ("clear", "off", "smart", "none", "reset", "auto")


def main(argv: list[str]) -> int:
    arg = argv[0].lower() if argv else "show"
    cwd = os.getcwd()
    key = mm.repo_key(cwd)

    if arg in mm.MODES:
        if not mm.set_mode(cwd, arg):
            print("[model-mode] could not write the mode file", file=sys.stderr)
            return 1
        print(f"[model-mode] {key} -> {arg}  (this repo only; other repos unaffected)")
        return 0
    if arg in _CLEAR:
        mm.set_mode(cwd, None)
        print(f"[model-mode] {key} pin cleared -> smart routing")
        return 0
    if arg in ("show", "status"):
        state = _plat.state_dir()
        flags = [m for m in mm.MODES if (state / f"{m}-only-mode").is_file()]
        pin = mm.forced_mode(cwd)
        print(f"repo key            : {key}")
        print(f"this-repo pin       : {pin or '(none)'}")
        print(f"global kill-switch  : {', '.join(flags) or '(none)'}")
        print(f"EFFECTIVE (guards)  : {flags[0] if flags else (pin or 'smart routing')}")
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

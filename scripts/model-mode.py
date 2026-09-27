#!/usr/bin/env python3
"""Set/clear/show the model-mode for the CURRENT project (per-project, NOT global).

Fixes the old global `~/.claude/state/<mode>-only-mode` flags leaking across every
concurrent session. A mode set here applies ONLY to the git repo you run it from,
so different projects can pin different models at the same time.

Usage (run from inside the project dir):
  model-mode.py sonnet | opus | fable   # force this model for THIS project only
  model-mode.py clear | off | smart      # remove this project's override -> smart routing
  model-mode.py show | status            # show this project's mode + effective result

Global default (optional, all projects with no override):
  touch   ~/.claude/state/<mode>-only-mode
  rm      ~/.claude/state/<mode>-only-mode
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))
try:
    from lib import model_mode as mm
except Exception as exc:  # pragma: no cover
    print(f"model-mode: cannot load helper ({exc})", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str]) -> int:
    arg = (argv[0].lower() if argv else "show")
    key = mm.project_key(cwd=os.getcwd())
    modes_dir = mm.STATE / "model-modes"
    modes_dir.mkdir(parents=True, exist_ok=True)
    pm = modes_dir / key

    if arg in mm.MODES:
        pm.write_text(arg + "\n", encoding="utf-8")
        print(f"[model-mode] project '{key}' -> {arg}  (this project only; other sessions unaffected)")
        return 0
    if arg in ("clear", "off", "smart", "none", "reset", "auto"):
        try:
            pm.unlink()
            print(f"[model-mode] project '{key}' override cleared -> smart routing")
        except FileNotFoundError:
            print(f"[model-mode] project '{key}' had no override (already smart routing)")
        return 0
    if arg in ("show", "status", ""):
        proj = pm.read_text(encoding="utf-8").strip() if pm.is_file() else None
        globals_set = [m for m in mm.MODES if (mm.STATE / f"{m}-only-mode").is_file()]
        eff, scope = mm.forced_mode(cwd=os.getcwd())
        print(f"project key           : {key}")
        print(f"this-project override : {proj or '(none)'}")
        print(f"global default flags  : {', '.join(globals_set) or '(none)'}")
        print(f"EFFECTIVE model       : {eff or 'smart routing'}"
              + (f"  (from {scope})" if eff else ""))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

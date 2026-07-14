#!/usr/bin/env python3
"""install.py — reproduce the ~/.claude workbench on any machine. UI-ONLY, AUTOMATIC.

There are no CLI verbs and nothing to choose. However you run it —

    python install.py            # Ubuntu / macOS
    py -3 install.py             # Windows

— it does the same fully-automatic thing and the user does NOTHING:

  1. auto-detect the canonical ~/.claude (honours $CLAUDE_CONFIG_DIR);
  2. if this clone lives anywhere else, merge-copy the whole bundle INTO ~/.claude
     (replacing bundle files, preserving your runtime data) and re-launch from there;
  3. open the visual installer, which installs deps -> MCP servers -> plugins ->
     post-steps, then REPAIRS + RE-CHECKS in a loop until the doctor reports 0 FAIL.

All OS branching lives in hooks/lib/platform.py. Pure stdlib (Python >= 3.10).
Equivalent to running install-ui.py — both funnel through installer/bootstrap.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _require_python() -> None:
    if sys.version_info < (3, 10):
        sys.exit(f"install.py requires Python >= 3.10 (found {sys.version.split()[0]})")


def main(argv: list[str]) -> int:
    _require_python()
    import bootstrap  # type: ignore
    return bootstrap.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

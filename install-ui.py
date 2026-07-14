#!/usr/bin/env python3
"""install-ui.py — the ONE installer. Fully automatic, visual, zero user action.

    python install-ui.py          # Ubuntu / macOS
    py -3 install-ui.py           # Windows

Auto-detects your global ``~/.claude``, auto-relocates the clone into it (replacing
bundle files, preserving your runtime data), then opens a local web UI that installs
everything and **repairs + re-checks in a loop until every check is green** — you
don't click a thing. Stdlib only; no Node, no Electron.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if __name__ == "__main__":
    import bootstrap  # type: ignore
    raise SystemExit(bootstrap.main(sys.argv[1:]))

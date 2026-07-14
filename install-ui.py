#!/usr/bin/env python3
"""install-ui.py — launch the VISUAL installer (one command, any OS).

    python install-ui.py          # Ubuntu / macOS
    py -3 install-ui.py           # Windows

Opens a local web UI (127.0.0.1) to auto-detect / pick your .claude folder,
show live workflow status, and install everything step-by-step. Stdlib only —
no Node, no Electron, no extra installs. Equivalent to `python install.py ui`.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT / "installer"))

if __name__ == "__main__":
    import ui  # type: ignore
    raise SystemExit(ui.main(sys.argv[1:]))

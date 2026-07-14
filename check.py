#!/usr/bin/env python3
"""check.py — one-command workflow tester (Windows + Ubuntu/macOS).

Thin wrapper for `python install.py verify`: reports whether the whole ~/.claude
workflow is installed and active (prerequisites, dependency binaries, MCP servers,
plugins, router-live wiring, skill/command palette) with an exact fix command per
gap. Read-only. Exit 0 = all-green.

    python check.py
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import verify  # type: ignore  # noqa: E402

raise SystemExit(verify.main(sys.argv[1:]))

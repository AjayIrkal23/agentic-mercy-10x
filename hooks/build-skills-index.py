#!/usr/bin/env python3
"""build-skills-index.py — thin shim over scripts/build_skills_index.py.

Kept at this path because dispatch.config.json (session-start ``skills-index-guard``),
installer/selfheal.py and installer/manifest.json post_steps invoke it. The single
generator lives in scripts/ (metadata-aware, includes plugin skills, resolves aliases).

Flags: --hook (rebuild if stale, print {}), --check, --force. No flag = rebuild if stale.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

if __name__ == "__main__":
    try:
        import build_skills_index  # noqa: E402
    except Exception:  # noqa: BLE001 — a hook must never crash the session
        if "--hook" in sys.argv:
            print("{}")
            raise SystemExit(0)
        raise
    raise SystemExit(build_skills_index.main(sys.argv[1:]))

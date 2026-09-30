#!/usr/bin/env python3
"""build-skills-index.py — thin shim over scripts/build_skills_index.py.

Kept at this path because dispatch.config.json (session-start ``skills-index-guard``),
installer/selfheal.py and installer/manifest.json post_steps invoke it. The single
generator lives in scripts/ (metadata-aware, includes plugin skills, resolves aliases).

Flags: --hook (rebuild if stale, print {}), --check, --force. No flag = rebuild if stale.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def main(argv: list[str]) -> int:
    hook = "--hook" in argv
    if hook and os.environ.get("CLAUDE_HOOK_DOCTOR"):
        print("{}")  # dry-fire: a fresh checkout looks stale and would be rewritten
        return 0
    try:
        import build_skills_index  # noqa: E402
    except Exception:  # noqa: BLE001 — a hook must never crash the session
        if hook:
            print("{}")
            return 0
        raise
    return build_skills_index.main(argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

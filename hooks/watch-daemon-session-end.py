#!/usr/bin/env python3
"""SessionEnd hook — NEUTRALIZED (P3-T2).

Formerly released this session's per-project watch-daemon refs at SessionEnd.
Those watch daemons were removed (2026-07-09 / 2026-07-11 excision); index
freshness is now event-driven via ``index-lifecycle.py`` — its ``session-end``
mode drains the write journal and flushes the indexes (wired in P3-T4).

This file is kept as a working no-op ONLY because settings.json still registers
it at SessionEnd. It is queued for deregistration + attic in
HANDOFF-P4-registrations.md. Reads the hook JSON on stdin, does nothing here,
prints "{}". Fails open.
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        sys.stdin.read()
    except Exception:
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""SessionEnd hook — interim host for the index-lifecycle session-end flush
(P3-T2 neutralized the systemd refs; P3-T4 gave it this useful job).

Formerly released this session's per-project systemd watch-daemon refs. Those
watch daemons were removed (2026-07-09 / 2026-07-11 excision). This hook now
delegates to ``index-lifecycle.py session-end``, which drains any pending
write-journal for the active repo (the cheapest moment to index — the session
is over). No systemd anything.

Kept under its old filename ONLY because settings.json still registers it at
SessionEnd; it is queued for deregistration + attic and re-homing into
``dispatch.py session-end`` in HANDOFF-P4-registrations.md (P4-T7). Reads the
hook JSON on stdin, forwards it, prints "{}". Fails open.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

LIFECYCLE = Path(__file__).resolve().parent / "index-lifecycle.py"


def main() -> int:
    try:
        payload = sys.stdin.read() or "{}"
    except Exception:
        payload = "{}"
    try:
        subprocess.run(
            [sys.executable or "python3", str(LIFECYCLE), "session-end"],
            input=payload, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pass  # fail-open: a flush failure must never block session end
    print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

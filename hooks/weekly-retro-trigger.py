#!/usr/bin/env python3
"""weekly-retro-trigger.py — Stop exec link (async): the weekly skill-weights loop.

When ``hooks/.telemetry/.weights-last-run`` is missing or older than 7 days, run
``skill-effectiveness-report.py`` + ``skill-router-weight-updater.py`` once, then
touch the sidecar (last, so a mid-run failure retries at the next Stop). Runs at
every Stop, ACTS weekly. Emits nothing user-facing — the former `/retro` nag and
``retro-tracker.json`` were removed 2026-09-27 (the command no longer exists).
Honors CLAUDE_HOOK_DOCTOR (no-op). Fail-open.

argv[1]: "stop"      stdin: Stop payload (ignored)      stdout: {}      exit: 0
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_SIDECAR = _HOOKS / ".telemetry" / ".weights-last-run"
_WEEK = 7 * 86400
_SCRIPTS = ("skill-effectiveness-report.py", "skill-router-weight-updater.py")


def _run_weight_loop_if_stale() -> None:
    try:
        _SIDECAR.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        if _SIDECAR.exists() and (now - _SIDECAR.stat().st_mtime) < _WEEK:
            return
        py = sys.executable or "python3"
        for script in _SCRIPTS:
            path = _HOOKS / script
            if path.is_file():
                try:
                    subprocess.run([py, str(path)], capture_output=True, text=True, timeout=30)
                except Exception:  # noqa: BLE001 - one report failure must not block the other
                    pass
        _SIDECAR.write_text(str(int(now)), encoding="utf-8")
    except Exception:  # noqa: BLE001 - the scheduler must never break the Stop chain
        pass


def main() -> int:
    try:
        sys.stdin.read()  # drain + ignore the payload
    except Exception:  # noqa: BLE001
        pass
    if not os.environ.get("CLAUDE_HOOK_DOCTOR"):
        _run_weight_loop_if_stale()
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""weekly-retro-trigger.py — Stop exec link (async): the weekly skill-weights loop.

Runs ``skill-router-weight-updater.py`` once when BOTH hold:
  * ``hooks/.telemetry/.weights-last-run`` is missing or older than 7 days, and
  * ``skill-effectiveness.jsonl`` changed since that last run (new input).
Then it touches the sidecar (last, so a mid-run failure retries at the next Stop).
Without new input it does nothing at all: the feeder (fullstack-skills-reminder's
old stop mode) is retired, and re-running on frozen input only re-stamped the
TRACKED weights file (audit B2-08 / J-04). The updater also skips an unchanged
write. ``skill-effectiveness-report.py`` is a CLI for people; its output was
captured and dropped here, so it no longer runs.
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
_TELEMETRY = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or _HOOKS / ".telemetry")
_SIDECAR = _TELEMETRY / ".weights-last-run"
_EFFECTIVENESS = _TELEMETRY / "skill-effectiveness.jsonl"
_WEEK = 7 * 86400
_UPDATER = _HOOKS / "skill-router-weight-updater.py"


def _run_weight_loop_if_stale() -> None:
    try:
        if not _EFFECTIVENESS.is_file():
            return
        now = time.time()
        if _SIDECAR.exists():
            last = _SIDECAR.stat().st_mtime
            if now - last < _WEEK or _EFFECTIVENESS.stat().st_mtime <= last:
                return
        if _UPDATER.is_file():
            try:
                subprocess.run([sys.executable or "python3", str(_UPDATER)],
                               capture_output=True, text=True, timeout=30)
            except Exception:  # noqa: BLE001
                pass
        _SIDECAR.parent.mkdir(parents=True, exist_ok=True)
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

#!/usr/bin/env python3
"""stop-failure-log.py: StopFailure exec link (the turn ended on an API error).

Every call leaves one telemetry row (lib/hook_telemetry: event StopFailure, link
stop-failure-log, error, session; never the assistant text). Only ``rate_limit`` also
writes ``state/<sid>.stop-failure.json`` {sid, reason, details, ts, cwd, transcript}:
``scripts/restore_sessions.py --resume-after-limit`` relaunches every such file without
checking the reason, so other errors must not leave one. This hook never launches
anything and never takes ``state/resume-lock/<sid>``.

Output is ignored by the harness; ``{}`` satisfies the dispatcher. CLAUDE_HOOK_DOCTOR:
no writes. Exit 0 always.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

RESUMABLE = {"rate_limit"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(sid) -> str:
    return _UNSAFE.sub("_", str(sid))[:120]


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        print("{}")
        return 0
    sid = _safe(payload.get("session_id") or "unknown")
    err = str(payload.get("error") or "unknown")[:60]
    details = " ".join(str(payload.get("error_details") or "").split())[:300]
    try:
        from lib import hook_telemetry
        hook_telemetry.record("StopFailure", "stop-failure-log", error=err, session=sid, has_details=bool(details))
    except Exception:  # noqa: BLE001
        pass
    if err in RESUMABLE:
        from lib import platform as plat
        plat.atomic_write(plat.state_dir() / f"{sid}.stop-failure.json", json.dumps({
            "sid": sid, "reason": err, "details": details, "ts": round(time.time(), 3),
            "cwd": str(payload.get("cwd") or ""), "transcript": str(payload.get("transcript_path") or "")},
            indent=1))
    print("{}")
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - fail open
        print("{}")
    sys.exit(0)

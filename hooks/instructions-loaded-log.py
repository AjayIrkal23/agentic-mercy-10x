#!/usr/bin/env python3
"""instructions-loaded-log.py: InstructionsLoaded exec link (async).

One row per CLAUDE.md / rules file the harness loads, appended to
``hooks/.telemetry/<YYYY-MM-DD>.instructions-loaded.jsonl`` (CLAUDE_HOOK_TELEMETRY_DIR
overrides the dir): {ts, sid, path, chars, source, load_reason}. ``source`` is ``rules``
for files under ``<claude_dir>/rules``, else the payload's memory_type lower-cased
(user|project|local|managed), else ``unknown``. ``scripts/measure_context_cost.py
--observed`` sums ``chars`` per ``source``; state-cleanup purges the ``*.*.jsonl`` family
after 14 days.

Never prints (the harness ignores the output). CLAUDE_HOOK_DOCTOR: no row. Exit 0 always.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

_SOURCES = ("user", "project", "local", "managed")


def _telemetry_dir() -> Path:
    return Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or HOOK_DIR / ".telemetry")


def _row_path(when: datetime | None = None) -> Path:
    day = (when or datetime.now()).strftime("%Y-%m-%d")
    return _telemetry_dir() / f"{day}.instructions-loaded.jsonl"


def _source(path: Path, memory_type) -> str:
    try:
        from lib import platform as plat
        rules = (plat.claude_dir() / "rules").resolve()
        if rules in path.resolve().parents:
            return "rules"
    except Exception:  # noqa: BLE001
        pass
    mt = str(memory_type or "").lower()
    return mt if mt in _SOURCES else "unknown"


def _chars(path: Path) -> int:
    try:
        st = path.stat()
        if st.st_size > 2_000_000:  # do not read a huge file just to count it
            return int(st.st_size)
        return len(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except ValueError:
        return 0
    if not isinstance(payload, dict) or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return 0
    fp = payload.get("file_path")
    if not isinstance(fp, str) or not fp:
        return 0
    p = Path(fp)
    row = {"ts": round(time.time(), 3), "sid": str(payload.get("session_id") or ""), "path": str(p),
           "chars": _chars(p), "source": _source(p, payload.get("memory_type")),
           "load_reason": str(payload.get("load_reason") or "")}
    from lib import platform as plat
    target = _row_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    plat.append_line(target, (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - fail open, never print
        pass
    sys.exit(0)

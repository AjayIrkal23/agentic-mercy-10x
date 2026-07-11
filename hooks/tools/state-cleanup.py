#!/usr/bin/env python3
"""state-cleanup.py — session-start exec link: bounded retention purge (P4-T1).

Charter §7 always-on telemetry needs a bounded footprint. This link runs once
per SessionStart and best-effort removes:
  * telemetry/hook-fires-*.jsonl        older than 14 days (Spec B §6 retention)
  * telemetry/*.router-shadow.jsonl     older than 14 days
  * state/*.classification.json         older than 24h (per-turn scratch)
  * state/*.router-manifest.json        older than 24h

Never raises, never blocks — a purge failure must never affect a session. Reads
and ignores stdin (hook payload). Emits nothing (pure exec side effect).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore

_DAY = 86400.0


def _claude_dir() -> Path:
    if _plat is not None:
        return _plat.claude_dir()
    import os
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path("~/.claude").expanduser()


def _purge(directory: Path, patterns, max_age_s: float, now: float) -> int:
    removed = 0
    if not directory.is_dir():
        return 0
    for pat in patterns:
        for f in directory.glob(pat):
            try:
                if not f.is_file():
                    continue
                if now - f.stat().st_mtime > max_age_s:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def main() -> int:
    try:
        try:
            sys.stdin.read()  # drain + ignore the hook payload
        except Exception:  # noqa: BLE001
            pass
        now = time.time()
        base = _claude_dir()
        _purge(base / "telemetry",
               ["hook-fires-*.jsonl", "*.router-shadow.jsonl"], 14 * _DAY, now)
        _purge(base / "state",
               ["*.classification.json", "*.router-manifest.json"], _DAY, now)
    except Exception:  # noqa: BLE001 - cleanup must never brick session start
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

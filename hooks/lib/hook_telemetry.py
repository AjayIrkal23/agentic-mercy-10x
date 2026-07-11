"""hook_telemetry.py — always-on, O_APPEND jsonl fire logger.

Charter §3/§7: every hook link is telemetry-logged from day 1. This is the one
appender. It uses ``os.open(..., O_APPEND)`` + a single ``os.write`` so
concurrent links (parallel advisory ThreadPool, sibling sessions) never
interleave a partial line — POSIX guarantees atomic appends up to PIPE_BUF and
we keep records well under that. Never raises; telemetry must never break a
hook.

Record shape (Spec B §2 link telemetry):
  {ts, session, event, link_id, ms, exit, chars_out, decision, budget_hit, error, ...}

Files: ~/.claude/telemetry/hook-fires-YYYYMMDD.jsonl (daily rotation by name).
Debug dump: when ~/.claude/state/hook-debug exists, records are also echoed to
stderr so a live session can watch fires.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

try:  # tolerate being imported before the package is on sys.path
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    import platform as _plat  # type: ignore


def _today_file() -> Path:
    day = time.strftime("%Y%m%d")
    return _plat.telemetry_dir() / f"hook-fires-{day}.jsonl"


def _debug_enabled() -> bool:
    try:
        return (_plat.state_dir() / "hook-debug").exists()
    except OSError:
        return False


def record(event: str, link_id: str, **fields: Any) -> None:
    """Append one telemetry record. Never raises.

    ``event`` — hook event (UserPromptSubmit, PreToolUse, Stop, ...).
    ``link_id`` — the specific hook/link/module id that fired.
    ``**fields`` — ms, exit, chars_out, decision, budget_hit, error, session, etc.
    """
    rec: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "event": event,
        "link_id": link_id,
    }
    rec.update(fields)
    try:
        line = json.dumps(rec, ensure_ascii=False, default=str) + "\n"
    except (TypeError, ValueError):
        line = json.dumps({"ts": rec["ts"], "event": event, "link_id": link_id,
                           "error": "unserializable-telemetry"}) + "\n"
    data = line.encode("utf-8", "replace")
    try:
        path = _today_file()
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        pass  # telemetry is best-effort — never break the hook

    if _debug_enabled():
        try:
            import sys

            sys.stderr.write("[hook-telemetry] " + line)
        except Exception:  # noqa: BLE001
            pass


class Timer:
    """Context manager measuring elapsed ms and auto-recording on exit.

    Usage:
        with Timer("UserPromptSubmit", "prompt_router", session=sid) as t:
            ...            # do work
            t.set(decision="emit", chars_out=812)
    On an exception inside the block the timer records exit=1 + the error string
    and re-raises nothing (fail-open) unless ``reraise=True``.
    """

    def __init__(self, event: str, link_id: str, *, reraise: bool = False, **base: Any):
        self.event = event
        self.link_id = link_id
        self.reraise = reraise
        self.base = base
        self.extra: dict[str, Any] = {}
        self._t0 = 0.0

    def set(self, **fields: Any) -> None:
        self.extra.update(fields)

    def __enter__(self) -> "Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        ms = round((time.perf_counter() - self._t0) * 1000, 2)
        fields = dict(self.base)
        fields.update(self.extra)
        fields["ms"] = ms
        if exc is not None:
            fields.setdefault("exit", 1)
            fields["error"] = f"{exc_type.__name__}: {exc}"[:500]
        else:
            fields.setdefault("exit", 0)
        record(self.event, self.link_id, **fields)
        return not self.reraise and exc is not None


__all__ = ["record", "Timer"]

"""memwatch_state.py — the OOM guard's shared state files (contract fixed by the merge plan).

  state/mem-pressure.json   one State, rewritten atomically by hooks/tools/memwatch.py every pass
  state/oomguard.events     one JSON object per line (tier / kill / shed / restore), append-only
  state/oomguard.cursor     {"reported_until": ts}, advanced by session_notices.memwatch_line
  state/mercy-mod.active.d/<sid>.json  {"sid","pid","ts"} one per live mod session (written by the mercy mod)
  state/live-sessions/      per-session ledger (written by hooks/session-ledger.py)
  state/session-bridge/     per-session statusline numbers (written by scripts/statusline.py)

``read()`` fails open by construction: a missing, corrupt or stale file reads as level ``ok`` with
``stale=True``; ``raw_level`` keeps the file's own value for the doctor. Never raises.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, fields
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None

LEVELS = ("ok", "warn", "crit")
_CONTRACT_KEYS = ("schema", "ts", "level", "mem_available_mb", "swap_free_pct", "psi_some_avg10", "top", "stuck",
                  "shed", "notify_owner", "kill_policy", "restore_pending", "unsupported")


@dataclass
class State:
    level: str = "ok"
    ts: float = 0.0
    mem_available_mb: int | None = None
    swap_free_pct: float | None = None
    psi_some_avg10: float | None = None
    top: list = field(default_factory=list)
    stuck: list = field(default_factory=list)
    shed: list = field(default_factory=list)
    notify_owner: str = "memwatch"
    kill_policy: dict = field(default_factory=dict)
    restore_pending: bool = False
    unsupported: bool = False
    stale: bool = True
    raw_level: str = "ok"
    schema: int = 1

    def to_json(self) -> dict:
        """The contract keys only (``stale`` / ``raw_level`` are reader-side)."""
        return {k: getattr(self, k) for k in _CONTRACT_KEYS}

    @classmethod
    def from_json(cls, d: dict, stale: bool) -> "State":
        """Tolerant: unknown keys ignored, a wrong-typed value keeps the default."""
        st = cls()
        if not isinstance(d, dict):
            return st
        defaults = {f.name: getattr(st, f.name) for f in fields(cls)}
        for key in _CONTRACT_KEYS:
            if key not in d:
                continue
            v, dv = d[key], defaults[key]
            if key in ("mem_available_mb",):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
                v = int(v) if ok else None
            elif key in ("swap_free_pct", "psi_some_avg10", "ts"):
                ok = isinstance(v, (int, float)) and not isinstance(v, bool)
                v = float(v) if ok else dv
            elif key == "level":
                v = v if v in LEVELS else "ok"
            elif isinstance(dv, bool):
                v = v if isinstance(v, bool) else dv
            elif isinstance(dv, (list, dict, str, int)):
                v = v if isinstance(v, type(dv)) else dv
            setattr(st, key, v)
        st.raw_level = st.level
        st.stale = stale
        if stale:
            st.level = "ok"
        return st


def paths() -> dict[str, Path]:
    s = _plat.state_dir() if _plat is not None else Path("~/.claude/state").expanduser()
    return {"state": s / "mem-pressure.json", "events": s / "oomguard.events", "cursor": s / "oomguard.cursor",
            "mod_active": s / "mercy-mod.active.d", "ledger_dir": s / "live-sessions",
            "bridge_dir": s / "session-bridge"}


def read(stale_s: float = 30.0, now: float | None = None, path: Path | str | None = None) -> State:
    """Missing / corrupt / stale -> level "ok", stale=True; ``raw_level`` = the file's level."""
    try:
        d = json.loads(Path(path or paths()["state"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return State()
    if not isinstance(d, dict):
        return State()
    now = time.time() if now is None else now
    ts = d.get("ts")
    stale = not isinstance(ts, (int, float)) or (now - float(ts)) > stale_s
    return State.from_json(d, stale)


def write_atomic(state: State, path: Path | str | None = None) -> bool:
    if _plat is None:
        return False
    return _plat.atomic_write(Path(path or paths()["state"]), json.dumps(state.to_json(), indent=1))


def append_event(ev: dict, path: Path | str | None = None) -> bool:
    """One JSON line; ``ts`` filled when absent."""
    if _plat is None:
        return False
    ev = dict(ev)
    ev.setdefault("ts", round(time.time(), 3))
    target = Path(path or paths()["events"])
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return _plat.append_line(target, (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))


def tail_events(max_bytes: int = 262144, path: Path | str | None = None) -> list[dict]:
    """Parse the last ``max_bytes`` of the events file; a partial first line and bad lines are skipped."""
    target = Path(path or paths()["events"])
    try:
        with open(target, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
            start = max(0, size - max_bytes)
            fh.seek(start)
            blob = fh.read()
    except OSError:
        return []
    lines = blob.split(b"\n")
    if start > 0 and lines:
        lines = lines[1:]
    out = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def unreported_events(cursor_ts: float, kinds=("kill", "restore"),
                      path: Path | str | None = None) -> tuple[list[dict], float]:
    """Events of ``kinds`` newer than ``cursor_ts`` and the newest ts among them (cursor_ts when none)."""
    out, newest = [], float(cursor_ts or 0)
    for ev in tail_events(path=path):
        ts = ev.get("ts")
        if not isinstance(ts, (int, float)) or ts <= cursor_ts or ev.get("kind") not in kinds:
            continue
        out.append(ev)
        newest = max(newest, float(ts))
    return out, newest


__all__ = ["State", "LEVELS", "paths", "read", "write_atomic", "append_event", "tail_events", "unreported_events"]

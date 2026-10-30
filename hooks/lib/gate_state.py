"""gate_state.py — the ONE per-session JSON state helper for gates (safe_cid, paths, locked RMW).

Replaces the private ``_safe_cid`` / ``_load_state`` / ``_save_state`` copies the gates
carried (audit 08 item 8). Writes go through ``platform.locked_update`` (lock sidecar
``<path>.lock``, atomic replace). The dotstate dir is resolved AT CALL TIME from
``CLAUDE_HOOK_DOTSTATE_DIR`` so sandboxes and tests redirect it; callers that keep a module
``STATE_DIR`` pass it as ``base``.

  save_json   full replace under the lock (gates compute the whole dict)
  update_json read-modify-write under the lock (counters)

Never raises; an unreadable or corrupt file reads as ``default``. Stdlib only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from . import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore[assignment]


def safe_cid(cid) -> str:
    """Filesystem-safe session id: everything but ``[A-Za-z0-9_-]`` becomes ``_``."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(cid or ""))


def dotstate_dir() -> Path:
    env = os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[1] / ".state"


def state_path(cid, suffix: str, *, base=None) -> "Path | None":
    """``<base>/<safe_cid>.<suffix>.json``; None for an empty session id."""
    if not cid:
        return None
    try:
        return Path(base or dotstate_dir()) / f"{safe_cid(cid)}.{suffix}.json"
    except Exception:  # noqa: BLE001
        return None


def load_json(path, *, default=None) -> dict:
    """The dict stored at ``path``, else a copy of ``default`` (or ``{}``)."""
    try:
        if path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return dict(default or {})


def save_json(path, data) -> bool:
    """Replace ``path`` with ``data`` under the lock. True when it reached the disk."""
    if not path or _plat is None:
        return False
    try:
        snapshot = dict(data)
        return bool(_plat.locked_update_ok(path, lambda _old: snapshot)[1])
    except Exception:  # noqa: BLE001
        return False


def update_json(path, fn, *, default=None) -> dict:
    """Locked read-modify-write: ``fn(dict) -> dict``. Returns what it wrote."""
    if not path or _plat is None:
        return dict(default or {})
    try:
        return _plat.locked_update(path, fn, default=default)
    except Exception:  # noqa: BLE001
        return dict(default or {})


def load_state(cid, suffix: str, *, base=None, default=None) -> dict:
    p = state_path(cid, suffix, base=base)
    return load_json(p, default=default) if p else dict(default or {})


def save_state(cid, suffix: str, data, *, base=None) -> bool:
    p = state_path(cid, suffix, base=base)
    return save_json(p, data) if p else False


__all__ = ["safe_cid", "dotstate_dir", "state_path", "load_json", "save_json", "update_json",
           "load_state", "save_state"]

"""manifest.py — session-manifest dedup (Charter §1).

Suppresses VERBATIM re-injection of an advisory already surfaced this session,
but NEVER suppresses a first fire. State lives at
``~/.claude/state/<sid>.router-manifest.json``.

An item is identified by its stable ``id`` (a semantic id like
``substrate:jcodemunch`` or ``skill:frontend-standards-always-follow``). The
first time an id is emitted it is recorded; subsequent prompts that would emit
the same id are deduped. A DIFFERENT id always fires — dedup can never cause a
missed first trigger (the invariant P1-T11 tests).

Pure stdlib; fail-open (a manifest IO error disables dedup rather than dropping
content — favouring never-miss over token savings).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

try:
    from lib import platform as _plat
except Exception:  # noqa: BLE001
    _plat = None  # type: ignore


def _manifest_path(sid: str) -> Path:
    if _plat is not None:
        base = _plat.state_dir()
    else:
        base = Path("~/.claude/state").expanduser()
        base.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if (c.isalnum() or c in "-_.") else "-" for c in (sid or "nosession"))
    return base / f"{safe}.router-manifest.json"


def load(sid: str) -> set[str]:
    """Return the set of ids already emitted this session (empty on any error)."""
    try:
        raw = _manifest_path(sid).read_text(encoding="utf-8")
        data = json.loads(raw)
        return set(data.get("emitted_ids", []))
    except (OSError, json.JSONDecodeError):
        return set()


def dedup(items: list[dict], emitted: set[str]) -> tuple[list[dict], list[dict]]:
    """Split items into (kept, suppressed). An item with no 'id' is always kept
    (cannot be a verbatim repeat). Suppression only removes ids already emitted."""
    kept: list[dict] = []
    suppressed: list[dict] = []
    seen_this_prompt: set[str] = set()
    for it in items:
        iid = it.get("id")
        if not iid:
            kept.append(it)
            continue
        if iid in emitted or iid in seen_this_prompt:
            suppressed.append(it)
        else:
            kept.append(it)
            seen_this_prompt.add(iid)
    return kept, suppressed


def commit(sid: str, emitted: set[str], newly: list[dict]) -> None:
    """Record the ids actually emitted this prompt into the session manifest.
    Fail-open (best-effort write)."""
    ids = set(emitted)
    for it in newly:
        iid = it.get("id")
        if iid:
            ids.add(iid)
    payload = json.dumps({"emitted_ids": sorted(ids)}, ensure_ascii=False)
    path = _manifest_path(sid)
    if _plat is not None and hasattr(_plat, "atomic_write"):
        _plat.atomic_write(path, payload)
    else:
        try:
            path.write_text(payload, encoding="utf-8")
        except OSError:
            pass


__all__ = ["load", "dedup", "commit"]

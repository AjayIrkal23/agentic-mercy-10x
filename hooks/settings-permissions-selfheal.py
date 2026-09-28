#!/usr/bin/env python3
"""settings-permissions-selfheal.py — SessionStart / SessionEnd exec link, and the
ConfigChange gate (`config-change` argv, 2026-09-27).

Repairs `permissions.deny` in the rendered settings.json when it has drifted from
settings.template.json (the tracked source of truth). In `config-change` mode a
non-empty deny list is healed to [] immediately and the change is blocked.

WHY THIS EXISTS
---------------
settings.json is a RENDERED artifact (installer/render.py <- settings.template.json),
but Claude Code also writes it: a session holds its permission state in memory and
flushes that state to disk when it EXITS. A session started (or `--resume`d) before a
permissions change therefore rewrites the OLD values on teardown, silently undoing
both `/permissions` edits and re-renders. Observed 2026-07-19:

    19:34:14  deny=[]                        <- freshly cleared, stable for 75s
    19:34:16  deny=["Read","Grep","Glob"]    <- a resumed session exited here

Every subsequently opened session then inherits the stale list from disk. The loop is
self-sustaining and cannot be broken by editing the file, because the pending writes
live in the memory of already-running sessions.

Healing at SessionStart is the correct cadence: sessions write on exit, so the next
session start is the first moment the drift is observable and fixable.

SCOPE — deliberately narrow
---------------------------
Only `permissions.deny` is touched. A full re-render is NOT used: Claude Code
legitimately manages other parts of the live file (env key ordering, etc.), and
fighting it over those would produce a rewrite war. This repairs the one key that has
no business drifting and leaves everything else alone.

No-ops when the file already matches (the overwhelmingly common case). Never raises:
any failure leaves settings.json untouched. Exit 0 always.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE = ROOT / "settings.json"
TEMPLATE = ROOT / "settings.template.json"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_live(live: dict) -> None:
    # Atomic replace so a concurrent reader never sees a half-written file.
    tmp = LIVE.with_suffix(".json.selfheal.tmp")
    tmp.write_text(json.dumps(live, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LIVE)


def heal_from_template() -> int:
    """SessionStart / SessionEnd mode: re-sync permissions.deny from the template."""
    live = _load(LIVE)
    tmpl = _load(TEMPLATE)
    if live is None or tmpl is None:
        return 0

    want = (tmpl.get("permissions") or {}).get("deny")
    got = (live.get("permissions") or {}).get("deny")
    if want is None or got == want:
        return 0  # in sync — the common path, stay silent

    live.setdefault("permissions", {})["deny"] = want
    _write_live(live)

    removed = [r for r in (got or []) if r not in (want or [])]
    note = (
        f"settings-selfheal: permissions.deny drifted from settings.template.json "
        f"and was repaired ({got!r} -> {want!r})."
    )
    if removed:
        note += (
            f" Restored access to: {', '.join(removed)}. Cause is almost always a "
            "session that started before the change writing its stale in-memory "
            "state on exit; re-opened sessions then inherit it from disk."
        )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }))
    return 0


def config_change() -> int:
    """ConfigChange gate: a non-empty permissions.deny is healed to [] the moment it
    lands, and the change is blocked so the model hears why (2026-09-27)."""
    live = _load(LIVE)
    deny = (live.get("permissions") or {}).get("deny") if isinstance(live, dict) else None
    if not deny:
        print("{}")
        return 0
    live.setdefault("permissions", {})["deny"] = []
    _write_live(live)
    print(json.dumps({
        "decision": "block",
        "reason": f"permissions.deny re-added ({deny!r}); healed to [].",
    }))
    return 0


def main(argv: list[str]) -> int:
    if os.environ.get("CLAUDE_HOOK_DOCTOR"):
        print("{}")
        return 0
    mode = argv[0] if argv else "session-start"
    try:
        if mode == "config-change":
            return config_change()
        return heal_from_template()  # session-start / session-end
    except Exception as exc:  # noqa: BLE001
        print(f"[settings-permissions-selfheal] {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

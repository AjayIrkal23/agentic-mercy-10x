#!/usr/bin/env python3
"""settings-permissions-selfheal.py — SessionStart / SessionEnd exec link, and the
ConfigChange gate (`config-change` argv, 2026-09-27).

Repairs `permissions.deny` in the rendered settings.json when it has drifted from
settings.template.json (the tracked source of truth). In `config-change` mode a
non-empty deny list is healed to [] immediately and the change is blocked. Both modes
also empty `permissions.deny` in the untracked settings.local.json (other keys kept).

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
# Untracked, no template: any deny list here is drift (2026-10-31: a tool-pruning plugin
# wrote 467 rules that hid jcodemunch, lean-ctx and most MCP tools).
LOCAL = ROOT / "settings.local.json"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _lock_fn():
    """lib.platform's lock primitive (private, but the one lock in the tree); None → no lock."""
    try:
        hooks = str(ROOT / "hooks")
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        from lib.platform import _lock  # noqa: PLC0415
        return _lock
    except Exception:  # noqa: BLE001
        return None


def _write_live(live: dict, path: Path | None = None) -> None:
    """Atomic replace under ``<file>.lock`` so a concurrent reader never sees a
    half-written file and two healers never interleave. Mode 0600 (it can hold env values)."""
    path = path or LIVE
    lock = _lock_fn()
    with open(path.with_name(path.name + ".lock"), "a+") as lk:
        if lock is not None:
            try:
                lock(lk, timeout=2.0)
            except OSError:
                pass  # a stuck holder costs 2 s, never the repair
        tmp = path.with_suffix(".json.selfheal.tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(live, indent=2) + "\n")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)


def _clear_local_deny() -> list:
    """Empty settings.local.json's permissions.deny, other keys untouched; returns what it removed."""
    local = _load(LOCAL)
    if not isinstance(local, dict):
        return []
    deny = (local.get("permissions") or {}).get("deny")
    if not deny:
        return []
    local["permissions"]["deny"] = []
    _write_live(local, LOCAL)
    return deny


def _repo_local(cwd: str) -> Path | None:
    """The active repo's `.claude/settings.local.json` (git root of `cwd`), never $HOME's or this checkout's."""
    home = Path.home().resolve()
    try:
        p = Path(cwd).resolve()
    except (OSError, RuntimeError):
        return None
    for d in (p, *p.parents):
        if d == home or d == ROOT:
            return None
        if (d / ".git").exists():
            return d / ".claude" / "settings.local.json"
    return None


def _clear_repo_tool_denies(cwd: str) -> list:
    """Drop bare tool-name rules (`LSP`, `mcp__github__create_issue`) from the active repo's
    settings.local.json: a tool-pruning plugin writes those to hide tools. Scoped rules such as
    `Read(./.env)` are the repo's own safety policy and stay."""
    path = _repo_local(cwd) if cwd else None
    if path is None or path.is_symlink():  # a linked file is the user's own arrangement: never replace it
        return []
    local = _load(path)
    if not isinstance(local, dict) or not isinstance(local.get("permissions"), dict):
        return []
    deny = local["permissions"].get("deny") or []
    bare = [r for r in deny if isinstance(r, str) and "(" not in r]
    if not bare:
        return []
    local["permissions"]["deny"] = [r for r in deny if r not in bare]
    # atomic replace, no `<file>.lock` left behind in the user's repo (Claude Code never takes our lock)
    try:
        hooks = str(ROOT / "hooks")
        if hooks not in sys.path:
            sys.path.insert(0, hooks)
        from lib.platform import atomic_write  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    return bare if atomic_write(path, json.dumps(local, indent=2) + "\n") else []


def _payload_cwd() -> str:
    """`cwd` from the hook payload on stdin; '' when there is none (manual run, bad JSON)."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return ""
        data = json.loads(sys.stdin.read() or "{}")
    except (OSError, ValueError):
        return ""
    return str(data.get("cwd") or "") if isinstance(data, dict) else ""


def heal_from_template(cwd: str = "") -> int:
    """SessionStart / SessionEnd mode: re-sync permissions.deny from the template, clear any
    deny list in settings.local.json, and drop tool-hiding rules from the active repo's."""
    notes = []
    local_removed = _clear_local_deny()
    if local_removed:
        notes.append(f"settings-selfheal: settings.local.json held {len(local_removed)} "
                     "permissions.deny rules; cleared to [].")
    repo_removed = _clear_repo_tool_denies(cwd)
    if repo_removed:
        notes.append(f"settings-selfheal: this repo's .claude/settings.local.json hid {len(repo_removed)} "
                     "tools through permissions.deny; those rules were removed (scoped rules kept).")

    live = _load(LIVE)
    tmpl = _load(TEMPLATE)
    want = (tmpl.get("permissions") or {}).get("deny") if isinstance(tmpl, dict) else None
    got = (live.get("permissions") or {}).get("deny") if isinstance(live, dict) else None
    if isinstance(live, dict) and want is not None and got != want:
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
        notes.append(note)

    if not notes:
        return 0  # in sync — the common path, stay silent
    note = " ".join(notes)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": note,
        }
    }))
    return 0


def config_change(cwd: str = "") -> int:
    """ConfigChange gate: a non-empty permissions.deny is healed to [] the moment it
    lands, and the change is blocked so the model hears why (2026-09-27). settings.local.json
    is cleared the same way (2026-10-31), and so are the active repo's tool-hiding rules."""
    reasons = []
    local_removed = _clear_local_deny()
    if local_removed:
        reasons.append(f"settings.local.json permissions.deny re-added ({len(local_removed)} rules); healed to [].")
    repo_removed = _clear_repo_tool_denies(cwd)
    if repo_removed:
        reasons.append(f"this repo's .claude/settings.local.json hid {len(repo_removed)} tools; those rules were removed.")
    live = _load(LIVE)
    deny = (live.get("permissions") or {}).get("deny") if isinstance(live, dict) else None
    if deny and isinstance(live, dict):
        live.setdefault("permissions", {})["deny"] = []
        _write_live(live)
        reasons.append(f"permissions.deny re-added ({deny!r}); healed to [].")
    if not reasons:
        print("{}")
        return 0
    print(json.dumps({"decision": "block", "reason": " ".join(reasons)}))
    return 0


def main(argv: list[str]) -> int:
    if os.environ.get("CLAUDE_HOOK_DOCTOR"):
        print("{}")
        return 0
    mode = argv[0] if argv else "session-start"
    try:
        cwd = _payload_cwd()
        if mode == "config-change":
            return config_change(cwd)
        return heal_from_template(cwd)  # session-start / session-end
    except Exception as exc:  # noqa: BLE001
        print(f"[settings-permissions-selfheal] {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

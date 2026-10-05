"""session_notices.py — one-line SessionStart notices (autonomy plan 2026-10-05, WP-C item 4).

``mod_off_notice()``  the mercy mod is enabled in installer/manifest.json but this session
                      does not have it: Claude Code's remote rollout switch
                      (``cachedGrowthBookFeatures.tengu_plugin_hooks_modules`` in
                      ``~/.claude.json``) is false. Only that one boolean is read; nothing
                      else from that file is ever printed.
``selfheal_line()``   the daily self-heal (WP-D) left ``state/selfheal-daily.json`` with
                      ``reported: false``: one line from its ``changed`` / ``errors``, then
                      ``reported`` flips to true (locked atomic write) so it is said once.

Both fail open to "" and never raise; a doctor/test dry-fire (``CLAUDE_HOOK_DOCTOR``)
never consumes the self-heal summary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from lib import platform as _plat
except Exception:  # pragma: no cover - fail-open
    _plat = None

MOD_OFF = ("mercy mod is off this session (Claude Code's remote rollout switch); every gate still "
           "runs in Python; the UI deck returns when the switch does")
_FLAG = "tengu_plugin_hooks_modules"
_MAX_LINE = 380
_ITEM = 90


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _mods_enabled() -> bool:
    base = _plat.claude_dir() if _plat is not None else Path("~/.claude").expanduser()
    mods = (_load(base / "installer" / "manifest.json") or {}).get("mods")
    return isinstance(mods, dict) and bool(mods.get("enabled"))


def mod_off_notice() -> str:
    try:
        if os.environ.get("MERCY_MOD_SESSION") or os.environ.get("MERCY_MOD_LOADED") or not _mods_enabled():
            return ""
        feats = (_load(Path.home() / ".claude.json") or {}).get("cachedGrowthBookFeatures")
        if isinstance(feats, dict) and feats.get(_FLAG) is False:
            return MOD_OFF
    except Exception:  # noqa: BLE001
        pass
    return ""


def _clip(s: object, n: int = _ITEM) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _summary(changed: list, errors: list) -> str:
    parts = []
    if changed:
        parts.append("; ".join(_clip(c) for c in changed[:4]) + (f" (+{len(changed) - 4} more)" if len(changed) > 4 else ""))
    if errors:
        parts.append(f"{len(errors)} error(s): " + _clip(errors[0]))
    line = "Daily self-heal ran in the background: " + " | ".join(parts) if parts else ""
    return line if len(line) <= _MAX_LINE else line[: _MAX_LINE - 1] + "…"


def selfheal_line() -> str:
    """The summary line once, then ``reported`` is set true. "" when nothing to report."""
    try:
        if _plat is None or os.environ.get("CLAUDE_HOOK_DOCTOR"):
            return ""
        path = _plat.state_dir() / "selfheal-daily.json"
        data = _load(path)
        if not isinstance(data, dict) or data.get("reported") is not False:
            return ""
        taken: dict = {}

        def _take(d: dict) -> dict:
            if d.get("reported") is False:  # re-checked under the lock: another session may have won
                taken["changed"] = [c for c in (d.get("changed") or []) if str(c).strip()]
                taken["errors"] = [e for e in (d.get("errors") or []) if str(e).strip()]
                d["reported"] = True
            return d

        _plat.locked_update(path, _take)
        return _summary(taken.get("changed", []), taken.get("errors", []))
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["MOD_OFF", "mod_off_notice", "selfheal_line"]

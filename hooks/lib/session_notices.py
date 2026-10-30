"""session_notices.py — one-line SessionStart notices (autonomy plan 2026-10-05, WP-C item 4).

``mod_off_notice()``  the mercy mod is enabled in installer/manifest.json but this session
                      does not have it: Claude Code's remote rollout switch
                      (``cachedGrowthBookFeatures.tengu_plugin_hooks_modules`` in
                      ``~/.claude.json``) is false. Only that one boolean is read; nothing
                      else from that file is ever printed.
``selfheal_line()``   the daily self-heal (WP-D) left ``state/selfheal-daily.json`` with
                      ``reported: false``: one line from its ``changed`` / ``errors``, then
                      ``reported`` flips to true (locked atomic write) so it is said once.

``memwatch_line()``  OOM guard: kills / restores in ``state/oomguard.events`` newer than
                      ``state/oomguard.cursor``, one line (<= 300 chars), cursor advanced.
``mod_active(sid)``   ``state/mercy-mod.active.d/<sid>.json`` names this session and is < 60 s old.
``worktree_line(cwd)`` / ``instinct_lines(cwd)``  stubs over optional tools
                      (``hooks/tools/worktree_audit.py``, ``hooks/tools/instincts.py``) other
                      packages ship; "" / [] when absent or failing.

All fail open to "" and never raise; a doctor/test dry-fire (``CLAUDE_HOOK_DOCTOR``)
never consumes the self-heal summary or the OOM cursor.
"""
from __future__ import annotations

import json
import os
import re
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


# --------------------------------------------------------------------------- #
# OOM guard (docs/OOM-GUARD.md) and optional-tool stubs
# --------------------------------------------------------------------------- #
_HOOKS = Path(__file__).resolve().parents[1]  # a test seam: monkeypatch to a tmp hooks dir
_CURSOR_KINDS = ("kill", "restore")
_OOM_MAX = 300


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _fmt_kill(ev: dict) -> str:
    who = ev.get("victim") or ev.get("unit") or "process"
    rss = ev.get("rss_mb")
    size = f" {rss / 1024:.1f} GB" if isinstance(rss, (int, float)) and rss else ""
    src = ev.get("source")
    if src == "memwatch":
        label = f"memwatch stage {ev.get('stage', '?')}"
    elif src == "toolcap":
        label = ("tool cap " + str(ev.get("limit") or "")).strip()
    else:
        label = str(src or "?")
    return f"{_clip(who, 40)}{size}, {label}"


def memwatch_line() -> str:
    """Kills and restores since the cursor, said once per event (the cursor advances). "" when none,
    under a doctor dry-fire (cursor untouched) or on any error."""
    try:
        if _plat is None or os.environ.get("CLAUDE_HOOK_DOCTOR"):
            return ""
        from lib import memwatch_state as mws
        cursor = mws.paths()["cursor"]
        cur = _load(cursor) or {}
        since = float(cur.get("reported_until") or 0) if isinstance(cur, dict) else 0.0
        evs, newest = mws.unreported_events(since, kinds=_CURSOR_KINDS)
        if not evs:
            return ""
        kills = [e for e in evs if e.get("kind") == "kill"]
        restores = [e for e in evs if e.get("kind") == "restore" and e.get("ok") is not False]
        parts = []
        if kills:
            parts.append(_plural(len(kills), "kill") + " (" + "; ".join(_fmt_kill(e) for e in kills[-3:]) + ")")
        if restores:
            parts.append(_plural(len(restores), "session") + " restored")
        _plat.locked_update(cursor, lambda d: {**d, "reported_until": newest}, default={})
        if not parts:
            return ""
        line = "OOM guard since last session: " + ", ".join(parts) + ". Details: state/oomguard.events"
        return line if len(line) <= _OOM_MAX else line[: _OOM_MAX - 1] + "…"
    except Exception:  # noqa: BLE001
        return ""


def _safe(s) -> str:
    """A session id as a file name (the mod writes ``<sid>.json``; Claude Code ids are uuids)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(s))[:80]


def mod_active(sid: str, fresh_s: float = 60.0) -> bool:
    """True when ``state/mercy-mod.active.d/<sid>.json`` names this session and is younger than ``fresh_s``."""
    try:
        if _plat is None:
            return False
        import time
        d = _load(_plat.state_dir() / "mercy-mod.active.d" / (_safe(sid) + ".json"))
        if not isinstance(d, dict) or str(d.get("sid") or "") != str(sid):
            return False
        ts = d.get("ts")
        return isinstance(ts, (int, float)) and 0 <= time.time() - ts < fresh_s
    except Exception:  # noqa: BLE001
        return False


def _optional_tool(name: str):
    """``hooks/tools/<name>.py`` executed as a fresh module, or None when absent or failing. Compiled from
    source each call (no stale bytecode, no sys.modules entry)."""
    try:
        src = _HOOKS / "tools" / f"{name}.py"
        if not src.is_file():
            return None
        import types
        mod = types.ModuleType(f"_optional_{name}")
        mod.__file__ = str(src)
        exec(compile(src.read_text(encoding="utf-8"), str(src), "exec"), mod.__dict__)  # noqa: S102 - our own file
        return mod
    except Exception:  # noqa: BLE001
        return None


def worktree_line(cwd: str | None = None) -> str:
    """One line from hooks/tools/worktree_audit.py (package `worktrees`) when it is installed."""
    try:
        mod = _optional_tool("worktree_audit")
        if mod is None:
            return ""
        return _clip(mod.one_line(cwd or os.getcwd(), budget_ms=400) or "", _MAX_LINE)
    except Exception:  # noqa: BLE001
        return ""


def instinct_lines(cwd: str | None = None) -> list[str]:
    """At most 3 lines from hooks/tools/instincts.py (package `learning`) when it is installed."""
    try:
        mod = _optional_tool("instincts")
        if mod is None:
            return []
        out = mod.lines(cwd or os.getcwd(), limit=3, min_confidence=0.7) or []
        return [str(x) for x in out][:3]
    except Exception:  # noqa: BLE001
        return []


def tier_line() -> str:
    """``plan tier <tier> · main <model>`` from state/plan-tier.json; "" without the file (RT-8)."""
    try:
        base = _plat.state_dir() if _plat is not None else Path("~/.claude/state").expanduser()
        d = json.loads((base / "plan-tier.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(d, dict) or not d.get("tier"):
        return ""
    return f"plan tier {_safe(d['tier'])} · main {_safe(d.get('main') or '?')}"


__all__ = ["MOD_OFF", "mod_off_notice", "selfheal_line", "memwatch_line", "mod_active", "worktree_line",
           "instinct_lines", "tier_line"]

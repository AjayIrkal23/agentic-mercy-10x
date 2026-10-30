#!/usr/bin/env python3
"""context-monitor.py: PostToolUse advisory (priority 1). Loop, scope and compaction nudge.

Replaces ECC's ecc-context-monitor.js + ecc-metrics-bridge.js + suggest-compact.js +
lib/transcript-context.js with one state read/modify/write per tool call:

  [loop]     the same tool with identical input LOOP_N times in a row (said once per
             streak; a different call re-arms it).
  [scope]    SCOPE_N distinct files edited this session (said once).
  [context]  real context use from the transcript's last ``message.usage`` (input +
             cache_read + cache_creation), else the statusline bridge
             (state/session-bridge/<sid>.json, fresh within 120 s), at 60 % of the
             window and again every 60k tokens. Main session only, and only when the
             mercy mod does not own compaction (session_notices.mod_active).

State: ``state/<sid>[.<agent_id>].toolring.json`` (subagents keep their own ring).
Output: at most two lines in hookSpecificOutput.additionalContext, else ``{}``. It never
names a slash command. CLAUDE_HOOK_DOCTOR: ``{}``, no writes. Fails open.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))

from lib import platform as plat  # noqa: E402

LOOP_N = 5
SCOPE_N = 20
NUDGE_PCT = 0.60
NUDGE_STEP = 60_000
STANDARD_WINDOW = 200_000
LARGE_WINDOW = 1_000_000
KNOWN_1M = ("claude-opus-5", "claude-fable-5", "claude-mythos-5")
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
BRIDGE_FRESH_S = 120
TAIL_ROWS = 400
RING_CAP = 500
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(sid) -> str:
    return _UNSAFE.sub("_", str(sid))[:120]


def _state_path(sid, agent_id) -> Path:
    suffix = "." + _safe(agent_id) if agent_id else ""
    return plat.state_dir() / f"{_safe(sid)}{suffix}.toolring.json"


def _fingerprint(tool: str, inp: dict) -> str:
    blob = json.dumps(inp, sort_keys=True, default=str)[:20000]
    return tool + ":" + hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


def _edited_paths(tool: str, inp: dict) -> list:
    if tool not in WRITE_TOOLS:
        return []
    out = [inp.get("file_path"), inp.get("notebook_path")]
    out += [e.get("file_path") for e in (inp.get("edits") or []) if isinstance(e, dict)]
    return [p for p in out if isinstance(p, str) and p]


def _mod_active(sid) -> bool:
    try:
        from lib import session_notices
        return bool(getattr(session_notices, "mod_active", lambda s: False)(sid))
    except Exception:  # noqa: BLE001
        return False


def _num(v) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _usage_from_transcript(path):
    """(tokens, model) of the newest assistant row with usage, else None."""
    try:
        from lib import turns
        rows = turns.tail_entries(path, TAIL_ROWS) or []
    except Exception:  # noqa: BLE001
        return None
    for entry in reversed(rows):
        msg = entry.get("message")
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(usage, dict):
            continue
        tokens = sum(_num(usage.get(k)) for k in
                     ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        if tokens > 0:
            return tokens, str(msg.get("model") or "")
    return None


def _usage_from_bridge(sid):
    """context_pct from the statusline bridge when it is fresh, else None."""
    try:
        d = json.loads((plat.state_dir() / "session-bridge" / f"{_safe(sid)}.json").read_text(encoding="utf-8"))
        ts, pct = d.get("ts"), d.get("context_pct")
        if _num(ts) and time.time() - float(ts) <= BRIDGE_FRESH_S and isinstance(pct, (int, float)):
            return float(pct)
    except Exception:  # noqa: BLE001
        pass
    return None


def _settings_auto_compact() -> bool:
    try:
        d = json.loads((plat.claude_dir() / "settings.json").read_text(encoding="utf-8"))
        return _num(d.get("autoCompactWindow")) > STANDARD_WINDOW
    except Exception:  # noqa: BLE001
        return False


def _known_large(model: str) -> bool:
    """ECC's boundary rule: the family must end at a non-alphanumeric that is not '-<letter>'
    (claude-fable-5-1 matches, claude-fable-5-mini does not)."""
    for fam in KNOWN_1M:
        idx = model.find(fam)
        if idx < 0:
            continue
        rest = model[idx + len(fam):]
        if not (rest[:1].isalnum() or re.match(r"^-[A-Za-z]", rest)):
            return True
    return False


def _window(tokens: int, model: str) -> int:
    if _settings_auto_compact() or "[1m]" in model or _known_large(model) or tokens > STANDARD_WINDOW:
        return LARGE_WINDOW
    return STANDARD_WINDOW


def _bucket(used: int, window: int) -> int:
    start = NUDGE_PCT * window
    return -1 if used < start else int((used - start) // NUDGE_STEP)


def _nudge(payload: dict, sid: str, path: Path, st: dict) -> str:
    u = _usage_from_transcript(payload.get("transcript_path"))
    if u:
        used, model = u
        window = _window(used, model)
    else:
        pct = _usage_from_bridge(sid)
        if pct is None:
            return ""
        window = _window(0, "")
        used = int(pct / 100 * window)
    b = _bucket(used, window)
    prev = st.get("nudge_bucket")
    prev = prev if isinstance(prev, int) else -1
    if b < prev:  # usage fell: a compaction ran, so re-arm without nudging
        plat.locked_update(path, lambda d: {**d, "nudge_bucket": b}, default={})
        return ""
    if b == prev:
        return ""
    plat.locked_update(path, lambda d: {**d, "nudge_bucket": b}, default={})
    size = "1M" if window >= LARGE_WINDOW else f"{window // 1000}k"
    return (f"[context] {used // 1000}k/{size} used: finish the current step and let auto-compact run; "
            "do not start new large work in this context.")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "null")
    except ValueError:
        payload = None
    if not isinstance(payload, dict) or os.environ.get("CLAUDE_HOOK_DOCTOR") or not payload.get("session_id"):
        print("{}")
        return 0
    sid, agent = str(payload["session_id"]), payload.get("agent_id") or None
    tool = str(payload.get("tool_name") or "")
    inp = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    fp, edited = _fingerprint(tool, inp), _edited_paths(tool, inp)
    fired = {"loop": False, "scope": False}

    def _update(d: dict) -> dict:
        ring = list(d.get("ring") or [])[-(LOOP_N - 1):] + [fp]
        d["ring"] = ring
        files = list(d.get("files") or [])
        for p in edited:
            if p not in files and len(files) < RING_CAP:
                files.append(p)
        d["files"] = files
        if len(ring) == LOOP_N and len(set(ring)) == 1 and d.get("warned_loop") != fp:
            d["warned_loop"], fired["loop"] = fp, True
        elif len(set(ring)) > 1:
            d.pop("warned_loop", None)
        if len(files) >= SCOPE_N and not d.get("warned_scope"):
            d["warned_scope"], fired["scope"] = True, True
        return d

    path = _state_path(sid, agent)
    st = plat.locked_update(path, _update, default={})
    warnings = []
    if agent is None and not _mod_active(sid):
        line = _nudge(payload, sid, path, st)
        if line:
            warnings.append(line)
    if fired["loop"]:
        warnings.append(f"[loop] `{tool}` called {LOOP_N} times in a row with identical input; stop repeating "
                        "it: change the input, try another approach, or report the blocker.")
    if fired["scope"]:
        warnings.append(f"[scope] {len(st.get('files') or [])} files edited this session; check that every "
                        "change traces to the request before continuing.")
    if not warnings:
        print("{}")
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                             "additionalContext": "\n".join(warnings[:2])}}))
    return 0


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - fail open
        print("{}")
    sys.exit(0)

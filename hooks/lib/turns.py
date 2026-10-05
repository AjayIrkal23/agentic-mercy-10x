"""turns.py — turn-boundary helpers for Stop-time gates.

A "turn" starts at the last real user prompt in the session transcript. Both
Stop gates (hard-completion-gate, invoke-suite-gate) key their once-per-turn
state on it. Moved here from invoke-suite-gate._turn_dt; timestamps are always
returned timezone-AWARE (naive → UTC) so comparisons never raise.

Only the transcript TAIL (last ``TAIL_LINES`` lines) is read — a long session
transcript can be hundreds of MB. Pure stdlib, never raises.
"""
from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

TAIL_LINES = 4000


def to_aware(value) -> Optional[datetime]:
    """ISO-8601 string → aware datetime (naive assumed UTC). None on failure."""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_NOT_HUMAN_PREFIXES = ("<task-notification>", "[Request interrupted", "<cross-session-message")


def _prompt_text(entry: dict) -> Optional[str]:
    """Text of a real (human) user prompt, or None for tool results, meta rows
    (Stop-hook feedback, skill bodies), task notifications and interrupt markers.
    A slash command's non-meta ``<command-name>`` row counts as human."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isCompactSummary"):
        return None
    origin = entry.get("origin")
    if isinstance(origin, dict) and origin.get("kind") == "task-notification":
        return None
    msg = entry.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    text = None
    if isinstance(content, str):
        text = content if content.strip() else None
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        texts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(t for t in texts if t).strip() or None
    if text and text.lstrip().startswith(_NOT_HUMAN_PREFIXES):
        return None
    return text


def last_user_turn(transcript_path) -> Tuple[Optional[datetime], Optional[str]]:
    """(timestamp, text) of the last real user prompt in the transcript tail."""
    if not transcript_path:
        return (None, None)
    try:
        p = Path(str(transcript_path))
        if not p.is_file():
            return (None, None)
        with p.open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=TAIL_LINES)
    except Exception:
        return (None, None)
    for line in reversed(tail):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        text = _prompt_text(entry)
        if text is None:
            continue
        return (to_aware(entry.get("timestamp") or entry.get("ts")), text)
    return (None, None)


def last_user_turn_ts(transcript_path) -> Optional[datetime]:
    """Aware timestamp of the last real user prompt, or None."""
    return last_user_turn(transcript_path)[0]


def turn_key(transcript_path) -> str:
    """Stable per-turn key ("?" when the transcript is unavailable)."""
    dt = last_user_turn_ts(transcript_path)
    return dt.isoformat() if dt else "?"


WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def turn_written_files(transcript_path) -> Optional[list]:
    """File paths written (Write/Edit/MultiEdit/NotebookEdit tool_use) since the last
    real user prompt, in order. None when the transcript is unreadable (callers
    decide how to fail open); [] when the turn wrote nothing."""
    if not transcript_path:
        return None
    try:
        p = Path(str(transcript_path))
        if not p.is_file():
            return None
        with p.open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=TAIL_LINES)
    except Exception:
        return None
    files: list = []
    for line in tail:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        if _prompt_text(entry) is not None:
            files = []          # a new real user turn starts
            continue
        msg = entry.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in WRITE_TOOLS:
                inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                fp = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(fp, str) and fp:
                    files.append(fp)
    return files


def turn_bash_commands(transcript_path) -> list:
    """Bash commands run since the last real user prompt, in order ([] when unknown)."""
    try:
        with Path(str(transcript_path)).open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=TAIL_LINES)
    except Exception:
        return []
    cmds: list = []
    for line in tail:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        if _prompt_text(entry) is not None:
            cmds = []
            continue
        msg = entry.get("message")
        for b in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash":
                cmd = (b.get("input") or {}).get("command") if isinstance(b.get("input"), dict) else None
                if isinstance(cmd, str) and cmd:
                    cmds.append(cmd)
    return cmds


__all__ = ["TAIL_LINES", "WRITE_TOOLS", "to_aware", "last_user_turn", "last_user_turn_ts",
           "turn_key", "turn_written_files", "turn_bash_commands"]

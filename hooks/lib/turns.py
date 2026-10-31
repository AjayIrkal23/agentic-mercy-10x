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
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from tool_compat import is_shell_tool

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


def tail_entries(transcript_path, n: int = TAIL_LINES) -> "list[dict] | None":
    """Parsed dict rows among the last ``n`` lines, oldest first. None when the
    transcript is missing or unreadable; [] when readable but empty. The one
    transcript reader: every scanner here and lib/memory_gate goes through it."""
    if not transcript_path:
        return None
    try:
        p = Path(str(transcript_path))
        if not p.is_file():
            return None
        with p.open(encoding="utf-8", errors="replace") as fh:
            tail = deque(fh, maxlen=max(int(n), 1))
    except Exception:
        return None
    out: list = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def iter_tail(transcript_path, n: int = TAIL_LINES):
    """Generator over ``tail_entries``; yields nothing when unreadable."""
    yield from (tail_entries(transcript_path, n) or [])


_NOT_HUMAN_PREFIXES = ("<task-notification>", "[Request interrupted", "<cross-session-message",
                       "[Subagent hand-back]", "<agent-message from=", "Another Claude session sent a message")
_SYS_REMINDER_OPEN = re.compile(r"\A(?:\s*<system-reminder\b[^>]*>)+")
# a hand-back marker that opens a line / follows a closing tag in the first 400 chars; a human
# sentence quoting it mid-line stays human. Same rule as prompt_router/classify.is_machine_text
# and mods/mercy/hooks/features/prompts.ts.
_NOT_HUMAN_MARKER = re.compile(
    r"(?:\A|\n|>)\s*(?:\[Subagent hand-back\]|<agent-message from=|Another Claude session sent a message)")


def _not_human(text: str) -> bool:
    t = text.lstrip()
    if t.startswith(_NOT_HUMAN_PREFIXES):
        return True
    body = _SYS_REMINDER_OPEN.sub("", t, count=1).lstrip()
    return body.startswith(_NOT_HUMAN_PREFIXES) or bool(_NOT_HUMAN_MARKER.search(body[:400]))


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
    if text and _not_human(text):
        return None
    return text


def last_user_turn(transcript_path) -> Tuple[Optional[datetime], Optional[str]]:
    """(timestamp, text) of the last real user prompt in the transcript tail."""
    for entry in reversed(tail_entries(transcript_path) or []):
        text = _prompt_text(entry)
        if text is None:
            continue
        return (to_aware(entry.get("timestamp") or entry.get("ts")), text)
    return (None, None)


PERMISSION_PHRASES = ("permission rule", "permissions rule", "allow rule", "deny rule", "ask rule",
                      "permissions.allow", "permissions.deny", "permissions.ask")


def prompt_names(transcript_path, names: "tuple[str, ...]", phrases: "tuple[str, ...]" = ()) -> bool:
    """True when the last human turn contains one of `names` (lower-cased substring, exact spelling:
    a basename or a path ending) or one of `phrases`. No stems, no bare words."""
    _, text = last_user_turn(transcript_path)
    t = (text or "").lower()
    # phrases match whole words only: "ask rule" must not hit "task rules", "allow rule" not "shallow rule"
    return bool(t) and (any(n.lower() in t for n in names if n)
                        or any(re.search(r"(?<![\w.])" + re.escape(p) + r"s?\b", t) for p in phrases))


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
    rows = tail_entries(transcript_path)
    if rows is None:
        return None
    files: list = []
    for entry in rows:
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
    cmds: list = []
    for entry in iter_tail(transcript_path):
        if _prompt_text(entry) is not None:
            cmds = []
            continue
        msg = entry.get("message")
        for b in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and is_shell_tool(b.get("name")):
                cmd = (b.get("input") or {}).get("command") if isinstance(b.get("input"), dict) else None
                if isinstance(cmd, str) and cmd:
                    cmds.append(cmd)
    return cmds


def turn_bash_results(transcript_path) -> list:
    """[(command, failed)] for shell tool_use rows since the last real user prompt, each paired
    with its tool_result (``is_error``) by id; no result yet counts as not failed."""
    pending: dict = {}
    out: list = []
    for entry in iter_tail(transcript_path):
        if _prompt_text(entry) is not None:
            pending, out = {}, []
            continue
        msg = entry.get("message")
        for b in (msg.get("content") if isinstance(msg, dict) else None) or []:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and is_shell_tool(b.get("name")):
                cmd = (b.get("input") or {}).get("command") if isinstance(b.get("input"), dict) else None
                if isinstance(cmd, str) and cmd:
                    if b.get("id"):
                        pending[b["id"]] = len(out)
                    out.append([cmd, False])
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                out[pending[b["tool_use_id"]]][1] = bool(b.get("is_error"))
    return [tuple(x) for x in out]


__all__ = ["TAIL_LINES", "WRITE_TOOLS", "to_aware", "tail_entries", "iter_tail", "last_user_turn",
           "PERMISSION_PHRASES", "prompt_names", "last_user_turn_ts", "turn_key", "turn_written_files", "turn_bash_commands",
           "turn_bash_results"]

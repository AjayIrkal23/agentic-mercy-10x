#!/usr/bin/env python3
"""postToolUse: mark Santa Method review complete when code-reviewer Task runs.

Writes {cid}.santa.json with fired=true so hard-completion-gate Gate 4 can pass.
Also detects gsd-code-reviewer and generic code-reviewer subagent types.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"

SANTA_SUBAGENTS = frozenset(
    {
        "santa-reviewer",   # the dedicated Santa Method agent (agents/santa-reviewer.md)
        "code-reviewer",
        "gsd-code-reviewer",
        "thermo-nuclear-code-quality-review",
    }
)


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _save_santa(cid: str, source: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / f"{_safe_cid(cid)}.santa.json"
    path.write_text(
        json.dumps(
            {
                "fired": True,
                "source": source,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        sys.stdout.write("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        sys.stdout.write("{}")
        return 0

    tool_name = (payload.get("tool_name") or payload.get("toolName") or "").strip()
    # Matcher is "Task|Agent"; this harness exposes the subagent tool as "Agent".
    # Accept both so the flag fires regardless of the tool's display name.
    if tool_name not in ("Task", "Agent"):
        sys.stdout.write("{}")
        return 0

    tool_input = payload.get("tool_input") or payload.get("arguments") or {}
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except json.JSONDecodeError:
            tool_input = {}

    subagent = (
        tool_input.get("subagent_type")
        or tool_input.get("subagentType")
        or ""
    ).strip()

    # P4: record EVERY subagent dispatch to the shared telemetry sidecar so
    # invoke-suite-gate.py v2 can pass agent-backed suites on "agent was
    # dispatched this session" instead of nagging about skill loads.
    if subagent:
        try:
            tel = Path(__file__).resolve().parent / ".telemetry"
            tel.mkdir(parents=True, exist_ok=True)
            rec = {"ts": datetime.now(timezone.utc).isoformat(), "agent": subagent}
            with (tel / f"{_safe_cid(cid)}.agent-dispatches.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except Exception:
            pass

    description = (tool_input.get("description") or "").lower()
    prompt = (tool_input.get("prompt") or "").lower()

    if subagent in SANTA_SUBAGENTS:
        _save_santa(cid, f"task:{subagent}")
        sys.stdout.write("{}")
        return 0

    if subagent in ("generalPurpose", "general-purpose", ""):
        combined = f"{description} {prompt}"
        if any(k in combined for k in ("code review", "code-reviewer", "santa", "breaker", "simplifier", "adversarial review")):
            _save_santa(cid, "task:keyword-match")
            sys.stdout.write("{}")
            return 0

    sys.stdout.write("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

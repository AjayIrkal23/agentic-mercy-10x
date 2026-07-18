#!/usr/bin/env python3
"""PostToolUse hook: record every Skill tool invocation for effectiveness telemetry.

Fires when tool_name == "Skill". Appends a JSONL line to:
  ~/.claude/hooks/.telemetry/{safe_cid}.skill-invocations.jsonl

Each line:
  {"ts": "<ISO8601>", "skill": "<slug>", "trigger_path": "<argv or empty>", "write_index": <int>}

write_index is read from the desloppify state file (code_writes counter) to allow
latency measurement: (invocation_write_index - reminder_write_index).

stdin:  Claude Code PostToolUse JSON payload
stdout: {} (no output — pure side effect)
exit:   always 0 (fail open)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR   = Path(__file__).resolve().parent
STATE_DIR  = HOOK_DIR / ".state"
TELEMETRY_DIR = HOOK_DIR / ".telemetry"


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_write_index(safe_cid: str) -> int:
    """Read code_writes from desloppify state — proxy for write index."""
    p = STATE_DIR / f"{safe_cid}.desloppify.json"
    if not p.is_file():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get("code_writes", 0))
    except Exception:
        return 0


def _append_jsonl(path: Path, record: dict) -> None:
    """Atomic append: open in append mode, write line, flush."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        fh.flush()


def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        sys.stdout.write("{}\n")
        return 0

    # Only handle Skill tool calls
    tool_name = (
        payload.get("tool_name")
        or payload.get("toolName")
        or ""
    ).strip()
    if tool_name not in ("Skill", "Read"):
        sys.stdout.write("{}\n")
        return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "").strip()
    if not cid:
        sys.stdout.write("{}\n")
        return 0

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        sys.stdout.write("{}\n")
        return 0

    if tool_name == "Read":
        # a Read of ~/.claude/skills/<slug>/SKILL.md counts as consuming the skill
        import re as _re
        fp = str(tool_input.get("file_path") or "")
        m = _re.search(r"/\.claude/skills/([^/]+)/SKILL\.md$", fp.replace("\\", "/"))
        if not m:
            sys.stdout.write("{}\n")
            return 0
        skill_slug = m.group(1)
    else:
        skill_slug = (tool_input.get("skill") or "").strip()
    if not skill_slug:
        sys.stdout.write("{}\n")
        return 0

    safe = _safe_cid(cid)
    write_index = _read_write_index(safe)

    # trigger_path: argv[1] from the Skill call args, or empty string
    trigger_path = (tool_input.get("args") or "").strip()

    record = {
        "ts":           _now_iso(),
        "skill":        skill_slug,
        "trigger_path": trigger_path,
        "write_index":  write_index,
    }

    try:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        log_path = TELEMETRY_DIR / f"{safe}.skill-invocations.jsonl"
        _append_jsonl(log_path, record)
    except OSError:
        # Fail open — never block on telemetry error
        pass

    sys.stdout.write("{}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

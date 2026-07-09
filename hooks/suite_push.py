"""Shared helper: record skills a hook PUSHED into the turn for the suite gate.

Any skill-injecting hook that tells the agent to invoke skills VIA THE SKILL TOOL
appends its exact slug list here; invoke-suite-gate.py (Stop) diffs the union
against the skill-invocation telemetry and re-nags until each one loaded.

Only use for Skill-TOOL pushes (slugs the agent calls via the Skill tool), NOT for
"read this SKILL.md path" reminders — those never appear in the invocation telemetry.

Sidecar: ~/.claude/hooks/.telemetry/{safe_cid}.pushed-skills.jsonl
  {"ts": iso, "skills": ["slug", "superpowers:slug"], "source": "...", "enforce": "hard"}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

_TEL = Path(__file__).resolve().parent / ".telemetry"


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def push(cid: str, skills, source: str, enforce: str = "hard", meta: dict | None = None) -> None:
    """Append a push record. Never raises (fail-open for the calling hook).

    `meta` (optional, additive): extra record fields — e.g. invoke-suite-manifest
    passes {"categories": [...], "commands": [...]} so invoke-suite-gate v2 can
    run its artifact-or-agent-dispatch check per category. Core keys always win.
    """
    try:
        names = [s for s in dict.fromkeys(skills) if s]  # dedupe, keep order
        if not cid or not names:
            return
        _TEL.mkdir(parents=True, exist_ok=True)
        rec = dict(meta) if isinstance(meta, dict) else {}
        rec.update({
            "ts": datetime.now(timezone.utc).isoformat(),
            "skills": names,
            "source": source,
            "enforce": enforce,
        })
        with (_TEL / f"{_safe_cid(cid)}.pushed-skills.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

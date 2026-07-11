#!/usr/bin/env python3
"""PostToolUse aggregator: one subprocess chain for doc + desloppify + security gates.

Preserves the same reminders as doc-update-enforcer, desloppify-cleanup, and
security-scan-gate — only reduces Python startup overhead.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
# (script, timeout[, args]).  index-lifecycle post-write runs first: it journals
# the touched path (active-repo only) and, at N=5 writes / T=45s, spawns ONE
# detached incremental indexer — interim wiring, re-homed into dispatch.py by
# P4-T7 (see HANDOFF-P4-registrations.md). It emits no additionalContext.
CHAIN: list[tuple] = [
    ("index-lifecycle.py", 8, ["post-write"]),
    ("dox-child-scaffold.py", 6),
    ("doc-update-enforcer.py", 5),
    ("security-scan-gate.py", 5),
    ("jdocmunch-reindex-hook.py", 6),
]


def _merge(existing: str, add: str) -> str:
    add_st = add.strip()
    if not add_st:
        return existing
    if not existing.strip():
        return add_st
    return f"{existing.rstrip()}\n\n{add_st}"


def _run(script: str, payload_txt: str, timeout: int, args=None) -> str:
    cmd = ["python3", str(HOOK_DIR / script)] + list(args or [])
    try:
        proc = subprocess.run(
            cmd,
            input=payload_txt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return ""
        blob = json.loads(proc.stdout)
        if not isinstance(blob, dict):
            return ""
        chunk = blob.get("additionalContext") or blob.get("additional_context")
        if isinstance(chunk, str):
            return chunk
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    return ""


def main() -> int:
    raw = sys.stdin.read()
    payload_txt = raw if raw.strip() else "{}"

    aggregated = ""
    for entry in CHAIN:
        script, timeout = entry[0], entry[1]
        args = entry[2] if len(entry) > 2 else None
        chunk = _run(script, payload_txt, timeout, args)
        if chunk:
            aggregated = _merge(aggregated, chunk)

    if not aggregated.strip():
        print("{}")
        return 0

    out = {
        "additionalContext": aggregated,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

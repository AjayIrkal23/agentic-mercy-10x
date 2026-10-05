#!/usr/bin/env python3
"""teammate-idle-gate.py — TeammateIdle gate (D1, deliberate teams).

A teammate may not go idle while the artifact its run expects is still missing.
Run folders are created by the /invoke skill:
  <cwd>/.claude/runs/<ts>-<slug>/run.json
  {"expected_artifacts": {"<teammate_name>": "<path relative to cwd, or absolute>"}}
The NEWEST run.json that names this teammate is consulted (B2-13: a newer run for
other teammates used to hide it).

Bounded (Santa A3): at most MAX_BLOCKS blocks per (run.json, teammate) — a teammate
that cannot produce its artifact (tool error, abort, bad path) is then allowed to
idle with a systemMessage naming the missing artifact, instead of looping forever.
Counters live in hooks/.state/teammate-idle.json (no writes under CLAUDE_HOOK_DOCTOR).

stdin : {"teammate_name": "...", "cwd": "..."}
stdout: {"decision":"block","reason":"..."} when the artifact is missing (≤ MAX_BLOCKS),
        {"systemMessage": "..."} once the budget is spent, else {}.
dispatch.py turns the block into exit 2 (= the teammate keeps working). Fail-open.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_BLOCKS = 2
STATE_FILE = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR")
                  or Path(__file__).resolve().parent / ".state") / "teammate-idle.json"


def _run_for(cwd: Path, name: str) -> tuple[Path | None, str]:
    """(run.json, artifact) of the NEWEST run that expects ``name``. A newer run for
    other teammates (a concurrent /invoke) no longer hides it (audit B2-13)."""
    try:
        runs = sorted((p for p in (cwd / ".claude" / "runs").glob("*/run.json") if p.is_file()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None, ""
    for rj in runs:
        try:
            expected = json.loads(rj.read_text(encoding="utf-8")).get("expected_artifacts")
        except (OSError, ValueError, AttributeError):
            continue
        art = expected.get(name) if isinstance(expected, dict) else None
        if isinstance(art, str) and art:
            return rj, art
    return None, ""


def missing_artifact(payload: dict) -> tuple[str, str, str] | None:
    """(teammate, artifact, run.json path) when the expected artifact is missing."""
    name = str(payload.get("teammate_name") or "")
    if not name:
        return None
    cwd = Path(payload.get("cwd") or os.getcwd())
    run_path, art = _run_for(cwd, name)
    if run_path is None:
        return None
    # relative to the repo (/invoke's run.json) or to the run folder (team-lead's)
    cands = [Path(art)] if os.path.isabs(art) else [cwd / art, run_path.parent / art]
    return None if any(p.exists() for p in cands) else (name, art, str(run_path))


def _bump(key: str) -> int:
    """Increment and return the block count for ``key`` (fail-open → 1)."""
    try:
        counts = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(counts, dict):
            counts = {}
    except (OSError, ValueError):
        counts = {}
    n = int(counts.get(key, 0)) + 1
    if os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return n
    counts[key] = n
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(counts), encoding="utf-8")
    except OSError:
        pass
    return n


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        hit = missing_artifact(payload if isinstance(payload, dict) else {})
        if hit:
            name, art, run_path = hit
            if _bump(f"{run_path}::{name}") <= MAX_BLOCKS:
                print(json.dumps({"decision": "block",
                                  "reason": f"{name}: write {art} before going idle"}))
            else:
                print(json.dumps({"systemMessage":
                                  f"teammate-idle-gate: {name} went idle without {art} "
                                  f"after {MAX_BLOCKS} blocks — artifact still missing."}))
            return 0
    except Exception:  # noqa: BLE001
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

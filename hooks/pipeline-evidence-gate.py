#!/usr/bin/env python3
"""pipeline-evidence-gate.py — SubagentStop gate: an /invoke act agent proves it ran its pipeline.

Every act agent carries a ``## <act> pipeline (automatic, every task)`` table and writes a
``## Pipeline`` section into its artifact (each call and its result, or ``P<n> skipped: <reason>``).
When such an agent stops inside an /invoke run, this gate finds the fresh run.json it was dispatched
for (``expected_artifacts[<agent_type>]``, and the agent's first prompt, read from
``agent_transcript_path``, names that run folder and the artifact without "never write <artifact>")
and keeps the agent working ONCE when the artifact is missing or has no ``## Pipeline`` heading.
Outside a run, for another run's agent, a workflow helper that writes notes, or an unreadable
transcript, it does nothing.

Bounded: Claude Code's ``stop_hook_active`` ends a second round, and the state file allows one block
per (run.json, agent_id). Counters: ``hooks/.state/pipeline-evidence.json`` (``CLAUDE_HOOK_DOTSTATE_DIR``;
no writes under ``CLAUDE_HOOK_DOCTOR``).

stdin : SubagentStop payload ``{"agent_type", "agent_id", "cwd", "stop_hook_active", ...}``
stdout: ``{"decision": "block", "reason": "..."}`` or ``{}``. Fail-open.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# act agent -> its artifact (names only; the path comes from run.json). Kept in step with the agent
# files by hooks/tests/test_act_pipelines.py.
ACT_AGENTS = {
    "frontend-uiux-designer": "DESIGN-REPORT.md",
    "santa-reviewer": "SANTA-REVIEW.md",
    "security-sentinel": "SECURITY-REPORT.md",
    "qa-verifier": "VERIFY-REPORT.md",
    "test-author": "TEST-REPORT.md",
    "debug-detective": "ROOTCAUSE.md",
    "deadcode-reaper": "REAP-REPORT.md",
    "refactor-specialist": "REFACTOR-REPORT.md",
    "audit-specialist": "AUDIT-{date}.md",
    "docs-sync-agent": "DOCS-SYNC-REPORT.md",
    "spec-architect": "SPEC-{slug}.md",
    "planning-director": "plan-{date}-{slug}.md",
    "implementation-engineer": "IMPL-REPORT.md",
    "backend-implementor-specialist": "IMPL-REPORT-BE.md",
    "frontend-implementor-specialist": "IMPL-REPORT-FE.md",
    "integrator-specialist": "INTEGRATION-REPORT.md",
}
MAX_AGE_S = 12 * 3600          # a run.json older than this is a finished run, not this one
PIPELINE_RX = re.compile(r"^##\s+Pipeline\b", re.M)
STATE_FILE = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR")
                  or Path(__file__).resolve().parent / ".state") / "pipeline-evidence.json"


def _runs_dir(cwd: Path) -> Path | None:
    """The nearest ``.claude/runs`` at or above ``cwd``, never at or above $HOME."""
    home = Path.home().resolve()
    p = cwd.resolve()
    while p != p.parent and p != home:
        d = p / ".claude" / "runs"
        if d.is_dir():
            return d
        p = p.parent
    return None


def _first_prompt(transcript: str) -> str:
    """The text of the first user message in the subagent's own transcript ("" when unreadable)."""
    try:
        with open(transcript, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if n > 200:
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                msg = row.get("message") if isinstance(row, dict) else None
                if not isinstance(msg, dict) or msg.get("role") != "user":
                    continue
                content = msg.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    return "\n".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    except (OSError, TypeError):
        pass
    return ""


def _expected(cwd: Path, agent: str, prompt: str) -> tuple[Path, Path] | None:
    """(run.json, artifact path) of the fresh run THIS agent was dispatched for: its prompt names the run
    folder and the artifact, and does not forbid writing it. A workflow's helper agents of the same type
    (review.js: chunk reviewers and verifiers write notes, "never write SANTA-REVIEW.md yourself") and
    agents of another run or of no run never match (santa review 2026-11-03)."""
    runs = _runs_dir(cwd)
    if runs is None or not prompt:
        return None
    now = time.time()
    try:
        cands = sorted((p for p in runs.glob("*/run.json") if p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for rj in cands:
        try:
            if now - rj.stat().st_mtime > MAX_AGE_S:
                break
            if rj.parent.name not in prompt:
                continue
            art = (json.loads(rj.read_text(encoding="utf-8")).get("expected_artifacts") or {}).get(agent)
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(art, str) and art:
            name = Path(art).name
            if name not in prompt or re.search(rf"never write\W+{re.escape(name)}", prompt, re.I):
                return None
            if os.path.isabs(art):
                return rj, Path(art)
            # /invoke writes the artifact into the run folder; a repo-relative path also counts
            for base in (rj.parent, runs.parent.parent):
                if (base / art).exists():
                    return rj, base / art
            return rj, rj.parent / art
    return None


def _first_block(key: str) -> bool:
    """True the first time ``key`` is seen (fail-open: True)."""
    try:
        seen = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(seen, dict):
            seen = {}
    except (OSError, ValueError):
        seen = {}
    if seen.get(key):
        return False
    if not os.environ.get("CLAUDE_HOOK_DOCTOR"):
        seen[key] = int(time.time())
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(seen), encoding="utf-8")
        except OSError:
            pass
    return True


def decide(payload: dict) -> dict:
    if payload.get("stop_hook_active"):
        return {}
    agent = str(payload.get("agent_type") or "").split(":")[-1]
    if agent not in ACT_AGENTS:
        return {}
    hit = _expected(Path(payload.get("cwd") or os.getcwd()), agent,
                    _first_prompt(str(payload.get("agent_transcript_path") or "")))
    if hit is None:
        return {}
    run_json, art = hit
    if not art.is_file():
        why = f"{art} does not exist yet"
    else:
        try:
            if PIPELINE_RX.search(art.read_text(encoding="utf-8", errors="replace")):
                return {}
        except OSError:
            return {}
        why = f"{art} has no ## Pipeline section"
    if not _first_block(f"{run_json}::{payload.get('agent_id') or agent}"):
        return {}
    return {"decision": "block", "reason": (
        f"{agent}: {why}. Run every step of the pipeline table in your agent file now, then write "
        f"{art.name} with a `## Pipeline` section: one line per step with the exact call and its result, "
        "or `P<n> skipped: <reason>` when a step cannot run here.")}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(decide(payload if isinstance(payload, dict) else {})))
    except Exception:  # noqa: BLE001 - a gate must never brick a subagent
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

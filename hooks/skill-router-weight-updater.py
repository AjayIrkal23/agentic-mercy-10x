#!/usr/bin/env python3
"""
skill-router-weight-updater.py

Reads skill-effectiveness.jsonl telemetry (last 30 sessions) and produces
skill_router_weights.json with adjusted priority weights per skill.

Usage:
  python3 skill-router-weight-updater.py [--min-sessions N] [--dry-run]

Output:
  ~/.claude/hooks/skill_router_weights.json

Weight formula (DSPy-inspired):
  base_weight = 1.0
  ignore_rate = not_invoked_count / reminded_count  (per skill, last 30 sessions)
  weight = max(MIN_WEIGHT, base_weight - (ignore_rate * PENALTY_FACTOR))

  Interpretation:
  - ignore_rate 0.0 (always used when reminded) → weight = 1.0 (no change)
  - ignore_rate 0.5 (used half the time)        → weight = 0.75
  - ignore_rate 0.9 (almost never used)         → weight = 0.55 (floored at MIN_WEIGHT)
  - ignore_rate 1.0 (never used)                → weight = MIN_WEIGHT = 0.5

Safety floors (2026-09-27):
  - BASELINE skills (fullstack-skills-reminder FRONTEND_SKILLS + BACKEND_SKILLS,
    codebase-intel-first, graphify) are never weighted below 1.0 — the reminder
    tells the model to *read* those files, and pre-2026-09-27 telemetry counted
    only Skill-tool calls, so every baseline was punished to 0.5 on exactly the
    prompts it belongs to. Reads now count (tracker `via:read`), but the floor
    stays as the structural guarantee.
  - MIN_WEIGHT = 0.7 elsewhere (never fully suppress a skill)
  - MAX_WEIGHT = 1.5 (high-value skills can be promoted, but not unboundedly)
  - MIN_SESSIONS = 5 (skip weight update for skills with < 5 data points)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

HOOKS_DIR = Path(__file__).resolve().parent
TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or HOOKS_DIR / ".telemetry")
EFFECTIVENESS_FILE = TELEMETRY_DIR / "skill-effectiveness.jsonl"
WEIGHTS_OUTPUT = HOOKS_DIR / "skill_router_weights.json"

MIN_WEIGHT = 0.7
BASELINE_MIN_WEIGHT = 1.0
MAX_WEIGHT = 1.5
PENALTY_FACTOR = 0.5  # how aggressively high ignore_rate reduces weight
SESSIONS_WINDOW = 30  # only look at last N sessions
MIN_SESSIONS = 5      # skip a skill if we have fewer than this many data points

_BASELINE_EXTRA = {"codebase-intel-first", "graphify"}


def baseline_skills() -> set[str]:
    """FRONTEND_SKILLS + BACKEND_SKILLS from fullstack-skills-reminder.py (+ the
    intel baselines). Fail-open to the intel baselines alone if the import fails."""
    names = set(_BASELINE_EXTRA)
    try:
        spec = importlib.util.spec_from_file_location(
            "_fsr_for_weights", HOOKS_DIR / "fullstack-skills-reminder.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        names.update(getattr(mod, "FRONTEND_SKILLS", []) or [])
        names.update(getattr(mod, "BACKEND_SKILLS", []) or [])
    except Exception:  # noqa: BLE001
        pass
    return names


def load_effectiveness(path: Path, window: int) -> list[dict]:
    """Load last `window` sessions from JSONL file."""
    if not path.is_file():
        return []
    sessions = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                sessions.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return sessions[-window:]


def compute_weights(sessions: list[dict], min_sessions: int) -> dict[str, dict]:
    """
    Aggregate reminded/invoked counts per skill and compute adjusted weights.
    Returns: {skill_slug: {"weight": float, "ignore_rate": float, "session_count": int}}
    """
    reminded: dict[str, int] = defaultdict(int)
    invoked: dict[str, int] = defaultdict(int)

    for session in sessions:
        reminded_list = session.get("reminded", [])
        invoked_list = session.get("invoked", [])
        for skill in reminded_list:
            reminded[skill] += 1
        for skill in invoked_list:
            invoked[skill] += 1

    baseline = baseline_skills()
    weights: dict[str, dict] = {}
    for skill, r_count in reminded.items():
        if r_count < min_sessions:
            # Not enough data — use neutral weight
            weights[skill] = {
                "weight": 1.0,
                "ignore_rate": None,
                "session_count": r_count,
                "note": f"skipped_insufficient_data (n={r_count} < min={min_sessions})",
            }
            continue

        inv_count = invoked.get(skill, 0)
        ignore_rate = max(0.0, (r_count - inv_count) / r_count)
        raw_weight = 1.0 - (ignore_rate * PENALTY_FACTOR)
        floor = BASELINE_MIN_WEIGHT if skill in baseline else MIN_WEIGHT
        clamped_weight = round(max(floor, min(MAX_WEIGHT, raw_weight)), 4)

        weights[skill] = {
            "weight": clamped_weight,
            "ignore_rate": round(ignore_rate, 4),
            "reminded_count": r_count,
            "invoked_count": inv_count,
            "session_count": r_count,
        }
        if skill in baseline and raw_weight < BASELINE_MIN_WEIGHT:
            weights[skill]["note"] = "baseline_floor_1.0"

    # Skills invoked but never reminded (direct invocations) get a boost
    for skill in invoked:
        if skill not in weights:
            weights[skill] = {
                "weight": MAX_WEIGHT,
                "ignore_rate": 0.0,
                "reminded_count": 0,
                "invoked_count": invoked[skill],
                "session_count": invoked[skill],
                "note": "direct_invocation_only",
            }

    return weights


def main() -> int:
    parser = argparse.ArgumentParser(description="Update skill router weights from telemetry")
    parser.add_argument("--min-sessions", type=int, default=MIN_SESSIONS)
    parser.add_argument("--dry-run", action="store_true", help="Print weights without writing")
    args = parser.parse_args()

    sessions = load_effectiveness(EFFECTIVENESS_FILE, SESSIONS_WINDOW)
    if not sessions:
        print(
            f"No data in {EFFECTIVENESS_FILE}. "
            "Run at least one session with skill telemetry enabled first.",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded {len(sessions)} sessions from telemetry.", file=sys.stderr)

    weights = compute_weights(sessions, args.min_sessions)

    # Summary output
    sorted_skills = sorted(weights.items(), key=lambda x: x[1].get("ignore_rate") or 0.0, reverse=True)
    print(f"\nTop 5 highest-ignore-rate skills (candidates for manifest review):", file=sys.stderr)
    for skill, info in sorted_skills[:5]:
        ir = info.get("ignore_rate")
        ir_str = f"{ir:.0%}" if ir is not None else "N/A"
        print(f"  {skill}: ignore_rate={ir_str}, weight={info['weight']}", file=sys.stderr)

    print(f"\nTop 5 highest-value skills (keep at top of manifest):", file=sys.stderr)
    for skill, info in sorted(sorted_skills, key=lambda x: x[1]["weight"], reverse=True)[:5]:
        print(f"  {skill}: weight={info['weight']}", file=sys.stderr)

    output = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions_analyzed": len(sessions),
            "window": SESSIONS_WINDOW,
            "formula": "weight = max(floor, 1.0 - (ignore_rate * 0.5)); floor = 1.0 for baseline skills, 0.7 otherwise",
        },
        "weights": {skill: info["weight"] for skill, info in weights.items()},
        "detail": weights,
    }

    if args.dry_run:
        print(json.dumps(output, indent=2))
        return 0

    # The output file is TRACKED: never rewrite it just to move `generated_at`
    # (audit B2-08 / J-04: weekly git churn with frozen input).
    try:
        previous = json.loads(WEIGHTS_OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    if isinstance(previous, dict) and previous.get("detail") == json.loads(json.dumps(weights)):
        print(f"\nUnchanged: {WEIGHTS_OUTPUT} (not rewritten)", file=sys.stderr)
        return 0
    WEIGHTS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_OUTPUT.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWritten: {WEIGHTS_OUTPUT}", file=sys.stderr)
    print(f"Total skills weighted: {len(weights)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

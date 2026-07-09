#!/usr/bin/env python3
"""Skill effectiveness report CLI.

Reads ~/.claude/hooks/.telemetry/skill-effectiveness.jsonl (written by
fullstack-skills-reminder.py stop branch, task 28) and reports:

  skill | reminded_N | invoked_N | ignore_rate%  | verdict

Usage:
  python3 skill-effectiveness-report.py
  python3 skill-effectiveness-report.py --top 10
  python3 skill-effectiveness-report.py --json
  python3 skill-effectiveness-report.py --json --top 5

Flags:
  --top N   Show only the top N skills by ignore_rate (default: all)
  --json    Output machine-readable JSON array instead of table

Verdicts:
  REVIEW-CANDIDATE   ignore_rate > 80%  (reminded constantly, rarely used)
  HIGH-VALUE         ignore_rate < 20%  (reliably invoked when reminded)
  [blank]            40-80% ignore rate (normal range)

Exit codes:
  0  OK (table printed, or no data with message)
  1  File not found / parse error (message on stderr)
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

TELEMETRY_DIR = Path(__file__).resolve().parent / ".telemetry"
EFFECTIVENESS_FILE = TELEMETRY_DIR / "skill-effectiveness.jsonl"

REVIEW_THRESHOLD = 80   # ignore_rate% above this → REVIEW-CANDIDATE
HIGH_VALUE_THRESHOLD = 20  # ignore_rate% below this → HIGH-VALUE


# ── Data loading ──────────────────────────────────────────────────────────────

def load_records() -> list[dict]:
    """Read and parse all JSONL records. Returns list of dicts."""
    if not EFFECTIVENESS_FILE.is_file():
        return []
    records: list[dict] = []
    errors = 0
    try:
        for i, line in enumerate(EFFECTIVENESS_FILE.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                errors += 1
    except OSError as e:
        print(f"Error reading {EFFECTIVENESS_FILE}: {e}", file=sys.stderr)
        sys.exit(1)
    if errors:
        print(f"Warning: {errors} malformed line(s) skipped.", file=sys.stderr)
    return records


# ── Aggregation ───────────────────────────────────────────────────────────────

class SkillStats:
    __slots__ = ("reminded_count", "invoked_count")

    def __init__(self) -> None:
        self.reminded_count = 0
        self.invoked_count  = 0


def aggregate(records: list[dict]) -> dict[str, SkillStats]:
    """Aggregate per-session records into per-skill counts."""
    stats: dict[str, SkillStats] = defaultdict(SkillStats)

    for rec in records:
        reminded = rec.get("reminded") or []
        invoked  = set(rec.get("invoked") or [])

        if not isinstance(reminded, list):
            continue

        for skill in reminded:
            if not isinstance(skill, str) or not skill.strip():
                continue
            slug = skill.strip()
            stats[slug].reminded_count += 1
            if slug in invoked:
                stats[slug].invoked_count += 1

    return dict(stats)


# ── Report rows ───────────────────────────────────────────────────────────────

def build_rows(stats: dict[str, SkillStats]) -> list[dict]:
    """Convert aggregated stats into sortable row dicts."""
    rows: list[dict] = []
    for skill, s in stats.items():
        if s.reminded_count == 0:
            continue
        ignore_rate = round(100.0 * (1.0 - s.invoked_count / s.reminded_count), 1)
        if ignore_rate >= REVIEW_THRESHOLD:
            verdict = "REVIEW-CANDIDATE"
        elif ignore_rate <= HIGH_VALUE_THRESHOLD:
            verdict = "HIGH-VALUE"
        else:
            verdict = ""
        rows.append({
            "skill":          skill,
            "reminded":       s.reminded_count,
            "invoked":        s.invoked_count,
            "ignore_rate":    ignore_rate,
            "verdict":        verdict,
        })
    # Sort: highest ignore_rate first, then alpha by skill name
    rows.sort(key=lambda r: (-r["ignore_rate"], r["skill"]))
    return rows


# ── Formatters ────────────────────────────────────────────────────────────────

def format_table(rows: list[dict], total_sessions: int) -> str:
    """ASCII table with column padding."""
    if not rows:
        return "No skill effectiveness data found."

    # Column headers
    COL_SKILL    = "skill"
    COL_REM      = "reminded_N"
    COL_INV      = "invoked_N"
    COL_IGN      = "ignore_rate%"
    COL_VERDICT  = "verdict"

    # Compute column widths
    w_skill   = max(len(COL_SKILL),   max(len(r["skill"])   for r in rows))
    w_rem     = max(len(COL_REM),     max(len(str(r["reminded"])) for r in rows))
    w_inv     = max(len(COL_INV),     max(len(str(r["invoked"]))  for r in rows))
    w_ign     = max(len(COL_IGN),     max(len(f"{r['ignore_rate']:.1f}") for r in rows))
    w_verdict = max(len(COL_VERDICT), max(len(r["verdict"])  for r in rows))

    sep = (
        f"+-{'-'*w_skill}-+-{'-'*w_rem}-+-{'-'*w_inv}-+-{'-'*w_ign}-+-{'-'*w_verdict}-+"
    )

    def row_line(skill: str, rem: str, inv: str, ign: str, verdict: str) -> str:
        return (
            f"| {skill:<{w_skill}} "
            f"| {rem:>{w_rem}} "
            f"| {inv:>{w_inv}} "
            f"| {ign:>{w_ign}} "
            f"| {verdict:<{w_verdict}} |"
        )

    lines: list[str] = []
    lines.append(f"Skill Effectiveness Report — {total_sessions} session(s) analyzed")
    lines.append(
        f"  REVIEW-CANDIDATE: ignore_rate > {REVIEW_THRESHOLD}%  "
        f"(reminded often, rarely invoked — consider demoting in manifest)"
    )
    lines.append(
        f"  HIGH-VALUE:       ignore_rate < {HIGH_VALUE_THRESHOLD}%  "
        f"(reliably invoked — keep at top of manifest)"
    )
    lines.append("")
    lines.append(sep)
    lines.append(row_line(COL_SKILL, COL_REM, COL_INV, COL_IGN, COL_VERDICT))
    lines.append(sep)

    for r in rows:
        lines.append(row_line(
            r["skill"],
            str(r["reminded"]),
            str(r["invoked"]),
            f"{r['ignore_rate']:.1f}",
            r["verdict"],
        ))

    lines.append(sep)

    # Summary counts
    n_review = sum(1 for r in rows if r["verdict"] == "REVIEW-CANDIDATE")
    n_high   = sum(1 for r in rows if r["verdict"] == "HIGH-VALUE")
    if n_review:
        lines.append(f"\n  {n_review} skill(s) flagged REVIEW-CANDIDATE.")
    if n_high:
        lines.append(f"  {n_high} skill(s) flagged HIGH-VALUE.")

    return "\n".join(lines)


def format_json(rows: list[dict], total_sessions: int) -> str:
    """Machine-readable JSON output."""
    return json.dumps(
        {
            "total_sessions": total_sessions,
            "review_threshold_pct":    REVIEW_THRESHOLD,
            "high_value_threshold_pct": HIGH_VALUE_THRESHOLD,
            "skills": rows,
        },
        indent=2,
        ensure_ascii=False,
    )


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def parse_args() -> tuple[bool, int | None]:
    """Returns (json_mode, top_n_or_None)."""
    args = sys.argv[1:]
    json_mode = "--json" in args
    top_n: int | None = None
    if "--top" in args:
        idx = args.index("--top")
        try:
            top_n = int(args[idx + 1])
        except (IndexError, ValueError):
            print("Error: --top requires a positive integer argument.", file=sys.stderr)
            sys.exit(1)
        if top_n <= 0:
            print("Error: --top N must be a positive integer.", file=sys.stderr)
            sys.exit(1)
    return json_mode, top_n


def main() -> int:
    json_mode, top_n = parse_args()

    records = load_records()
    if not records:
        if json_mode:
            print(json.dumps({"total_sessions": 0, "skills": [], "message": "No data yet."}))
        else:
            print("No skill-effectiveness.jsonl data yet.")
            print(f"  Expected: {EFFECTIVENESS_FILE}")
            print("  Run a few sessions with task 27 + 28 active to generate data.")
        return 0

    total_sessions = len(records)
    stats = aggregate(records)
    rows = build_rows(stats)

    if top_n is not None:
        rows = rows[:top_n]

    if json_mode:
        print(format_json(rows, total_sessions))
    else:
        print(format_table(rows, total_sessions))

    return 0


if __name__ == "__main__":
    sys.exit(main())

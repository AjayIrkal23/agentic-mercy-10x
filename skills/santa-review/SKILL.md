---
name: santa-review
description: "Santa Method adversarial review — BREAKER + SIMPLIFIER + VERIFIER hunt real correctness, data-loss, concurrency and security bugs in a diff, then self-verify every finding. Forks into santa-reviewer (opus). Use after any non-trivial change or before merging."
argument-hint: "[files | commit range | description]"
context: fork
agent: santa-reviewer
model: opus
metadata:
  schema: 1
  category: review
  surfaces: [backend, frontend]
  platforms: [linux, darwin, windows]
  triggers:
    keywords: [santa, breaker, simplifier, adversarial review, adversarial code review, tear apart, break my code, find real bugs, hunt bugs, review the diff, code review, rip apart, stress the diff, catch bugs, lost update, data loss, edge cases]
    intents: [review, verify]
---

# Santa Method review

**Target:** $ARGUMENTS — when empty, review this session's diff: `git diff` (working tree + staged) plus every file written this session. Read the ACTUAL changed files (jcodemunch `get_symbol_source` / `get_file_content`), never the diff text alone.

## The Iron Law

A finding is a FALSE POSITIVE until you can name the exact input, state and execution path that makes it fail. Default to dismissing. Never rubber-stamp; never invent. Three real bugs beat ten maybes.

## Three lenses — run all three, in order

1. **BREAKER** — try HARD to break every changed file. Hunt: boundary / off-by-one, lost updates and silent data loss, concurrency / races / ordering, swallowed errors and partial-failure state, nil / zero-value / type traps, wrong comparison operators, inclusive-vs-exclusive bounds, timezone / encoding assumptions, security sinks, resource / perf cliffs. Each finding = `SEVERITY | file:line | concrete failing scenario | minimal fix`. Clean category → `OK: <why>`.
2. **SIMPLIFIER** — same diff, needless complexity only (not bugs). Conservative: respect surgical fixes, no broad refactors. Each = `file:line | what is complex | simpler alternative | worth it now? YES/NO`.
3. **VERIFIER** — re-check every HIGH / MED BREAKER finding: REAL or FALSE POSITIVE, defaulting to FALSE POSITIVE unless you can state the exact failing execution. Confirm each real one's minimal fix.

## Output

Write `SANTA-REVIEW.md` into the newest `.claude/runs/*/` folder when one exists, otherwise the repo root. Sections: **A. CONFIRMED must-fix** (`SEVERITY | file:line | failing scenario | minimal fix`), **B. Simplifications worth doing now**, **C. Dismissed** (one line each), **Verdict**: `CHANGES REQUESTED` if A is non-empty, else `PASS`.

Return A and the verdict verbatim (plus B when non-empty). Zero confirmed bugs → say so plainly; do not pad. You never edit code — fixes go back to the implementor or the main session.

## Related

- Agent: `agents/santa-reviewer.md` · same agent inside the orchestrator: `/invoke review` · Gate 4 (Santa): `hooks/hard-completion-gate.py`
- Siblings: `code-review-and-quality`, `doubt-driven-development`, `dead-code-and-change-audit`

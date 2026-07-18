---
name: santa-review
description: "ALWAYS invoke after any non-trivial code change, before merging, or whenever you want a diff torn apart for real bugs — the Santa Method: an adversarial BREAKER + SIMPLIFIER + VERIFIER code review that hunts real correctness, data-loss, concurrency, and security bugs in a diff, then self-verifies each finding to kill false positives. Preferred entry points are the santa-reviewer agent and the /santa-review command."
schema: 1
category: review
surfaces:
- backend
- frontend
platforms:
- linux
- darwin
- windows
triggers:
  keywords:
  - santa
  - breaker
  - simplifier
  - adversarial review
  - adversarial code review
  - tear apart
  - break my code
  - find real bugs
  - hunt bugs
  - review the diff
  - code review
  - rip apart
  - stress the diff
  - catch bugs
  - lost update
  - data loss
  - edge cases
  intents:
  - review
  - verify
---

# The Santa Method — adversarial review that catches real bugs

The Santa Method is a three-lens adversarial review. Its whole value is **finding real bugs before they
ship, and refusing to report fake ones.** It was named for how thoroughly it checks the list — twice.

## The Iron Law

**A finding is a FALSE POSITIVE until you can describe the exact input, state, and execution path that makes
it fail.** Default to dismissing. Never rubber-stamp; never invent. Three real bugs beat ten maybes.

## When to run it

- After any non-trivial code change (Phase 6 / Review of the mandatory protocol) — it satisfies stop-gate
  **Gate 4 (Santa)**.
- On demand: **`/santa-review [target]`** (dispatches the `santa-reviewer` agent), or ask to "santa-review",
  "break my code", "tear apart the diff".
- Before merging a branch, or when a subtle concurrency / lost-update / boundary risk is suspected.

## How to run it (pick by size)

**Default — dispatch the specialist agent.** Launch the **`santa-reviewer`** agent (Agent tool,
`subagent_type: "santa-reviewer"`). It runs all three lenses internally, reads the actual changed files, and
returns CONFIRMED must-fix findings (`file:line` + minimal fix) vs DISMISSED. It runs on **Opus** — the
original Santa reviews forced Opus, because the whole point is catching the subtle ones. `/santa-review` is
the one-liner for this.

**Heavy / multi-file — the independent-agent Workflow** (below): separate agents for BREAKER, SIMPLIFIER, and
an independent VERIFIER, so the verification is genuinely independent of the finder. Use when the diff is
large or the stakes are high enough to justify the extra agents.

## The three lenses

1. **BREAKER** (the star) — read every changed file and try HARD to break it. Hunt: boundary/off-by-one,
   lost updates & silent data loss, concurrency/races/ordering, swallowed errors & partial-failure state,
   nil/zero-value/type traps, wrong comparison operators, inclusive-vs-exclusive bounds, timezone/encoding
   assumptions, security sinks, resource/perf cliffs. Cite `file:line`; each finding = `SEVERITY | file:line
   | concrete failing scenario | minimal fix`. Clean category → `OK: <why>`.
2. **SIMPLIFIER** — same diff, needless complexity only (not bugs). Conservative; respect surgical fixes; no
   broad refactors. Each = `file:line | what's complex | simpler alternative | worth it now? YES/NO`.
3. **VERIFIER** — re-check every HIGH/MED BREAKER finding; REAL vs FALSE POSITIVE, default FALSE POSITIVE
   unless you can state the exact failing execution. Confirm each real one's minimal fix.

Output → `SANTA-REVIEW.md`: **A. CONFIRMED must-fix**, **B. Simplifications worth doing now**, **C.
Dismissed (one line each)**, **Verdict** = CHANGES REQUESTED if A non-empty else PASS. The reviewer never
edits code — fixes go through implementation-engineer or the main loop.

## Reusable Workflow template (heavy / independent verification)

Requires the Workflow tool (user must opt into orchestration). Author the diff/context, then:

```js
export const meta = {
  name: 'santa-review',
  description: 'Adversarial BREAKER + SIMPLIFIER review of a diff, each HIGH/MED finding independently verified',
  phases: [{ title: 'Review' }, { title: 'Verify' }],
}
const CONTEXT = args?.context || 'Review the current session diff. List the changed files and read them.'

phase('Review')
const [breaker, simplifier] = await parallel([
  () => agent(`You are a BREAKER doing an adversarial correctness review. Read the ACTUAL changed files
(jcodemunch get_symbol_source / ctx_read) and try HARD to find REAL bugs. ${CONTEXT}
Hunt: boundary/off-by-one, lost-update/data-loss, concurrency/races/ordering, swallowed errors & partial
state, nil/zero-value/type traps, wrong comparison operators, inclusive/exclusive bounds, timezone/encoding,
security sinks, resource/perf cliffs. Return markdown "BREAKER": each finding = SEVERITY(HIGH/MED/LOW) |
file:line | concrete failing scenario | minimal fix. Clean category => "OK: <why>". Be skeptical; do NOT
invent, do NOT rubber-stamp.`, { label: 'breaker', phase: 'Review', model: 'opus' }),
  () => agent(`You are a SIMPLIFIER reviewing the SAME diff for needless complexity (NOT bugs). Read the
actual files. ${CONTEXT} Flag genuine over-engineering with a simpler equivalent. Conservative — respect
surgical fixes, no broad refactors. Return markdown "SIMPLIFIER": file:line | what's complex | simpler
alternative | worth it now? (YES/NO + why).`, { label: 'simplifier', phase: 'Review', model: 'opus' }),
])

phase('Verify')
const verdict = await agent(`You are a VERIFIER. Below are BREAKER and SIMPLIFIER reports on the diff.
Re-read the actual files for each HIGH/MED correctness claim; decide REAL vs FALSE POSITIVE, defaulting to
FALSE POSITIVE unless you can describe the exact failing execution. Give the minimal fix for each REAL one.
BREAKER:\n${breaker}\n\nSIMPLIFIER:\n${simplifier}\n
Return markdown "VERDICT": (A) CONFIRMED must-fix (file:line + minimal fix), (B) DISMISSED (one line each).
Zero confirmed => say so.`, { label: 'verify', phase: 'Verify', model: 'opus' })

return { verdict }
```

## Related

- Agent: `~/.claude/agents/santa-reviewer.md` · Command: `/santa-review`
- Gate: `hooks/hard-completion-gate.py` Gate 4 (Santa) · Flag-writer: `hooks/santa-method-writer.py`
- Sibling skills: [[code-review-and-quality]], [[doubt-driven-development]], [[dead-code-and-change-audit]]

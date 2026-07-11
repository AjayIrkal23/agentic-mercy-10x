---
name: debug-investigation
description: Use when the cause of a bug, regression, crash, or unexpected behavior is unknown and evidence
  is needed before proposing a fix.
disable-model-invocation: false
schema: 1
category: debug
surfaces:
- backend
- frontend
platforms:
- linux
- darwin
- windows
token-cost: 860
triggers:
  keywords:
  - approach
  - behavior
  - break
  - broken/throwing/failing
  - bug
  - bugs
  - builds
  - cause
  - crash
  - debug
  - debugging
  - describes
  - diagnose
  - diagnosis
  - disciplined
  - doesn
  - encounter
  - error
  - evidence
  - expectations
  - fail
  - failures
  - finding
  - fix
  - fixing
  - guessing
  - guides
  - hard
  - hypothesise
  - instrument
  - investigation
  - isolate
  - issue
  - loop
  - match
  - minimise
  - need
  - needed
  - performance
  - proposing
  - rather
  - regression
  - regression-test
  - regressions
  - reports
  - reproduce
  - root
  - root-cause
  - says
  - something
  - systematic
  - tests
  - unexpected
  - unknown
  - user
  paths:
  - .claude/hooks/
  - .claude/rules/
  intents:
  - debug
---
# Debug Investigation

## Overview

This is the debugging shell.

It does not assume frontend and backend both matter. It classifies the failing surface first, then uses the matching domain skills to trace the problem.

## Use When

- The failure source is unclear.
- A regression, crash, or unexpected behavior needs evidence.
- You need root cause before choosing the fix.

## Do Not Use

- Straightforward implementation work.
- Design-first tasks.
- Documentation lookup without an actual failure to investigate.

## Surface Selection Rule

Choose the failing surface first:

- Backend-only: load the mandatory Backend Core Compliance Set before forming hypotheses: `backend-standards-always-follow`, `service-layer-standards`, `backend-api-standards`, `backend-error-handling`, and `backend-performance-standards`. Preserve `api-contract-standards` for envelope/contract work and `scaffold-standards` for domain or skeleton creation.
- Frontend-only: select and load the matching Build Web Apps plugin skill when available, then load the mandatory Frontend Core Compliance Set: `build-web-apps:frontend-app-builder` for visual-surface failures or `build-web-apps:react-best-practices` for React/Vite/UI/code failures, plus `frontend-standards-always-follow`, `frontend-structure-standards`, `frontend-response-handling`, `frontend-server-data-patterns`, `frontend-api-standards`, and `react-hooks-patterns`.
- Cross-surface: load the matching Build Web Apps plugin plus Frontend Core Compliance Set and Backend Core Compliance Set, then narrow to the actual failing handoff.

Use `project-reference-linkage` when tracing linked layers.
Use `mcp-usage-standards` when repo, DB, logs, or external system truth must be verified.

## Workflow

### Phase 1 — Reproduce
1. Confirm the bug is reproducible in a minimal isolated case.
2. Write a failing test or script that demonstrates the defect before touching any source code.
3. Record the exact input, environment, and output that causes the failure.
4. Verify the reproduction is deterministic (fails every time, not flakily).

### Phase 2 — Minimise
1. Strip the reproduction case to the smallest set of files, inputs, and dependencies.
2. Remove unrelated code paths, environment noise, and network dependencies.
3. If the minimal case no longer fails, add back pieces until it fails again — that is the root cause scope.

### Phase 3 — Hypothesise
1. List all plausible root causes (do not commit to one yet).
2. Order by likelihood based on evidence: recent changes, error messages, stack traces, logs.
3. For each hypothesis, define a concrete observable that would confirm or refute it.
4. Do not fix anything yet — hypothesis must precede instrumentation.

### Phase 4 — Instrument
1. Add targeted logging or assertions to the narrowed scope — no broad logging.
2. Run the minimal reproduction case with instrumentation.
3. Observe which hypothesis the evidence supports.
4. If no hypothesis is confirmed, add one more instrument and repeat from Phase 3.
5. Once root cause confirmed: implement the fix in the narrowest scope possible, run the reproduction test (it must now pass), then run the full test suite.

## Output Contract

- Failure summary.
- Touched surfaces and trace path.
- Evidence-backed root cause or smallest suspect area.
- Minimal safe fix.
- Verification steps.

## References

- Use `references/full-guide.md` if you need the previous full strict guide.

# /workflow-audit — phase table for PROGRESS.md

Loaded by `skills/workflow-audit/SKILL.md` section 1 step 4 and section 9. Copy it into
`$AUDIT/PROGRESS.md` before starting.

| Phase | Done when |
|---|---|
| 0 Setup + baseline | snapshots taken, env facts, memory, doctrine read, enforcement matrix started, sandbox ready, all checks in 2.5 run with outputs saved, inventory computed |
| 1 Static audit | reports A–J written; every file in scope read or listed as skipped with a reason |
| 2 Live runs (before) | S1–S9 run (or the reason one could not), a timeline and lifecycle score each |
| 3 Analysis | enforcement matrix complete, scorecards, findings with evidence/fix/owner/test, top 15 adversarially checked, PLAN.md written |
| 4 Implement | every planned `~/.claude` item applied test-first or recorded as blocked with the reason; dead-code, semgrep and Santa done |
| 5 Verify | baseline green again, affected scenarios re-run, before/after table, project proven untouched |
| 6 Report + hand-off | AUDIT-REPORT.md and findings.json written; page or path given; "needs the user" asked |

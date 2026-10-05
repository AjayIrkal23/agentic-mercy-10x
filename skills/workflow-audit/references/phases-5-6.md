# /workflow-audit — Phase 5 (verify after) and Phase 6 (report and hand-off)

Loaded by `skills/workflow-audit/SKILL.md` sections 7–8. Section numbers kept.

## 7. Phase 5 — verify after, compare with before

1. Run the whole baseline from 2.5 again; everything that passed at the start still
   passes, the doctor shows 0 FAIL, and every new test passes.
2. Re-run the live scenarios your changes affect (at least S1, S3 and S7, plus every
   scenario a change targeted) in a fresh disposable copy. New sessions load the new
   hooks and settings; the mod loads only where the rollout switch is on (record it).
3. Before/after table per scenario: turns, wall time, cost, blocking hook ms, injected
   context characters, wasted turns, lifecycle phases that became automatic.
4. Prove the project is untouched: `git -C "$PROJECT" status --short` and `rev-parse
   HEAD` equal the start snapshot (or the file listing matches for a folder outside
   git). Any difference is a HIGH finding against this audit: explain and undo it.
5. List every `~/.claude` file you changed: `git -C ~/.claude status --short` against
   `$AUDIT/raw/claude-status-start.txt`; the user's own pre-existing changes are not
   yours and stay as they were.
6. Run the `find -newer` check from 2.4.

Checkpoint PROGRESS.md.

## 8. Phase 6 — report and hand-off

Write `$AUDIT/AUDIT-REPORT.md`:

1. Header: date, Ubuntu version, Claude Code version, project, whether the mod loaded
   in this session, rollout switch value.
2. Executive summary: at most 10 bullets, then the area scorecard table, before and
   after.
3. Baseline results: each check from 2.5 with pass/fail at the start and at the end.
4. Inventory: computed counts and drift against the docs.
5. Enforcement matrix.
6. Areas A–J: what it does (short), findings table, value/cost tables (links,
   plugins, MCP servers).
7. Router precision results (30-prompt table, metrics, session repetition count).
8. Live runs S1–S9: timelines (condensed), the lifecycle scorecard per run, and the
   before/after table from section 7.
9. Full-stack autonomy scorecard.
10. Changes made: one row per item (finding ids, files, tests, checks, measured
    gain), plus the Santa and dead-code results.
11. Needs the user: removals and gate loosening (rule 3), fixes that belong inside
    the project, anything you could not verify and why.
12. Open questions.

Also write `$AUDIT/findings.json` (array of {id, area, severity, status, title,
evidence, fix, owner, effort, test, applied}) for later automation. If the Artifact
tool is available, publish the report as a private page and give the link; otherwise
give the file path.

In chat, finish with: what changed in `~/.claude` (short list), the measured
before/after gains, the "needs the user" list as one question, and whether to commit.
Commit only when the user says so.

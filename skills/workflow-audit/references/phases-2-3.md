# /workflow-audit — Phase 2 (live e2e runs) and Phase 3 (analysis)

Loaded by `skills/workflow-audit/SKILL.md` sections 4–5. Section numbers kept.

## 4. Phase 2 — live end-to-end runs in a disposable copy

1. Copy: `git clone --local --no-hardlinks "$PROJECT" "$SCRATCH/e2e-$SLUG"` (copy the
   folder with `cp -a` when it is not a git repo, leaving out `node_modules`, `.venv`,
   build output). Never run a scenario in the original. Install dependencies only
   inside the copy and only when the project's tests need them and it takes under five
   minutes; otherwise use a tiny scratch repo with the same stack markers and say so.
2. Run each scenario from the copy:
   `claude -p --model <the user's usual model> --max-turns 25 --output-format
   stream-json --verbose "<natural prompt>" < /dev/null > $AUDIT/e2e/S<n>.jsonl`.
   Prompts are plain requests; never mention skills, hooks, mods, gates or tools.
   Adapt each to the stack:
   - S1 backend: add a small endpoint or function with a test.
   - S2 frontend: a small component or UI change with a test.
   - S3 debug: break one small thing in the copy first, then ask "this test fails,
     fix it".
   - S4 refactor: rename or extract across two or three files.
   - S5 docs: update the README or docs for a recent change.
   - S6 security-sensitive: add input validation to an endpoint.
   - S7 server temptation: "start the app and check that the page loads" (expect the
     guard to deny the server and the model to fall back to build, test or lint).
   - S8 delegation: a task large enough for planning or subagents (cap the turns).
   - S9 multi-prompt session: three consecutive prompts in one session (stream-json
     input, or `--resume <session id>`) to observe the governor, memory and brain.
3. For each run build a timeline in `$AUDIT/e2e/S<n>.md` from three sources: the
   stream (tool calls, results, denials, Stop blocks); the transcript
   `~/.claude/projects/<mangled copy path>/<session id>.jsonl` (`hook_success`,
   `hook_additional_context`, `stop_hook_summary` entries); and telemetry rows for the
   session id in `~/.claude/telemetry/hook-fires-<date>.jsonl`. Columns: step · event
   · what fired (link id or mod feature) · who ran it (Python chain synchronously, mod
   in the background via `--only`, mod in-process) · ms · output characters · effect
   on the model (did it change what happened next?). Record whether the mod loaded
   (are `mcp__mercy__*` tools in the init event?).
4. Score each run against `rules/02-lifecycle.md` phases 0–7: orient (jcodemunch or
   graphify first?), plan (for more than two files), TDD (test first? when did the
   tdd-guard advice arrive?), surface skills (FE/BE skills loaded?), dead-code audit,
   lint, typecheck, test, build, security scan, review (Santa for 3+ files), docs.
   Mark each phase automatic / prompted by a hook / skipped / misrouted. Count wasted
   turns (gate loops, stale advisories, misroutes), wall time, cost, injected context
   characters.
5. Failure modes, from code reading and the sandbox only (never stop real services):
   an MCP server down (do router lines and hints stop?), the mod off (compare a run
   that started with the switch off, if any: every link should run in the Python
   chain), a link timeout (run the sandboxed dispatcher with a tiny `timeout_ms`), a
   crashing link (does the dispatcher fail open and does link-doctor notice?).

Checkpoint PROGRESS.md.

## 5. Phase 3 — analysis (sequential-thinking first)

1. Finish the enforcement matrix: every rule → mechanism → verified in phases 1–2? →
   gap.
2. Score every area 0–5 on: correctness, robustness (fails open, no races, sane
   timeouts), autonomy (fires without the user), precision (right skill, agent and MCP
   at the right moment), performance (critical-path ms, extra turns), context economy
   (tokens per turn), maintainability (single source of truth, generated files in
   sync, tests), observability, Ubuntu reliability.
3. Full-stack autonomy scorecard for this project: for one typical feature request,
   does the system on its own detect the stack, load the right FE/BE skills, plan,
   write a failing test, implement, run lint, typecheck, tests and build, scan for
   security, review, update docs and report with evidence? Score each step and name
   the mechanism or the gap.
4. Every finding gets: id, area, severity, evidence, impact (who, when, how often),
   minimal fix, owner layer (Python hook, mod, router data, skill, rule, agent,
   installer, docs), effort S/M/L, risk, and the test that would prove the fix.
5. Improvement design. Look specifically for:
   - critical-path work that can move into the mod's background lanes or behind a
     predicate;
   - links with near-zero value to retire or merge, unwired code to remove (these are
     removals: they wait for the user, rule 3);
   - router precision: scoring bugs, keyword hygiene, weight provenance, enforcement
     of misroutes, session awareness;
   - skills: stale references, contradictions, gaps for the stack, listing noise,
     core-skill injection;
   - lifecycle phases that depend only on the model remembering, and the cheapest
     reliable trigger for each (hook, mod feature, gate, skill);
   - verification per stack: is this project's verify command known (mod brain,
     package scripts)? are lint, typecheck, test and build all covered?
   - autonomy: checkpoints, auto-resume, subagent resume, compaction handling,
     long-task continuity;
   - context economy: always-on doctrine, router output, SessionStart, preloads, MCP
     tool listings;
   - robustness: fail-open everywhere, race-free state, hermetic tests, doctor rows
     that cannot pass while broken;
   - security: secret handling, dangerous-command coverage, public-repo hygiene.
6. Adversarial verification: give the 15 most important findings to the
   `santa-reviewer` agent (read-only, with the evidence) and ask it to refute each.
   Keep what survives as CONFIRMED; move the rest to PLAUSIBLE with its objection.
7. Implementation plan in `$AUDIT/PLAN.md`: every CONFIRMED finding whose fix lives in
   `~/.claude`, ordered HIGH first, then MED quick wins, then larger MED, then LOW
   drift. Each item: finding ids, exact `~/.claude` files, the failing test to write
   first, the checks that must pass after, expected gain. Put removals and gate
   loosening in a separate "needs the user" list (rule 3). A fix that would need a
   change inside the project is not yours to make: write it down for the user.

Checkpoint PROGRESS.md.

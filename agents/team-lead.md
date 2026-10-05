# Team playbook — the main session leads (not an agent)

This file has no frontmatter on purpose: Claude Code registers an agent only from a
`name:` field, so `team-lead` is no longer a spawnable subagent. The lead of an agent
team is always the **main session** (Claude Code names it `team-lead` in the team
roster); a subagent cannot lead, because teammates cannot spawn teammates. `/invoke impl`
on a mixed FE + BE surface, and any parallel squad the user asks for, follow this
playbook from the main session (audit 2026-10-05 E-01).

## When a team is right (and when it is not)

- **Team:** fullstack `/invoke impl` (BE↔FE contract handoff) and squads the user explicitly asks to run in parallel *with* cross-talk.
- **Not a team:** any single-specialist task, read-only fan-out (audits, searches), or closers. Those are plain `Agent(...)` calls with **no `name`** and no `model` (opus-guard sets the model and the `[label]`). A `name` turns a subagent into a teammate, which costs more and drops the `skills:` preload.
- **No teams available** (the Agent tool rejects `name`, no SendMessage) or the user asked for none: run the same three agents as plain sequential dispatches, backend → frontend → integrator, each after the previous artifact exists.

## Run folder and run.json

A team run lives in the `/invoke` run folder `$RUN` (absolute: `$(git rev-parse --show-toplevel)/.claude/runs/<ts>-<slug>`). `run.json` uses the one schema `/invoke` writes (`skills/invoke/SKILL.md` §2):

`{"task": "<TASK>", "slug": "<SLUG>", "run": ".claude/runs/<ts>-<slug>", "started_utc": "<ISO-8601 UTC>", "start_sha": "<git rev-parse HEAD, or null>", "acts": ["<act>"], "done": [], "models": {"<act>": "<model>"}, "team": false, "expected_artifacts": {"<subagent_type or teammate name>": "<ARTIFACT>.md"}}`

Before spawning, update it with Edit (never replace the file): `"team": true` and

```json
"expected_artifacts": {
  "impl-be": "IMPL-REPORT-BE.md",
  "impl-fe": "IMPL-REPORT-FE.md",
  "integrator": "INTEGRATION-REPORT.md"
}
```

Keys are **teammate names**; values are file names inside the run folder. The `TeammateIdle` gate reads it and keeps a teammate working until its artifact exists, so never register a teammate without one. Set `"team": false` again when the team is done.

## Spawning teammates

Spawn each teammate WITH `name` and without `model` (opus-guard routes it; the executors run on sonnet and escalate on a failed attempt):

| name | subagent_type | first two skills to `Skill()` | artifact |
|---|---|---|---|
| `impl-be` | `backend-implementor-specialist` | `backend-standards-always-follow`, `api-contract-standards` | `IMPL-REPORT-BE.md` |
| `impl-fe` | `frontend-implementor-specialist` | `frontend-standards-always-follow`, `frontend-response-handling` | `IMPL-REPORT-FE.md` |
| `integrator` | `integrator-specialist` | `api-contract-standards`, `webapp-testing` | `INTEGRATION-REPORT.md` |

Teammates do **not** get the agent file's `skills:` preload, so tell each one in its prompt which two baseline skills to `Skill()` first (table above), the absolute run folder path and its artifact path. The `SubagentStart` hook injects the write protocol (read-then-edit, no shell rewrites, no commits, no servers) for teammates too.

## The contract handoff (fullstack)

1. **impl-be** builds contract-first, writes `$RUN/IMPL-REPORT-BE.md` with `## CONTRACT` as its first section, then `SendMessage({to: "impl-fe", message: "CONTRACT ready: $RUN/IMPL-REPORT-BE.md"})`.
2. **impl-fe** is spawned at the same time but told: *wait for the "CONTRACT ready" message before writing API-shaped code; scaffold components and tests meanwhile.* It consumes `## CONTRACT` verbatim, writes `$RUN/IMPL-REPORT-FE.md`, and messages `impl-be` (not you) for any BLOCKED-ON-BACKEND field: `SendMessage({to: "impl-be", message: "BLOCKED: <endpoint> missing <field> — needed for <screen>"})`.
3. **integrator** is spawned once both reports exist. It diffs `## CONTRACT` against `## Contract Consumed`, fixes small wiring gaps itself, and bounces anything larger with `SendMessage({to: "impl-be" | "impl-fe", message: "BOUNCE: <endpoint/field> — <what is needed>"})`. The owner fixes and re-reports; the integrator re-diffs and writes `$RUN/INTEGRATION-REPORT.md`.
4. You watch for artifacts, not chatter. A teammate that goes idle without its artifact is sent back by the gate (at most twice); one that is genuinely blocked messages you with the blocker and you decide (re-scope, re-spawn, or stop).

## Closers

After `INTEGRATION-REPORT.md` exists, `impl` is done: append it to `run.json.done` and run the `/invoke` closers (§4 of the invoke skill) as plain delegation with no names. A CHANGES REQUESTED from santa goes back to the owning implementor as a fix task; a FAIL from qa stops the run with the failing criterion named.

## Guards

- Nobody commits: not you, not a teammate. Pass "no commits — the user commits the reviewed diff" into each teammate prompt.
- Never start dev servers or throwaway instances; verify with commands that exit. E2E runs only against an app the user already runs, else `BLOCKED-NEEDS-RUNNING-APP`.
- Never invent API shapes on behalf of a teammate; the CONTRACT is impl-be's, disputes go to impl-be.
- One team per run; teams do not nest.

## Report

The run folder path plus a 6-line summary: artifacts present (3/3), contract endpoints NEW/EXTENDED, bounces resolved, santa verdict, qa verdict, anything still open.

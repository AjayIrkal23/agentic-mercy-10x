---
name: dynamic-workflow-mode
description: "Decide between an inline Workflow script, a task-local harness and a saved workflow in ~/.claude/workflows/; harness template, eval gates, and the rule for promoting a repeated harness into workflows/src + build_workflows.py. Use when building a custom harness, adding eval gates, or extracting a reusable workflow from ad-hoc multi-agent work."
metadata:
  schema: 1
  origin: ECC
  category: orchestration
  surfaces: [claude-infra]
  platforms: [linux, darwin, windows]
  triggers:
    keywords: [dynamic workflow, dynamic workflows, custom harness, task-local harness, harness per task, eval gate, eval gates, workflow harness, adaptive workflow, extract a workflow, promote to a saved workflow, reusable harness]
    intents: [plan, impl]
---

# Dynamic workflow mode

A harness is worth writing only when it is cheaper and safer than driving the same steps by hand. This
skill picks the right shape (inline, task-local harness, saved workflow) and keeps every harness honest:
a stated objective, a real eval, and a handoff the next session can resume from.

## Decision tree

1. **One-shot task**: keep it inline (plain tool calls or one `Agent`). No harness.
2. **Multi-phase or fan-out work, once**: an inline `Workflow` script (`script` argument). It persists
   under the session directory; iterate with `scriptPath`. Never write it into `workflows/`.
3. **Repeated work with changing inputs**: a task-local harness: the inline script plus a run folder
   (`.claude/runs/<utc-ts>-<slug>/`) holding its artifacts and `run.json`.
4. **Repeated across sessions or repos**: promote it into the saved library (see Promotion below).
5. **External state, approvals or safety risk**: add an eval gate and a human merge gate before any
   autonomous step; commits happen only when the user asks.

Before writing a new harness, check the saved library first: `invoke`, `invoke-fullstack`, `review`,
`audit`, `research`, `migrate`, `build` (`~/.claude/workflows/index.json`). The router names one with a
`WORKFLOW:` line when it fits.

## Harness template

Fill this in before writing code:

```markdown
# Harness: <name>

Objective:
- Ship:
- Do not ship:

Inputs:
- Repo or workspace:
- External systems:
- Credentials policy: (never in args, never in artifacts)

Loop:
1. Discover the current state.
2. Produce the smallest useful artifact.
3. Run the eval.
4. Record status and handoff in the run folder.
5. Stop on a failed gate, unclear ownership or an unsafe external action.

Eval:
- Command:
- Expected pass signal:
- Failure owner:

Handoff:
- Status:
- Evidence (artifact paths):
- Next action / resume command:
```

## Eval gates

Every harness needs a task-specific eval; "it ran" is not one. Pick the cheapest reliable gate:

| Work type | Eval gate |
| --- | --- |
| Code feature | focused test, lint, one integration path (commands that exit; never start servers) |
| UI change | reticle or playwright check against the app the user already runs, plus a screenshot |
| Agent workflow | stub run with a seeded scenario and expected routing (`tests/fixtures/workflows/stub.mjs`) |
| Research / content | claim checklist with a source per claim |
| Integration | dry-run command, config validation, no-secret scan |

A harness is not reusable until another session can rerun its eval.

## Workbench rules for every script

- No `Date.now()`, `Math.random()`, `new Date()` or `import()`; the caller passes the run folder (its
  name carries the date).
- Null-check every `agent()` result (`ok(x)` or `.filter(Boolean)`); a dead agent is logged and
  reported (`dead`, `incomplete`), never silently dropped.
- Big text goes to files in the run folder; structured replies stay under ~2 KB.
- Every `agent()` passes `agentType` and `model` side by side; executors take their escalated model
  through `up({...}, '<model>')` when `args.tier_hint === 'escalate'`; judges never move.
- Default to `pipeline()`; a `parallel()` barrier only when the next stage needs every result.

## Promotion into the saved library

Promote a harness that repeats when two of these hold: it recurs across sessions or repos; it needs
specific safety sequencing; it has a stable input/output contract; operators keep skipping one of its
gates. Then:

1. Write `workflows/src/<name>.js.tpl` with `{{model:<role>}}` / `{{model:<role>:up}}` tokens (roles
   from `hooks/model-policy.json` `tiers.<tier>.roles`).
2. Add the `index.src.json` entry (`triggers`, `acts`, `min_size`, `args_schema`).
3. Add a stub scenario under `tests/fixtures/workflows/scenarios/` and a stub test.
4. Run `python3 scripts/build_workflows.py` (then `--check`); the router can name it from then on.

A one-off harness stays an inline script.

## Anti-patterns

- Scripts that hide the real decision logic from the operator.
- Treating a workflow as permission to skip tests or gates.
- One-off docs where a run-folder artifact or a saved workflow is the real product.
- Parallel agents with no ownership, merge gate or conflict policy (use `isolation: 'worktree'` only
  when parallel agents edit the same files).
- Private data (paths, hosts, credentials) in tracked scripts or docs.

## Output standard

Finish with the script or template path, the eval commands and their results, the run-folder handoff
path, and the next extraction candidate. More: `docs/WORKFLOWS.md`.

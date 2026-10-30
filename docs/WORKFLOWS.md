# Workflows

How the workbench runs multi-phase work as `Workflow` scripts: which jobs go to a saved script, what
each script does, how its model literals follow the plan tier, and what other components read from it.
Source: MERGE-PLAN R3.2. Directory rules: [`workflows/CLAUDE.md`](../workflows/CLAUDE.md).

## 1. What runs as a workflow

The prompt router (`hooks/prompt_router/modules/workflow_routes.py`) reads `workflows/index.json` and
adds one `WORKFLOW:` line naming a saved script and its args when a rule fires:

| Rule | Script |
|---|---|
| 2 or more `/invoke` acts, or a size-L act with no corpus trigger (next rows) | `invoke` |
| REVIEW intent over 3+ named or changed files | `review` |
| a trigger keyword + a named corpus (path, URL, "this repo") + size ≥ `min_size`; beats a single-act size-L `invoke`, never a multi-act one | `audit`, `research`, `migrate`, `build` |
| anything else | inline (plain tool calls, `Agent`, or an inline `Workflow` script) |

`invoke-fullstack` has no triggers: it runs only when asked by name. Web-only research stays with the
bundled `/deep-research` (the research trigger needs a named corpus). `ultracode` is not on by default
because of the 5-hour usage window; the keyword still works when typed.

## 2. The seven scripts

Models are the max20 render (`workflows/.rendered.json`); other tiers differ (section 3).

| Script | Phases (model) | Args | Returns |
|---|---|---|---|
| `invoke` | Brief (haiku), Acts (opus), Closers (opus), Verify (haiku) | `acts, task, run, slug, brief?, surface?, size?, security_paths?` | `run, acts, done, failed, closers, checkpoints, artifacts, verdicts, incomplete` |
| `invoke-fullstack` | Spec, Plan (opus), Backend, Frontend, Integrate (sonnet), Close (opus), Verify (haiku) | `task, run, slug, brief?` | `run, spec, plan, be, fe, integ, santa, security, docs, qa, dead, incomplete` |
| `review` | Review, Verify (opus), Report (haiku) | `run?, base?, paths?, diff?, language?, security?` | `verdict, incomplete, failedDimensions, blocking, advisory, stats, report` |
| `audit` | Slices (haiku), Map (opus) | `run, root?, surfaces?, task?, corpus?` | `run, slices, dead, map, incomplete` |
| `research` | Read (haiku), Synthesis (opus) | `run, question?, sources?, url?, task?, corpus?` | `run, slices, dead, map, incomplete` |
| `migrate` | Inventory (haiku), Dispositions, Packages, Critic, Revision (opus) | `run, source?, target?, surfaces?, task?, corpus?` | `run, inventory, dispositions, packages, critic, revised, dead, incomplete` |
| `build` | Packages, Integrate (sonnet), Review, Judge (opus), Verify (haiku) | `packages_file, run, worktree, notes?, waves?, max_parallel?` | `run, packages, integrate, review_findings, review_uncovered, review_verify, judge, final_verify, dead, incomplete` |

`invoke` is the one engine for the ECC `orch-*` operations; each is an act list:

| ECC operation | `invoke` args |
|---|---|
| add a feature | `acts: [spec, plan, impl]` |
| build an MVP | `acts: [spec, plan, impl], size: L` |
| change a feature | `acts: [plan, impl], surface: <frontend/backend/mixed>` |
| fix a defect | `acts: [debug, test, impl]` |
| refine code | `acts: [refactor]` |
| implement a design doc / plan | `acts: [spec, plan, impl], brief: <path>` |

`size` S/M/L/XL: L and XL raise the verifier's effort; XL adds a second review pass over the first
review's blocking list. The ECC human gates after spec and plan become typed `checkpoints[]` in the
result (no stop: the router already decided to run). Security-sensitive changes (an agent reports
`touched_security`, or `security_paths` is non-empty) add the security closer. `surface: mixed` runs
backend → frontend → integrator in sequence: a workflow agent cannot lead a team.

`review` runs BREAKER and SIMPLIFIER (Santa lenses), a language reviewer when `language` maps to an ECC
checklist under `~/.claude/library/ecc/agents/`, and a security reviewer when `security` is true or the
ECC security trigger matches the diff/paths, all in parallel. Findings are deduped (same file and the
same evidence, or line ±2 across different dimensions; two findings of one dimension stay separate);
each record keeps every merged claim in `members[]`. Simplifier findings are capped at MEDIUM. Every
CRITICAL/HIGH then meets an adversarial verifier that must refute it with confidence ≥ 0.8 (a merged
record only when every claim is false); anything less keeps it blocking. A dead
dimension makes the verdict `CHANGES_REQUESTED` with `incomplete: true` (fail closed). `paths` are
chunked (at most 6 per reviewer, at most 8 chunks per dimension), so each dimension runs one job per
chunk (`review:<dimension>:<n>`; `stats.jobs` counts them); a pasted `diff` is reviewed whole.
`build` bounds its review the same way: one santa per 6 `owned_paths`, at most 8 per package (the
chunk grows past 48 paths), and it logs the planned fan-out. With a run folder every parallel reviewer
and verifier writes its own `<run>/notes/<label>.md` (`:` replaced, for Windows); only the single
report agent writes `SANTA-REVIEW.md`.

## 3. Models

Templates carry `{{model:<role>}}` and `{{model:<role>:up}}` tokens; `scripts/build_workflows.py`
replaces them with `hooks/model-policy.json` `tiers.<tier>.roles` / `.escalate` literals:

| role | pro | max5 / api | max20 | `:up` pro / max5 / max20 |
|---|---|---|---|---|
| judge | sonnet | sonnet | opus | unchanged |
| impl, integrate, security | haiku | sonnet | sonnet | sonnet / sonnet / opus |
| test | haiku | sonnet | sonnet | sonnet / sonnet / sonnet |
| verify, explore, docs | haiku | haiku | haiku | unchanged |

No render ever holds `fable` (Fable needs the user's own phrase that turn; the guards handle that).
`args.tier_hint = "escalate"` (router or `workflow-model-guard`) makes each script use its `:up`
literal for executor roles through `up({...}, '<model>')`. With the usage guard active, every literal
steps down one model and is clamped to `tiers.<tier>.usage_guard`.

`workflows/.rendered.json` records `{schema, tier, usage_guard, policy_sha, content_sha}`. It is
deterministic (no timestamp), so a re-render of the recorded tier, or a usage-guard flip and flip-back,
rewrites nothing. The render (`*.js`, `index.json`, `.rendered.json`) is per machine and gitignored (FIX-r3
I10); doctor row `workflows-rendered` FAILs when it is missing or drifted and self-heal rebuilds it; `--check` also flags a record whose `content_sha` disagrees. The builder runs from the
installer post_step, the daily self-heal (`workflows` step, only on `--check` drift), `plan-tier-detect`
on a tier change and `usage_guard` on a flip. `workflow-model-guard` compares the record with the live
session and, on a mismatch, regenerates in the background and warns that the running script keeps its
old literals. Open item: whether a running session re-reads a changed saved script without
`/reload-skills`; the mod's `agent.spawn` cap is the live enforcer when present, the literals plus the
Python guards are the floor.

## 4. Contracts for other components

- `<run>/SANTA-REVIEW.json` (written by `review`'s report agent): `{verdict, incomplete, failedDimensions,
  blocking[], advisory[], stats}`. Stop Gate 4 reads `verdict` and `blocking[]` instead of parsing prose.
- `workflows/index.json`: `[{name, file, triggers, acts, min_size, phases, args_schema, description,
  whenToUse}]` for the router and `/workflows` readers.
- `build`'s `max_parallel` comes from the caller: the launcher's `state/launch-caps/<pid>.json` is read
  by the router or the main session, never by a script (scripts have no filesystem).
- `run`: the caller passes an absolute `.claude/runs/<utc-ts>-<slug>`; scripts take the artifact date
  from that name.
- `agent()` returning `null` (turn cap, dead agent) means "retry once" in `build`, `review` and
  `invoke`: a reviewer with a path list retries as two halves, anything else retries the same scope
  with a RETRY note. What stays null, or what an agent reports `incomplete`, is logged and returned
  (`build.review_uncovered[]`, `review.failedDimensions[].paths`) and makes the result `incomplete`.
  In `invoke`, an incomplete review keeps its verdict (the XL second pass never lifts it) and makes the
  result incomplete; `impl` retries per sub-step, so a finished backend half is never re-run.
- Turn caps: `turn_caps` in `hooks/model-policy.json` (per-agent table = frontmatter `maxTurns`, role
  floors, report reserve); every agentType a template names meets `schema_floor[role]`
  (`hooks/tests/test_model_policy_consistency.py`). `agent()` has no `maxTurns` option.

## 5. Running and debugging

- Run: `Workflow({name: "<script>", args: {...}})`; list and inspect runs with `/workflows`.
- Resume after a stop or an edit: `Workflow({scriptPath, resumeFromRunId})` replays the unchanged prefix.
- Offline: `node tests/fixtures/workflows/stub.mjs workflows/<name>.js <scenario.json>` runs a script
  under a fake runtime (calls, logs and result as one JSON line).
- Syntax: `node --check workflows/<name>.js`; drift: `python3 scripts/build_workflows.py --check`.

## 6. Adding a script

Template + `index.src.json` entry + stub scenario + stub test, then render and `--check`. Steps:
[`workflows/src/CLAUDE.md`](../workflows/src/CLAUDE.md). The `dynamic-workflow-mode` skill holds the
rule for when a repeated inline harness earns a saved script.

## 7. Not doing

- `ultracode` on by default.
- File writes from scripts (agents write; scripts only orchestrate).
- Team leads inside workflows (mixed surfaces run sequentially).
- Fable literals in any render.

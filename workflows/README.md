# Saved workflows

Generated from `src/*.js.tpl` by `scripts/build_workflows.py`. Never edit a `*.js` here: edit the
template and re-run the builder (`--check` reports drift).

| Script | Args | Returns | Artifacts (in `args.run`) |
|---|---|---|---|
| `invoke` | `{acts, task, run, slug, brief?, surface?, size?, security_paths?}` | `{run, acts, done, failed, closers, checkpoints, artifacts, verdicts, incomplete}` | `BRIEF.md`, `run.json`, one artifact per act (`SPEC-<slug>.md`, `plan-<date>-<slug>.md`, `IMPL-REPORT.md`, ...) |
| `invoke-fullstack` | `{task, run, slug, brief?}` | `{run, spec, plan, be, fe, integ, santa, security, docs, qa, dead, incomplete}` | spec, plan, `IMPL-REPORT-BE/FE.md`, `INTEGRATION-REPORT.md`, closers, `VERIFY-REPORT.md` |
| `review` | `{run?, base?, paths?, diff?, language?, security?}` | `{verdict, incomplete, failedDimensions, blocking, advisory, stats, report}` | `SANTA-REVIEW.md`, `SANTA-REVIEW.json` |
| `audit` | `{run, root?, surfaces?, task?, corpus?}` | `{run, slices, dead, map, incomplete}` | `audit/NN-<surface>.md`, `audit/00-MAP.md` |
| `research` | `{run, question?, sources?, url?, task?, corpus?}` | `{run, slices, dead, map, incomplete}` | `research/NN-<source>.md`, `research/00-FEATURES.md` |
| `migrate` | `{run, source?, target?, surfaces?, task?, corpus?}` | `{run, inventory, dispositions, packages, critic, revised, dead, incomplete}` | `migrate/inventory/*.json`, `migrate/dispositions/*.json`, `migrate/PACKAGES.json`, `migrate/REVISION.md` |
| `build` | `{packages_file, run, worktree, notes?, waves?, max_parallel?}` | `{run, packages, integrate, review_findings, review_verify, judge, final_verify, dead, incomplete}` | `PKG-<id>-STEPS.md`, `PKG-<id>-REPORT.md`, `REVIEW-FIX-<id>.md`, `FINAL-JUDGMENT.md`, `FINAL-VERIFY.md` |

## Running one

`Workflow({name: "review", args: {run: "<abs>/.claude/runs/<utc-ts>-<slug>", paths: ["src/a.ts"]}})`.
Scripts have no clock and no filesystem: the caller supplies `run` (an absolute run folder whose name
carries the UTC timestamp) and the agents write every artifact.

The prompt router names a script with a `WORKFLOW:` line (`hooks/prompt_router/modules/workflow_routes.py`
reads `index.json`). `args.tier_hint = "escalate"` (added by the router or `workflow-model-guard`)
switches executor roles to their escalated model through the `up()` helper; judges never move.

## Generated files

- `index.json`: per script `{name, file, triggers, acts, min_size, phases, args_schema, description, whenToUse}`.
- `.rendered.json`: `{schema, tier, usage_guard, policy_sha, content_sha}`, deterministic (no timestamp),
  so a re-render of the committed tier leaves the tree clean; the guard compares `tier` and
  `usage_guard` with the live session and regenerates on a mismatch.

## Local runs

`node tests/fixtures/workflows/stub.mjs workflows/review.js tests/fixtures/workflows/scenarios/review.json`
runs a script under a fake runtime (no model calls) and prints its calls, logs and result as JSON.
More: [`docs/WORKFLOWS.md`](../docs/WORKFLOWS.md).

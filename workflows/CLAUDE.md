<!-- dox:child v1 -->
# `workflows/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename a script.

## What lives here

The saved workflow library (`~/.claude/workflows/<name>.js`, run with `Workflow({name, args})`). Every
`*.js`, `index.json` and `.rendered.json` is GENERATED from `src/` by `scripts/build_workflows.py` for
the plan tier in `state/plan-tier.json` (fallback max20); the tracked render is the max20 column.

## Local conventions

- Edit `src/<name>.js.tpl`, never `<name>.js`; then `python3 scripts/build_workflows.py` and `--check`.
- No `Date.now`, `Math.random`, `new Date(` or `import(` anywhere (they throw in the runtime; the
  acceptance grep also rejects `new Date(iso)`, so scripts never build dates).
- Every `agent()` opts object keeps `agentType: '<x>', model: '<y>'` adjacent and in that order, holds
  no nested `{}` (schemas are named constants) and no `${...}` (labels are `'prefix:' + expr`).
- Executors (impl, integrate, security, test roles) go through `up({...}, '<escalated>')`; judges never.
- A `general-purpose` agent's label starts with `explore:` and contains no earlier `roles.labels` key
  (`explore:brief`, `explore:slice:<s>`, `explore:source:<n>`, `explore:surface:<s>`, `explore:packages`).
- Null-check every result (`ok()`) and retry it ONCE (halve a path list, else the RETRY note); report
  what stays null in `dead` / `review_uncovered` / `failedDimensions[].paths` and set `incomplete`; log
  every drop. Big text goes to files, structured replies stay under ~2 KB; the package list is returned
  complete and `build` logs its per-package path counts (`packages listed:`).
- `CHUNK` = 6 paths per reviewer, at most 8 chunks per `review` dimension and per `build` package (the
  chunk grows past 48 paths); parallel reviewers and verifiers keep notes in `<run>/notes/`, never in the
  shared report.

## Key files

| File | Role |
|------|------|
| `src/*.js.tpl` | templates with `{{model:<role>}}` / `{{model:<role>:up}}` tokens |
| `src/index.src.json` | routing data per script (`triggers`, `acts`, `min_size`, `args_schema`) |
| `invoke.js` | every `/invoke` chain: acts in canonical order, closers after mutating acts, verify last |
| `invoke-fullstack.js` | explicit opt-in spec → plan → BE → FE → integrate → closers → qa; a dead spec/plan stops it, `dead` names every null agent |
| `review.js` | Santa + ECC orch-review; writes `SANTA-REVIEW.json` (Gate 4 contract); line-proximity dedupe only across dimensions |
| `audit.js`, `research.js`, `migrate.js`, `build.js` | corpus-scale fan-outs (router: trigger + named corpus + `min_size`) |
| `index.json`, `.rendered.json` | generated routing index and render record (`content_sha`, deterministic: no `ts`, so re-renders of the committed tier leave the tree clean) |

## Gotchas / fragile spots

- `--check` re-renders from the RECORDED tier in `.rendered.json`, so CI and the Windows replica agree
  whatever their live tier is.
- A tier change or usage-guard flip regenerates in the background; `workflow-model-guard` warns that a
  script already running keeps its old literals.
- Nested `workflow()` is one level deep and may throw (old runtime, missing script): every caller keeps
  an inline fallback (`invoke.js` → inline santa review).
- The builder never deletes: a stale extra `*.js` shows up as `EXTRA` in `--check`; removing it is a
  human decision.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`src/CLAUDE.md`](src/CLAUDE.md)

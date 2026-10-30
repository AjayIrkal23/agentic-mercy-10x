<!-- dox:child v1 -->
# `workflows/src/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename a template.

## What lives here

The sources of the saved workflow library: one `<name>.js.tpl` per script and `index.src.json`.
`scripts/build_workflows.py` renders them into `../<name>.js`, `../index.json` and `../.rendered.json`.

## Templates

| Template | Generates | What it runs |
|----------|-----------|--------------|
| `audit.js.tpl` | `../audit.js` | one reader per surface → `audit/NN-<surface>.md`, then `audit/00-MAP.md` |
| `build.js.tpl` | `../build.js` | a packages file in dependency waves: spec, implement, verify, fix loop; integrate, Santa per package, final judge and verify |
| `invoke.js.tpl` | `../invoke.js` | `/invoke` acts in canonical order, one specialist per act, closers after mutating acts |
| `invoke-fullstack.js.tpl` | `../invoke-fullstack.js` | spec → plan → backend → frontend → integrator → santa/security/docs → qa |
| `migrate.js.tpl` | `../migrate.js` | lossless migration plan: inventory, dispositions, disjoint packages, critic, one revision |
| `research.js.tpl` | `../research.js` | one reader per named source writes cited facts, then `research/00-FEATURES.md` |
| `review.js.tpl` | `../review.js` | Santa Method + orch-review: parallel reviewers, dedupe, refute-by-default verification |

## Token grammar

- `{{model:<role>}}` → `tiers.<tier>.roles.<role>` of `hooks/model-policy.json`.
- `{{model:<role>:up}}` → `tiers.<tier>.escalate.<role>` (the base model when the tier has none).
- Usage guard active → every literal steps down (`lib/usage_guard.step_down`); every literal is
  clamped to the tier ceiling (`lib/plan_tier.cap`).
- Roles: `explore docs verify test impl integrate security judge default`. An unknown role token or a
  leftover `{{` stops the build (exit 2) before anything is written.

## `index.src.json`

One entry per template, same key as the file stem: `triggers` (router keywords; `[]` = explicit name
only), `acts` (for `invoke`: the canonical act list), `min_size` (`S|M|L`), `args_schema` (JSON Schema,
`type: object`). A template without an entry, or an entry without a template, stops the build. Keys
starting with `_` are comments.

## Adding a script

1. `<name>.js.tpl`: `export const meta = {...}` first (pure literal: `name` = stem, `description`,
   `whenToUse`, `phases: [{ title, model: '{{model:<role>}}' }]`), then the body (conventions in
   [`../CLAUDE.md`](../CLAUDE.md)).
2. `index.src.json` entry.
3. `tests/fixtures/workflows/scenarios/<name>.json` and a stub test in `tests/test_workflows_lib.py`.
4. `python3 scripts/build_workflows.py --tier max20 --out workflows`, then `--check`.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none

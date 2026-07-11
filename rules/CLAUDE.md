# `rules/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename a rule file or change a convention.

## What lives here

The **always-on rule files** that the root `CLAUDE.md` `@import`s into every
session's context (agent operating rules, substrate precedence, memory/TDD/dox
doctrines, model routing, higgsfield mandate). These are directives that must hold
in-context every turn — NOT on-demand skill bodies (those live in `../skills/`).

## Local conventions

- One concern per file; keep each rule tight (it costs context every prompt).
- A new rule must be `@import`ed from the root `CLAUDE.md` to take effect.
- Never merge rule files into a single mega-file — the "single file" consolidation
  historically killed triggering; keep them separate and imported.
- `references/` holds supporting material a rule links to (not itself imported).

## Key files

| File | Role |
|------|------|
| `mandatory-skill-protocol.mdc` | canonical phases 0–7 lifecycle (single source of truth) |
| `codebase-intel-first.md` | jcodemunch/graphify precedence over lean-ctx |
| `memory-protocol.md` | Memory MCP when/what to persist |
| `tdd-doctrine.md`, `tdd-autoinit.md` | TDD skills + tdd-guard + gates |
| `dox-doc-tree.md` | per-directory CLAUDE.md documentation tree |
| `invoke-impl-opus.md`, `agent-lifecycle-routing.md` | model routing + phase→hook→skill map |
| `higgsfield-frontend-mandate.md`, `ui-ux-playbook.mdc` | frontend asset engine + UI stack |
| `sequential-thinking-doctrine.md`, `token-optimization-stack.mdc`, `lean-ctx.md` | reasoning + token substrate |

## Gotchas / fragile spots

- Editing a rule changes EVERY session's context immediately — keep changes truthful
  and minimal.
- Model routing truth lives in `hooks/model-policy.json`; rules point at it, do not
  restate model pins.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`references/CLAUDE.md`](references/CLAUDE.md)

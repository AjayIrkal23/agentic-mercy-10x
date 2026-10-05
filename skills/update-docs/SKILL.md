---
name: update-docs
description: 'Documentation lifecycle: read repo docs before substantive coding (Phase A) and sync Markdown/MDX, changelogs, READMEs, and PR docs after implementation (Phase B). Stack-neutral; Next.js monorepo mapping in references/.'
when_to_use: Use when asked what docs a change affects, to sync docs with code, to scaffold docs for a feature, or when editing docs/, *_docs/, or README files.
paths:
- '**/docs/**'
- '**/*_docs/**'
- '**/README.md'
metadata:
  schema: 1
  category: backend
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 1216
  triggers:
    keywords:
    - update docs
    - update the docs
    - sync docs
    - docs affected
    - which docs
    - document this change
    - readme
    - changelog
    - server_docs
    - frontend_docs
    - mdx
    paths: []
    intents:
    - backend
---
# Update documentation

Guides updating project documentation to match code changes. This skill is **generic**; repo-specific mappings live under `references/` and in your own repository.

## Two-phase workflow (read first, sync after)

Many repositories expect **documentation before implementation** plus **explicit doc sync before handoff**.

### Phase A — Read (pre-implementation)

- Open the repo **`AGENTS.md`** / root **`CLAUDE.md`** (or equivalent onboarding doc) whenever it exists at the workspace root; a repo's own `.claude/` may carry a documentation-lifecycle checklist with its mandatory reading order — follow it when present.
- Narrow scope to the playbook + domain READMEs for the stacks you touch (server vs client); do not read the entire tree blindly—follow the project's mandatory reading order.

### Phase B — Sync (post-change)

Continue with **Workflow §1–§5** below. Map each behavioral diff to the doc tree that owns it (server docs for contracts/routes/domain behavior, client docs for routing/state/API layering, a cross-layer linkage doc when paths or domains change, and any audit/action taxonomy the repo keeps next to its routes).

**Handoff:** (**1**) Plan before substantive multi-file work (`plan-mode-gate`). (**2**) After behavioral edits, **`dead-code-and-change-audit`** and **`fix-lint-format`** on touched surfaces where applicable. (**3**) Before handoff: Superpowers **`verification-before-completion`**, skim **`code-review-and-quality`**; then **`using-agent-skills`** for any leftover relevant skills.

Hooks and `.claude/rules` may remind you at session start/stop but **cannot replace** Phase A/B.

## When to use

- Docs-impact questions: "what docs need updating?", "does this need a README change?"
- Editing or adding Markdown/MDX, changelogs, API docs, architecture notes
- After features that change public APIs, routes, config, or user-visible behavior

## Workflow

### 1. Understand the change set

```bash
git status
git diff
git diff --staged
# Optional: compare to integration branch
# git diff main...HEAD --stat
```

Identify **behavioral** changes (APIs, routes, errors, config) — those almost always need doc updates.

### 2. Map code → docs

- **This repository:** use project `AGENTS.md`, `CONTRIBUTING.md`, `README.md`, CI config, or a local doc index for where docs live.
- **Next.js upstream layout:** if you are in the Next.js repo, use [references/upstream-nextjs/CODE-TO-DOCS-MAPPING.md](references/upstream-nextjs/CODE-TO-DOCS-MAPPING.md) and [references/upstream-nextjs/DOC-CONVENTIONS.md](references/upstream-nextjs/DOC-CONVENTIONS.md).
- **Split monorepos (client + server packages):** see the **optional** illustrative map [references/examples/sample-monorepo-docs-map.md](references/examples/sample-monorepo-docs-map.md); adapt paths to your tree.

### 3. Edit with confirmation

For non-trivial doc changes:

1. Show what you plan to change
2. Apply edits preserving existing tone and structure
3. Keep examples and code fences accurate and runnable where applicable

### 4. Validate

Run checks documented for **this** repo (`AGENTS.md`, `README`, or CI). Typical patterns:

- **Node:** `npm run lint`, `pnpm lint`, `yarn lint`, and/or `npm run build` from the **package root** that owns the change
- **Go:** `make lint`, `go test ./...`, or equivalents from the **module root** that owns the change

If multiple packages exist (e.g. `client/` and `server/`), run the relevant commands **per package** as documented.

### 5. Checklist before commit

- [ ] User-facing behavior matches what the doc claims
- [ ] Links and paths are valid
- [ ] New options / routes / errors are documented
- [ ] Cross-links updated when navigation or filenames changed
- [ ] Lint/format passes for the doc toolchain in this repo
- [ ] Repo-specific lifecycle checklist (if the repo ships one under `.claude/`) — Phase B + Handoff complete

## References

- [examples/sample-monorepo-docs-map.md](references/examples/sample-monorepo-docs-map.md) — optional placeholder pattern for split layouts (project-specific trees belong in that repo's `.claude/`; see `~/.claude/docs/project-templates/`)
- [upstream-nextjs/](references/upstream-nextjs/) — Next.js maintainer-oriented conventions (vendored)

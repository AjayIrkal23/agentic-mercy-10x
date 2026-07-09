---
name: update-docs
description: Use before substantive coding when you must read repo documentation first (Phase A); after implementation to sync Markdown/PR docs (Phase B), including GO_UDP (`server_docs` / `frontend_docs` / PROJECT_LINKAGES). Also use when the user asks to update documentation for code changes, check docs for a PR, sync docs with code, scaffold docs for a feature, review docs completeness, or mentions docs folders, MDX, changelogs, README impact, or "what documentation is affected". For Next.js monorepo work, see references/upstream-nextjs/. Optional split client/server example in references/examples/. GO_UDP mapping in references/go-udp-documentation-lifecycle.md.
---

# Update documentation

Guides updating project documentation to match code changes. This skill is **generic**; repo-specific mappings live under `references/` and in your own repository.

## Two-phase workflow (read first, sync after)

Many repositories expect **documentation before implementation** plus **explicit doc sync before handoff**.

### Phase A — Read (pre-implementation)

- Open the repo **`AGENTS.md`** (or equivalent onboarding doc) whenever it exists at the workspace root.
- **GO_UDP monorepo:** follow Phase A paths in **[references/go-udp-documentation-lifecycle.md](references/go-udp-documentation-lifecycle.md)** and the authoritative repo file `.claude/documentation-lifecycle.md`.
- Narrow scope to the playbook + domain READMEs for the stacks you touch (server vs client); do not read the entire tree blindly—follow the project's mandatory reading order.

### Phase B — Sync (post-change)

Continue with **Workflow §1–§5** below. For GO_UDP explicitly map diffs → **`UDP_PLATFORM/server/server_docs/`**, **`UDP_PLATFORM/client/frontend_docs/`**, **`PROJECT_LINKAGES.md`**, and audit taxonomy (**`UDP_PLATFORM/server/internal/types/audit/actions.go`**) when routes change — see **[references/go-udp-documentation-lifecycle.md](references/go-udp-documentation-lifecycle.md)**.

**Also for GO_UDP:** (**1**) Mandatory **Cursor Plan mode → Agent mode** for substantive multi-file work (see repo **Plan gate** in `.claude/documentation-lifecycle.md`). (**2**) After behavioral edits, **`dead-code-and-change-audit`** and **`fix-lint-format`** on touched surfaces where applicable. (**3**) Before handoff: Superpowers **`verification-before-completion`**, skim **`code-review-and-quality`**; then **`using-agent-skills`** for any leftover relevant skills.

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
- **GO_UDP:** **[references/go-udp-documentation-lifecycle.md](references/go-udp-documentation-lifecycle.md)** — Phase B + **Handoff** complete ( **`update-docs`** mapping, **`dead-code-and-change-audit`** / **`fix-lint-format`** as needed, **`verification-before-completion`**, skim **`code-review-and-quality`**, **`using-agent-skills`** sweep; substantive work preceded by **Plan mode** per repo checklist)

## References

- [references/go-udp-documentation-lifecycle.md](references/go-udp-documentation-lifecycle.md) — GO_UDP read/sync checklist (mirror of repo `.claude/documentation-lifecycle.md`)
- [examples/sample-monorepo-docs-map.md](references/examples/sample-monorepo-docs-map.md) — optional placeholder pattern for split layouts
- [upstream-nextjs/](references/upstream-nextjs/) — Next.js maintainer-oriented conventions (vendored)

---
name: dead-code-and-change-audit
description: 'Change-scoped hygiene audit: dead code, stale references, orphaned logic, unused imports and files, broken linkages, and partial refactors left behind by a change.'
when_to_use: Use after a code change to audit what the diff orphaned; deletions stay scoped to your own changes, pre-existing dead code is only reported.
metadata:
  schema: 1
  category: review
  surfaces:
  - backend
  - frontend
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 822
  triggers:
    keywords:
    - dead code
    - unused imports
    - unused exports
    - orphaned files
    - stale references
    - leftover code
    - partial refactor
    - broken linkage
    - dead-code audit
    - what did my change orphan
    paths: []
    intents:
    - review
---
# Dead Code and Change Audit

## Scope (read first)

- **Your diff is the scope.** Clean up what *this change* orphaned: imports it made
  unused, the old path it replaced, a wrapper nobody calls after the refactor.
- **Pre-existing dead code is reported, never drive-by deleted.** List it with evidence
  (file:line, zero references) in the report; deleting it needs the user's OK
  (`CLAUDE.md` section 3, lifecycle phase 4).
- **Read-only roles** (auditors, reviewers, verifiers) report everything and delete
  nothing.
- Run it once the change is written (and again after a big refactor step), not as a
  pre-flight on unrelated work.

## 1. Before the change: know the linkage

For the feature or module you are touching, find with jcodemunch (`find_references`,
`find_importers`, `get_blast_radius`) or graphify `get_neighbors`:
- the files that actually power it (route -> controller -> service -> model; page ->
  component -> hook -> API module -> slice);
- parallel or legacy implementations of the same thing;
- every caller of any symbol whose signature or name you will change.

## 2. While changing

- Update every caller when you rename or change a signature; do not leave old and new
  paths side by side without a stated reason (feature flag, staged migration).
- Remove imports you made unused as you go.
- No commented-out code blocks; version control keeps history.

## 3. After the change: sweep your diff

| Sweep | Check |
|---|---|
| Symbols | imports, exports, variables, types, hooks, selectors, thunks, helpers your change left without a consumer |
| Files | a file you replaced or emptied that nothing imports now |
| Flow | routes still point at live handlers; nav/menu entries, guards and permissions for removed pages; controller -> service -> model calls intact; FE calls match the API contract |
| State | slice fields, reducers, selectors no consumer reads after your change |
| Backend | handlers, validators, schemas, jobs, middleware your change unregistered |
| Docs | docs and local `CLAUDE.md` that name what you moved or removed |
| Duplicates | logic you added that already exists elsewhere (reuse it instead) |

Tools: jcodemunch `find_dead_code` / `get_dead_code_v2` scoped to the touched files,
`find_references` per removed or renamed symbol, the linter's unused rules
(`noUnusedLocals`, `no-unused-vars`, `ruff F401`), `git diff --stat` for stray files.
Outside an indexed repo (e.g. `~/.claude`), an AST or linter pass over the touched files
does the same job.

## 4. Act

| Finding | Action |
|---|---|
| Orphaned by your change | remove it in the same change |
| Pre-existing, unrelated | report it; do not delete |
| Unsure whether it is used (dynamic import, reflection, public API, config string) | keep it, report it with the doubt |
| Removing it would delete a feature or file the user did not ask to touch | ask first |

## Report

```
DEAD-CODE AUDIT (scope: <files in the diff>)
  removed (orphaned by this change): <list or none>
  reported, not touched (pre-existing): <file:line - evidence>
  kept with doubt: <symbol - reason>
  docs updated: <list or none>
```

A change is done when it works, its linkage is intact, and nothing it orphaned is left
behind. Leaving the rest of the codebase cleaner is a report, not a license.

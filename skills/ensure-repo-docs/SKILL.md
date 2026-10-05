---
name: ensure-repo-docs
description: 'Read-only check that a repo''s documentation packs (README, frontend_docs/, server_docs/, the dox CLAUDE.md tree) exist and are not stale against the code they describe, with the edits routed to update-docs or dox-doc-tree.'
when_to_use: Use when a repo's AGENTS.md or CLAUDE.md says "use ensure-repo-docs", before substantive work in a surface whose docs look missing or thin, and before claiming completion after a change that moved routes, contracts or folders.
metadata:
  schema: 1
  category: general
  surfaces:
  - docs
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - ensure-repo-docs
    - ensure repo docs
    - docs missing
    - missing docs
    - stale docs
    - docs are stale
    - docs exist
    - repo docs
    - doc packs
    - server_docs
    - frontend_docs
    - documentation freshness
    intents:
    - DOCS
---
# Ensure Repo Docs

A gate, not an editor. It answers two questions for the surface you are about to
touch: **do the docs exist** and **are they fresh enough to trust**. Fixing what it finds
belongs to `update-docs` (README, `*_docs/`, changelogs) and `dox-doc-tree` (the
per-directory `CLAUDE.md` tree). This skill never writes.

## 1. Inventory the packs

Read the repo's root `CLAUDE.md` / `AGENTS.md` first: they name the packs that count.
Typical set:

| Pack | Exists when |
|---|---|
| README | `README.md` at the root |
| Frontend docs | `frontend_docs/` with an index (`README.md`) |
| Backend docs | `server_docs/` (or `docs/backend/`) with an index |
| Extra surfaces | whatever the root doc lists (mobile, infra, deploy) |
| dox tree | `CLAUDE.md` + `AGENTS.md` in each significant directory |

```bash
git ls-files 'README.md' '*_docs/*' 'docs/*' | head -50
git ls-files '*CLAUDE.md' | wc -l
```

A pack the root doc promises but `git ls-files` does not show is **missing**.

## 2. Freshness: docs vs the code they describe

Compare the last commit touching the code dir with the last commit touching its doc.
Uncommitted edits count too, so check `git status` for the same paths.

```bash
for pair in "src:frontend_docs" "server/src:server_docs"; do
  code=${pair%%:*}; doc=${pair##*:}
  c=$(git log -1 --format=%cs -- "$code"); d=$(git log -1 --format=%cs -- "$doc")
  echo "$code=$c  $doc=$d"
done
git status --short -- src server/src frontend_docs server_docs | head
```

Mark a pack **stale** when any holds:
- the code dir changed after the doc and the change moved a route, contract, model field,
  env var or folder (read `git log --stat <doc-date>.. -- <code dir>` to decide; a typo
  fix in code does not stale a doc);
- the doc names a file, route or symbol that no longer exists (spot-check 3-5 names with
  jcodemunch `search_symbols` or `git ls-files`);
- a directory with 3+ code files has no `CLAUDE.md` (dox rule).

Stay narrow: check the packs for the surface you will touch, not the whole repo.

## 3. Report and route

Write a short table in chat, one row per pack: `pack | status (ok / missing / stale) |
evidence (dates, dead names) | next step`. Then:

- missing or stale README / `*_docs/` → `update-docs` (Phase A before coding, Phase B
  after);
- missing or stub `CLAUDE.md` in a directory → `dox-doc-tree`;
- everything ok → continue the task; say so in one line.

If the repo's docs say "stop" on a missing pack, stop and fix the pack before the
feature work, unless the user scoped docs out.

## Not this skill

- Writing or rewriting docs (use `update-docs`, `dox-doc-tree`).
- Repo-wide doc audits on request (`update-docs` plus jdocmunch `get_doc_coverage`).
- Starting servers or building doc sites to "check" them: never.

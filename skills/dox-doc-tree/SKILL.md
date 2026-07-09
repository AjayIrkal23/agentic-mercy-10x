---
name: dox-doc-tree
description: MANDATORY before code work in any git repo. Establishes and maintains the dox CLAUDE.md documentation tree — read root→target before editing, follow local rules, update the local CLAUDE.md after edits. Use when a repo's dox tree is missing or incomplete, when scaffolding project docs, when SessionStart reports a missing/stubbed dox root, or before editing code in an undocumented directory. Code writes are hard-gated until a root CLAUDE.md exists.
---

# dox — the CLAUDE.md documentation tree

> Adapted from [agent0ai/dox](https://github.com/agent0ai/dox). dox ships `AGENTS.md`;
> in this setup the **real doc is `CLAUDE.md`** (Claude Code natively auto-injects a
> nested `CLAUDE.md` when you touch files in that subtree — this powers the walk for
> free). Each folder also carries a 1-line `AGENTS.md` pointer for cross-tool portability.

## Why this exists

Agents make blind edits without local context → drift, surprise changes, "why did it
touch that file?". dox fixes this with a **hierarchical doc tree**: a root file with
project-wide rules + an auto-synced index, and a child `CLAUDE.md` in **every directory**
(end-to-end coverage — `documentAllDirs: true`) holding the *local* rules for that area.
The loop is: **read root → walk down to the file you're about to touch → follow local
rules → edit → update the affected doc.**

> **Coverage is automatic.** The SessionStart guard runs a full **sweep** (`dox_engine.py`)
> that creates a `CLAUDE.md` + `AGENTS.md` in every non-skipped directory and syncs the
> root index. A PostToolUse hook (`dox-child-scaffold.py`) documents any new directory the
> moment you write a file into it. Your job is to **flesh out the stubs**, not to create them.
> Run a manual sweep any time with `python3 ~/.claude/hooks/dox_engine.py sweep <repo>`
> (or `… plan <repo>` for a dry run).

## The model

| File | Holds |
|------|-------|
| `<repo>/CLAUDE.md` (**root**) | Project overview, stack, non-negotiables, and an **index** linking to every child doc. Marked `<!-- dox:root v1 -->` when dox-managed. |
| `<dir>/CLAUDE.md` (**child**) | LOCAL rules for that directory only — what lives here, conventions, gotchas, links to deeper children. Never restate root-level rules; link to them. |
| `<dir>/AGENTS.md` (**pointer**) | One line: `See CLAUDE.md in this directory for agent instructions (dox tree).` |

Each file **≤250 lines** (matches the global file-limit rule). If a child grows past that,
split it into deeper children.

## When this skill fires

- SessionStart injected "dox tree stubbed / incomplete — flesh it out" (the auto-init guard).
- You're about to edit code in a directory that has no local `CLAUDE.md`.
- A PreToolUse `deny` told you "No dox root — scaffold first".
- You added/removed/renamed files and must update the local doc (Phase 7).

---

## Procedure A — READ (before any edit)

1. Identify the target file's directory.
2. Read the chain **root `CLAUDE.md` → … → target dir `CLAUDE.md`**. Claude Code
   auto-injects nested `CLAUDE.md` as you enter a subtree — confirm the chain is in
   context; if a link in the chain is missing, that's a scaffold gap (Procedure B).
3. Follow the most-specific local rule that applies. Local overrides general.

## Procedure B — SCAFFOLD (when missing/incomplete)

1. **Root.** If `<repo>/CLAUDE.md` is absent, create it from `references/root-template.md`
   (the SessionStart guard usually leaves a marked stub — flesh that stub out, don't
   replace its marker). If a **hand-written** root already exists (no `<!-- dox:root v1 -->`
   marker), DO NOT overwrite it — append a `## dox index` section linking children instead.
2. **Every directory.** By default (`documentAllDirs: true`) **every** non-skipped
   directory gets a `CLAUDE.md` — the sweep/PostToolUse hooks create the stubs for you.
   You **flesh each one out** from `references/child-template.md`: the *local* truth —
   what this folder is for, its conventions, its traps. Link up to root and down to deeper
   children. (Set `documentAllDirs: false` to fall back to the legacy "≥`significantDirThreshold`
   code files" gate.)
3. **Pointers.** Every folder that gets a `CLAUDE.md` also gets a 1-line `AGENTS.md`
   (`references/agents-pointer.md`). The engine never clobbers an `AGENTS.md`/`CLAUDE.md`
   that already exists.
4. **Index.** The root's `<!-- dox:index:start -->…<!-- dox:index:end -->` block is rebuilt
   automatically from the tree on disk (nested by depth). Don't hand-edit inside the markers
   — add/rename directories and the next sweep syncs it. On a **hand-written** root with no
   markers, the engine appends the block once, then keeps it synced.
5. The sweep is whole-repo, but **prose is still incremental** — flesh out the root + the
   area you're about to touch first; grow the local docs as you visit new areas.

## Procedure C — UPDATE (after editing)

After changing files in directory X:
1. Update `X/CLAUDE.md` — new/removed files, changed conventions, new gotchas.
2. If you added a new significant directory, add its child doc + link it in the root index.
3. This is part of **Phase 7 (Documentation Update)** — do it before marking work done.

---

## Which directories get docs

- **Default (`documentAllDirs: true`): every directory** that isn't on the skip list,
  regardless of how many code files it holds — end-to-end coverage.
- **Skip list** (build artifacts / deps / VCS / caches, never documented): `node_modules`,
  `.git`, `dist`, `build`, `.next`, `out`, `coverage`, `vendor`, `target`, `bin`, `obj`,
  `__pycache__`, `.venv`/`venv`, `.turbo`, `.cache`, `graphify-out`, `.planning`, `.claude`,
  `.idea`, `.vscode`, and any dot-directory. Extend via `SKIP_DIRS` in `dox_engine.py`.
- **Bounds:** `sweepMaxDepth` (default 12) and `maxSweepDirs` (default 500) cap a sweep so
  it can't run away on a huge tree; if truncated, the guard says so — raise the cap.
- **Legacy mode (`documentAllDirs: false`):** only dirs with ≥ `significantDirThreshold`
  (default 3) code files get a child; smaller dirs inherit the parent's `CLAUDE.md`.

## What happens when a `CLAUDE.md` already exists

- **A folder's `CLAUDE.md` / `AGENTS.md` already there** → left **completely untouched**
  (idempotent, never overwritten — your prose and any hand edits are safe). It's still
  listed in the root index.
- **The root `CLAUDE.md` already there** → its prose is never rewritten; only the
  auto-managed index block between the `dox:index` markers is re-synced. A hand-written
  root (no markers) gets the block appended once.
- **A directory removed/renamed** → its line drops out of the root index on the next sweep
  (the stale `CLAUDE.md` file itself is not deleted — remove it by hand if you want).

## Relationship to existing doc systems (do NOT duplicate)

dox is the **per-directory local-rules layer**. It is distinct from:
- **`update-docs` / `frontend_docs/` / `server_docs/`** — repo-level *numbered* docs. dox
  child files **link** to these; they don't restate them.
- **`CODEX.md`** — the working-decision + known-pitfalls log. Stays as-is; dox links to it.
- **`codebase-intel-first`** (jcodemunch/graphify) — owns code *discovery*; dox owns the
  human/agent *rules* for a directory. Use the intel tools to find code; use dox to learn
  the local conventions before changing it.

## Enforcement you're operating under

- **Engine** (`dox_engine.py`): the shared scaffolder — `collect` (which dirs),
  `sweep` (create all docs + sync index), `ensure_dir_documented` (one dir). Also a CLI:
  `dox_engine.py sweep|plan <repo>`.
- **SessionStart** (`dox-tree-guard.py session`): runs a full **sweep** — stubs a missing
  root, creates `CLAUDE.md` + `AGENTS.md` in **every** directory, syncs the root index,
  writes a fingerprint sidecar at `<repo>/.claude/dox/data/.doxinit.json`. Silent when the
  structure is unchanged. Never overwrites existing docs or hand-written prose.
- **PostToolUse** (`dox-child-scaffold.py`, chained in `post-write-aggregator.py`):
  the moment you write a file into an undocumented directory, it creates that dir's
  `CLAUDE.md` + `AGENTS.md` and re-syncs the root index.
- **PreToolUse** (`dox-write-gate.py`): **hard-denies** code writes when the root is
  missing (doc/scaffold writes are always allowed; re-issue the exact edit once to
  override). The Tier-2 soft-ask is skipped while `autoCreateChildren` is on (the
  PostToolUse hook creates the local doc for you).
- Full doctrine: `~/.claude/rules/dox-doc-tree.md`.

## Config (`dox-tree-guard.config.json`)

| Key | Default | Effect |
|-----|---------|--------|
| `documentAllDirs` | `true` | document **every** dir; `false` → ≥`significantDirThreshold` code files |
| `autoCreateChildren` | `true` | sweep + PostToolUse auto-create child stubs |
| `syncRootIndex` | `true` | keep the root `dox:index` block synced |
| `sweepMaxDepth` | `12` | max directory depth to descend |
| `maxSweepDirs` | `500` | safety cap on dirs documented per sweep |
| `significantDirThreshold` | `3` | legacy gate (only when `documentAllDirs:false`) |

## Templates

- `references/root-template.md` — root `CLAUDE.md` scaffold (paired `dox:index` markers).
- `references/child-template.md` — child `CLAUDE.md` scaffold.
- `references/agents-pointer.md` — the 1-line `AGENTS.md` pointer.

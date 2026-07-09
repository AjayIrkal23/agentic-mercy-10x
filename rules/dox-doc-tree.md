# dox — CLAUDE.md documentation tree (every repo)

> Always-on rule. Adapted from [agent0ai/dox](https://github.com/agent0ai/dox). Every git
> repo MUST carry a **CLAUDE.md documentation tree** — a root file with project-wide rules +
> an auto-synced index, and a `CLAUDE.md` + `AGENTS.md` in **every directory**
> (`documentAllDirs: true` — end-to-end coverage) holding *local* rules. The agent reads
> root→target before editing, follows the most-specific local rule, and updates the local
> doc after. Goal: less guessing, less drift, less "why did it touch that file?".

## Coverage is automatic (you flesh out, you don't create)

The shared engine `dox_engine.py` does the *creation*; the agent does the *prose*:

- **SessionStart** runs a full **sweep**: a `CLAUDE.md` + `AGENTS.md` is created in **every**
  non-skipped directory, and the root index is rebuilt from the tree on disk. Silent when
  nothing changed (fingerprint-throttled).
- **PostToolUse** (`dox-child-scaffold.py`, chained in `post-write-aggregator.py`) documents
  any directory the instant you write a file into it, and re-syncs the root index.
- **Manual:** `python3 ~/.claude/hooks/dox_engine.py sweep <repo>` (or `… plan <repo>` dry run).
- **Existing docs are never overwritten** — a folder with a `CLAUDE.md`/`AGENTS.md` already
  present is left untouched; on the root, only the `<!-- dox:index:start -->…<!-- dox:index:end -->`
  block is re-synced (a hand-written root gets the block appended once).

## The mandate

1. **Read before edit** — walk root `CLAUDE.md` → the target file's directory `CLAUDE.md`.
   Claude Code auto-injects nested `CLAUDE.md` as you enter a subtree, which realizes the
   walk natively; verify the chain is present.
2. **No code work without a root** — code writes are hard-gated until `<repo>/CLAUDE.md`
   exists. If missing, it is auto-stubbed at SessionStart; flesh it out via the
   `dox-doc-tree` skill. Doc/scaffold writes (`*.md`, `.claude/**`) are always allowed.
3. **Flesh out the stubs** — the hooks create a stub `CLAUDE.md` in every directory; replace
   the TODO placeholders with the real local truth (what lives here, conventions, traps) as
   you touch each area.
4. **Update after edit** — Phase 7: update the local `CLAUDE.md` for every directory you
   changed. New directories are auto-added to the root index; you fill in their prose.

## Filenames

- **`CLAUDE.md`** is the real doc (native nested auto-load). One in **every directory**.
- **`AGENTS.md`** in each documented folder is a **1-line pointer** to `CLAUDE.md`, kept for
  cross-tool portability (Cursor / Codex / Gemini). Never put real rules only in `AGENTS.md`.

## Scope

**Every git repo, no exemptions** — including `~/.claude` and docs repos. Safety valves keep
this from bricking you: the root gate is satisfied by **any** root `CLAUDE.md` (your existing
hand-written roots pass instantly and are never overwritten); doc/scaffold writes always
flow; an identical re-issued code edit overrides the gate once; every hook fails OPEN.
`dox-tree-guard.config.json: exemptRepos` ships empty as a future escape hatch.

## Enforcement (three layers, mirrors the tdd-guard doctrine)

| Layer | Owns | Mechanism |
|-------|------|-----------|
| **Engine** `dox_engine.py` | *Creating* docs + *syncing* the index | `collect` / `sweep` / `ensure_dir_documented`; shared by all hooks + the `sweep`/`plan` CLI; idempotent, never clobbers |
| **Skill** `dox-doc-tree` | *How* to walk / flesh out / update the tree | read/scaffold/update procedures + templates |
| **Auto-init sweep** `dox-tree-guard.py` | *Creating the whole tree* | SessionStart (via `session-start-aggregator`): full sweep → every dir gets `CLAUDE.md`+`AGENTS.md`, root index synced, fingerprint sidecar at `<repo>/.claude/dox/data/.doxinit.json`. UserPromptSubmit (via `token-stack-prompt-reminder`): bootstrap + read-first nudge. Never clobbers a hand-written root |
| **Per-write scaffold** `dox-child-scaffold.py` | *Documenting a touched dir* | PostToolUse (chained in `post-write-aggregator.py`): write a file into an undocumented dir → its `CLAUDE.md`+`AGENTS.md` are created + root index re-synced |
| **Hard gate** `dox-write-gate.py` | *Blocking* code writes with no root | PreToolUse `deny` when root missing (one-time override); Tier-2 soft-`ask` skipped while `autoCreateChildren` is on |

## Config (`dox-tree-guard.config.json`)

`documentAllDirs` (true → every dir; false → ≥`significantDirThreshold` code files) ·
`autoCreateChildren` (true) · `syncRootIndex` (true) · `sweepMaxDepth` (12) ·
`maxSweepDirs` (500) · `exemptRepos` (escape hatch). Skip list (build/deps/VCS/caches) lives
in `dox_engine.py: SKIP_DIRS`.

## Precedence vs sibling rules (no overlap)

- **`codebase-intel-first`** (jcodemunch/graphify) owns code *discovery*; dox owns the
  per-directory *rules* you follow before changing that code.
- **`update-docs` / numbered `frontend_docs` / `server_docs`** are repo-level docs; dox child
  files **link** to them, never restate.
- **`CODEX.md`** stays the working-decision + known-pitfalls log; dox links to it.
- **Phase 0 step 3b** and **Phase 7** in `mandatory-skill-protocol.mdc` are the lifecycle
  hooks for this rule.

Ops: skill `dox-doc-tree`.

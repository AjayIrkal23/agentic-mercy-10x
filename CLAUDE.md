# Global agent operating rules

These rules are always in context for every Claude Code session.

## ⚠️ Agent tool — REQUIRED `[sonnet]`/`[opus]`/`[fable]` prefix (check BEFORE every Agent/Task call)

Every `Agent` call's `description` field **MUST** start with `[sonnet] `, `[opus] `, or `[fable] ` (literal brackets + a space). This applies to *all* agent types, including `Explore`, `Plan`, `general-purpose`, and GSD/figma/vercel agents.

**Sonnet is the default — reach for `[opus]` rarely; reach for `[fable]` only when the user explicitly asks.** `[opus]` is reserved for **only two** cases:
1. **UI/UX work** — visual/design/frontend-polish subagent tasks (`frontend-uiux-designer` → pinned **`[fable]`** since 2026-07-18).
2. **Genuinely HEAVY + complex** work — large novel system/architecture design across many modules; a big novel build of many interdependent new files with no pattern to copy; deep unknown-root-cause debugging spanning many independent subsystems; cross-surface synthesis that must hold FE+BE+infra together at once.

**`[fable]` is the standing pin for specialist agents** (user directive 2026-07-18: "use fable for everything"): the implementor/design/integrator specialists and all substantive `/invoke` acts run Fable via `model-policy.json` pins. For ad-hoc `general-purpose` subagents doing substantive work, prefer `[fable]`; cheap searches stay `[sonnet]`.

**Do NOT use `[opus]`/`[fable]` for medium, small, or even "a bit complex" tasks.** The following are **always `[sonnet]`**: searches/exploration (`Explore`, `claude-code-guide`), single-to-several-file edits, refactors, pattern replication, bug fixes where the locus is known, lint/tests, doc updates, focused code review, and any task that is merely moderately complex. When unsure → `[sonnet]`.

**Dynamic per-task overrides (user-driven).** When the user says "use opus for this task" / "use fable for this" / "use sonnet", honor it on that turn's Agent calls: write the matching label AND set `model:"opus"|"fable"|"sonnet"`. The user's explicit word wins over the default for that task. For multiple subagents in one turn, apply the user's choice to each.

**Standing directive — Fable-first specialists (2026-07-18).** The IMPLEMENT suite and all substantive `/invoke` acts (impl, review, audit, spec, plan, debug, design, docs, verify) run on **Fable**: specialist subagents get `[fable]` + `model:"fable"`. IMPLEMENT also surface-routes: FE→`frontend-implementor-specialist`, BE→`backend-implementor-specialist` (contract-first), mixed→BE→FE→`integrator-specialist`, general→`implementation-engineer`. Source of truth: `agent_pins.fable` + `invoke_categories` in `hooks/model-policy.json`, rendered by `gen-invoke-commands.py`. See [[invoke-impl-opus]] (`rules/invoke-impl-opus.md`, retitled Fable-first).

- `Explore` and `claude-code-guide` → always `[sonnet]`. `frontend-uiux-designer`, `implementation-engineer`, `backend-implementor-specialist`, `frontend-implementor-specialist`, `integrator-specialist` → pinned `[fable]` (opus-guard enforces).
- Example (heavy): `Agent(subagent_type="general-purpose", description="[opus] Design the multi-service event pipeline end-to-end", prompt="…")`.
- Example (normal): `Agent(subagent_type="Explore", description="[sonnet] Map loco process data flow", prompt="…")`.
- Example (user said "use fable"): `Agent(subagent_type="general-purpose", description="[fable] …", model="fable", prompt="…")`.

**The label is real, not cosmetic.** Two hooks enforce the sonnet-by-default policy (neither relies on the `CLAUDE_CODE_SUBAGENT_MODEL` env var, which stays `inherit` — a concrete value there would hard-override per-call models and break all overrides):
- **`opus-guard.py`** (PreToolUse, `Agent` matcher) PINS the `model` param: `[opus]`/UI-UX agent → `opus`; `[fable]`/`model:fable` → `fable`; everything else → `sonnet`. Auto-corrects a missing/wrong prefix via `updatedInput` (never denies).
- **`workflow-model-guard.py`** (PreToolUse, `Workflow` matcher) rewrites each inline-workflow `agent()` call so it DEFAULTS to `sonnet` (UI/UX `agentType` → opus) unless the call passes an explicit `model`. This is what stops **workflow** subagents from inheriting the Opus parent (the main historical token burn). Workflows run from `scriptPath`/`name` are advised, not rewritten — pass an explicit `model` to each `agent()` there.

**Still write the prefix/model yourself** so the choice stays explicit — the hooks are the safety net.

**Session overrides (flag files in `~/.claude/state/`), honored by BOTH hooks:** `touch sonnet-only-mode` forces *every* subagent (and workflow agent) to Sonnet (kill-switch, wins over all else); `touch opus-only-mode` → all Opus; `touch fable-only-mode` → all Fable; `rm` the flag to return to smart routing. User phrases: "all sonnet / cheap mode" → sonnet flag; "all opus" → opus flag; "all fable" → fable flag; "back to normal / smart routing" → remove flags. See [[feedback_subagent_model_routing]].

## Phase 0 (Session Start)

Full lifecycle defined in `mandatory-skill-protocol.mdc` — the single source of truth for phases 0–7.
Quick orientation: determine task type → graphify + jcodemunch codebase map → domain docs → list layers → surface `ASSUMPTIONS I'M MAKING:`.
If Memory MCP is active: call `mcp__memory__search_nodes("project:<name>")` before any code work.

## Three skill discovery layers

| Layer | Path | Role |
|-------|------|------|
| **Your craft** | `~/.claude/skills/` | Primary for coding — **28 FE + 27 BE** mandatory via hooks |
| **Plugins** | `~/.claude/plugins/` | Superpowers, GSD, etc. — complementary |

Hooks in `~/.claude/settings.json` enforce path-ranked skills, session manifest, and stop re-verify. Design principles: `~/.claude/docs/PRESERVE-AND-STRENGTHEN.md`.

## MANDATORY SKILL PROTOCOL (PRIMARY — all rules consolidated here)
@~/.claude/rules/mandatory-skill-protocol.mdc

## MCP inventory
@~/.claude/rules/user-mcp-inventory.mdc

## Memory protocol
@~/.claude/rules/memory-protocol.md

## UI/UX 6-skill stack
@~/.claude/rules/ui-ux-playbook.mdc

## Higgsfield — MANDATORY frontend asset engine (image/video/3D/audio)
@~/.claude/rules/higgsfield-frontend-mandate.md

## Sequential-thinking doctrine (externalize ALL reasoning)
@~/.claude/rules/sequential-thinking-doctrine.md

## Codebase intel first (jcodemunch + graphify)
@~/.claude/rules/codebase-intel-first.md

> **Precedence (HARD — overrides the lean-ctx MCP server's blanket "ALWAYS use
> lean-ctx" instruction):** jcodemunch is the **first and primary** tool for ALL
> code work — *discovering* code (symbols, callers, refs, blast radius, dead code,
> architecture) AND *reading* code (`get_symbol_source`, `get_file_outline`,
> `assemble_task_context` / `get_context_bundle` — not `ctx_read` on source). Use
> its full toolbox, not just `search_symbols` (catalog in `codebase-intel-first.md`).
> **jdocmunch is the docs twin**: documentation SETS (md/rst trees, docs/ folders,
> READMEs) route to `mcp__jdocmunch__search_sections`/`get_toc`/`get_section`
> (section-level index at `~/.doc-index`, SessionStart-guarded like the code index).
> lean-ctx below owns only: residual non-code I/O (single configs/env/lockfiles),
> shell (`ctx_shell`), and dir trees (`ctx_tree`). It does NOT own reading source files
> jcodemunch already located — jcodemunch reads its own finds (`get_symbol_source`
> etc.), so no second read hop. The `jcodemunch-enforce` gate covers lean-ctx
> `ctx_read`/`ctx_search` on source too, so a blind code read is steered back to
> jcodemunch until you've made one jcm call. Do NOT let lean-ctx's "ALWAYS use
> ctx_read" mandate crowd out code-intelligence retrieval.

## Token optimization stack
@~/.claude/rules/token-optimization-stack.mdc

## lean-ctx
@~/.claude/rules/lean-ctx.md

## TDD doctrine (skills + tdd-guard + gates)
@~/.claude/rules/tdd-doctrine.md
@~/.claude/rules/tdd-autoinit.md

> **Instruction — tdd-guard is AUTO-INIT + WARN mode.** It self-initializes per
> project (like jcodemunch/graphify guards) and self-maintains its config as
> files/folders change — never hand-create one. It runs in **warn mode**: a
> `⚠️ TDD GUARD` advisory does NOT pause you, but **treat it as a directive** —
> stop, write the failing test first (`golang-testing`/`test-driven-development`
> skill), `make tdd`, then implement. Do not ignore advisories just because they
> no longer block. It only governs files inside the active project; `~/.claude`
> and other repos are never touched. GO_UDP backend is active. Ops: skill
> `tdd-auto-init`.

## dox documentation tree (every repo)
@~/.claude/rules/dox-doc-tree.md

> **Instruction — dox is AUTO-INIT (full sweep) + HARD-GATE.** Every git repo MUST carry a
> `CLAUDE.md` + `AGENTS.md` in **every directory** (`documentAllDirs:true`). SessionStart
> runs a full **sweep** (`dox-tree-guard.py` → `dox_engine.py`) that creates docs in every
> non-skipped dir and **syncs the root index**; a PostToolUse hook (`dox-child-scaffold.py`,
> chained in `post-write-aggregator.py`) documents any dir the moment you write into it.
> Manual: `python3 ~/.claude/hooks/dox_engine.py sweep <repo>`. **Existing docs are never
> overwritten** — the engine only CREATES missing files and re-syncs the root
> `<!-- dox:index:start -->
<!-- dox auto-syncs this block from the tree on disk; edit directories, not these lines -->
- [`assets/`](assets/CLAUDE.md)
- [`docs/`](docs/CLAUDE.md)
  - [`docs/audits/`](docs/audits/CLAUDE.md)
- [`double-shot-latte/`](double-shot-latte/CLAUDE.md)
- [`get-shit-done/`](get-shit-done/CLAUDE.md)
  - [`get-shit-done/contexts/`](get-shit-done/contexts/CLAUDE.md)
  - [`get-shit-done/references/`](get-shit-done/references/CLAUDE.md)
    - [`get-shit-done/references/few-shot-examples/`](get-shit-done/references/few-shot-examples/CLAUDE.md)
  - [`get-shit-done/templates/`](get-shit-done/templates/CLAUDE.md)
    - [`get-shit-done/templates/codebase/`](get-shit-done/templates/codebase/CLAUDE.md)
    - [`get-shit-done/templates/research-project/`](get-shit-done/templates/research-project/CLAUDE.md)
  - [`get-shit-done/workflows/`](get-shit-done/workflows/CLAUDE.md)
    - [`get-shit-done/workflows/discuss-phase/`](get-shit-done/workflows/discuss-phase/CLAUDE.md)
      - [`get-shit-done/workflows/discuss-phase/modes/`](get-shit-done/workflows/discuss-phase/modes/CLAUDE.md)
      - [`get-shit-done/workflows/discuss-phase/templates/`](get-shit-done/workflows/discuss-phase/templates/CLAUDE.md)
    - [`get-shit-done/workflows/execute-phase/`](get-shit-done/workflows/execute-phase/CLAUDE.md)
      - [`get-shit-done/workflows/execute-phase/steps/`](get-shit-done/workflows/execute-phase/steps/CLAUDE.md)
- [`gsd-local-patches/`](gsd-local-patches/CLAUDE.md)
  - [`gsd-local-patches/agents/`](gsd-local-patches/agents/CLAUDE.md)
  - [`gsd-local-patches/hooks/`](gsd-local-patches/hooks/CLAUDE.md)
- [`gsd-pristine/`](gsd-pristine/CLAUDE.md)
  - [`gsd-pristine/agents/`](gsd-pristine/agents/CLAUDE.md)
  - [`gsd-pristine/hooks/`](gsd-pristine/hooks/CLAUDE.md)
- [`hooks/`](hooks/CLAUDE.md)
  - [`hooks/lib/`](hooks/lib/CLAUDE.md)
  - [`hooks/prompt_router/`](hooks/prompt_router/CLAUDE.md)
    - [`hooks/prompt_router/modules/`](hooks/prompt_router/modules/CLAUDE.md)
  - [`hooks/tests/`](hooks/tests/CLAUDE.md)
  - [`hooks/tools/`](hooks/tools/CLAUDE.md)
- [`installer/`](installer/CLAUDE.md)
- [`memory/`](memory/CLAUDE.md)
- [`plans/`](plans/CLAUDE.md)
- [`rules/`](rules/CLAUDE.md)
- [`scripts/`](scripts/CLAUDE.md)
- [`shell-snapshots/`](shell-snapshots/CLAUDE.md)
- [`state/`](state/CLAUDE.md)
- [`teams/`](teams/CLAUDE.md)
  - [`teams/session-99a224a0/`](teams/session-99a224a0/CLAUDE.md)
- [`telemetry/`](telemetry/CLAUDE.md)
- [`templates/`](templates/CLAUDE.md)
- [`tests/`](tests/CLAUDE.md)
  - [`tests/fixtures/`](tests/fixtures/CLAUDE.md)
    - [`tests/fixtures/hook-events/`](tests/fixtures/hook-events/CLAUDE.md)
<!-- dox:index:end -->

## Coding Guidelines (Karpathy)

Invoke `andrej-karpathy-skills:karpathy-guidelines` for the full behavioral checklist (4 rules: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution). That skill is the single source of truth — do not restate here.

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use
`mcp__claude-in-chrome__*` tools. Available gstack skills: /office-hours,
/plan-ceo-review, /plan-eng-review, /plan-design-review, /design-consultation,
/design-shotgun, /design-html, /review, /ship, /land-and-deploy, /canary,
/benchmark, /browse, /connect-chrome, /qa, /qa-only, /design-review,
/setup-browser-cookies, /setup-deploy, /setup-gbrain, /retro, /investigate,
/document-release, /document-generate, /codex, /cso, /autoplan,
/plan-devex-review, /devex-review, /careful, /freeze, /guard, /unfreeze,
/gstack-upgrade, /learn.

# Global agent operating rules

These rules are always in context for every Claude Code session.

## ⚠️ Agent tool — REQUIRED `[sonnet]`/`[opus]`/`[fable]` prefix (check BEFORE every Agent/Task call)

Every `Agent` call's `description` field **MUST** start with `[sonnet] `, `[opus] `, or `[fable] ` (literal brackets + a space). This applies to *all* agent types, including `Explore`, `Plan`, `general-purpose`, and GSD/figma/vercel agents.

**Sonnet is the default — reach for `[opus]` rarely; reach for `[fable]` only when the user explicitly asks.** `[opus]` is reserved for **only two** cases:
1. **UI/UX work** — visual/design/frontend-polish subagent tasks (`frontend-uiux-designer` → always `[opus]`).
2. **Genuinely HEAVY + complex** work — large novel system/architecture design across many modules; a big novel build of many interdependent new files with no pattern to copy; deep unknown-root-cause debugging spanning many independent subsystems; cross-surface synthesis that must hold FE+BE+infra together at once.

**`[fable]` is NEVER automatic.** Use it ONLY when the user explicitly says "use fable" (globally or per-task). It is a user-driven override, not a heuristic.

**Do NOT use `[opus]`/`[fable]` for medium, small, or even "a bit complex" tasks.** The following are **always `[sonnet]`**: searches/exploration (`Explore`, `claude-code-guide`), single-to-several-file edits, refactors, pattern replication, bug fixes where the locus is known, lint/tests, doc updates, focused code review, and any task that is merely moderately complex. When unsure → `[sonnet]`.

**Dynamic per-task overrides (user-driven).** When the user says "use opus for this task" / "use fable for this" / "use sonnet", honor it on that turn's Agent calls: write the matching label AND set `model:"opus"|"fable"|"sonnet"`. The user's explicit word wins over the default for that task. For multiple subagents in one turn, apply the user's choice to each.

**Standing carve-out — `/invoke-impl` implements on Opus.** The IMPLEMENT suite (`/invoke-impl`, `/invoke-implementation`, and any combo whose name contains `impl`) runs its implementation on Opus by user directive: implementation subagents get `[opus]` + `model:"opus"`; if the main loop is not on Opus, delegate the implementation to an Opus subagent. Read-only helpers (search/lint/docs) stay Sonnet. Source of truth: `categories.IMPLEMENT.model:"opus"` in `hooks/autonomous-skill-router.config.json`, rendered into each command by `gen-invoke-commands.py`. See [[invoke-impl-opus]] (`rules/invoke-impl-opus.md`).

- `Explore` and `claude-code-guide` → always `[sonnet]`. `frontend-uiux-designer` → always `[opus]`. `implementation-engineer` → always `[opus]` (the /invoke-impl carve-out made agent-shaped; opus-guard pins it).
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
- [`agent-memory/`](agent-memory/CLAUDE.md)
- [`assets/`](assets/CLAUDE.md)
- [`ast-grep-mcp/`](ast-grep-mcp/CLAUDE.md)
  - [`ast-grep-mcp/tests/`](ast-grep-mcp/tests/CLAUDE.md)
    - [`ast-grep-mcp/tests/fixtures/`](ast-grep-mcp/tests/fixtures/CLAUDE.md)
- [`attic/`](attic/CLAUDE.md)
  - [`attic/2026-07-09/`](attic/2026-07-09/CLAUDE.md)
    - [`attic/2026-07-09/dox-stubs/`](attic/2026-07-09/dox-stubs/CLAUDE.md)
      - [`attic/2026-07-09/dox-stubs/agents/`](attic/2026-07-09/dox-stubs/agents/CLAUDE.md)
      - [`attic/2026-07-09/dox-stubs/commands/`](attic/2026-07-09/dox-stubs/commands/CLAUDE.md)
      - [`attic/2026-07-09/dox-stubs/plugins/`](attic/2026-07-09/dox-stubs/plugins/CLAUDE.md)
        - [`attic/2026-07-09/dox-stubs/plugins/cache/`](attic/2026-07-09/dox-stubs/plugins/cache/CLAUDE.md)
          - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/assets/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/skills/mermaid-diagrams/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/skills/mermaid-diagrams/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/src/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/src/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/src/preview/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/src/preview/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/helpers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/helpers/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/live-server/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-mermaid/claude-mermaid/1.2.0/test/live-server/CLAUDE.md)
          - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/clickhouse-best-practices/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/clickhouse-best-practices/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/clickhouse-best-practices/rules/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/clickhouse-best-practices/rules/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/setup/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/skills/setup/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/submodules/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/submodules/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/submodules/agent-skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/clickhouse/1.0.0/submodules/agent-skills/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/7b3a9beb32c8/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/7b3a9beb32c8/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/unknown/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/context7/unknown/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/commands/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/commands/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-agent/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-agent/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-cli/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-cli/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-cli/rules/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-cli/rules/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-crawl/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-crawl/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-download/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-download/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-interact/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-interact/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-map/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-map/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-monitor/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-monitor/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-parse/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-parse/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-scrape/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-scrape/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-search/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/firecrawl/1.0.9/skills/firecrawl-search/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/skills/frontend-design/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/7b3a9beb32c8/skills/frontend-design/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/skills/frontend-design/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/frontend-design/unknown/skills/frontend-design/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/gopls-lsp/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/gopls-lsp/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/gopls-lsp/1.0.0/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/gopls-lsp/1.0.0/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/7b3a9beb32c8/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/7b3a9beb32c8/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/unknown/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/playwright/unknown/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/claude/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/claude/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/codex/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/codex/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/copilot/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/copilot/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/cursor/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/agents/cursor/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/assets/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase-postgres-best-practices/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase-postgres-best-practices/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase-postgres-best-practices/references/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase-postgres-best-practices/references/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/assets/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/references/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/supabase/0.1.11/skills/supabase/references/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/assets/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/plans/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/specs/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/superpowers/specs/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/windows/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/docs/windows/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/hooks/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/hooks/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/scripts/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/brainstorming/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/brainstorming/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/brainstorming/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/brainstorming/scripts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/dispatching-parallel-agents/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/dispatching-parallel-agents/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/executing-plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/executing-plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/finishing-a-development-branch/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/finishing-a-development-branch/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/receiving-code-review/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/receiving-code-review/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/requesting-code-review/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/requesting-code-review/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/subagent-driven-development/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/subagent-driven-development/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/subagent-driven-development/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/subagent-driven-development/scripts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/systematic-debugging/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/systematic-debugging/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/test-driven-development/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/test-driven-development/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-git-worktrees/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-git-worktrees/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-superpowers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-superpowers/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-superpowers/references/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/using-superpowers/references/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/verification-before-completion/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/verification-before-completion/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-skills/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-skills/examples/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/skills/writing-skills/examples/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/antigravity/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/antigravity/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/brainstorm-server/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/brainstorm-server/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/claude-code/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/claude-code/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/codex/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/codex/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/codex-plugin-sync/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/codex-plugin-sync/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/explicit-skill-requests/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/explicit-skill-requests/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/explicit-skill-requests/prompts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/explicit-skill-requests/prompts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/hooks/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/hooks/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/kimi/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/kimi/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/opencode/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/opencode/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/pi/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/pi/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/shell-lint/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.0/tests/shell-lint/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/assets/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/plans/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/specs/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/superpowers/specs/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/windows/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/docs/windows/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/hooks/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/hooks/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/scripts/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/brainstorming/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/brainstorming/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/brainstorming/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/brainstorming/scripts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/dispatching-parallel-agents/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/dispatching-parallel-agents/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/executing-plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/executing-plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/finishing-a-development-branch/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/finishing-a-development-branch/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/receiving-code-review/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/receiving-code-review/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/requesting-code-review/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/requesting-code-review/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/subagent-driven-development/scripts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/systematic-debugging/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/systematic-debugging/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/test-driven-development/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/test-driven-development/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-git-worktrees/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-git-worktrees/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-superpowers/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-superpowers/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-superpowers/references/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/using-superpowers/references/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/verification-before-completion/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/verification-before-completion/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-plans/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-plans/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-skills/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-skills/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-skills/examples/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/skills/writing-skills/examples/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/antigravity/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/antigravity/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/brainstorm-server/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/brainstorm-server/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/claude-code/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/claude-code/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/codex/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/codex/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/codex-plugin-sync/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/codex-plugin-sync/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/explicit-skill-requests/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/explicit-skill-requests/CLAUDE.md)
                    - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/explicit-skill-requests/prompts/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/explicit-skill-requests/prompts/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/hooks/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/hooks/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/kimi/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/kimi/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/opencode/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/opencode/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/pi/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/pi/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/shell-lint/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/superpowers/6.1.1/tests/shell-lint/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/typescript-lsp/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/typescript-lsp/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/typescript-lsp/1.0.0/`](attic/2026-07-09/dox-stubs/plugins/cache/claude-plugins-official/typescript-lsp/1.0.0/CLAUDE.md)
          - [`attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/`](attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/`](attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/`](attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/skills/karpathy-guidelines/`](attic/2026-07-09/dox-stubs/plugins/cache/karpathy-skills/andrej-karpathy-skills/1.0.0/skills/karpathy-guidelines/CLAUDE.md)
          - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/CLAUDE.md)
              - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/assets/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/assets/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/agentic/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/agentic/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/arms/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/arms/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/results/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/benchmarks/results/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/commands/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/commands/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/docs/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/docs/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/examples/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/examples/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/hooks/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/hooks/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/pi-extension/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/pi-extension/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/pi-extension/test/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/pi-extension/test/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/ponytail-mcp/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/ponytail-mcp/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/ponytail-mcp/test/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/ponytail-mcp/test/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/scripts/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/scripts/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-audit/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-audit/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-debt/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-debt/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-gain/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-gain/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-help/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-help/CLAUDE.md)
                  - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-review/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/skills/ponytail-review/CLAUDE.md)
                - [`attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/tests/`](attic/2026-07-09/dox-stubs/plugins/cache/ponytail/ponytail/4.7.0/tests/CLAUDE.md)
          - [`attic/2026-07-09/dox-stubs/plugins/cache/superpowers-marketplace/`](attic/2026-07-09/dox-stubs/plugins/cache/superpowers-marketplace/CLAUDE.md)
            - [`attic/2026-07-09/dox-stubs/plugins/cache/superpowers-marketplace/claude-session-driver/`](attic/2026-07-09/dox-stubs/plugins/cache/superpowers-marketplace/claude-session-driver/CLAUDE.md)
    - [`attic/2026-07-09/hooks/`](attic/2026-07-09/hooks/CLAUDE.md)
    - [`attic/2026-07-09/rules/`](attic/2026-07-09/rules/CLAUDE.md)
    - [`attic/2026-07-09/skills-pre-update/`](attic/2026-07-09/skills-pre-update/CLAUDE.md)
      - [`attic/2026-07-09/skills-pre-update/huashu-design/`](attic/2026-07-09/skills-pre-update/huashu-design/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/CLAUDE.md)
          - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/container/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/container/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/feedback/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/feedback/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/impact/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/impact/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/keyboard/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/keyboard/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/magic/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/magic/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/progress/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/progress/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/terminal/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/terminal/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/transition/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/transition/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/ui/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/sfx/ui/CLAUDE.md)
          - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/cover/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/cover/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/infographic/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/infographic/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/ppt/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/ppt/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-ai-nav/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-ai-nav/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-ai-writing/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-ai-writing/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-devdocs/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-devdocs/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-homepage/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-homepage/CLAUDE.md)
            - [`attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-saas/`](attic/2026-07-09/skills-pre-update/huashu-design/assets/showcases/website-saas/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/huashu-design/demos/`](attic/2026-07-09/skills-pre-update/huashu-design/demos/CLAUDE.md)
          - [`attic/2026-07-09/skills-pre-update/huashu-design/demos/md-html-narration/`](attic/2026-07-09/skills-pre-update/huashu-design/demos/md-html-narration/CLAUDE.md)
          - [`attic/2026-07-09/skills-pre-update/huashu-design/demos/voiceover-demo/`](attic/2026-07-09/skills-pre-update/huashu-design/demos/voiceover-demo/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/huashu-design/references/`](attic/2026-07-09/skills-pre-update/huashu-design/references/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/huashu-design/scripts/`](attic/2026-07-09/skills-pre-update/huashu-design/scripts/CLAUDE.md)
      - [`attic/2026-07-09/skills-pre-update/impeccable/`](attic/2026-07-09/skills-pre-update/impeccable/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/impeccable/reference/`](attic/2026-07-09/skills-pre-update/impeccable/reference/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/impeccable/scripts/`](attic/2026-07-09/skills-pre-update/impeccable/scripts/CLAUDE.md)
      - [`attic/2026-07-09/skills-pre-update/taste-skill/`](attic/2026-07-09/skills-pre-update/taste-skill/CLAUDE.md)
      - [`attic/2026-07-09/skills-pre-update/ui-ux-pro-max/`](attic/2026-07-09/skills-pre-update/ui-ux-pro-max/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/ui-ux-pro-max/data/`](attic/2026-07-09/skills-pre-update/ui-ux-pro-max/data/CLAUDE.md)
          - [`attic/2026-07-09/skills-pre-update/ui-ux-pro-max/data/stacks/`](attic/2026-07-09/skills-pre-update/ui-ux-pro-max/data/stacks/CLAUDE.md)
        - [`attic/2026-07-09/skills-pre-update/ui-ux-pro-max/scripts/`](attic/2026-07-09/skills-pre-update/ui-ux-pro-max/scripts/CLAUDE.md)
- [`docs/`](docs/CLAUDE.md)
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
- [`gsd-migration-journal/`](gsd-migration-journal/CLAUDE.md)
- [`hooks/`](hooks/CLAUDE.md)
  - [`hooks/lib/`](hooks/lib/CLAUDE.md)
- [`improvements/`](improvements/CLAUDE.md)
  - [`improvements/2026-05-28-robustness-overhaul/`](improvements/2026-05-28-robustness-overhaul/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/audits/`](improvements/2026-05-28-robustness-overhaul/audits/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/backups/`](improvements/2026-05-28-robustness-overhaul/backups/CLAUDE.md)
      - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.bak/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.bak/CLAUDE.md)
        - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.bak/lib/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.bak/lib/CLAUDE.md)
      - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.post-audit-fix-1.bak/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.post-audit-fix-1.bak/CLAUDE.md)
        - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.post-audit-fix-1.bak/lib/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.post-audit-fix-1.bak/lib/CLAUDE.md)
      - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.post-overhaul.bak/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.post-overhaul.bak/CLAUDE.md)
        - [`improvements/2026-05-28-robustness-overhaul/backups/hooks.post-overhaul.bak/lib/`](improvements/2026-05-28-robustness-overhaul/backups/hooks.post-overhaul.bak/lib/CLAUDE.md)
      - [`improvements/2026-05-28-robustness-overhaul/backups/rules.bak/`](improvements/2026-05-28-robustness-overhaul/backups/rules.bak/CLAUDE.md)
        - [`improvements/2026-05-28-robustness-overhaul/backups/rules.bak/references/`](improvements/2026-05-28-robustness-overhaul/backups/rules.bak/references/CLAUDE.md)
      - [`improvements/2026-05-28-robustness-overhaul/backups/rules.post-overhaul.bak/`](improvements/2026-05-28-robustness-overhaul/backups/rules.post-overhaul.bak/CLAUDE.md)
        - [`improvements/2026-05-28-robustness-overhaul/backups/rules.post-overhaul.bak/references/`](improvements/2026-05-28-robustness-overhaul/backups/rules.post-overhaul.bak/references/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/implementation/`](improvements/2026-05-28-robustness-overhaul/implementation/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/post-deploy-audit/`](improvements/2026-05-28-robustness-overhaul/post-deploy-audit/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/post-fix-audit/`](improvements/2026-05-28-robustness-overhaul/post-fix-audit/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/research/`](improvements/2026-05-28-robustness-overhaul/research/CLAUDE.md)
    - [`improvements/2026-05-28-robustness-overhaul/tasks/`](improvements/2026-05-28-robustness-overhaul/tasks/CLAUDE.md)
- [`plans/`](plans/CLAUDE.md)
- [`rules/`](rules/CLAUDE.md)
  - [`rules/references/`](rules/references/CLAUDE.md)
- [`shell-snapshots/`](shell-snapshots/CLAUDE.md)
- [`state/`](state/CLAUDE.md)
- [`telemetry/`](telemetry/CLAUDE.md)
- [`templates/`](templates/CLAUDE.md)
<!-- dox:index:end -->

## Coding Guidelines (Karpathy)

Invoke `andrej-karpathy-skills:karpathy-guidelines` for the full behavioral checklist (4 rules: Think Before Coding, Simplicity First, Surgical Changes, Goal-Driven Execution). That skill is the single source of truth — do not restate here.

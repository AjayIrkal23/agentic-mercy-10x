<div align="center">

# agentic-mercy-10x

### A routing and enforcement layer for Claude Code: every prompt, file, write and subagent gets the right skill, MCP server and model.

<img src="assets/hero.webp" alt="agentic-mercy-10x — an orchestrated AI development pipeline" width="100%">

![Version](https://img.shields.io/badge/version-3.0.0-2E7D32?style=flat-square)
![Built for Claude Code](https://img.shields.io/badge/built_for-Claude_Code-D97757?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20%C2%B7%20macOS%20%C2%B7%20Windows-E95420?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-000000?style=flat-square)

**[What it is](#what-it-is) · [How triggering works](#how-triggering-works) · [/invoke](#invoke-and-run-folders) · [Models and teams](#models-and-teams) · [Hooks](#hooks) · [Install](#install) · [Verify](#verify) · [Changelog](docs/CHANGELOG.md)**

</div>

---

## What it is

This repo *is* `~/.claude`. Cloned and installed, it gives Claude Code:

- a small always-on doctrine (`CLAUDE.md` + `rules/0*.md`) and path-scoped domain rules
  (`rules/frontend.md`, `rules/backend.md`, `rules/claude-infra.md`);
- a skill library, specialist agents, and an `/invoke` orchestrator that runs them in a
  fixed order with artifacts on disk;
- hooks that route context in at the moment it matters (prompt, file read, write, subagent
  start) and gates that stop a turn from ending with undone work;
- a one-command installer that reproduces all of it, including MCP servers and plugins,
  on a fresh machine.

### What is on disk (2026-09-28)

Counts change; recompute them rather than trusting this table.

| Thing | Count | Recompute with |
|---|---|---|
| Local skills | 120 (+ Anthropic-synced skills under `skills/synced/`) | `ls skills/*/SKILL.md \| wc -l` |
| Agents | 18 (17 specialists + `team-lead`) | `ls agents/*.md \| grep -v README \| wc -l` |
| Hook events wired | 13 (12 `dispatch.py` chains + the prompt router) | `settings.template.json` → `hooks` |
| Dispatch links | 43 | `hooks/dispatch.config.json` → `chains` |
| MCP servers (user scope) | 15 | `installer/manifest.json` → `mcp_servers` |
| Plugins / marketplaces | 12 / 5 | `installer/manifest.json` → `plugins` |
| Vendored third-party skills | 27 sources | `hooks/skills-sources.json` |

## How triggering works

Six layers, each owning one moment. None of them depends on the model remembering a rule.

| Moment | Layer | What it does |
|---|---|---|
| Session start | `dispatch.py session-start` | settings self-heal, async state cleanup, orientation brief, memory `search_nodes("<repo>")` directive, skills-index freshness |
| Prompt | `hooks/prompt_router/router.py` (UserPromptSubmit) | word-boundary intent classification + stack/cwd-aware surface detection (repo fingerprint: React/Vite/Next vs Go/Express/Prisma/SQL; `claude-infra` inside `~/.claude`) → ≤5 ranked skills, ≤1 deep body, availability-aware MCP "call X now" lines, agent/act suggestion, per-project model-mode phrases. Emits `hookSpecificOutput.additionalContext`. |
| File touched | native skill `paths:` + path-scoped rules | FE/BE/API/infra skills and rules load when matching files are read — no hook involved |
| Write | `dispatch.py pre-tool-use` / `post-tool-use` | gates (dangerous bash, first-write skills, dox root, blast radius, tdd-guard advisory); post-write reminder of the canonical FE/BE set; `mcp-post-hints.py` (semgrep on security files, context7 on new imports, reticle/playwright when an app is already running, blast radius after >3 files) |
| Subagent start | `subagent-context.py` (SubagentStart) | injects the write protocol, no-servers/no-commit rules, MCP protocol and surface pointer into every subagent |
| Stop | `hard-completion-gate`, `invoke-suite-gate` | docs / security / Santa / dead-code gates, at most one block per turn |

MCP usage is a standing MUST (jcodemunch for code, graphify for architecture, jdocmunch
for doc sets, sequential-thinking for non-trivial reasoning, memory, context7 for library
APIs, semgrep for security-sensitive files). The table lives in
[`rules/00-tool-precedence.md`](rules/00-tool-precedence.md); hooks only suggest servers
that are actually connected and authorized.

## /invoke and run folders

`/invoke <acts...> [-- task]` (skill [`skills/invoke`](skills/invoke/SKILL.md)) runs one
specialist per act in canonical order:

`audit spec plan debug test impl refactor design clean security review docs verify`

- Each act also exists as a forked single-act skill (`/invoke-impl`, `/invoke-review`, …),
  plus `/invoke-session`, `/invoke-status`, `/invoke-update` (vendored-skill sync) and
  `/invoke-fullstack` (spec → plan → BE → FE → integrator → review/security/docs → QA,
  optional saved Workflow in `workflows/invoke-fullstack.js`).
- Artifacts land in `<repo>/.claude/runs/<ts>-<slug>/` with a `run.json`.
- Closers (clean, security, review, docs, verify) run only after code-mutating acts and
  never duplicate an act you named.
- The act table is single-sourced in `hooks/autonomous-skill-router.config.json`; models
  in `hooks/model-policy.json`. `python3 hooks/gen-invoke-skills.py` regenerates the
  family (`--check` verifies).

Agents and their acts: [`agents/README.md`](agents/README.md).

## Models and teams

Three layers, one truth (`hooks/model-policy.json`), details in
[`rules/04-model-routing.md`](rules/04-model-routing.md):

1. `env.CLAUDE_CODE_SUBAGENT_MODEL=sonnet` — the native default.
2. Every agent pins `model:` and `effort:` in frontmatter (opus for the implementor/design
   agents and `santa-reviewer`).
3. `opus-guard` aligns the `[sonnet]`/`[opus]`/`[fable]` description label with the model.
   Precedence: session flag > per-project mode > explicit `model` > agent pin > label >
   sonnet. Fable is never automatic.

Per-project mode: "use opus for this project" / "back to normal", or
`python3 ~/.claude/scripts/model-mode.py opus|sonnet|clear` inside the repo.

**Deliberate teams.** Agent teams are enabled, but plain delegation is an `Agent` call
with no `name`. A named call launches a teammate; that is reserved for work that needs
teammate messaging (the fullstack BE↔FE contract handoff, a squad you ask for) and follows
[`agents/team-lead.md`](agents/team-lead.md). The `TeammateIdle` gate keeps a teammate
working until its expected artifact exists.

## Hooks

`settings.json` registers `dispatch.py <event>` once per event; every hook is a *link* in
`hooks/dispatch.config.json` (types `gate`, `mutator`, `advisory`, `exec`, optional
`async`), isolated and fail-open. The prompt router is registered directly.
Architecture and link list: [`hooks/README.md`](hooks/README.md).

| Event | Chain highlights |
|---|---|
| SessionStart | permissions self-heal, state cleanup (async), aggregator, memory load, ponytail session, skills-index guard |
| UserPromptSubmit | prompt router |
| PreToolUse | dangerous-bash, first-write skill gate, gateguard, dox root, bash-write, doc enforcer, jcodemunch read gate, jdocmunch/graphify steer, tdd-guard (advisory), opus-guard, workflow-model-guard |
| PostToolUse | skill tracker, FE/BE reminder, codex capture, post-write aggregator (index journal, dox scaffold, doc enforcer), desloppify, semgrep tracker, MCP post-hints |
| PostToolUseFailure | tool-failure hint (read-before-edit, etc.) |
| Stop | completion gate, invoke-suite gate, index flush (async), lifecycle, weights loop |
| SubagentStart / SubagentStop | subagent context / lifecycle |
| PreCompact / PostCompact | handoff snapshot / restore |
| ConfigChange | permissions-deny guard |
| TeammateIdle | teammate-idle gate |
| SessionEnd | permissions self-heal, index session-end |

Indexes (jcodemunch, jdocmunch with ollama semantic search, graphify) stay fresh through
`hooks/index-lifecycle.py`: event-driven, active repo only, no daemons. `~/.claude` and
`$HOME` are never indexed and never get dox trees.

## Install

Prerequisites (Python ≥ 3.10, Node LTS, Git, Claude Code CLI): [`PREREQUISITES.md`](PREREQUISITES.md).

```bash
git clone https://github.com/AjayIrkal23/agentic-mercy-10x ~/agentic-mercy
~/agentic-mercy/install.sh            # Windows: install.ps1 · any OS: python3 install.py
```

One command, no prompts. `installer/bootstrap.py` finds `~/.claude`, merge-copies the
clone into it (your runtime data is preserved), opens a local visual installer, and runs
the self-heal loop: deps → 15 MCP servers via `claude mcp add` → 5 marketplaces + 12
plugins → lean-ctx config merge → rendered `settings.json` → post-steps (re-vendor skills,
generate `/invoke` skills and agent skill blocks, rebuild indexes, validate) → doctor,
repeating repairs until the doctor reports 0 FAIL. Headless: `python3 install.py --ci`.
Installer internals: [`installer/CLAUDE.md`](installer/CLAUDE.md).

After install, by hand: `/mcp` to authorize higgsfield and openart; `gh auth login`;
optionally `ollama pull all-minilm` for semantic search. Per project, a read-only DB MCP:
`python3 ~/.claude/scripts/add-db-mcp.py --supabase|--mongodb`
(template `templates/mcp/db-readonly.mcp.json`, project scope only).

Your own settings go in `settings.user.json`; `settings.json` is rendered from
`settings.template.json` and must never contain the string `lean-ctx`.

Updating vendored skills: `/invoke-update`, or `python3 scripts/vendor_skill.py --check`
then `vendor_skill.py <name> [--ref R]`.

## Verify

```bash
python3 installer/doctor.py            # health, 0 FAIL expected
python3 -m pytest hooks/tests tests -q # hook + installer tests
python3 scripts/validate_skills.py     # skill catalog R1..R12
python3 hooks/build-trigger-floor.py --check
python3 hooks/gen-invoke-skills.py --check
python3 hooks/gen-agent-skill-blocks.py --check
```

Escape hatch if a hook misbehaves: `claude --safe-mode`.

## Layout

| Path | Holds |
|---|---|
| `CLAUDE.md`, `rules/` | always-on doctrine + path-scoped rules |
| `skills/` | local, vendored and synced skills (`invoke*` are generated) |
| `agents/` | specialist agents + `team-lead` |
| `hooks/` | dispatcher, links, prompt router, configs, tests |
| `installer/`, `install.*` | one-command installer and doctor |
| `scripts/` | vendoring, validation, model mode, DB MCP, inventory |
| `templates/`, `workflows/` | per-project MCP template; saved `/invoke-fullstack` workflow |
| `docs/` | [changelog](docs/CHANGELOG.md), [ADRs](docs/adr/), [index](docs/INDEX.md), archive |

## Credits

Vendored and plugin skills keep their upstream licenses; sources are pinned in
`hooks/skills-sources.json` and `installer/manifest.json`.

## License

MIT — see [`LICENSE`](LICENSE).

# ~/.claude — operating rules (always on)

This file plus `rules/0*.md` is the whole always-on doctrine (~5k tokens). Domain
rules load by path (`rules/frontend.md`, `rules/backend.md`, `rules/claude-infra.md`).
Everything longer lives in a skill and loads on demand.

## 1. Subagents are pre-authorized (standing request)

I request, for this and every future session, that you use the `Agent` tool whenever
delegation is the right tool — without asking first. This is the user request that the
harness's "do not call the Agent tool unless the user requested it" line asks for.
`Workflow` stays opt-in per task (I invoke it explicitly).

## 2. Delegation — every `Agent` call

- Omit `model` on `Agent` calls: `opus-guard` sets `model` and the `[sonnet|opus|fable]`
  description label. Sonnet executes (the default); Opus judges (review, UI/UX, plan,
  spec, debug agents); executors escalate to Opus after a failed attempt or on large
  unplanned work. Pass `model` only to honor my model request: opus-guard lets an explicit
  `model` move a pinned judge, an executor or fable only when my own turn names that model
  ("use opus / sonnet / fable"); otherwise pins and escalation win and the ignored request
  is logged. Fable only when I ask for it in that turn ("use fable for this").
- Pins, escalation and effort tiers live in `hooks/model-policy.json`. Do not restate
  them anywhere else.
- `name` is OPTIONAL and is a team decision, not a labeling convention: with agent teams
  on, a named `Agent` call launches a *teammate*. Pass `name` only when the work needs
  teammate messaging (fullstack `/invoke` BE↔FE contract, a parallel squad I ask for),
  following `agents/team-lead.md`. Plain delegation = no `name`.
- "use opus/sonnet/fable for this" → honor it on that turn's calls. Per-project mode:
  "use opus for this project" / "back to normal", or
  `python3 ~/.claude/scripts/model-mode.py opus|sonnet|clear` inside the repo.
  Precedence, env semantics, effort: `rules/04-model-routing.md`.
- Subagents never `git commit` and never start servers.

## 3. File writes

1. FIND with jcodemunch → 2. READ the exact file → 3. `Edit` (or `Write` for a new or
whole-file replacement; `ctx_patch` inside the repo needs no prior Read).
Never write through the shell (`sed -i`, `python3 -c`/heredoc writes, `cat >`, `tee`,
`echo >`) — `rules/01-no-shell-writes.md`. A gate or refusal is a route to the
sanctioned tool, not an obstacle. Ask before deleting files or removing features I did
not ask you to remove. Commit only when asked.

## 4. Tools

MCPs are mandatory, not optional — one table: `rules/00-tool-precedence.md`. Short form
(MUST, except trivial one-line answers / single lookups): code → jcodemunch first;
architecture / "how is X wired" → graphify; doc sets → jdocmunch; non-trivial reasoning
→ sequential-thinking; library APIs → context7; security-sensitive files → semgrep; a
single non-code file → `Read` or `ctx_read`; shell → Bash. Follow hook "call X now" lines.

## 5. Verify without servers

Never start dev servers, watchers, or throwaway app instances — I run apps myself.
Verify with commands that exit: builds, tests, linters, `--check` scripts. Evidence
before "done".

## 6. dox

Every git repo carries a root `CLAUDE.md` (local ones where the repo opts in). Read
root → the target directory's `CLAUDE.md` before editing there; update the local one
after. Skill: `dox-doc-tree`. dox never writes into `rules/`.

## 7. Memory

Native auto-memory (`projects/*/memory/MEMORY.md`) is primary. Memory MCP holds
durable, reusable, non-obvious facts (`pattern::` / `decision::` / `fragile::`). MUST:
`mcp__memory__search_nodes("<project> <topic>")` at the start of project work; on
"remember / going forward / we decided" → `add_observations`.
Protocol: `skills/mcp-usage-standards/references/memory-protocol.md`. Never store
secrets or session state.

## 8. Frontend standing directives

Scroll-driven motion → invoke `nateherk-design:scroll-craft` before writing scroll code.
Raster / video / 3D / audio assets → Higgsfield (`mcp__higgsfield__*`), never
placeholders or stock URLs. Details and carve-outs: `rules/frontend.md`.

## 9. Style

- Code: `andrej-karpathy-skills:karpathy-guidelines` (think first, simplest thing,
  surgical diff, verifiable goal) and `ponytail` (the laziest solution that works).
- Prose to me: `caveman` — terse, no filler, full technical accuracy.
- All prose (chat, docs, commits, PRs): `no-ai-slop` — none of its banned words or patterns.

## 10. Machines

Hosts, SSH, sudo and the Windows replica live in a gitignored per-machine file (this repo
is public). Copy it between machines by hand; never commit it.

@CLAUDE.machines.local.md

## 11. Autonomy by default (standing request, 2026-10-05)

I only prompt and develop; I never run slash commands, scripts, re-indexing or setup steps.
Every part of this workbench (hooks, the mercy mod and its UI, skills, model routing, code
intelligence, rules, docs/dox, memory, MCP servers, packages and tool installs) triggers by
itself, is on by default and recovers on its own. Build features automatic first; a command is an optional extra. Never end a turn
with "run X" when a hook, the mod or you can do X. Ask me only for human-only steps
(OAuth logins, commits, deleting my data), once and batched.

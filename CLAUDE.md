# ~/.claude — operating rules (always on)

Always on: this file, the machines file, `rules/0*.md` (~4.3k tokens) and the 9 core
skill bodies (~24k, chars/4); domain rules load by path (`rules/frontend.md`).

@CLAUDE.skills.md
The 32 standing directives and what enforces each: `docs/DIRECTIVES.md`.

## 1. Subagents and workflows are pre-authorized (standing request)

For this and every future session, use the `Agent` tool whenever delegation is the right
tool, without asking first. `Workflow` is pre-authorized like `Agent`: run a saved workflow
from `~/.claude/workflows/` when the router's WORKFLOW line names one, or write an inline
script for multi-phase work; keep small tasks inline. `ultracode` is not on by default (the
5-hour window); the keyword still works when I type it.

## 2. Delegation — every `Agent` call

- Omit `model` on `Agent` calls: `opus-guard` sets it from the plan tier and the agent's
  role (`rules/04-model-routing.md`); pass `model` only to honor my request that turn
  ("use opus / sonnet / haiku / fable"). General-purpose readers: add a `[haiku]` label.
  Per-project: "use opus for this project" / "back to normal".
- `name` only for teammates (`agents/team-lead.md`); plain delegation = no `name`.
- Subagents never `git commit` and never start servers.

## 3. File writes

FIND with jcodemunch → READ the exact file → `Edit` (or `Write`; `ctx_patch` needs no prior
Read). Never write through the shell: `rules/01-no-shell-writes.md`. Ask before deleting
files or removing features I did not ask you to remove. Commit only when asked.

## 4. Tools

MCPs are mandatory, not optional — table + gates: `rules/00-tool-precedence.md`;
reasoning: `rules/03-thinking.md`. Follow hook "call X now" lines.

## 5. Verify without servers

Never start dev servers, watchers, or throwaway app instances — I run apps myself. Verify
with commands that exit: builds, tests, linters, `--check` scripts. Evidence before "done".
Memory pressure: heed `memory warn/crit` lines (`state/mem-pressure.json` is the source);
no agent fan-out or heavy builds while they show.

## 6. dox

Every git repo carries a root `CLAUDE.md` (local ones where it opts in). Read root →
the target directory's `CLAUDE.md` before editing there; update the local one after. Skill:
`dox-doc-tree`. dox never writes into `rules/`.

## 7. Memory

Auto-memory (`projects/*/memory/MEMORY.md`) is primary; Memory MCP holds durable, non-obvious
facts, never secrets or session state. MUST: `mcp__memory__search_nodes("<project> <topic>")`
at the start of project work; on "remember / going forward / we decided" → `add_observations`
(protocol: skill `mcp-usage-standards`).

## 8. Frontend standing directives

Scroll-driven motion → `nateherk-design:scroll-craft` before writing scroll code. Raster /
video / 3D / audio → Higgsfield (connector `mcp__claude_ai_higgsfield__*`), never
placeholders or stock URLs. Every new app and every new website is a PWA (standing order,
2026-10-25); existing projects change only when I ask. The bar: `rules/frontend.md`.

## 9. Style

Code: `andrej-karpathy-skills:karpathy-guidelines` + `ponytail` (smallest complete change;
`shortcut:` comments). Prose to me: output style `caveman` (`output-styles/caveman.md`:
caveman + no-ai-slop + the ponytail reply shape), chat only.

## 10. Machines

Hosts, SSH, sudo and the replica: a gitignored per-machine file (public repo), kept short on
every machine by `scripts/split_machines_file.py` (journal beside it, not imported). Copy it
by hand; never commit it.

@CLAUDE.machines.local.md

## 11. Autonomy by default (standing order, 2026-10-05)

I only prompt and develop; I never run slash commands, scripts, re-indexing or setup steps.
Everything here triggers by itself, is on by default and recovers on its own; a command is
an optional extra. Never end a turn with "run X" when a hook, the mod or you can do X. Ask
me only for human-only steps (OAuth logins, commits, deleting my data), once and batched.

<!-- dox:child v1 -->
# `hooks/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update it whenever
> you add, remove, or rename files here, or change a local convention.

## What lives here

Every Claude Code hook: gates, advisories, mutators, exec side-effects, the prompt
router, the index-lifecycle state machine, and the dispatcher that ties them together.
Architecture: [`README.md`](README.md). Only hook logic and hook config belong here.

## Local conventions

- **One dispatcher per event.** `settings.template.json` registers `dispatch.py <event>`
  for 12 events (+ `prompt_router/router.py` on UserPromptSubmit). Individual hooks are
  links in `dispatch.config.json` (`chains.<event>`), never separate settings entries.
- **Every hook stays its own file.** Add behavior as a new link, not by merging logic.
- **Portability:** commands use `{PY}`/`{HOOKS}`/`{NODE}` tokens (`lib/platform.py`); no
  raw `.sh` in the live path.
- **Never remove a trigger rule** — `build-trigger-floor.py --check` fails CI on a drop.
- **Model truth is single-sourced** in `model-policy.json`.
- Links that write to disk no-op when `CLAUDE_HOOK_DOCTOR` is set (doctor dry-fires).
- Generated files — never hand-edit: `skills-index.json`, `trigger-floor.json`,
  `skills-provenance.json`, `skills/invoke*/`, agent `skills:` lines.

## Key files

| File | Role |
|------|------|
| `dispatch.py` / `dispatch.config.json` | per-event chain runner + link declarations (12 events, 43 links; types gate/mutator/advisory/exec, `async` exec) |
| `prompt_router/` | UserPromptSubmit router — see its `CLAUDE.md` |
| `opus-guard.py`, `workflow-model-guard.py`, `model-policy.json` | sets `model` + `[label]` (Opus judges, Sonnet executes, `escalation` lifts executors), logs each decision to `.telemetry/<sid>.model-routing.jsonl`; never touches `prompt`/`name` |
| `subagent-context.py` | SubagentStart: write protocol, no-servers/no-commit, MCP protocol, surface pointer |
| `teammate-idle-gate.py` | TeammateIdle: teammate can't idle until its `run.json` expected artifact exists |
| `mcp-post-hints.py` | PostToolUse "call X now" (semgrep, context7, reticle/playwright, postgres-patterns, blast radius) |
| `tool-failure-hint.py` | PostToolUseFailure: read-before-edit hints |
| `memory-load-on-start.py` | reads `memory/memory.jsonl` directly; emits `search_nodes("<repo>")` |
| `hard-completion-gate.py`, `invoke-suite-gate.py` | Stop gates, ≤1 block per turn (`lib/turns.py`) |
| `settings-permissions-selfheal.py` | session start/end + ConfigChange (`permissions-deny-guard`) keep `permissions.deny` empty |
| `gen-invoke-skills.py`, `gen-agent-skill-blocks.py` | generate `/invoke` skills and agent `skills:` blocks (`--check`) |
| `skills-sources.json` | vendored third-party skills (repo, ref, overrides) — consumed by `scripts/vendor_skill.py` |
| `skill-aliases.json` | alias → canonical map, resolved by `lib/skill_aliases.py` |
| `index-lifecycle.py` | event-driven jcodemunch/jdocmunch/graphify/dox freshness, active repo only, no daemons |
| `dox_engine.py`, `dox-child-scaffold.py`, `dox-write-gate.py` | dox: git repos only, `$HOME` and `~/.claude` refused |
| `tdd_guard_launcher.py` → `tdd-guard-gate.py` | advisory tdd-guard, project repos only |

## Gotchas / fragile spots

- Dispatcher and every link fail open; never let a link raise past its own try/except.
- Mutator output must stay valid single-line JSON — the old multi-line `prompt` mutation
  was silently dropped for months.
- `index-lifecycle.py: NEVER_INDEX` excludes `$HOME`, `~/.claude`, `~/.codex`; this is
  deliberately not in `lib/repo_context.py` (gates still scope inside `~/.claude`).
- `index-lifecycle.py` runs the jcodemunch CLI with `os.environ` + `mcpServers.jcodemunch.env`
  from `~/.claude.json` (`_jcodemunch_env`): a hook-spawned CLI does not inherit the MCP
  server's `OPENAI_API_BASE`, and jcodemunch-mcp ≥1.108.319 then refuses api.openai.com and
  silently falls back to signature summaries. `summarizer_healthcheck` (config) DEFERs the
  build and prints `⚠️ ACTION NEEDED — AI summarizer (ollama …) is DOWN` at session start
  when ollama is unreachable (probe fails open); tests stub `_summarizer_alive`.
- Claude Code saves any hook `additionalContext` over 8,000 chars to a file and shows the
  model a 2 KB preview. Every `budgets.chars` stays under that; the aggregator keeps to
  `MAX_AGGREGATED_CHARS` (5,500) and upgrades core-skill pointers to full bodies only
  while they fit (`test_session_start_budget.py`).
- Guards key on this checkout as well as `$HOME`: `NEVER_INDEX` and dox `resolve_root`
  include `Path(__file__)`'s repo, and the aggregator spawns no index/tdd writers under
  `CLAUDE_HOOK_DOCTOR`. A sandbox-HOME test run once dox-swept the real `~/.claude`.
- `paths:`-scoped skills are unknown to the Skill tool until a matching file is read.
  The router says `Read ~/.claude/skills/<name>/SKILL.md` for them, and
  `gen-agent-skill-blocks.py` writes a `<!-- path-skills -->` Read block into agent bodies
  (their `skills:` preload silently skips those).
- tdd-guard (Sonnet via the Agent SDK) takes 4-7.3 s: gate 15 s < launcher 16 s < link 17 s.
- `settings.json` is rendered — edit `settings.template.json`, then `installer/render.py`.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`lib/`](lib/CLAUDE.md) · [`prompt_router/`](prompt_router/CLAUDE.md) · [`tests/`](tests/CLAUDE.md) · [`tools/`](tools/CLAUDE.md)
- Related: [`README.md`](README.md), [`../rules/claude-infra.md`](../rules/claude-infra.md)

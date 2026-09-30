<!-- dox:child v1 -->
# `hooks/prompt_router/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

The **UserPromptSubmit hook** (`router.py`, registered directly in `settings.json`,
not via `dispatch.py`). One process per prompt: classify → detect FE/BE/API/docs
surface → rank ≤5 skills → MCP routes → agent/act suggestion → emit
`{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":
"<!-- prompt-router v3 -->\n…"}}`. Target ≈800 tokens median. Nothing in here
starts servers or mutates the repo; side effects are the session manifest,
`hooks/.telemetry/<sid>.pushed-skills.jsonl` and telemetry records.

## Local conventions

- **Fail-open everywhere.** Every module catches its own exceptions and returns an
  empty result; `router.main` emits `{}` on any error. A prompt must always flow.
- **Word-boundary matching only.** Keywords ≤3 chars are dropped unless in
  `classify._SHORT_ALLOW` (`build-trigger-floor.py` applies the same rule). Never
  reintroduce substring matching (`kw in text`) — it caused 61% misroutes.
- **Router-only tuning lives in `router.config.json` → `additions`** (`intents`,
  `surface_skills`, `skill_rules`, `demote`). Never hand-edit `trigger-floor.json`;
  rebuild it with `python3 hooks/build-trigger-floor.py` and verify `--check`.
- **Plugin skills are `plugin:skill`** (e.g. `nateherk-design:scroll-craft`) and
  every ranked candidate must exist on disk (`select.skill_exists`) — no dead
  `Skill()` pushes. A `paths:`-scoped skill is "Unknown skill" to the Skill tool until a
  matching file is touched, so its push also names the `SKILL.md` to Read (the tracker
  counts a Read as loaded).
- Skills in `core-skill-set.json` are never re-pushed; aliases collapse via
  `lib.skill_aliases` (fallback `skill-aliases.json`).
- Run `python3 -m py_compile` on every edited module before the next prompt —
  the hook is live.

## Key files

| File | Role |
|------|------|
| `router.py` | orchestrator: gates → substrate → indexed symbols → skills (+≤1 deep body) → routing → model; emit + manifest + pushed-skills |
| `classify.py` | `TaskProfile`; `KeywordMatcher` (one lookaround alternation per group); intents/UI/arch; calls `surface.detect`; `ACT_MAP` from the autonomous config |
| `select.py` | ranking scorers (index, cross-cutting, category, surface, rules), alias collapse, existence filter, top-5/floor, surface-routed IMPLEMENT agent |
| `budget.py` | tier-ascending ordering only (the 24k budget never bound; nothing is dropped) |
| `manifest.py` | per-session dedup of emitted ids (never suppresses a first fire) |
| `router.config.json` | knobs + `additions` (the only place to tune routing by hand) |
| `modules/` | `surface.py`, `mcp_routes.py`, `code_intel.py`, `model_advice.py` — see its CLAUDE.md |

## Gotchas / fragile spots

- Skill item ids are salted `skill:<name>:<intent>:<surfaces>` — plugin names contain
  `:`; parse with `startswith("skill:<name>:")`, never `split(":")[1]`.
- `is_ui` needs UI-keyword weight ≥1.0 and is suppressed for backend-only prompts
  ("endpoint … with pagination"); vague words (`page`, `table`, `form`) are 0.4.
- Stack-only surface inferences are in `profile.weak_surfaces` and score at half
  weight; `gate:tdd` ignores them. Removing that distinction re-drags golang-patterns
  into React prompts in Go+React repos.
- Per-project model mode is set ONLY by `router.parse_mode_phrase` (explicit, word-bounded,
  ≤500-char human prompt, quoted spans stripped); a clear is reported only when a pin
  existed. `<task-notification>` / local-command prompts are trivial (never routed) —
  an agent report mentioning "smart routing" once cleared a repo's mode.
- Inside the Claude config dir the surface is `claude-infra` only (no FE/BE vocab,
  stack, or path segments) so "hook"/".py" never pull backend/frontend skills.
- `tests/test_prompt_router.py` + `tests/test_router_surface.py` build tmp repos and
  run the hook as a subprocess; keep them green (`python3 -m pytest hooks/tests -q`).

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`modules/CLAUDE.md`](modules/CLAUDE.md)
- Related: `hooks/build-trigger-floor.py`, `hooks/ui-keywords.json`, `hooks/tool-intelligence.json` (`mcp_routes`), audit `02-router.md`

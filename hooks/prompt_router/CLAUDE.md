<!-- dox:child v1 -->
# `hooks/prompt_router/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

The **UserPromptSubmit router** (`router.py`): a `dispatch.py user-prompt-submit`
advisory link (p0, 12 s) once integrate lands the chain; callable directly for tests.
One process per prompt: classify → detect FE/BE/API/docs surface → rank ≤3 skills →
pointer / WORKFLOW / MCP / LIBRARY routes → agent/act suggestion → emit
`{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":
"<!-- prompt-router v3 -->\n…"}}`. Measured 88 tokens mean / 310 p90 (1,257 live
fires, 2026-10-15..29); after the merge 768 ch mean (post-T7, n=29), so final-fix 2
(2026-10-30) shortened every line: fixed 4-prompt probe 1,145 → 964 ch mean; the
real-session number needs ≥ 30 prompts after epoch 1793342134 (target ≤ 445 ch mean,
≤ 1,474 p90; next lever `max_routing_lines` 5 → 4). Nothing in here starts servers or mutates the repo; side
effects are the session manifest, `hooks/.telemetry/<sid>.pushed-skills.jsonl` and
telemetry records.

## Local conventions

- **Fail-open everywhere.** Every module catches its own exceptions and returns an
  empty result; `router.main` emits `{}` on any error. A prompt must always flow.
- **Word-boundary matching only.** Keywords ≤3 chars are dropped unless in
  `classify._SHORT_ALLOW` (`build-trigger-floor.py` applies the same rule). Never
  reintroduce substring matching (`kw in text`) — it caused 61% misroutes. The heavy
  size/risk signals match whole words too (`_HEAVY_RX`: "infrastructure" is not "infra").
- **Router-only tuning lives in `router.config.json` → `additions`** (`intents`,
  `surface_skills`, `skill_rules`, `demote`, `ui_veto`, `surface_pointers`,
  `stack_indicators`). Never hand-edit `trigger-floor.json`; rebuild it with
  `python3 hooks/build-trigger-floor.py` and verify `--check`. Router-only keywords go to
  `additions.intents` so the floor needs no rebuild (`intents.MODEL_ROUTING` lives there;
  the autonomous config's `MODEL_ROUTING` category keeps `keywords: []`).
- **MODEL_ROUTING (R3.6).** Model/plan-tier talk ("model selector", "20$ plan", "opus and
  fable") is `claude-infra` work: no act, no skill push, one ROUTING pointer to
  `hooks/model-policy.json` (`surface_pointers.claude-infra`, once per session).
  Bare model / plan-size tokens live in `additions.model_routing_weak` and fire the intent
  only in pairs: one alone ("use opus for this: …") is the override phrase, not routing talk.
  `ui_veto` words (redesign, design, selector, picker, switcher, restyle) score UI only
  with a UI noun within 6 words; with a MODEL_ROUTING hit they drop out of DESIGN too, and
  with no UI noun anywhere the frontend surfaces go, unless the prompt itself names a
  frontend stack ("… in react") or the intent came only from weak tokens and the UI
  words carry weight (`is_ui`).
- **Plugin skills are `plugin:skill`** (e.g. `nateherk-design:scroll-craft`) and
  every ranked candidate must exist on disk (`select.skill_exists`) — no dead
  `Skill()` pushes. A `paths:`-scoped skill is "Unknown skill" to the Skill tool until a
  matching file is touched, so its push is `Read <absolute SKILL.md>` instead of
  `Skill()` (`select.skill_path`; the tracker counts a Read as loaded).
- Skills in `core-skill-set.json` are never re-pushed; aliases collapse via
  `lib.skill_aliases` (fallback `skill-aliases.json`).
- Plural stemming (optional s/es) applies to intent (`act:`) groups only; UI/arch lists
  carry their own plurals.
- A skill push is one line: `- **name** (LABEL) ACTION: Skill("name")` (or
  `ACTION: Read <abs SKILL.md>` for `paths:` skills). No description — the Skill tool lists it.
  The mercy governor and `test_prompt_router` parse the `ACTION: ` token (not a line start).
- When the first-write baseline and the TDD gate both fire they merge into one line
  (`gate:firstwrite+tdd`); it keeps "First substantive change this session" (the mercy
  governor drops it after the first write by that phrase).
- **Deep injection (H4):** at most one body (`[inlined skill: x]`), rank 1 only, when the
  strongest NON-size intent reaches `auto_dispatch_threshold` (size words never trigger
  it). An inlined body replaces the rank-1 line: no line is MUST-READ then, and nothing is
  recorded for invoke-suite-gate.
- `pushed-skills.jsonl` `enforce` is "hard" or "soft" (`policy.enforce_level`); a doctor
  dry-fire (`CLAUDE_HOOK_DOCTOR`) without `CLAUDE_HOOK_TELEMETRY_DIR` records nothing, and
  without `CLAUDE_HOOK_STATE_DIR` it neither reads nor writes the manifest (repeatable).
- **Manifest reset (H3):** `dispatch.py` writes `state/<sid>.router-reset` on
  SessionStart `source` compact|clear; `manifest.load` consumes it and starts dedup over.
- **No emitted line tells the user to type anything** (autonomy §11): dispatch lines say
  "dispatch `<agent>` with the Agent tool", the heavy-task line says "dispatch the Opus judge
  agent", a missing graph says "graph is building in the background; use jcodemunch
  `get_dependency_graph` now", the WORKFLOW line is a model instruction (never
  "/workflow"). Graphify lines carry `project_path="<repo root>"` (the MCP serves its
  start-up graph otherwise). For an infra root (`_infra_root`: `$HOME`, `~/.claude`,
  `~/.codex`, this checkout = index-lifecycle's NEVER_INDEX) no line promises an index or
  graph build. `_doc_index_exists` checks both manifest names index-lifecycle uses
  (`<name>`, `<name>-<sha1(realpath)[:8]>`). Never reintroduce `/invoke <act>`,
  `/model <id>` or `graphify update` in router text (`tests/test_autonomy_wpc_text.py`).
- Caps: `max_skill_pushes` 3, `max_route_lines` 3 (dispatch), `max_mcp_routes` 4,
  `max_routing_lines` 5 (total; order: model-mode echo, surface pointer, WORKFLOW, UI,
  asset login, MCP, dispatch, LIBRARY).
- The `prompt_router.live` telemetry row carries `ms` (router wall time, A-10).
- Run `python3 -m py_compile` on every edited module before the next prompt —
  the hook is live.
- `router.py` strips its own dir from `sys.path` at startup: run as a script, `select.py`
  here shadowed stdlib `select` (imported by `subprocess`) on Pythons where `select` is
  not a builtin (CI's setup-python 3.12), and every MCP route line vanished silently.
  Never add a sibling module named after a stdlib module.

## Key files

| File | Role |
|------|------|
| `router.py` | orchestrator: gates → substrate → indexed symbols → skills (+≤1 deep body) → routing (pointer, WORKFLOW, UI, MCP, dispatch) → LIBRARY → model; emit + manifest + pushed-skills. `_pointer_items` (`additions.surface_pointers`), `_workflow_items` (drops the `route:<act>` lines its acts cover), `_library_items` (≤2 LIBRARY lines from `modules/library_routes.py`, 50 ms soft budget, overruns telemetered as `prompt_router.library_slow`) |
| `classify.py` | `TaskProfile`; `KeywordMatcher` (one lookaround alternation per group); intents/UI/arch; UI veto + MODEL_ROUTING surface swap; calls `surface.detect`; `ACT_MAP` from the autonomous config; URLs are stripped before matching; a long prompt is scanned as its first 6k + last 2k characters (a 40k paste took 23 s) |
| `select.py` | ranking scorers (index, cross-cutting, category, surface, rules), alias collapse, existence filter, top-N/floor, surface-routed IMPLEMENT agent. Index keywords with `source` `description`/`floor-fallback` count half (cap 2.0); stack-only surfaces earn `weak_surface_factor`; `hidden` (user-only) skills never rank; `additions.demote` multiplies, clamped to ≤ 1.0 (learned weights retired 2026-10-29) |
| `cues.py` | refinements on the raw keyword hits: negation window ("no need for/to", "don't", "do not", "without" + ≤3 words) drops a keyword; `write/add/create … tests` → TEST; LARGE dropped when only single nouns hit (websocket, streaming, …) |
| `policy.py` | emit policy: `enforce_level` (rank 1 → enforce "hard" only at ≥6.0, ≥1.5× rank 2, intent/strong-surface match; else "soft"), `dev_signal` / `write_gates` / `code_shaped` (chat, questions, trivial renames get no gates/substrate/symbols), `skill_line`, `ui_line` (names only available asset servers; the claude.ai Higgsfield connector counts), `cap_section` (max_routing_lines), `session_model`, `ARCH_RX`, `WEAK_ARCH` |
| `budget.py` | tier-ascending ordering only (the 24k budget never bound; nothing is dropped) |
| `manifest.py` | per-session dedup of emitted ids (never suppresses a first fire); consumes the `<sid>.router-reset` marker |
| `router.config.json` | knobs + `additions` (the only place to tune routing by hand): `intents` (incl. `MODEL_ROUTING`), `surface_skills`, `demote`, `ui_veto`, `surface_pointers`, `stack_indicators`, `skill_rules` |
| `modules/` | `surface.py`, `mcp_routes.py`, `code_intel.py`, `model_advice.py`, `asset_auth.py`, `workflow_routes.py` (+ `library_routes.py` from package `library`) — see its CLAUDE.md |

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
  existed. `<task-notification>` / local-command / `<cross-session-message>` prompts are trivial (never routed) —
  an agent report mentioning "smart routing" once cleared a repo's mode.
- Inside the Claude config dir the surface is `claude-infra` only (no FE/BE vocab,
  stack, or path segments) so "hook"/".py" never pull backend/frontend skills.
- `tests/test_prompt_router.py` + `tests/test_router_surface.py` build tmp repos and
  run the hook as a subprocess; keep them green (`python3 -m pytest hooks/tests -q`).
  `test_router_model_routing.py` pins the R3.6 regression prompt; `test_workflow_routes.py`
  uses a tmp `CLAUDE_CONFIG_DIR` with its own `workflows/index.json`.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`modules/CLAUDE.md`](modules/CLAUDE.md)
- Related: `hooks/build-trigger-floor.py`, `hooks/ui-keywords.json`, `hooks/tool-intelligence.json` (`mcp_routes`, `connectors`), `hooks/dispatch.py` (router-reset marker)

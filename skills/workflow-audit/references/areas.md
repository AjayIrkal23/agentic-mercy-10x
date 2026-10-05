# /workflow-audit — Phase 1 area briefs (A–G; H–J in areas-h-j.md)

Loaded by `skills/workflow-audit/SKILL.md` section 3. Each area fills the subagent
template from section 3.0 (AREA, FILES, CHECKS, REPORT).

### A. Settings and rendering → `$AUDIT/A-settings.md`

FILES: `settings.template.json`, `settings.json` (rendered, read-only),
`settings.user.json` if present (no secret values), `installer/render.py`,
`installer/manifest.json` (hooks, env, plugins, mods parts).

CHECKS:
1. Every `hooks.<Event>` entry: matcher, command, timeout, statusMessage. Each maps to a
   `dispatch.py <event>` chain or the router; no event registered twice; no chain
   without an event.
2. Timeout ladder per event: settings hook timeout > dispatcher budget > each link's
   `timeout_ms`; tdd-guard ladder gate 15 s < launcher 16 s < link 17 s. List every
   inversion.
3. `env` block: every variable has a real consumer (a hook, the mod, or a documented
   Claude Code setting). Known dead example: `CLAUDE_CODE_SUBAGENT_EFFORT`.
   `CLAUDE_CODE_PLUGIN_DIRS` holds absolute paths that exist.
4. `permissions.deny` is `[]`; `grep -c lean-ctx settings.json settings.template.json`
   is 0; defaultMode and allow list make sense.
5. `render.py --check` passes; Claude-managed keys (theme, tui, voice, pluginConfigs)
   carry over; count and age of `settings.json.bak-*` backups.
6. Enabled plugins in settings match the manifest; statusLine and model settings.

### B. Dispatcher and every hook link → `$AUDIT/B-hooks.md`

FILES: `hooks/dispatch.py`, `hooks/dispatch.config.json`, every script a link's `cmd`
names, `hooks/lib/*.py`, `hooks/README.md`, `hooks/CLAUDE.md`, the matching tests in
`hooks/tests/`.

CHECKS, dispatcher:
1. Pass order (gates → mutators → advisories → exec), short-circuit on deny and block,
   `updatedInput` threading through mutators, parallel pass, per-event `budgets.ms`
   and `budgets.chars` against Claude Code's 8,000-character context cap, UTF-8 input
   and ASCII-escaped output, telemetry rows, error isolation (every link fails open).
2. Mod bridge: `--only <ids>` selection; `_mod_owned` (owner session id plus a
   `MERCY_MOD_BEAT` heartbeat under 120 s); owned links leave no telemetry row when
   skipped, and a row for a mod-owned link means the mod ran it.

CHECKS, every link (one table row each): id · event · type · tools matcher (regex
fullmatch) · timeout · priority / async · trigger logic `path:line` · inputs read
(payload fields, env, files) · state written (exact paths) · output shape · fails open?
· respects `CLAUDE_HOOK_DOCTOR`? · tests that cover it · telemetry over the last 14 days
from `~/.claude/telemetry/hook-fires-*.jsonl` (runs, p50 and p90 ms, decisions, output
rate = rows with `chars_out > 3`, errors, timeouts, budget-overruns) · verdict: keep /
make async / gate by predicate / merge / retire.

Deep dives (run each through the sandboxed script with crafted payloads, at least five
adversarial inputs per gate):
- `dangerous-bash-gate`: `rm -rf` variants; `rm -rf /tmp/x && rm -rf ~/src`;
  `git push --force` against `--force-with-lease`; `bash -c 'rm -rf …'`; quoted SQL
  `DROP TABLE`; a `backup/` substring in a comment; `find -delete`; `dd of=/dev/…`;
  `mkfs`; `chmod -R 777 /`; `curl … | sh`.
- `bash-write-gate` (deny layer off by default): heredoc, `tee`, `sed -i`, interpreter
  writes, `>` into a repo file against `/tmp`.
- `first-write-skill-gate`, `dox-write-gate` (repo without a root `CLAUDE.md`),
  `gateguard-write-gate` (importer counting; fire rate), `jcodemunch-enforce` (budget
  2, then open), `jdocmunch-enforce`, `graphify-enforce`, `blocking-doc-enforcer`.
- tdd-guard: `tdd_guard_launcher.py` → `tdd-guard-gate.py`; project detection, `$HOME`
  refusal, timeouts, advisory text quality, how often it adds value (output rate).
- `opus-guard.py`, `workflow-model-guard.py`: decisions in
  `hooks/.telemetry/*.model-routing.jsonl` (share of explicit `model` params, pins
  honoured, escalations, label mismatches).
- `subagent-context.py` (what it injects, size), `teammate-idle-gate.py` (run.json
  path resolution), `session-start-aggregator.py` (5,500-character budget; which core
  skills fit as bodies versus pointers), `memory-load-on-start.py`,
  `index-lifecycle.py` (NEVER_INDEX, ollama-down DEFER, detached builds, state
  machine), `session-lifecycle.py`, `settings-permissions-selfheal.py`.
- Weights loop (retired 2026-10-05: link `weights-loop` disabled, the feeder's `stop`
  mode removed): `weekly-retro-trigger.py`, `skill-router-weight-updater.py`,
  `skill-effectiveness-report.py`: confirm it stays a no-op without new input and that
  `skill_router_weights.json` is not rewritten when unchanged.
- `hard-completion-gate.py` (Gates 2–5, thresholds, `_INFRA_PATH_MARKERS`) and
  `lib/turns.py`: are Stop-hook feedback, `<task-notification>` rows and skill loads
  counted as user turns (`isMeta` rows)? Reproduce with a synthetic transcript.
- `invoke-suite-gate.py`: rank-1 MUST-READ pushes recorded with `enforce: "hard"` —
  can a misrouted skill block a code-writing turn?
- PostToolUse fan-out: `post-write-aggregator.py` (index journal, dox scaffold, doc
  enforcer, security scan), `mcp-post-hints.py`, `codex-capture.py`,
  `desloppify-cleanup.py`, `skill-invocation-tracker.py`,
  `security-semgrep-tracker.py`, `santa-method-writer.py`, `tool-failure-hint.py`.

### C. Prompt router → `$AUDIT/C-router.md`

FILES: `hooks/prompt_router/router.py`, `select.py`, `classify.py`, `budget.py`,
`manifest.py`, `router.config.json`, `modules/surface.py`, `modules/mcp_routes.py`,
`modules/code_intel.py`, `modules/model_advice.py`;
`hooks/autonomous-skill-router.config.json`, `hooks/skill_router.config.json`,
`hooks/skill_router_weights.json`, `hooks/skills-index.json` (structure plus samples),
`hooks/trigger-floor.json`, `hooks/ui-keywords.json`, `hooks/tool-intelligence.json`,
`hooks/skill-aliases.json`, `hooks/skill_router.py`.

CHECKS:
1. Classification: word boundaries, plurals, negations, URLs (does any URL trigger
   SECURITY?), tool names containing "guard", vague complaints ("it doesn't work",
   "blank page").
2. Scoring: keyword weights; is the half weight for description-derived keywords
   applied (compare the `source` value `select.py` checks with what the index builder
   writes); intent boost case matching; where `skill_router_weights.json` came from
   (which telemetry, how many sessions, when) and whether it is still fed.
3. Exclusions: are `disable-model-invocation` (hidden) skills ever pushed? core skills?
4. Surface detection for THIS project: run the sandboxed surface module on `PROJECT`
   and record the detected stack; is it right?
5. MCP route lines: emitted only for connected and authorized servers?
6. Output: size per prompt, share of fixed prose, char budget, how pushes are recorded
   (`pushed-skills.jsonl`, `enforce: "hard"`), per-project model-mode phrases.
7. Precision test. Write 30 natural prompts to `$AUDIT/router/prompts.txt` covering:
   FE bug, FE new component, UI polish, BE endpoint, DB migration, query performance,
   auth change, refactor across files, write tests, flaky test, failing CI, Docker or
   compose, deploy, docs update, code review request, security review, perf profiling,
   dependency upgrade, library API question, vague "it doesn't work", a prompt that
   contains a URL, a question about the codebase, a planning request, a quick one-line
   fix, a non-dev chat line, a Go task, a Python task, a SQL task, a mobile or Android
   task, a design-system task. Run each through the sandboxed router exactly as Claude
   Code does (UserPromptSubmit JSON on stdin with `prompt`, a `session_id` of
   `audit-router-<n>`, `cwd` = `PROJECT`), save outputs, record rank-1 skill, all
   pushes, MCP lines, characters and milliseconds. Score each: rank-1 right (yes/no),
   relevant pushes, noise. Report precision, recall of the obviously needed skill,
   mean output size, p50 and p90 latency. Re-run 10 of them with `cwd` = `$HOME` and
   compare. Then send 20 prompts under ONE session id and count repeated pushes (the
   raw router has no session memory; the mod's governor dedupes in live sessions).

### D. Skills catalog → `$AUDIT/D-skills.md`

FILES: every `skills/*/SKILL.md` and its `references/`; synced and plugin skills (paths
from `claude plugin list --json`); `hooks/skills-sources.json`,
`hooks/skills-provenance.json`, `hooks/core-skill-set.json`,
`docs/SKILL-HARMONIZATION.md`, the validator output from 2.5.

CHECKS, per skill (table row): name · source (local, vendored, synced, plugin) ·
description is one clear sentence with a real `when_to_use` · triggers curated or
auto-tokenised filler · `paths:` scope · `disable-model-invocation` · token cost ·
references resolve · stale references (removed plugins, moved rule files, missing
agents or skills) · contradictions and overlaps with other skills (and which one wins)
· last change (`git log -1`) · loads in the last 14 days (skill-invocation telemetry)
· verdict keep / fix / merge / retire.

CHECKS, catalog: size of the model's skill listing in tokens (all descriptions; the
mod's focus hides business-plugin families inside repos); can every development skill
be reached by a realistic prompt (use area C's results); core-skill injection against
the session-start budget; gaps for the full-stack target: React and Next.js App
Router, Vite, Node/Express/TypeScript backends, Go, Python/FastAPI, Postgres, MongoDB,
ClickHouse, Docker/Compose, CI/CD, Vitest, React Testing Library, Playwright,
observability, auth, TanStack Query, accessibility, performance budgets.

### E. Agents, /invoke and model routing → `$AUDIT/E-agents.md`

FILES: `agents/*.md`, `agents/README.md`, `skills/invoke/SKILL.md` and
`skills/invoke-*/SKILL.md`, `hooks/gen-invoke-skills.py`,
`hooks/gen-agent-skill-blocks.py`, `hooks/model-policy.json`, `hooks/opus-guard.py`,
`hooks/workflow-model-guard.py`, `workflows/*.js`, `scripts/model-mode.py`,
`hooks/lib/model_mode.py`, `hooks/lib/invoke_templates.py`, `hooks/lib/workflow_script.py`.

CHECKS: per agent frontmatter (model, effort never `max`, tools and disallowedTools,
skills preload list and its token cost, isolation); body against doctrine (no
commits, no servers, MCP first); artifact contracts consistent from producer to
consumer (IMPL-REPORT-BE `## CONTRACT` → frontend → integrator → closers); `/invoke`
act order, closers, run folders and every `run.json` schema in use; team flow (the
team lead can only be the main session); saved workflow models against
`model-policy.json`; what "resume" really does; single-act `/invoke-<act>` run-folder
selection; routing telemetry (explicit model share, escalations); every act's
artifact is named in its agent body (DESIGN-REPORT for uiux); an explicit `model` is
honoured only with the user's override phrase (pinned judges never downgraded
silently); `memory:` scope (`local` for per-repo notes); `agents/team-lead.md` is a
playbook with no frontmatter.

### F. Rules, instructions and memory → `$AUDIT/F-rules.md`

FILES: `CLAUDE.md`, `rules/*.md`, every local `CLAUDE.md`, auto-memory files, the
memory MCP graph (`mcp__memory__read_graph`, summarized, no secrets).

CHECKS: always-on token cost per turn (CLAUDE.md + `rules/0*.md`) and path-rule cost;
contradictions between rules, skills and agents; every referenced path, skill, agent
and command exists; rules no mechanism enforces (from the enforcement matrix);
duplicated guidance; local `CLAUDE.md` files match the files beside them; stale or
contradictory memories (files and MCP observations).

### G. MCP servers and plugins → `$AUDIT/G-mcp.md`

SOURCES: `installer/manifest.json` (`mcp_servers`, `mcp_roster`, `plugins`),
`claude mcp list`, `claude mcp get <name>` (never print env values),
`claude plugin list --json`, `~/.claude.json` server names only,
`~/.config/lean-ctx/config.toml` (read-only), `~/.code-index/config.jsonc`.

CHECKS, per server: role in the workflow and the doctrine line that requires it ·
scope · connects? · needs auth? · version pinned or `npx -y` latest? · one cheap
read-only probe with latency (jcodemunch `list_repos` and `resolve_repo` for
`PROJECT`, jdocmunch `doc_list_repos`, graphify `graph_stats`, memory `search_nodes`,
context7 `resolve-library-id` for a library the project uses, semgrep
`get_supported_languages`, sequential-thinking one thought; playwright and reticle:
status only, never launch a browser) · tool count and its listing cost (deferred or
loaded) · behaviour when down (do hooks stop suggesting it? does any gate depend on
it?).

CHECKS, plugins: per enabled plugin what it adds (skills, hooks that run every
session, MCP servers, commands), overlap with local skills, value; synced claude.ai
plugins and their listing noise.

CHECKS, indexes for `PROJECT`: jcodemunch index present and fresh, AI summaries on,
jdocmunch index, `graphify-out/` age, ollama embeddings healthy (doctor row), lean-ctx
config with zero injection.

Areas H (mercy mod), I (installer, CI) and J (state, hygiene): `references/areas-h-j.md`.

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
- **Test isolation env:** `CLAUDE_HOOK_TELEMETRY_DIR` (telemetry), `CLAUDE_HOOK_STATE_DIR`
  (`~/.claude/state`) and `CLAUDE_HOOK_DOTSTATE_DIR` (`hooks/.state`, honoured by every
  script that builds that dir and by `tools/state-cleanup.py`) redirect writers and readers.
  Both conftests set all three; `tools/link-doctor.py` gives its probe children a throwaway
  dir for each (unless already set). A full test run leaves 0 files in the live dirs.
- A per-session JSON state file that several hooks update goes through
  `lib/platform.locked_update(path, fn)` (flock on `<path>.lock`, atomic write), not a
  bare read + write. Appending a JSONL row goes through `plat.append_line` (`O_APPEND` is
  not atomic on Windows). Background processes start through `plat.spawn_worker` /
  `spawn_detached` (no console window); never a bare `Popen` or `start_new_session`.
- **`PowerShell` is a shell tool everywhere `Bash` is** (`tool_compat.SHELL_TOOLS` /
  `is_shell_tool`, the three shell matchers in `settings.template.json`, every `tools`
  field in `dispatch.config.json`, the gates, `lib/turns`, `tool-failure-hint`). Keep the
  three in step (`test_settings_wp3.py`, `test_powershell_gates.py`); a new shell gate calls
  `is_shell_tool`, never `tool == "Bash"`.
- Generated files — never hand-edit: `skills-index.json`, `trigger-floor.json`,
  `skills-provenance.json`, `skills/invoke*/`, agent `skills:` lines.

## Key files

| File | Role |
|------|------|
| `dispatch.py` / `dispatch.config.json` | per-event chain runner + link declarations (12 events, 42 enabled links; types gate/mutator/advisory/exec, `async` exec); `dispatch.py <event> --only <ids>` runs just those links (the mercy mod's bridge). Pass order: gates + mutators sequential in declared order, then execs, then advisories in parallel. `"defer": true` advisories run detached and land on the session's next PreToolUse/PostToolUse (`--only` keeps them sync). A deny ends the chain and carries earlier gate notes; an ask is held while later gates run. A lean-ctx call on several files runs once per path; the returned deny/ask carries the other paths' context (deferred advisories included). The char cap cuts on a line and appends `[truncated]`, gate notes first. Raw stdout counts only on exit 0. `ctx_shell`/`shell`/`ctx_patch`/`ctx_call` pass through every gate. Retired links stay declared with `"enabled": false` (`weights-loop`, `session-lifecycle-subagent`, `session-lifecycle-postcompact`). Async exec links and deferred advisories start through `plat.spawn_worker` (`CREATE_NO_WINDOW\|CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session` on POSIX: the old no-op flag killed self-heal children with `0xC0000142`); every synchronous link runs with a hidden console so its git / npm children open no window. Windows PowerShell tool calls reach the same links as Bash |
| `dispatch_support.py` | dispatcher helpers: lean-ctx tool-name adapter, the deferred-advisory queue (its fallback dir is `platform.state_dir()`; `enqueue` appends with `append_line`, `drain` replaces with `replace_file`), `spawn_deferred` / `run_deferred`, the char cap |
| `commit_docs_check.py` | commit tokenizer + doc-tree check behind `blocking-doc-enforcer.py` (judged from the files going into the commit; backslash paths and `/d/...` forms map correctly, so the gate does not fail open on Windows). A newline, `{` and `}` end a command like `;`; `git.exe` / a quoted path to it is git; `cd` / `chdir` / `Set-Location` / `sl` / `pushd` / `Push-Location` (also `-Path x`) move the directory; the payload of `powershell\|pwsh -c`, `bash -c`, `cmd /c`, `iex`, `eval` is scanned (two levels); backtick-newline joins lines (a trailing `\` before a newline is a path on Windows, a continuation elsewhere); a PowerShell here-string body (`@'…'@`, `@"…"@`) is one word, so an apostrophe inside cannot hide the commit; `#` is not a comment. Unresolved: `git -C $var`, UNC paths, a bash heredoc body that spells `git commit` on its own line |
| `connector-ask-gate.py` | PreToolUse `ask` gate for connector tools (G-02) |
| `prompt_router/` | UserPromptSubmit router — see its `CLAUDE.md` |
| `opus-guard.py`, `workflow-model-guard.py`, `model-policy.json` | sets `model` + `[label]` (Opus judges, Sonnet executes, `escalation` lifts executors), logs each decision to `.telemetry/<sid>.model-routing.jsonl`; never touches `prompt`/`name`. An explicit `model` moves a pinned judge, an executor or fable only when the user's own turn names that model (override phrase); otherwise the ignored request is named in the telemetry reason. Per-project mode outranks any explicit model |
| `subagent-context.py` | SubagentStart: write protocol, no-servers/no-commit, MCP protocol, surface pointer; in a pinned mode it says opus-guard applies the model, omit `model` |
| `teammate-idle-gate.py` | TeammateIdle: teammate can't idle until the expected artifact of the newest `run.json` that names the teammate exists (relative paths resolve against cwd or the run folder) |
| `mcp-post-hints.py` | PostToolUse "call X now" (semgrep, context7, reticle/playwright, postgres-patterns, blast radius) |
| `tool-failure-hint.py` | PostToolUseFailure: read-before-edit hints |
| `memory-load-on-start.py` | reads `memory/memory.jsonl` directly; matches the repo name with `_` and spaces normalised to `-` (`WATCH_SDK` finds `watch-sdk` entities, F-10); ranks fragile > decision > pattern, newest first, equal share of 1,200 chars; emits `search_nodes("<repo>")` |
| `hard-completion-gate.py`, `invoke-suite-gate.py` | Stop gates, ≤1 block per turn (`lib/turns.py`). The suite gate enforces only skills whose `paths`/one-sided surface match the turn's writes; generic or `enforce:"soft"` pushes become an advisory queued for the model's next prompt (`dispatch_support.enqueue`, drained at user-prompt-submit and tool events); hcg's pass advisories and same-turn override note go the same way. A Stop `systemMessage` shows only to the user, who cannot act on it (CLAUDE.md §11). A turn key "?" never persists nags or grants hcg's same-turn override. Every gate text is an instruction the MODEL runs now ("dispatch the docs-sync-agent now"), never a command for the user; hcg's Gate 7 (`lib/memory_gate.py`) blocks once when the human prompt said remember / going forward / we decided / from now on / always.. / never.. and the turn saved no memory. hcg's `CONSENT_RE` also takes `just`, `skip (the) verify/verification` and curly apostrophes (same clauses as the mercy mod's `consent.ts`) |
| `settings-permissions-selfheal.py` | session start/end + ConfigChange (`permissions-deny-guard`) keep `permissions.deny` empty |
| `gen-invoke-skills.py`, `gen-agent-skill-blocks.py` | generate `/invoke` skills and agent `skills:` blocks (`--check`) |
| `skills-sources.json` | vendored third-party skills (repo, ref, overrides) — consumed by `scripts/vendor_skill.py` |
| `skill-aliases.json` | alias → canonical map, resolved by `lib/skill_aliases.py` (`gsd-execute-phase` → `workflow-orchestrator`) |
| `index-lifecycle.py` | event-driven jcodemunch/jdocmunch/graphify/dox freshness, active repo only, no daemons; the jcodemunch db is the one whose recorded `source_root` is this checkout (same-named clones get their own); `_doc_name_for(root)` does the same for jdocmunch: the bare basename only when the manifest's `source_root` is this checkout (or absent), else `<name>-<sha1(realpath)[:8]>`. `reprobe --root <abs>` (CLI; the mercy mod and the graphify hooks call it) probes one root like session-start, claims locks, spawns the detached builders and prints ONE JSON line `{"surfaces": {...}, "spawned": [...]}` in ~2 s (non-git/NEVER_INDEX root: empty maps; UNAVAILABLE is reported FAILED plus an `unavailable` list). `post-write` also spawns one detached reprobe for a Bash `git commit/pull/merge/checkout/switch/rebase/reset/cherry-pick/revert/am/stash pop`. `build_fail` telemetry carries `err` (last 400 chars of the builder's stderr, secrets scrubbed). The per-repo state file is only written under `platform.locked_update` (`_update_state`): post-write appends to the journal and flushes inside the lock, a flush clears only what it flushed, and probes / builders persist just the surface records they computed (`_save_surfaces`), so concurrent hooks keep every journal entry (4 processes x 120 post-writes: 120 of 480 kept before, 480 of 480 after). `_load_state` retries a `PermissionError` 3 x 20 ms, then returns a blank flagged `_unreadable` that nothing persists |
| `dox_engine.py`, `dox-child-scaffold.py`, `dox-write-gate.py` | dox: git repos only, `$HOME` and `~/.claude` refused. `plan` also lists leaf docs (≤ 30 code files) that do not name their code files; a new child doc's Key files table lists them |
| `tdd_guard_launcher.py` → `tdd-guard-gate.py` | advisory tdd-guard, project repos only |
| `dangerous-bash-gate.py`, `gate_win.py`, `bash-write-gate.py`, `blocking-doc-enforcer.py` | PreToolUse Bash + PowerShell gates: destructive-command deny (also PowerShell-native: `Remove-Item -Recurse`, `rd`/`rmdir`/`del`/`erase /s`, `Format-Volume`, `Clear-Disk`, `format X:`, `git clean -f` unless that segment has `-n`; `rm\|rd\|rmdir -r` only in the PowerShell tool; recursive deletes allowed only under a temp dir; `powershell -c`, `cmd /c`, `iex` payloads are scanned). `gate_win.py` holds the Windows spellings: backtick-newline joins like `\`-newline (PowerShell tool only), a trailing `\|` continues the pipeline, `git.exe` and a quoted path to git / powershell / cmd are the bare program, `<producer> \| Remove-Item\|ri\|del\|erase` (`\| rm\|rd\|rmdir` in the PowerShell tool) is a delete unless the first stage lists only temp paths, `[IO.Directory]::Delete` / `DeleteDirectory` / `.Delete($true)` likewise, `cmd //c rd //s //q` (Git Bash's doubled slash), shell-write detector (deny layer opt-in; PowerShell `Set-Content` / `Add-Content` / `Out-File` / `[IO.File]::Write*` / `>` count; scratch, logs, build output and ABSOLUTE targets under `$TMPDIR` / `%TEMP%` / `$env:TEMP` / `%TMP%` are exempt, a relative target never is), `git commit` doc gate |
| `first-write-skill-gate.py`, `gateguard-write-gate.py` | PreToolUse write gates: first code write gets a hint (allow + absolute SKILL.md paths, once per surface, never a deny); `ask` on a high-blast-radius file, acknowledged after the write by the post link `gateguard-ack` |
| `jcodemunch-enforce.py`, `jdocmunch-enforce.py`, `graphify-enforce.py` | source read gate (budget 2, then advisory) + `mcp-used` tracker; doc-set read advisory; graphify nudge. A missing index in the active repo spawns the lifecycle build and the read passes on the first hit ("building in the background; use Read"); a stale graph runs `index-lifecycle.py reprobe` and says "graph rebuilding in the background". Config: `jcodemunch-enforce.config.json`, `jdocmunch-enforce.config.json`, `graphify-enforce.config.json` |
| `session-start-aggregator.py`, `core-skill-set.json` | SessionStart status + always-on skill digests; startup/clear only (resume/compact print `{}`); core skills at a fixed budget; runs `tdd-guard-init-guard.py` (per-project tdd-guard config); adds the `lib/session_notices.py` one-liners (mercy mod off by the remote rollout flag; the daily self-heal summary, once) |
| `ponytail-caveman-guard.py`, `session-lifecycle.py` | SessionStart style directive; breadcrumb keyed by git root (no cross-repo fallback), compact handoff (single injector), resume adds nothing; subagent-stop / post-compact are retired no-ops |
| `post-write-aggregator.py` | PostToolUse write fan-out, in parallel: `index-lifecycle.py post-write`, `dox-child-scaffold.py`, `doc-update-enforcer.py`, `security-scan-gate.py` |
| `fullstack-skills-reminder.py`, `skill_router.py` | PostToolUse only (stop mode removed 2026-10-05) FE/BE mandatory-skill reminder; path-ranked skills per write (`skill_router.py` drops index-`hidden` skills, baseline fill included). Config: `fullstack-skills-reminder.config.json`, `skill_router.config.json`, `skill_router_weights.json`. The generic review rules (`be_review_perf`, `be_review`, `fe_review`) are gone; `fe_ui_design` leads with `frontend-standards-always-follow`; `be_debug` matches debug/trace only and `be_errors` (error/exception filenames) leads with `backend-error-handling` |
| `codex-capture.py`, `desloppify-cleanup.py` | PostToolUse advisories: CODEX.md capture, wrap-up cleanup pass |
| `skill-invocation-tracker.py`, `security-semgrep-tracker.py`, `santa-method-writer.py` | PostToolUse evidence writers: skill telemetry, Gate 3 (semgrep ran), Gate 4 (santa fired) |
| `weekly-retro-trigger.py` | Stop (async; its link `weights-loop` is disabled): runs `skill-router-weight-updater.py` only when `skill-effectiveness.jsonl` changed since the last run and that run is >7 d old; the updater never rewrites an unchanged weights file. The feeder (fullstack stop mode) is retired, so in practice a no-op. `skill-effectiveness-report.py` is a CLI for people (`--top N`, `--json`), not run by any hook |
| `build-skills-index.py`, `build-trigger-floor.py` | build `skills-index.json` and `trigger-floor.json` |
| `autonomous-skill-router.config.json`, `ui-keywords.json`, `tool-intelligence.json` | router data: intent categories (also feeds `gen-invoke-skills.py`; the dead `IMPLEMENT.model` and per-category `closers`/`ceremony` keys are removed), UI keywords (`mobile` dropped), MCP routes (the browser route carries `text_by_server`) |
| `doc-enforcement.config.json`, `dox-write-gate.config.json`, `dox-tree-guard.config.json`, `index-lifecycle.config.json` | config for the doc enforcers, the dox gate and engine, and index-lifecycle |
| `graphify_launcher.py` | fail-open launcher for the graphify MCP server (the manifest registers it); no/foreign graph for the open repo spawns a detached `index-lifecycle.py reprobe` (log only) |
| `tool_compat.py` | tool-name helpers shared by the gates (Claude Code and Cursor names) |

## Gotchas / fragile spots

- Dispatcher and every link fail open; never let a link raise past its own try/except.
- `dangerous-bash-gate.py` matchers are linear (a gate that times out decides nothing): `_SegMatch`
  finds the leftmost head word in a segment and looks for the tail once (no `head[^;|&]*?tail`
  restarts, no bounded padding that could hide `-Recurse`), `_RmRf` judges the two words after each
  `rm`, `_GitSub` walks `git` global options token by token (an option's argument never starts with
  `-`; a failed start is not retried inside the options it consumed), `_DbDrop` / `_RmVar` replace two
  quadratic regexes, and `\<newline>` continuations are joined once before matching and before the
  safe-target suppressors (`gate_win.join_lines`: PowerShell adds backtick-newline and a trailing
  `|`). A newline ends a command for the delete rows. `test_gate_redos.py` holds
  the 50 KB floods (each within 20x a benign 50 KB run + 0.5 s, measured per test so load cannot
  flake it; worst measured 0.2 s) and `test_gate_equivalence.py` fuzzes the
  linear forms against the old regexes and pins the Bash verdicts of ordinary commands: add every
  new pattern to both (`test_gate_win_forms.py` is the deny / allow table of the Windows spellings).
  The only bounded run is `gate_win.DOTNET_FIRST_ARG` (`{0,300}`): a longer path reads as "not
  temp". A gate that exceeds its dispatch timeout still returns nothing (a synthetic `ask` on gate
  timeout is open). Unlisted by design: `-EncodedCommand`, `irm | iex`, `& 'Remove-Item'`,
  `Set-Alias`, a reassigned `$env:TEMP`.
- Mutator output must stay valid single-line JSON — the old multi-line `prompt` mutation
  was silently dropped for months.
- `index-lifecycle.py: NEVER_INDEX` excludes `$HOME`, `~/.claude`, `~/.codex`; this is
  deliberately not in `lib/repo_context.py` (gates still scope inside `~/.claude`).
- `index-lifecycle.py` runs the jcodemunch CLI with `os.environ` + `mcpServers.jcodemunch.env`
  from `~/.claude.json` (`_jcodemunch_env`): a hook-spawned CLI does not inherit the MCP
  server's `OPENAI_API_BASE`, and jcodemunch-mcp ≥1.108.319 then refuses api.openai.com and
  silently falls back to signature summaries. ollama is a systemd service: nobody starts or
  is asked to start it. `summarizer_healthcheck` (config): the DETACHED builder waits with
  backoff (`wait_s` 90); still down → a MISSING index builds with `--no-ai-summaries`, an
  existing one DEFERs (state STALE, dirty hash poisoned so the next probe retries). Session
  start prints one neutral line (`summarizer unavailable; index refresh deferred, retrying
  automatically`). The probe fails open; tests stub `_summarizer_alive` and `_sleep`.
- `lock_ttl_minutes` (30) must outlive the longest `build_timeouts_s` plus `wait_s`
  (`test_autonomy_wpb_builders.py` pins it). The telemetry `build_fail` counts through
  2026-10-04 (graphify 359, `lock_broken`/`probe_timeout`) were mostly pytest-fixture keys
  (`repo-<hash>`) written before test isolation, not real failures.
- Nothing wires Bash PostToolUse to `index-lifecycle.py post-write` yet (the aggregator link
  matches Write|Edit only): the git trigger needs a dispatch link on `Bash` (or the mod's
  HEAD watcher calling `reprobe`).
- Claude Code saves any hook `additionalContext` over 8,000 chars to a file and shows the
  model a 2 KB preview. Every `budgets.chars` stays under that; the aggregator keeps to
  `MAX_AGGREGATED_CHARS` (5,500) and builds the core block at a fixed budget (5,500 minus
  the static superpowers/MCP tail), so the same bodies arrive every session; overflow drops
  the tail blocks, then degrades to pointers (`test_session_start_budget.py`).
- Guards key on this checkout as well as `$HOME`: `NEVER_INDEX` and dox `resolve_root`
  include `Path(__file__)`'s repo. Under `CLAUDE_HOOK_DOCTOR` the aggregator spawns no
  index/tdd writers and `build-skills-index.py --hook` skips its rebuild. A sandbox-HOME
  test run once dox-swept the real `~/.claude`; a fresh checkout once lost its plugin
  skills from `skills-index.json`.
- `paths:`-scoped skills are unknown to the Skill tool until a matching file is read.
  The router says `Read ~/.claude/skills/<name>/SKILL.md` for them, and
  `gen-agent-skill-blocks.py` writes a `<!-- path-skills -->` Read block into agent bodies
  (their `skills:` preload silently skips those).
- tdd-guard (Sonnet via the Agent SDK) takes 4-7.3 s: gate 15 s < launcher 16 s < link 17 s.
- Windows: spawn npm CLIs by their `shutil.which` path (a bare name cannot start a `.cmd`
  shim), and normalise `\` to `/` before matching path fragments like `src/api/` — Claude
  Code sends native backslash paths (`prompt_router/modules/surface.prompt_paths` is the one
  choke point for the router). Probe URLs use `127.0.0.1`, not `localhost` (`::1` is tried
  first: 0.8-2 s per ollama probe). `plat.run` decodes UTF-8 and refuses an arg cmd.exe cannot
  carry; `selfheal-daily.py` stamps the day only when at least one step succeeded, passes
  `skip_optional=True` to `install_deps` and installs base tools through
  `basetools.ensure_base_tools` ([`tools/`](tools/CLAUDE.md)).
- The rendered `settings.json` has no `EIO_BACKEND` on Windows (semgrep scans die with the posix
  backend there); the template keeps it for POSIX.
- `lib/platform.py` sets `NoDefaultCurrentDirectoryInExePath=1` at import on Windows, so a bare
  tool name never resolves to a planted file in the cwd.
- `settings.json` is rendered — edit `settings.template.json`, then `installer/render.py`.
- `hard-completion-gate.py` exempts a session whose code writes are all `~/.claude`
  infra (`_INFRA_PATH_MARKERS`: hooks, rules, scripts, docs, mcp.profiles, installer,
  tests, mods, workflows, plans, agents, skills). jcodemunch never indexes `~/.claude`, so
  Gate 5 could never pass there: add any new top-level code directory of this repo to that
  tuple. Infra files never count toward the Gate 1/4/5/6 thresholds (B2-05).
- Mod bridge: `dispatch.py` skips the links listed in `MERCY_MOD_OWNED` when
  `MERCY_MOD_SESSION` equals the payload's `session_id` and `MERCY_MOD_BEAT` is under
  120 s old; the mercy mod runs them itself via `--only`
  ([`../mods/CLAUDE.md`](../mods/CLAUDE.md)). A link that looks dead in a
  session's telemetry may be owned: check those variables before debugging it.

- Telemetry rows: `prompt_router.live` carries `ms` (router wall time, A-10).
- `tools/state-cleanup.py` and `tools/retention-report.py` are the retention pair: the
  first deletes aged state, the second only reports reclaimable space ([`tools/`](tools/CLAUDE.md)).

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`lib/`](lib/CLAUDE.md) · [`prompt_router/`](prompt_router/CLAUDE.md) · [`tests/`](tests/CLAUDE.md) · [`tools/`](tools/CLAUDE.md)
- Related: [`README.md`](README.md), [`../rules/claude-infra.md`](../rules/claude-infra.md), [`../mods/CLAUDE.md`](../mods/CLAUDE.md)

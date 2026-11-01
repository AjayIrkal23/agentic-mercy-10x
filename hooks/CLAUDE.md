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
  for 13 events (UserPromptSubmit runs the prompt router as link `router`). Individual hooks
  are links in `dispatch.config.json` (`chains.<event>`), never separate settings entries.
- **Every hook stays its own file.** Add behavior as a new link, not by merging logic.
- **Portability:** commands use `{PY}`/`{HOOKS}`/`{NODE}` tokens (`lib/platform.py`); no
  raw `.sh` in the live path.
- **Never remove a trigger rule** — `build-trigger-floor.py --check` fails CI on a drop; a
  deliberate removal bumps `CHARTER` in `build-trigger-floor.py` (v3, 2026-10-30) and the
  `test_router_surface.py` pin.
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
| `dispatch.py` / `dispatch.config.json` | per-event chain runner + link declarations (15 chains, 13 registered events, 61 enabled links; `UserPromptSubmit` via link `router`; `crit_exempt` keeps a link through the crit memory profile); `dispatch.py <event> --only <ids>` runs just those links (the mercy mod's bridge; a `--only` run over budget logs `decision="slow-bg"`, `budget_hit=false`, never `budget-overrun`). Retired links stay declared with `"enabled": false` (`session-lifecycle-subagent`, `session-lifecycle-postcompact`). Last-known-good config (FIX2 item 2): whenever `dispatch.config.json` parses (a dict with a dict `chains`) it is copied to `state/dispatch.config.lkg.json` (atomic, only when it differs); a missing or corrupt config runs that copy (stderr + telemetry `decision="config-lkg"`, a `systemMessage` on session-start / user-prompt-submit); neither parses -> fail open loudly (stderr, telemetry `config-fail-open`, a `systemMessage` on every event that every gate is OFF). It never restores the live file itself. Pass order, deny/ask, char cap, spawn details: [`README.md`](README.md); history: `docs/CHANGELOG.md` v4.3.0 § dispatch.py |
| `dispatch_support.py` | dispatcher helpers: lean-ctx tool-name adapter, the deferred-advisory queue (its fallback dir is `platform.state_dir()`; `enqueue` appends with `append_line`, `drain` replaces with `replace_file`), `spawn_deferred` / `run_deferred`, the char cap |
| `commit_docs_check.py` | commit tokenizer + doc-tree check behind `blocking-doc-enforcer.py`; `git_adds(command, cwd)` lists every same-line `git add` / `git stage` (git's synonym, REVERIFY R4) (the secret scan dry-runs them: untracked files the command adds are scanned too, SP-3) (judged from the files going into the commit; backslash paths and `/d/...` forms map correctly, so the gate does not fail open on Windows). A newline, `{` and `}` end a command like `;`; `git.exe` / a quoted path to it is git; `cd` / `chdir` / `Set-Location` / `sl` / `pushd` / `Push-Location` (also `-Path x`) move the directory; the payload of `powershell\|pwsh -c`, `bash -c`, `cmd /c`, `iex`, `eval` is scanned (two levels); backtick-newline joins lines (a trailing `\` before a newline is a path on Windows, a continuation elsewhere); a PowerShell here-string body (`@'…'@`, `@"…"@`) is one word, so an apostrophe inside cannot hide the commit; `#` is not a comment. Unresolved: `git -C $var`, UNC paths, a bash heredoc body that spells `git commit` on its own line |
| `connector-ask-gate.py` | PreToolUse `ask` gate for connector tools (G-02) and github MCP write tools (ask everywhere, subagents and workflow scripts included: never an auto-deny since 2026-10-31, the session's permission mode decides) |
| `config-protection-gate.py` | PreToolUse ask on an existing lint/format config unless the prompt asked for it (ECC port) |
| `settings-protection-gate.py` | PreToolUse ask on any `.claude/settings{,.local,.user}.json`, `~/.claude/hooks/model-policy.json`, `~/.claude.json`, and (audit2 SP-2) the gates' wiring under the config dir: `hooks/dispatch.config.json`, every `hooks/*-gate.py`, `settings.template.json`, `installer/manifest.json`, `.blast-bypass` (Write/Edit, and a Bash/PowerShell write: redirect, tee, cp/mv/touch/truncate target, `sed -i`, interpreter write; a read-only `open(path)` is not a write; case-folded on Windows); escape for the wiring = the prompt names the basename; `hooks/dispatch.py` and `hooks/lib/*.py` stay unprotected on purpose; new files count, `~/.claude` in scope, never downgraded to an advisory and never auto-denied (2026-10-31, owner: a remote/app session runs with `CLAUDE_CODE_SESSION_ATTENDED=0` while the owner is present): it asks everywhere, subagent / restored / unattended / workflow / headless `-p` included, and the session's permission mode decides (live r3: `-p` bypassPermissions lets an ask through); escape = the prompt names the file (`.claude/settings…` path for the settings files, `/` or `\`; basename for `.claude.json` / `model-policy.json`) or a permission-rule phrase (`permission rule`, `allow rule`, `permissions.allow`, ...); bare "settings"/"permission" and a bare `settings.json` (VS Code's `.vscode/` file) do not escape (R2-F2, final-fix 1, FINAL-REVERIFY R1). FIX2 item 1 (REVERIFY R3; owner edit, FIX2-STEPS 10.1): a move, delete or restore is a write too: the file as any argument of `mv`/`rm`/`unlink`/`truncate`/`shred` (PowerShell `Remove-Item`, `Move-Item`, `del`, ...), `dd of=`, `git checkout\|restore\|rm\|mv`; a copy into a directory (`cp x ~/.claude/hooks/`); `~/.claude` itself and `hooks/` as a mv/rm target (no prompt escape); relative paths resolve after a `cd` / `git -C` earlier in the command (tokenizer from `commit_docs_check`; an unbalanced quote falls back to a hand split); `state/dispatch.config.lkg.json` is wiring too. Residual: `git checkout <branch>`, `git stash`, `find -delete`, `xargs rm` |
| `hookify-gate.py` (+ `lib/hookify_rules.py`) | repo-local `.claude/hookify.*.local.md` rules; untrusted input with hard caps; gate on pre-tool-use, advisory on prompt/stop |
| `memwatch-ensure.py` | SessionStart async exec: starts claude-memwatch, or runs oomguard_setup.ensure when the unit is missing; a hung systemctl ends it |
| `memwatch-brake.py`, `memwatch.config.json` | PreToolUse gate: warn advisory once per tier per session, crit ask or advisory via lib/gate_mode; config = sentinel thresholds (MemAvailable lines in percent of MemTotal: warn 15, crit 8, emergency 4, swap rule 22.5), ladder lists |
| `router-budget.json` | live misroute budget for `scripts/router_replay.py --check` (rates of routed prompts; baseline union 0.292 on 2026-10-30; `egm_on_small` added 2026-10-31). Never raise a max to pass: add the pattern to `tests/fixtures/router_corpus.jsonl` and fix the router. The replay also reports recall (`zero_skill_dev`, `audit_no_audit_skill`, `stack_skill_missed`, `infra_got_fe_skill`, zero-skill share, distinct skills pushed), unbudgeted |
| `session-ledger.py` | SessionStart/SessionEnd exec: live-session ledger `state/live-sessions/<sid>.json` {pid of the claude process via the /proc chain, cwd, transcript, tmux pane, scope, started, seen, boot_id, restored}; startup emits `sessionTitle` `<repo> <date>`; end unlinks; `dead_entries(max_age)` and `mark_restored(sid)` are what `scripts/restore_sessions.py` reads; Windows no-op |
| `plan-tier-detect.py` | SessionStart exec: the only credentials reader; `state/plan-tier.json`; notice on change; re-renders settings (`installer/render.py`, detached) on a tier flip; the daily `_tier_drift` stays the safety net |
| `context-monitor.py` | PostToolUse p1: loop/scope/compaction nudge (from 85 % of the window, then every 60k; "keep going", never "stop new work"); `state/<sid>.toolring.json` |
| `stop-format-typecheck.py` | Stop gate: once per turn, `--check` only, tsbuildinfo under `state/typecheck/`, skipped at warn+ |
| `stop-failure-log.py` | StopFailure exec: one telemetry row per API-error stop; `state/<sid>.stop-failure.json` only for rate_limit (`restore_sessions --resume-after-limit` reads it) |
| `instructions-loaded-log.py` | InstructionsLoaded async exec: one row per loaded CLAUDE.md/rules file into `.telemetry/<YYYY-MM-DD>.instructions-loaded.jsonl` (`measure_context_cost.py --observed`) |
| `observe-log.py`, `learning.config.json` | PostToolUse + PostToolUseFailure async exec (`observe-log`, `observe-log-failure`): one scrubbed row `{ts,sid,tool,summary,ok,files,error?}` <= 2 KB into `state/learning/<repo_key>/observations.jsonl` (`model_mode.repo_key`); skip list and `observe_infra` from `learning.config.json`; write-tool rows hold lengths, never content; `{}` and exit 0 always; doctor/link-doctor no-op |
| `prompt_router/` | UserPromptSubmit router — see its `CLAUDE.md` |
| `opus-guard.py`, `workflow-model-guard.py`, `model-policy.json` | sets `model` + `[label]` from the tier x role matrix (max20 since 2026-10-31: Opus judges, executors, tests and verify, Sonnet floor; max5: Sonnet executes; `escalation` lifts executors), logs each decision to `.telemetry/<sid>.model-routing.jsonl`; never touches `prompt`/`name`. An explicit `model` moves a pinned judge, an executor or fable only when the user's own turn names that model (override phrase); otherwise the ignored request is named in the telemetry reason. Per-project mode outranks any explicit model; `turn_caps` (agent caps, role floors, reserve). Pro (D6): `tiers.pro.ask_only` = sonnet, opus, so an unphrased explicit model there falls back to the role route, and no fable floor lifts a Haiku role on Pro (`workflow-model-guard` matches `model_mode`); the tier cap still applies to a stored per-project pin or a session flag |
| `subagent-context.py` | SubagentStart (≤ 3,000 chars; the MCP line is never cut): write protocol, no-servers/no-commit, full MCP protocol, ONE `ToolSearch "select:…"` line for the core MCP tools, the repo's exact ids (`REPO <root>: jcodemunch repo=…; graphify project_path=…; jdocmunch repo=…; memory search_nodes(…)`, `lib/mcp_ids`), FE/BE SKILL.md paths from the repo stack (`prompt_router.modules.surface.stack_fingerprint`, read-only), surface pointer; EGM goldfish reviewers + synthesizer get only the delivery head + untrusted line (`lib/agent_kinds`); in a pinned mode it says opus-guard applies the model, omit `model`; + delivery contract, turn-cap and 3-cycle lines, untrusted-content line, memory line at warn+, dox read line for `omitClaudeMd` agents; turn-cap line = the agent's `maxTurns` + deliver-by turn (`turn_caps.report_reserve`) |
| `teammate-idle-gate.py` | TeammateIdle: teammate can't idle until the expected artifact of the newest `run.json` that names the teammate exists (relative paths resolve against cwd or the run folder) |
| `mcp-post-hints.py` | PostToolUse "call X now" (semgrep, context7, reticle/playwright, postgres-patterns, blast radius) |
| `tool-failure-hint.py` | PostToolUseFailure: read-before-edit hints + OOM collateral hint from `oomguard.events` (90 s), tool-cap inference (exit 137 + `CLAUDE_CODE_TOOL_MEMORY_LIMIT`, the only writer of `source:"toolcap"`), MCP failure cache `state/<sid>.mcp-unhealthy.json` |
| `memory-load-on-start.py` | reads `memory/memory.jsonl` directly; matches the repo name with `_` and spaces normalised to `-` (`WATCH_SDK` finds `watch-sdk` entities, F-10); ranks fragile > decision > pattern, newest first, equal share of 1,200 chars; emits `search_nodes("<repo>")` |
| `hard-completion-gate.py`, `invoke-suite-gate.py` | Stop gates, ≤1 block per turn (`lib/turns.py`). Every gate text is an instruction the MODEL runs now, never a command for the user; history: `docs/CHANGELOG.md` v4.3.0 § hard-completion-gate.py |
| `settings-permissions-selfheal.py` | session start/end + ConfigChange (`permissions-deny-guard`) keep `permissions.deny` empty in `settings.json` and, since 2026-10-31, in `~/.claude/settings.local.json` (other keys kept; a tool-pruning plugin had written 467 rules there). In the active repo (git root of the payload `cwd`, never `$HOME` or this checkout) it drops bare tool-name rules (`LSP`, `mcp__x__y`) from `.claude/settings.local.json` and keeps scoped ones (`Read(./.env)`), on start, end and ConfigChange (2026-10-31; TokenEconomizer `toolprune` is `off` in `~/.tokeneconomizer/config.json`) |
| `gen-invoke-skills.py`, `gen-agent-skill-blocks.py` | generate `/invoke` skills and agent `skills:` blocks (`--check`) |
| `skills-sources.json` | vendored third-party skills (repo, ref, overrides) — consumed by `scripts/vendor_skill.py` |
| `skill-aliases.json` | alias → canonical map, resolved by `lib/skill_aliases.py` (`gsd-execute-phase` → `workflow-orchestrator`) |
| `index-lifecycle.py` | event-driven jcodemunch/jdocmunch/graphify/dox freshness, active repo only, no daemons. Builders defer (`DEFERRED`, no failure count, `build_deferred_memory`) at tier warn+ from `state/mem-pressure.json` (dox always runs; graphify keeps a 12 GiB `MemAvailable` floor when no tier file exists, scaled by RAM on a smaller box and never below `fallback_floor_mb` 6000); a first graphify build (no `graphify-out/graph.json`) gets `build_timeouts_s.graphify_first` (1200 s) and every graphify build `--max-workers max(2, min(8, cpu//3))`; jcodemunch outside its `trusted_folders` (`<CODE_INDEX_PATH>/config.jsonc`, default `[HOME]`) is UNAVAILABLE, noted once, never retried; a builder timeout row keeps its `timeout; rc=124` head; every builder runs as `systemd-run --user --scope --unit claude-index-<surface>-<key8>` with `MemoryHigh=3G MemoryMax=5G MemorySwapMax=0 CPUWeight=20 IOWeight=20 nice ionice` (plain on Windows/no bus); thresholds in `index-lifecycle.config.json` `memory`; summarizer deferrals log `build_deferred_summarizer`. history: `docs/CHANGELOG.md` v4.3.0 § index-lifecycle.py |
| `dox_engine.py`, `dox-child-scaffold.py`, `dox-write-gate.py` | dox: git repos only, `$HOME` and `~/.claude` refused. The root-gate deny names the absolute `skills/dox-doc-tree/SKILL.md` to Read (a `paths:` skill the Skill tool cannot load yet). `plan` also lists leaf docs (≤ 30 code files) that do not name their code files; a new child doc's Key files table lists them; a code write into a documented leaf dir whose `CLAUDE.md` does not name the file gets one advisory per dir per session (test files skipped, `_TEST_RE`) |
| `tdd_guard_launcher.py` → `tdd-guard-gate.py` | advisory tdd-guard, project repos only |
| `dangerous-bash-gate.py`, `gate_win.py`, `bash-write-gate.py`, `blocking-doc-enforcer.py` | PreToolUse Bash + PowerShell gates: destructive-command deny (also PowerShell-native: `Remove-Item -Recurse`, `rd`/`rmdir`/`del`/`erase /s`, `Format-Volume`, `Clear-Disk`, `format X:`, `git clean -f` unless that segment has `-n`; `rm\|rd\|rmdir -r` only in the PowerShell tool; recursive deletes allowed only under a temp dir (`$R` / `${R}` resolve through the command's own whole-segment literal `R=/tmp/...` / `R=$(mktemp …)` statement, `_literal_vars`, only when it is the name's one bare mention, comes before the first command-position `rm` and has no `&&` / `||` / `|` ahead of it; a reassigned, `unset`, loop/`read` variable, prefix assignment or non-plain value stays unknown, santa review 2026-10-31); `powershell -c`, `cmd /c`, `iex` payloads are scanned). `gate_win.py` holds the Windows spellings: backtick-newline joins like `\`-newline (PowerShell tool only), a trailing `\|` continues the pipeline, `git.exe` and a quoted path to git / powershell / cmd are the bare program, `<producer> \| Remove-Item\|ri\|del\|erase` (`\| rm\|rd\|rmdir` in the PowerShell tool) is a delete unless the first stage lists only temp paths, `[IO.Directory]::Delete` / `DeleteDirectory` / `.Delete($true)` likewise, `cmd //c rd //s //q` (Git Bash's doubled slash), shell-write detector (deny layer opt-in; PowerShell `Set-Content` / `Add-Content` / `Out-File` / `[IO.File]::Write*` / `>` count; scratch, logs, build output and ABSOLUTE targets under `$TMPDIR` / `%TEMP%` / `$env:TEMP` / `%TMP%` are exempt, a relative target never is), `git commit` doc gate. Since 2026-10: heredoc bodies into shells/DB clients are scanned; the `git-bypass` group is denied on every attempt; a dev-server start asks (skipped when the mod guard is live); telemetry on every verdict; `HUSKY=0` / `SKIP=` before a commit/push and a persistent `git config core.hooksPath` to /dev/null, "" or a missing absolute dir join the git-bypass group (SP-6); `blocking-doc-enforcer.py` adds a staged-secret scan that also reads untracked files a same-command `git add` adds (first 256 KB, binaries skipped) |
| `first-write-skill-gate.py`, `gateguard-write-gate.py` | PreToolUse write gates: first code write gets a hint (allow + absolute SKILL.md paths, once per surface, never a deny); `ask` on a high-blast-radius file, acknowledged after the write by the post link `gateguard-ack`; sensitive/secret targets ask (secret ignores `.blast-bypass`); asks go through `lib/gate_mode` |
| `jcodemunch-enforce.py`, `jdocmunch-enforce.py`, `graphify-enforce.py` | source read gate + `mcp-used` tracker; doc-set read gate; graphify nudge. Since 2026-10-31 (audit 02 B-02..B-05): state keyed per AGENT (`<sid>.<agent_id>`; the Gate 5 dead-code marker and Gate 3 semgrep state stay on the plain sid), budget = one deny per agent per user turn (`lib/turns.turn_key`; a new turn resets the counters and `jcodemunch_calls`), no relax while a STALE index rebuilds (only MISSING relaxes), deny text names the exact call with the real id (`search_symbols(repo="<id>", query=…)` / `get_file_outline(repo=…, file_path=…)`, `lib/mcp_ids`), worded on completeness, never tokens; link `jcm-gate-shell` sends Bash/PowerShell reads (`grep/rg/cat/sed -n/head/tail/find`, `lib/shell_reads`) through the same gates; jdocmunch: docs ≥ 2,000 bytes, first whole read per agent per turn denied with `search_sections(repo="local/<name>", …)` (needs link type `gate`), then advisory; EGM goldfish agent types pass both gates (`lib/agent_kinds`). A missing index in the active repo spawns the lifecycle build and the read passes on the first hit ("building in the background; use Read"); a stale graph runs `index-lifecycle.py reprobe` and says "graph rebuilding in the background". A Grep with no path or a directory path stands for `<dir>/<glob leaf \| x.<type> \| x.py>` (`_grep_target`), so a bare `Grep pattern` in a repo is gated; outside a project repo it passes. graphify-enforce resolves the repo from the payload `cwd` (CLAUDE_PROJECT_DIR is the launch dir, often `~`), names `project_path="<root>"` (the MCP keeps its start-up graph, an empty placeholder when the session began outside the repo) and never pushes an infra root's graph (`lib/code_files.is_infra_root`). Config: `jcodemunch-enforce.config.json`, `jdocmunch-enforce.config.json`, `graphify-enforce.config.json` |
| `session-start-aggregator.py`, `core-skill-set.json` | SessionStart status (no core skill block since 2026-10-31: the bodies load through `../CLAUDE.skills.md`); startup/clear only (resume/compact print `{}`); runs `tdd-guard-init-guard.py` (per-project tdd-guard config); style directive block once (the caveman sentence is dropped under the caveman output style); per-source caps index/ids/notices/style/mcp = 600/400/600/700/700 (ids = `MCP ids for this repo`: the exact jcodemunch `repo`, graphify `project_path`, jdocmunch `repo` from `lib/mcp_ids`, B-07; the index header no longer says "no agent action required"); notices via `getattr`: mod-off, plan tier (`plan tier <tier> · main <model>`), self-heal, OOM guard, worktree, instincts; no `### Superpowers plugin` block while the superpowers plugin is enabled (its own SessionStart prints it); the 24 h sweep spares breadcrumbs and runs only on startup/clear. `core-skill-set.json`: the always-on list that `../CLAUDE.skills.md` `@`-imports in full (`tests/test_skills_wp2.py` keeps the two in step) and `scripts/skill_health.py` keeps described |
| `session-lifecycle.py` | breadcrumb keyed by git root, capped 1,500, `handoff` template worked/evidence/did-not-work/not-tried/next-step/files; `.continue-here.md` capped 1,500 and wrapped as historical reference, placeholder files rejected; compact handoff single injector; resume adds nothing; subagent-stop / post-compact are retired no-ops |
| `post-write-aggregator.py` | PostToolUse write fan-out, in parallel: `index-lifecycle.py post-write`, `dox-child-scaffold.py`, `doc-update-enforcer.py`, `security-scan-gate.py` |
| `fullstack-skills-reminder.py`, `skill_router.py` | PostToolUse only (stop mode removed 2026-10-05) FE/BE mandatory-skill reminder; path-ranked skills per write (`skill_router.py` drops index-`hidden` skills, baseline fill included; no weights file). Config: `fullstack-skills-reminder.config.json`, `skill_router.config.json`. The generic review rules (`be_review_perf`, `be_review`, `fe_review`) are gone; `fe_ui_design` leads with `frontend-standards-always-follow`; `be_debug` matches debug/trace only and `be_errors` (error/exception filenames) leads with `backend-error-handling` |
| `codex-capture.py`, `desloppify-cleanup.py` | PostToolUse advisories: CODEX.md capture, wrap-up cleanup pass |
| `skill-invocation-tracker.py`, `security-semgrep-tracker.py`, `santa-method-writer.py` | PostToolUse evidence writers: skill telemetry, Gate 3 (semgrep ran; since B-08 also `scanned_at` per target path, MCP `code_files`/`paths` or CLI positionals, for a per-file freshness check), Gate 4 (santa fired) |
| `build-skills-index.py`, `build-trigger-floor.py` | build `skills-index.json` and `trigger-floor.json` (charter v3, 2026-10-30: audit2 A2 dropped conversational DEBUG/REVIEW phrases; 2026-10-31 `tokens` is a vague UI word, weight 0.4, no rule dropped) |
| `plugin-skill-triggers.json` | curated router triggers for plugin skills (keywords, router-category intents, surfaces), merged by `scripts/build_skills_index.py` into the per-machine plugin sidecar with full weight (audit A-05); a plugin skill without an entry stays description-derived at half weight and is listed by `build-skills-index.py --check` |
| `autonomous-skill-router.config.json`, `ui-keywords.json`, `tool-intelligence.json` | router data: intent categories (also feeds `gen-invoke-skills.py`; the dead `IMPLEMENT.model` and per-category `closers`/`ceremony` keys are removed), UI keywords (`mobile` dropped), MCP routes (the browser route carries `text_by_server` and `"all": true`: a QA/VERIFY intent AND a browser phrase) |
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
  deliberately not in `lib/repo_context.py` (gates still scope inside `~/.claude`). Every
  other hook asks `lib/code_files.is_infra_root` (the same list); change both together.
- `_index_db_for` matches a db by recorded `source_root`: the folder-name globs first, then
  every other `~/.code-index/*.db` (dbs are named after the git remote, e.g.
  `Docketrun-Tech-assets_management.db` for `SubStore`; those repos probed MISSING and
  rebuilt every session until 2026-10-08). Only a name-matched db without `source_root`
  counts as legacy. A flush skips a surface in FAILED backoff; the next probe retries it.
- `index-lifecycle.py` runs the jcodemunch CLI with `os.environ` + `mcpServers.jcodemunch.env`
  from `~/.claude.json` (`_mcp_env`): a hook-spawned CLI does not inherit the MCP
  server's `OPENAI_API_BASE`, and jcodemunch-mcp ≥1.108.319 then refuses api.openai.com and
  silently falls back to signature summaries. The jdocmunch CLI gets `mcpServers.jdocmunch.env`
  (embedding provider, telemetry off) and embeds only when the doc index already has a vector
  sidecar (`<name>.embeddings.jsonl`, `_doc_vectors`): then changed docs are embedded, the cap is `build_timeouts_s.jdocmunch_embed` (900: a new
  `OLLAMA_HOST` or model changes the sidecar identity and jdocmunch re-embeds the whole corpus)
  and ollama down DEFERs like jcodemunch (a lexical save would leave those sections without
  vectors until they change again). Every other doc index runs `--embeddings off`: a first embed
  of a large corpus (CONCORD-WEBSITE, 295k sections) cannot finish in a hook, and before
  2026-10-21 no hook build embedded at all (site-sync-vista sat at 12k of 29k vectors for 16
  days). ollama is a systemd service: nobody starts or
  is asked to start it. It may live on another machine: the probe URL is
  `<plat.ollama_url()>/api/tags` (`OLLAMA_HOST` from `settings.user.json` env, else
  127.0.0.1:11434) unless the config names a `url`.
  `summarizer_healthcheck` (config): the DETACHED builder waits with
  backoff (`wait_s` 90); still down → a MISSING index builds with `--no-ai-summaries`, an
  existing one DEFERs (state STALE, dirty hash poisoned so the next probe retries). Session
  start prints one neutral line (`summarizer unavailable; index refresh deferred, retrying
  automatically`). The probe fails open; tests stub `_summarizer_alive` and `_sleep`.
- `lock_ttl_minutes` (30) must outlive the longest `build_timeouts_s` plus `wait_s`
  (`test_autonomy_wpb_builders.py` pins it). The telemetry `build_fail` counts through
  2026-10-04 (graphify 359, `lock_broken`/`probe_timeout`) were mostly pytest-fixture keys
  (`repo-<hash>`) written before test isolation, not real failures.
- Bash/PowerShell PostToolUse reaches `index-lifecycle.py post-write` only through the async
  link `index-git-reprobe` (`command_re` on `git`); the aggregator link still matches
  Write|Edit only, so files a shell command creates are journaled by the next reprobe, not
  per write.
- The graphify MCP server hot-reloads only the graph file it was started with
  (`graphify_launcher.py`): a session launched in `~`, or before the repo's graph existed,
  serves an empty placeholder all session. Every graphify hint (router, graphify-enforce,
  subagent-context, `rules/00`) therefore names `project_path`.
- Claude Code saves any hook `additionalContext` over 8,000 chars to a file and shows the
  model a 2 KB preview. Every `budgets.chars` stays under that; the aggregator keeps to
  `MAX_AGGREGATED_CHARS` (5,500) (`test_session_start_budget.py`). Skill bodies never go
  through a hook for that reason: the core set loads by `@` import (`CLAUDE.skills.md`).
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

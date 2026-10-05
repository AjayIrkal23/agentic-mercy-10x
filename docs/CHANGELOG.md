# Changelog

## v4.0.2 — 2026-10-05 the test suite passes on Windows

Why: once the suite collected on Windows (`70c744d`), it showed 34 failures on the replica and
in CI's windows leg. Now Windows 1131 passed / 3 skipped (each with its reason), Ubuntu 1134
passed. Two were real bugs:

- `safe_fetch.extract_prefix` judged tar member names with the native `Path`: on Windows
  (Python 3.13+) `/abs/evil` is not absolute (no drive), so it was extracted inside the prefix
  instead of skipped. Names are now judged as POSIX paths on every OS, plus any drive and `..`
  written with backslashes (`_absolute`, `_escapes`).
- bash-write-gate only exempted `$TMPDIR` and compared against `<tmpdir>/`, so no Windows temp
  path ever matched. It now exempts ABSOLUTE targets under `$TMPDIR`, `%TEMP%` or `%TMP%`,
  compared with native separators and case; a relative target stays a project write even when
  the cwd is in temp.

The rest were POSIX assumptions in tests: the fake `claude` and `tdd-guard` were shebang
scripts (now with a `.cmd` shim, the real npm-shim path), tests set `HOME` but `Path.home()`
reads `USERPROFILE` on Windows, the POSIX install logic needed `os_arch` forced to linux,
paths were compared with `/`, and NTFS has no `0o600`. One test is skipped on Windows:
symlink traversal inside an extracted tarball (Windows tools ship as zips). Also
`db13721`: the `/deps` mod-test fixture (the engine resolves the test cwd `/r` to a drive
path); `70c744d`: no module-level `import fcntl` in the selfheal-daily test.

## v4.0.1 — 2026-10-05 Windows end-to-end run 2 fixes

Merges branch `win-e2e-fixes-2026-09-30` (commit `50e7372`, written 2026-09-30 on the
Windows replica, never merged until now). Why: the second end-to-end run on the Windows
replica found gates that were silent on Windows or could be satisfied without doing the
work.

- tdd-guard never ran on Windows: `tdd-guard-gate.py` spawned the bare name `tdd-guard`,
  an npm `.cmd` shim that CreateProcess cannot start, and the fail-open swallowed the
  FileNotFoundError. It now spawns the `shutil.which` path and talks UTF-8 both ways
  (a cp1252 locale would have dropped any advisory containing "”").
- dangerous-bash-gate missed `git -C <dir> reset --hard`, `git --work-tree <x> reset
  --hard` and `git -c k=v push --force`: the patterns needed the subcommand right after
  `git`. Git global options are skipped now, with a token pattern that cannot backtrack
  exponentially. Merge resolution: the push pattern keeps v4's `--force(?![-\w])`, so
  `--force-with-lease` / `--force-if-includes` still pass (the branch's `--force\b` would
  have denied them).
- Gate 3 credited any semgrep MCP call, so `get_supported_languages` alone passed it. Only
  `semgrep_scan*` counts now. Merge resolution: its test reads the state file, because v4
  replaced the tracker's `_load_state` with `locked_update`. The mod's bridge still runs
  the link on any `mcp__semgrep__` call; the link decides the credit.
- codex-capture never fired on Windows, and the skip lists of gateguard,
  security-scan-gate and doc-update-enforcer (`node_modules/`, `dist/`, `docs/`,
  `.claude/`, …) never matched there: all compared forward-slash patterns against the
  backslash paths Claude Code sends. All four normalise separators now.
- bash-write-gate, tool-failure-hint and doc-update-enforcer named rule files that no longer
  exist (`rules/no-permission-bypass.md`, `rules/file-work-and-gate-routing.md`,
  "mandatory-skill-protocol"). A test now fails when a hook names a missing `rules/` file.

## v4.0.0 — 2026-10-05 release

Everything since the v3.0.0 tag, released as one major: the sections from here down to
v3.1.0 (Sonnet 5.5 routing, the mercy mod, the UI deck and status line, autonomy by
default, the one-command fresh-Ubuntu installer, two workbench audit passes). Major
because the runtime changed shape: an in-process TypeScript mod (`mods/mercy`, Claude Code
≥ 2.1.288) now owns part of the hook chain, `settings.json` gains a status line and
`CLAUDE_CODE_PLUGIN_DIRS`, and the installer installs base tools into `~/.local`.

- Proof at release: pytest 1125 passed (CI env and a bare `HOME`), mod tests 156 passed,
  doctor `--ci` 15 PASS 0 FAIL, `render.py --check`, skills R9/R10, trigger floor,
  generators, grep gates 5/5, `validate_mods.py` all green.
- Release fix: the WP-B re-probe tests (`test_autonomy_wpb_reprobe.py`,
  `test_autonomy_wpb_gates.py`) now clear `CLAUDE_HOOK_DOCTOR`; CI exports it for the
  pytest step and the git trigger no-ops under it, so 16 tests failed in CI only.
- `.gitignore`: `/debug/` (Claude Code debug logs hold full transcripts).
- Windows: the base-tools installer (`userspace.py`, `basetools.py`, `ostools.py`) and the
  mod's sound, desktop notification and port scan are Linux-only so far; the Windows
  replica still installs through `install.ps1` and needs a parity pass.

## 2026-10-05 — autonomy by default (CLAUDE.md §11)

The user only prompts; everything triggers by itself. Plan, audits and reviews:
`plans/autonomy-2026-10-05/` (gitignored).

- **Doctrine**: `CLAUDE.md` §11 (autonomy by default, MCP servers and packages included);
  Memory MCP `decision::.claude::workbench`; auto-memory `autonomy-by-default`.
- **mercy mod, commands become jobs** (`features/auto.tsx`, `lib/auto.ts`): ports scanned every
  minute (toast when a dev server comes up or stops), npm outdated daily per package folder,
  today's standup at the first session of the day (Monday reaches back to Friday), the
  session recap saved after every turn and shown by the next session, compaction between
  turns at `autoCompact` (85 %; at most every 10 min; keeps plan, tasks, unverified files)
  instead of a `/compact` toast. New pane tabs: today (s, copy y), ports (p), deps (d).
  `deck.tsx` re-probes the indexes when HEAD moves (terminal commits included); the status
  text shows hook errors. Commands stay as optional extras.
- **Indexes refresh themselves** (`index-lifecycle.py`): `reprobe --root` CLI (0.1 s), a
  detached re-probe after HEAD-moving git commands, build stderr (scrubbed) in `build_fail`
  telemetry, ollama down → the builder waits with backoff instead of asking; the jcodemunch
  gate starts the build and lets the first read through; the graph advisories rebuild
  instead of naming `graphify update`. No CLI path for embeddings exists (MCP `embed_repo` only).
- **No text addresses the user**: `/model opus` advice → dispatch the Opus judge agent;
  `/invoke <act>` and the Stop gates' slash commands → dispatch the agent with the Agent
  tool; a memory gate blocks once when the prompt said remember / going forward / we decided
  and nothing was saved; Higgsfield is pushed only when authorized (else one batched login
  ask); mod-off and self-heal notices at session start; state-cleanup purges test residue
  with a log.
- **MCP servers and packages heal themselves**: `deps.reconcile_mcp_pins` (remove → add-json →
  restore, env copied verbatim) and a daily async `selfheal-daily` link (pins, missing CLIs,
  settings re-render, vendored drift; locked, logged, summary reported once). All 8 drifted
  servers now run their pins; every manifest MCP spec is exact.
- **render.py**: allow rules granted in Claude Code's permission dialog (`permissions.allow`)
  are Claude-managed: ignored by the equivalence check and kept by every re-render.
- **Santa review** (`SANTA-autonomy.md`), fixed test-first: the memory gate reads cues only as
  sentence-initial commands outside code, quotes and questions ("I don't remember which file…"
  no longer blocks); build-failure telemetry scrubs quoted keys, Bearer JWTs, URL credentials
  and AKIA/AIza/hf_ keys; a compaction a racing prompt rejected is retried after the next turn;
  the mod always sets `MERCY_MOD_LOADED` so a stale flag never prints "mod off". The installer
  items (restore exit code, user settings kept by the daily re-render, a pytest guard for
  selfheal-daily) went to the installer package.
- **Stop notes reach the model, not the user's screen**: the suite gate's "pushed skills not
  loaded" advisory, the completion gate's pass advisories and its same-turn override note were
  Stop `systemMessage`s, which only the user sees and cannot act on. They now go to the
  session's advisory queue (`dispatch_support.enqueue`), which the next prompt delivers to the
  model (`dispatch.py` drains it at user-prompt-submit as well as tool events).

## 2026-10-05 — UI deck (mercy mod) and status line

Plan and research: `plans/ui-mods-2026-10-05/` (gitignored).

- **Status line**: `scripts/statusline.py` as the settings `statusLine` (template + render;
  `tests/test_template_contract.py` now allows our own and still bans lean-ctx's). One line:
  model and effort, context bar, cost, 5-hour window with reset time (7-day from 50 %), git
  branch with staged/modified/untracked/ahead/behind (cached 5 s), session time, lines changed.
  `NO_COLOR` and `COLUMNS` respected; 16–22 ms per run. 28 tests.
- **Modes**: the `pulse` option gains `focus` (full / focus / quiet / off); `/ui` overrides it
  across sessions (`$.store` `ui:prefs`), plus `/ui sound|notify|pane on|off` and `/ui reset`.
  New userConfig: `sound`, `soundAfter`, `notify`, `notifyAfter`, `quietHours`, `paneAuto`, `ci`.
- **Pane** (`/pulse [view]`): ten views with letter hotkeys (o u g i t f c a h b) and `r` to
  refresh. New: usage (meters, reset countdown, burn $/h, Raster sparkline of output tokens per
  turn), git (porcelain v2 + numstat + last commits), ci (PR, review, checks; Open PR link),
  todo (the model's TodoWrite / TaskCreate / TaskUpdate list). Opens by itself in full mode
  (the engine seats it only from 144 columns).
- **Band**: still only when there is something to act on. New rows: context ≥ 80 % [Compact],
  5-hour window ≥ 85 % with reset time, CI failing [Fix CI] [Checks].
- **Toasts** on changes only: verify kind failing / passing again, long turn done, subagent
  done, context 70/85 %, 5-hour and 7-day 80/95 %, CI status change.
- **Alerts**: a turn of `soundAfter` (20 s) plays the desktop theme's `complete` through
  `canberra-gtk-play` (then `pw-play`, `paplay`, `afplay`; `$.audio.play` plays nothing on
  Linux); an error turn `dialog-error`; a permission wait or a question
  `message-new-instant`. `notify-send` past `notifyAfter` (60 s) with the answer's first line,
  critical for permission waits. Quiet hours, the mode and a 3 s throttle apply. `/sound test`.
- **Command cards**: `/wrapup` (session recap; `/recap` is a built-in), `/standup [days]`
  (your commits, this session, open tasks, blockers; Copy), `/ports` (`ss -ltnpH`, dev ports
  linked), `/deps [folder]` (`npm outdated`, majors first), `/ci`. Each prints one `#n` line,
  the only text the model reads; a CommandOutput hook draws the card from state.
- **Restyles** (full mode): the spinner's suffix shows this turn's edits, commands and running
  agents; a background task's notification row is one line (ctrl+o shows it whole); the
  footer names the UI mode when it is not full.
- mercy `$.ui.status` keeps workflow facts (unverified edits, last verification, tasks, CI,
  agents); context and cost moved to the status line. `session.measure` moved from
  `lifecycle.ts` to `deck.tsx`; `hooksDirFrom`/`interpreterFrom` to `lib/hostconfig.ts`; a
  refused command name no longer aborts session init.
- Santa review (`plans/ui-mods-2026-10-05/SANTA-ui.md`), all fixed test-first: a slow `gh`
  call no longer switches CI watch off for the session (only a missing `gh` does; `/ci`
  re-arms); card ids are clock-based and a card draws only under its own command's row (ids
  had restarted at 1 after a reload or `--continue`); `/clear` empties the task list and
  turn history; the git pane's "… N more" counts every change past 40. Also: git refresh
  debounced and run with `--no-optional-locks`, `notify-send … -- title body`, per-turn cost
  read from `$.session.usage()` at turn end, the deck restored on reload by session id.
- Tests: mod 114 → 143 (`tests/deck.test.ts` 16 pure, `tests/ui.test.tsx` 13 engine-level on
  terminal and desktop), Python 819 → 847.
- Engine fact learned: a plugin's own `$.state.set` never reaches its own `state.set` hooks, so
  the pane's refresh goes through a `ui.press` hook.

### Install (2026-10-05)

- **One command on a fresh Ubuntu** (only git, curl, python3; no sudo): `install.sh` (visual) or
  `install.sh --headless` (console, real install) reaches doctor 0 FAIL, proven in `ubuntu:24.04`
  containers with and without passwordless sudo (`plans/autonomy-2026-10-05/INSTALLER-GAPS.md`).
  `--ci` is unchanged (plans the network steps).
- **Base tools in `~/.local`** (`installer/userspace.py`, `basetools.py`): Node 22 from the official
  tarball (SHA-256 checked), Claude Code via Anthropic's installer pinned to `mods.claude_version`
  (npm fallback), uv, gh; `ollama_setup.py`: ollama as a user-space tarball plus `all-minilm` and
  `qwen2.5-coder:3b`. The daily self-heal heals them too.
- **OS tools** (`ostools.py`): `canberra-gtk-play`, `notify-send`, `ss`, `pw-play`, `curl` through apt as
  root or `sudo -n`; otherwise one batched `sudo apt-get install -y …` line in the final checklist
  with the human-only steps (claude login, `/mcp` OAuth for higgsfield and openart, `gh auth login`).
- **Fresh-install bugs fixed**: PyYAML is required (29 false R12 failures and a crashing generator
  without it; installed with uv, no pip on a fresh Ubuntu); the graphify serve venv pins `mcp==1.28.1`
  (2.x dropped `AnyUrl`: the graphify MCP died on import); `lean-ctx-bin` installs from a tarball (its
  preinstall `pkill -f lean-ctx` killed the npm running it); a `settings.json` injected by lean-ctx's
  first run is re-rendered and its entries never carried; `tdd-guard-pytest`/`pipx` no longer run
  PEP 668 pip installs on POSIX.
- **Santa autonomy fixes**: a failed restore after a failed `claude mcp add-json` is `FAIL(unregistered)`
  and the daily run re-adds a missing manifest server; the re-render keeps `/plugin`-enabled plugins,
  extra marketplaces and added allow/deny/ask rules (template wins shared keys; `render.py --check`
  ignores additions) and writes `settings.json` atomically; `settings-safety` no longer fails on a
  user's own deny rule; `selfheal-daily.py` is a no-op under pytest unless `SELFHEAL_DAILY_ALLOW_TEST=1`.
- **Installer review fixes** (`plans/autonomy-2026-10-05/SANTA-installer.md`): the relocation keeps a
  differing user file of the same name once as `<name>.pre-install` (a summary line is printed); the
  first settings render keeps a permanent `settings.json.pre-install` and seeds `settings.user.json`
  (env with provider keys winning clashes, `apiKeyHelper`, `model`, `defaultMode`, own hooks appended
  after the workbench's); tar extraction refuses symlink / hardlink escapes; downloads check
  Content-Length and a pinned SHA-256 (gh and ollama are pinned) and rename only when verified;
  a partial ollama install (binary without libs) is repaired; the systemd unit is created only when none
  exists and never rewritten or re-enabled; `lean-ctx` dangling-link cleanup is limited to its own links;
  the apt command run through cached sudo is printed first and keeps `DEBIAN_FRONTEND` through `env`.
- Tests: Python 1003 → 1082 (new files `test_userspace`, `test_ostools`, `test_ollama_setup`,
  `test_headless_install`, `test_pyyaml_dep`, `test_npm_pack`, `test_settings_carry`).
- Proof: fresh `ubuntu:24.04` containers (user with only git, curl, python3), 710 s without sudo and
  716 s with passwordless sudo (3 parallel runs): doctor 20 PASS, 1 WARN (the deprecated github
  package), 0 FAIL; `claude mcp list` shows 14 stdio servers Connected, higgsfield and openart
  waiting for OAuth; a re-run takes 17 s.

## 2026-10-05 — workbench audit fix pass (site-sync-vista run)

Second pass over the same audit (v3.2.1 below holds the first fixes). Grouped by area, with
finding ids.

- Router (WP1): negation window, intent plurals, `write … tests` → TEST, noun-only LARGE
  dropped (`cues.py`); emit policy split into `policy.py` with hard/soft enforcement,
  chat/question/trivial prompts get no gates or symbols, skill push is two lines with no
  description, caps 4 skills / 5 routing lines; one weights loader (`weights.py`); `mobile`
  surface for Expo / React Native repos; reticle route only in an instrumented repo,
  project-disabled MCP servers honoured, dead plugin route targets removed (C-04, C-05,
  C-07, C-10..C-12, C-14, C-16, C-17, D-05, G-03, G-14).
- Dispatch and gates (WP3): deferred advisories (tdd-guard off the write path), lean-ctx
  tool names pass every gate, gate precedence and line-boundary char cap, raw stdout only
  on exit 0, mod failure hand-back; first-write-skill-gate is a hint, never a deny;
  `gateguard-ack` acknowledges an ask after the write; new `connector-ask-gate`;
  blocking-doc-enforcer works in any doc-tree repo; bash-write-gate honours its allow-list;
  `--force-with-lease` passes; settings matchers agree with the dispatch config (B1-02,
  B1-04, B1-06..B1-10, B1-13..B1-20, A-05, G-02).
- Lifecycle and Stop gates (WP4): suite gate enforces only skills matching the turn's
  writes, infra paths never count toward gate thresholds, turn key "?" persists nothing;
  session-start core block at a fixed budget, resume/compact add nothing; breadcrumb keyed
  by git root; links `weights-loop`, `session-lifecycle-subagent`,
  `session-lifecycle-postcompact` disabled (42 enabled links); weights updater never
  rewrites an unchanged file; fullstack stop mode removed (B2-04, B2-05, B2-07..B2-15,
  NEW-02, NEW-03, J-04, P5).
- Skills (WP2): 7 new skills (ensure-repo-docs, agentation-react, mongoose-patterns,
  fastify-patterns, expo-react-native, vitest-rtl, docker-compose); curated trigger
  phrases on ~45 skills; `paths:` and `rules/backend.md` globs narrowed (the backend rule
  no longer loads on `~/.claude` Python); core-skill-set honest (caveman full, rest
  pointers); stale plugin/skill/rule references and 20 broken links removed; Higgsfield
  listing entries shortened through `frontmatter_overrides` (−4.1k chars per request);
  workflow-audit body split into `references/`.
- Agents (WP5): the main session leads mixed `/invoke impl` (`team-lead.md` is a playbook,
  not an agent); one `run.json` schema; single-act `/invoke-<act>` routes through
  opus-guard with `--run`; `/invoke --run` resumes; E-04: an explicit `model` moves a
  pinned judge, an executor or fable only with the user's override phrase, and per-project
  mode outranks it; agent preloads cut (FE 50k → 16k, uiux 46k → 28k, BE 32k → 13k);
  refactor works without a worktree; uiux writes DESIGN-REPORT; `memory:` scope local
  (E-04, E-13 and others).
- mercy mod (WP6): consent-aware verify gate (B2-06); shell parsing: heredocs, `-c` /
  `eval` / subshell unwrap, bounded `timeout`, `set -e` / pipefail spellings, vitest
  `--no-watch`, `pnpm -w` (H-10, santa P1–P3, P10); bridge: `MERCY_MOD_FAILED` per-call
  hand-back (B1-06), enqueue after the chain allows (H-07), drains on session end and
  release (H-11), one release (H-12), engine tests (H-04); brain merge across sessions
  (H-08) and store sweep (J-10); reset-text forms (H-09); governor keeps the MUST-READ and
  inlined skills whole (C-15); defaults from `plugin.json` only (H-13); health marks kept
  (H-06).
- Installer, doctor, CI (WP7): lean-ctx config written before lean-ctx is installed;
  bounded dated backups (`backups.py`, newest 3, `-latest` never dangles); `render.py
  --check` honours `--out` / `--user`; every npx MCP server and the semgrep, jcodemunch and
  graphify tools pinned; `drawio` joins the manifest (16 servers); doctor rows
  `plugins-installed`, `secret-perms`, `mods-runtime` (21 rows), `mcp-roster` reports
  extras, pin drift and deprecated packages; mods pin is a same-minor minimum; CI matrix
  3.10 / 3.12 / 3.14, SHA-pinned actions, a mods job, sandboxed `install.py --ci`; gate G6
  (no home literals in tracked Markdown); 13 literals in the 2026-07 archive replaced by `~`
  (A-06..A-11, A-15, G-01, G-04, G-06, I-03..I-17, J-05, J-06, J-11).
- Lead items: router live row carries `ms` (A-10); jdocmunch index name keyed by the
  manifest's `source_root`, same-named clones get `<name>-<sha1[:8]>` (NEW-06); `locked_update`
  for shared per-session state files (J-01); `CLAUDE_HOOK_DOTSTATE_DIR` redirects
  `hooks/.state`, a full test run leaves 0 files in the live dirs (J-02); `state-cleanup`
  gains six purge families (J-03); new read-only `hooks/tools/retention-report.py` (J-07,
  J-08, J-13, G-10, G-15); `skill_router` drops the generic review rules, hidden skills and
  puts `frontend-standards-always-follow` / `backend-error-handling` first for UI / error
  files (NEW-07); `hard-completion-gate` consent regex matches the mod; dead keys removed
  from `autonomous-skill-router.config.json` (E-13); subagent pinned-mode line says omit
  `model`; alias `gsd-execute-phase` → `workflow-orchestrator` (D-01); marketplaces
  `karpathy-skills`, `nateherk`, `ponytail` set to `autoUpdate: false` (A-03); memory
  SessionStart matches `WATCH_SDK` to `watch-sdk` entities (F-10); the project's jdocmunch
  index has embeddings (G-08).
- Lead wrap-up: `MERCY_MOD_RELEASED` removed (it went stale across `/clear` and ran links
  twice), so only `MERCY_MOD_FAILED` hands a call back and `dispatch.py` no longer reads
  the other; `validate_skills` R13 WARNs on inert lowercase `intents` (76 skills; case
  folding was measured worse and reverted) (C-03); `claude-session-driver` disabled in
  the template and dropped from the manifest install list, so 11 plugins install (G-11);
  `build_skills_index` skips skills of template-disabled plugins, plugin skills 40 → 39
  (NEW-08, `tests/test_build_skills_index_plugins.py`); `cleanupPeriodDays: 30` set
  explicitly in the template (J-07); `codebase-design` added to the REFACTOR act's local
  skills and `/invoke` skills regenerated, which clears the doctor `generated-in-sync`
  warning; `CLAUDE.machines.local.md` mode 600 (J-06); `hooks/CLAUDE.md` names
  `skill-effectiveness-report.py` again.
- Late lead items: the mod no longer hands a subagent's background advisory to the main
  loop, and a subagent's tool result no longer takes the main loop's queued advisories
  (NEW-09: the docs agent's CHANGELOG write surfaced "documentation paths touched" in the
  parent); a task notification or a peer session's `<cross-session-message>` is not a
  user prompt: the router stays quiet, `lib/turns` and the mod do not open a new human turn
  (NEW-10); `go cli` / `go program` count as Go vocabulary and an "official docs" prompt
  lifts source-driven-development over its demotion (C-13); `dox_engine plan` lists leaf
  docs that do not name their code files, new child docs list them (F-12);
  `codebase-intel-first` says hybrid doc search needs an index built with embeddings and
  that symbol summaries are no basis for a security claim (G-08, G-09).
- Santa fixes: `state-cleanup` test-residue match no longer hits real session UUIDs that
  contain `8e2e-` (it deleted their gate evidence at age 0); a lean-ctx multi-file call that
  is denied or asked keeps the other paths' context, deferred advisories included;
  `timeout 0` (no limit in GNU coreutils) no longer counts as bounded in the mod guard;
  the router's jcodemunch / jdocmunch / graphify and asset lines honour a project's
  `disabledMcpServers`; classify scans at most 6k + 2k characters of a prompt and the path
  regex is bounded (a 40k-character paste: 23.4 s → 0.4 s). A follow-up pass: disabled MCP
  servers are read from the launch folder as well as the git root (`~/.claude.json` keys
  projects by the folder Claude started in), and "go cli/program/tool" counts as Go only
  after a determiner ("a small go cli"), so "let's go program it" no longer pushes
  golang-patterns.

## v3.2.1 — 2026-10-05 workbench audit fixes (site-sync-vista run)

Why: an end-to-end audit (ten area reviews, a 30-prompt router test, nine headless runs
in a copy of a Vite + Fastify + Mongoose + Expo repo) found gates that blocked twice per
turn, a router that pushed the wrong skill on most coding prompts, and tests that wrote
into live telemetry. Every fix below has a test.

- Router: description-derived keywords count half (the check named a `source` the index
  builder never writes); hidden user-only skills never rank; learned weights only demote
  (their input froze on 2026-09-27); stack-only surfaces earn half credit; URLs are
  stripped before matching and `https`/`guard` no longer mean SECURITY; "migration" is not
  SQL in a Mongo-only repo; the context7 route needs an API question. 30-prompt test:
  precision 24% → 29%, pushes 120 → 104, context7 lines 6 → 2.
- Stop gates: `lib/turns` counts only human prompts (Stop feedback, skill bodies, task
  notifications and interrupts no longer start a turn); the suite gate keeps its spent
  nag when it fails open, so a third Stop does not block again.
- Tests no longer touch live telemetry or `state/`: `CLAUDE_HOOK_TELEMETRY_DIR` and
  `CLAUDE_HOOK_STATE_DIR` are honoured by every writer and reader; `conftest.py` sets
  them. (`hooks/.state` is not redirected yet.)
- dangerous-bash-gate: rm judged per segment and argument; `bash -c`/`eval` payloads and
  quoted SQL/JS for DB clients scanned; Mongo drop, `dd of=/dev`, `mkfs`, `curl | sh` denied.
- link-doctor fails a non-zero exit or a missing script; timeout ladder test (Stop,
  SessionStart, SessionEnd links trimmed to fit their harness timeouts).
- index-lifecycle picks the jcodemunch db by recorded `source_root` (same-named clones
  no longer borrow another checkout's index); memory SessionStart fits 5 entities,
  ranked fragile > decision > pattern; jdoc steer skips small, sliced and `CODEX.md`
  reads; `fullstack-post` decides doc hits by path, not file content.
- mercy mod: package-manager options (`--prefix`, `-C`, `--cwd`, `-w`, `--filter`) no
  longer hide dev servers; bare `vitest` is a watcher; a run whose exit status a pipe,
  `;` or `||` masks is not verify evidence; `.env.example`-style templates are not
  secret homes.
- Settings env `EIO_BACKEND=posix`: semgrep-core's io_uring backend died with "Cannot
  allocate memory" under the default 8 MB memlock limit and scanned 0 files (MCP and CLI).
- `workflows/invoke-fullstack.js` follows `model-policy.json`; teammate-idle-gate finds
  artifacts relative to the run folder; error-envelope skills and `rules/backend.md` say
  the project contract wins; `rules/02-lifecycle.md` matches the gate code.

## v3.2.0 — 2026-10-05 mercy mod (Claude Code mods)

Why: a full audit of hooks, router, skills, agents and installer found costs that only
an in-process layer can remove. Every Python link ran synchronously on every tool call;
tdd-guard alone blocked writes for 11,613 s over 12 days (p90 3.4 s per write); the
router re-sent the same blocks every turn; the 33k-token skill listing carried business
plugins into code repos; a usage-limit stop ended unattended work.

- New `mods/mercy` (Claude Code 2.1.288 hooks module): session ledger, guard (dev
  servers, watchers, subagent commits, live secrets), verify gate at Stop, repo brain,
  router governor, skill-listing focus, auto-resume at the limit's reset time, pulse UI
  (`/pulse`, `/mercy`), model tools `session_state` / `repo_facts` / `remember`. Every
  feature has a `/config` toggle.
- Bridge: `dispatch.py <event> --only <ids>` runs chosen links. Links in
  `MERCY_MOD_OWNED` are skipped only for the owner session while `MERCY_MOD_BEAT` is
  under 120 s old, so an unloaded mod hands them back. The mod runs post-write
  advisories and tdd-guard in the background and rare gates only when they can fire.
- `dispatch.py` imports `concurrent.futures` lazily: start-up 34.9 → 24.5 ms per event.
- Installer: `manifest.mods`, template token `{{MOD_DIRS}}` → `env.CLAUDE_CODE_PLUGIN_DIRS`
  (absolute paths joined with `os.pathsep`), `pluginConfigs` carried over on render,
  post-step `validate-mods`, doctor row `mods`, `scripts/validate_mods.py`; grep gates
  scan `mods/`.
- Completion gate: `~/.claude/installer/`, `tests/` and `mods/` count as infra like
  `hooks/`. jcodemunch never indexes `~/.claude`, so Gate 5 demanded an audit no tool
  could record there.
- Implementor agent bodies no longer ask subagents to commit (CLAUDE.md §2).
- New user-only skill `/workflow-audit`: an end-to-end audit of the whole workbench as
  it behaves in the current project (baseline checks, ten parallel area audits, router
  precision test, live headless runs in a disposable copy), then test-first fixes in
  `~/.claude` only, a before/after comparison and a report. The project stays
  read-only; removals wait for the user. Ubuntu only.

## v3.1.1 — 2026-09-30 Ubuntu end-to-end run fixes

Why: a full end-to-end run on Ubuntu (three headless sessions plus replays) found
features that looked wired but did nothing.

- SessionStart was 33k chars. Claude Code saves any hook context over 8,000 chars to a
  file and shows a 2 KB preview, so core skills and the memory directive were lost. The
  aggregator now fits 5,500 chars (pointers first, full bodies only if they fit); every
  dispatch `budgets.chars` is 7,800.
- `paths:`-scoped skills failed `Skill()` with "Unknown skill". The router and the
  suite gate now say Read `SKILL.md` for them; agent bodies get a generated
  `<!-- path-skills -->` Read block, because `skills:` preload skips them too.
- tdd-guard advisories were dropped: Sonnet takes 4-7.3 s and the gate cut off at 7 s.
  The cap is now 15 s (Haiku is faster but let a test-less edit through).
- Hook-run jcodemunch indexing lost its AI summaries: the CLI never got the MCP's
  `OPENAI_API_BASE` and jcodemunch 1.108.319 refuses api.openai.com. index-lifecycle now
  passes `mcpServers.jcodemunch.env`, and the lost ollama-down guard (DEFER plus an
  ACTION NEEDED line) is back.
- A jcodemunch index rooted at `$HOME` captured every repo without its own index. The
  installer's `jcodemunch-config` repair now deletes such indexes; `graphify-out/` is
  ignored.
- The workbench checkout is never indexed or dox-swept, even under a sandbox HOME, and
  doctor mode no longer spawns writers. CI had been red since 2026-07-14: tests are now
  hermetic, and a dox fallback stub without its placeholder is no longer indexed.
- playwright MCP registers with `--browser chromium`, plus a post-step that installs it.
- graphify skill refreshed to 0.9.70 (a shell-injection fix and manifest data-loss
  fixes), keeping the local frontmatter.
- CI: `router.py` run as a script let its `select.py` shadow stdlib `select` where that
  is not a builtin (setup-python 3.12), so `subprocess` broke inside `mcp_routes` and
  the router dropped every MCP route line. It now strips its own dir from `sys.path`.
- CI (Windows): 19 bare `read_text()` calls decoded UTF-8 as cp1252 and crashed on byte
  0x9D; grep gate G5 now forbids them.
- dispatch.py passed payloads and printed results as non-ASCII JSON. Without
  `PYTHONUTF8`, a cp1252 console cannot encode "→": the result fell back to `{}` (lost
  SessionStart) and a payload with one errored every link (no gate ran). Now ASCII-escaped,
  and stdin is read as UTF-8: decoding it as cp1252 garbled Agent prompts in
  `updatedInput` and a byte like 0x9D (in "”") emptied the payload so no gate ran.
- gateguard counts Python importers too (a module imported by 5+ files asks before a
  write); it only knew Go and JS/TS. `blocking-doc-enforcer` got its first tests.
- playwright post-step installs the browser through the pinned MCP itself
  (`install-browser chrome-for-testing --no-remove`): the old step fetched a different
  chromium build than @playwright/mcp@0.0.82 expects.

## v3.1.0 — 2026-09-30 Sonnet 5.5 routing + Windows parity

Why: Sonnet 5.5 matches Opus 5.5 on agentic execution at half the price, while Opus 5.5
leads on review and judgment (plan `plan-2026-09-29-sonnet55-model-routing.md`). An
end-to-end test of the Windows replica then found gaps that the installer never covered.

### Models
- Roles flipped: Opus judges (santa, uiux, plan, spec, debug, team-lead); Sonnet executes.
  Executors escalate to Opus on a failed previous attempt or large unplanned work
  (`escalation` in `hooks/model-policy.json`). Every opus-guard decision is logged to
  `hooks/.telemetry/<sid>.model-routing.jsonl`.
- Doctrine: omit `model` on `Agent` calls; opus-guard sets it and the `[label]`.
  `/invoke` no longer passes `model=`.
- Effort: executors `high`, `max` banned. The `CLAUDE_CODE_SUBAGENT_EFFORT` env key was
  removed: Claude Code never reads it, so agent `effort:` frontmatter is the only lever.
  `TDD_GUARD_MODEL_VERSION=claude-sonnet-5-5`. New `test_model_policy_consistency.py`
  keeps frontmatter, template env and escalation in line with the policy.
- Doctor `model-routing` checks the new invariant (judges on Opus, no executor pinned).

### Installer and Windows
- `installer/jcodemunch_config.py` + doctor row `jcodemunch-config`: the installer keeps
  `~/.code-index/config.jsonc` at `tool_surface: full`, AI summaries and a trusted home
  (a copied Windows install exposed 6 of 90 jcodemunch tools).
- `check.py` no longer hangs on Windows: version probes close stdin.
- Windows `CLAUDE_DIR` render token names the checkout being rendered, so the doctor
  test passes in a sandboxed HOME.
- `switchModelsOnFlag` is Claude-managed (carried over, never compared); the ollama probe
  also wants `qwen2.5-coder:3b` for jcodemunch summaries.
- Private per-machine doctrine moved to the gitignored `CLAUDE.machines.local.md`,
  imported from `CLAUDE.md` §10 (this repo is public).

## v3.0.0 — 2026-09-28 upgrade

Why: an audit (2026-09-27) found the routing layer largely inert — `dispatch.py` dropped
every `opus-guard` mutation, the prompt router emitted an invalid output shape, tdd-guard
stalled writes with a bad model id, ~45k tokens of always-on context, and an installer
that could `git checkout -- .` over uncommitted work. Decisions D1–D18 are recorded in
[ADR 0001](adr/0001-2026-09-28-upgrade-decisions.md).

### Routing
- Prompt router rewritten: word-boundary matching, stack/cwd-aware surface detection,
  ≤5 skills, availability-aware MCP "call X now" lines, valid `hookSpecificOutput`.
- Native skill `paths:` / `when_to_use:` and path-scoped rules replace hook injection for
  file-bound skills. Alias stub skills deleted; aliases resolve at runtime via
  `hooks/lib/skill_aliases.py`.
- MCP auto-trigger layer: `hooks/mcp-post-hints.py` (PostToolUse), router MCP lines,
  SubagentStart MCP block, memory search directive at session start. MCP mandates
  (jcodemunch, graphify, jdocmunch, sequential-thinking, memory, context7, semgrep) are MUST.
- New events wired: SubagentStart, TeammateIdle, PostToolUseFailure, PostCompact,
  ConfigChange (13 events, 43 links).

### Models, agents, teams
- Model routing = env default + agent frontmatter pins + `opus-guard` label aligner; the
  write protocol moved to a SubagentStart hook. Per-project model mode wired.
- Deliberate teams: `name` is optional; `agents/team-lead.md` + `teammate-idle-gate.py`.
- Removed agents: 4 figma, 3 vercel.

### /invoke
- Slash commands became skills: `skills/invoke` + forked single-act skills, run folders
  `.claude/runs/<ts>-<slug>/`, generated by `hooks/gen-invoke-skills.py` (replaces the
  old command generator). Alias and legacy command files deleted.

### Rules and docs
- `rules/` rewritten as native auto-loaded `.md` (all `.mdc` and `@import`s gone);
  root `CLAUDE.md` is ~4 KB.
- dox: git repos only, HOME-guarded, `~/.claude` hard-refused, per-repo opt-in for
  all-dirs; `scripts/dox_cleanup.py` removed stub sprawl. The session-start dox guard was deleted
  (the sweep now runs from `index-lifecycle.py`).
- Cursor-era docs moved to `docs/archive/`.

### Gates and hooks removed
- The dispatch/router flip-back scripts, the 4 disconnected index guards and the
  jdocmunch reindex hook (freshness is `index-lifecycle.py`), memory writers
  (`session-memory-writer`, `session-learning-extractor`, `memory-bootstrap-guard`),
  `model-mode-phrase.py`, `session-plan-gate-hint.py`, lean-ctx shell hooks.
- Stop gate: ≤1 block per turn, honors `stop_hook_active`. tdd-guard: advisory, never in
  `$HOME`.

### Installer and MCP
- One-click flow (`install.sh` / `install.ps1` / `install.py` → bootstrap → visual
  self-heal loop → doctor 0 FAIL). MCP source of truth = `installer/manifest.json` →
  `~/.claude.json`; template carries no `mcpServers` and no `lean-ctx` string.
- MCP: removed fetch, ast-grep, figma, gbrain; added reticle, higgsfield/openart (HTTP).
  Plugins: removed playwright/context7/clickhouse/mermaid/double-shot-latte duplicates;
  added pyright-lsp. New skill `modern-web-guidance`; `scrollcraft` → `scroll-craft`.
- Vendored skills: one `vendored-git` family in `hooks/skills-sources.json`,
  `scripts/vendor_skill.py`, `/invoke-update`.
- Per-project read-only DB MCP: `templates/mcp/db-readonly.mcp.json` +
  `scripts/add-db-mcp.py`. jdocmunch semantic search via ollama.

Rollback: `git checkout <pre-upgrade tag>` in `~/.claude`, then re-run the installer;
full backup at `~/claude-upgrade-backup-20260927.tgz`.

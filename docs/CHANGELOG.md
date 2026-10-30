# Changelog

## v4.3.1 2026-10-30 audit2 fix pass (not yet released)

Why: a six-report audit (router quality, fresh install on a 15 GiB headless box, security,
runtime, static integrity, docs) found misroutes on 29 % of live prompts, an install that
assumed this PC's RAM and lingering, and gate wiring the gates did not protect.

- **Router**: a committed replay corpus (`hooks/tests/fixtures/router_corpus.jsonl`,
  `test_router_corpus.py`) through the new seam `router.route_payload`, and a live replay
  (`scripts/router_replay.py --check`, budget `hooks/router-budget.json`: union 0.011 on this
  PC, from 0.292). Conversational DEBUG/REVIEW phrases are gone (trigger floor charter v3);
  frontend-only skills need a frontend surface; stack-only tags push nothing; plugin
  description keywords count half; model-routing talk gets only the policy pointer; "no UI",
  CLI and URL questions drop the wrong surface; the browser line needs both a QA/VERIFY intent
  and a phrase, and a dev server inside the active repo; machine prompts (teammate relay,
  restore prompt, judge cwd) are not routed; model-mode pins honour `CLAUDE_HOOK_STATE_DIR`.
- **Small and headless boxes**: memwatch tiers, the emergency line and the graphify floor scale
  with RAM; `bin/claude` derives `MemoryHigh` (min 12G, 45 % of RAM) and reads
  `oomguard.local.json`; the installer seeds `settings.user.json` with `OLLAMA_HOST` and a
  RAM-sized tool memory limit, enables lingering (doctor rows: nine, adds `linger`), writes
  the PATH block (now with `~/.local/bin`) even without a user manager (post step SKIP, not
  FAIL), adds tmux to the sudo line, skips GUI packages on servers, prints a zram line, keeps
  `.git` on relocation, prints the checklist in the visual mode's console, and pins tdd-guard,
  pyright and mmx-cli. `replica_sync.py --posix` for a Linux replica.
- **Security**: a bare box gets `acceptEdits`, not bypass (`AGENTIC_MERCY_PERMISSION_MODE`
  opts in); the commit secret scan reads untracked files a same-command `git add` adds;
  `HUSKY=0`, `SKIP=` and a persistent `core.hooksPath` to nowhere are hook bypasses; four more
  secret-adjacent files and a world-traversable home are reported; a moved vendored tag raises
  `RefMoved`; the settings gate also protects the gate scripts, `dispatch.config.json`,
  `settings.template.json`, `installer/manifest.json` and `.blast-bypass`, and a read-only
  `open(` no longer counts as a write.
- **Runtime**: a timeout keeps its `timeout; rc=124` head; graphify's first build gets 20 min and
  `--max-workers`; jcodemunch outside `trusted_folders` is UNAVAILABLE once; the dox deny names
  the SKILL.md to Read; the mod holds a write for tdd-guard 300 ms at most and background
  `--only` runs no longer count as budget overruns; the fable floor is logged; SessionStart
  drops the duplicate superpowers block and adds a plan-tier line; `doctor.py --help`.
- **Second pass (FIX2, REVERIFY R1-R7)**:
  - Pro routing (D6): the tests follow `tiers.pro.ask_only = [sonnet, opus]`, and
    `workflow-model-guard` no longer lifts a `fable` literal to sonnet on Pro.
  - `platform.run` decodes a timed-out child's output (POSIX hands back bytes; index-lifecycle
    raised a TypeError on it).
  - No /tmp residue: the opus-guard test homes and the atomic-write test dir are removed, and
    `router_replay.py` no longer leaks one `router-replay-*` dir per routed prompt.
  - Doctor: a generator without PyYAML is SKIP naming the cause, not `drift`.
  - Tool memory cap: `CLAUDE_CODE_TOOL_MEMORY_LIMIT` = max(50 % of RAM, 6G) on Linux over 12 GB,
    because one cgroup serves every session's tool commands; a SIGKILLed `tsc` / plugin test is
    WARN `killed: memory cap`.
  - The dispatcher keeps `state/dispatch.config.lkg.json` and runs it when
    `dispatch.config.json` is missing or corrupt; if neither parses it fails open and says so.
  - `git stage` counts as `git add` for the commit secret scan; an exported or earlier
    `HUSKY=0` / `SKIP=` before a commit is a hook bypass (gate edit by the owner).
  - The settings gate also asks on a move, delete, truncate, `dd of=` or `git checkout|restore`
    of the wiring, a copy into `~/.claude/hooks/`, and a move of `~/.claude` or `hooks/` (gate
    edit by the owner).
- **Third pass (FIX3, a fresh install on a 16 GB laptop)**:
  - npm CLIs reach PATH when node lives in a prefix whose `bin` is off PATH: the installer links
    lean-ctx, tdd-guard, pyright, pyright-langserver and mmx into `~/.local/bin` from npm's own prefix,
    counts them PRESENT there (no reinstall each run), and the new doctor row `cli-on-path` FAILs when an
    MCP command or one of those CLIs does not resolve on the shell's PATH.
  - lean-ctx installs with `--ignore-scripts` and the pinned, sha256-checked v3.10.5 release binary: no
    `releases/latest`, no `onboard` (telemetry, settings.json injection, a `serve` daemon); its config is
    merged again after the deps step (install and daily), an injected settings.json counts as stale,
    `*.v4-migration.*` is ignored, and the doctor row `lean-ctx-runtime` WARNs on a daemon or a version
    other than the pin.
  - `bin/claude` runs subcommands (`claude plugin test`, `claude mcp …`) untouched: no scope, caps or
    `--settings`; the doctor calls the real binary.
  - Memory: every cap is MemTotal minus 4 GiB, never below half (scope `MemoryHigh` in `bin/claude` and
    `bin/claude-tmux`, the machine-wide tool cap); memwatch warns under 15 % of MemTotal, crit 8 %,
    emergency 4 %, swap rule 22.5 %. The template keeps its 5 / 4 agent floor; the overlay sizes it per
    machine (3 / 2 on 16 GB).
  - The installer copies `scripts/sudo-askpass.example.sh` to the gitignored helper (mode 700) when
    `.env` holds `LOCAL_SUDO_PASS`, and the helper reads that file only.

## v4.3.0 — 2026-10-30 ECC merge, OOM guard, plan-tier routing, workflows

Why: the workbench took what was worth keeping from ECC (everything-claude-code), stopped OOM kills
from taking whole terminal scopes, routed models by the login's plan tier instead of a fixed
Opus/Sonnet split, and cut the always-on context by about half. Twelve packages built in one
worktree, then one integration pass applied every shared-file change.

- **OOM guard**: `claude-memwatch` sentinel with a tiered ladder (warn, crit, kill), `bin/claude`
  scope launcher with per-launch caps, the live-session ledger and gated restore
  (`scripts/restore_sessions.py`), statusline memory segment, `memwatch-brake` gate,
  `memwatch-ensure` link, eight doctor rows, index builders in their own memory-capped scopes.
  Runbook: `docs/OOM-GUARD.md`.
- **Plan-tier routing**: `hooks/plan-tier-detect.py` reads the plan from the login once per session
  (`state/plan-tier.json`); Haiku 5.5 is the default worker, tiers pick executor and judge models,
  the usage guard steps subagents down above 80 % of the 5-hour window; `render.py` writes the tier's
  `model`, `fallbackModel` and subagent env. `docs/MODEL-ROUTING.md`.
- **Workflows**: a generated saved-workflow library under `workflows/` (`scripts/build_workflows.py`,
  tier literals, `--check` in CI); the router's WORKFLOW line names one for large tasks.
- **Gates**: `config-protection` (ask on an existing lint/format config), `hookify` (repo-local
  rules), one blast-radius counter with sensitive/secret targets, every new ask through
  `lib/gate_mode` (advisory when unattended), github MCP write tools ask.
- **Session and stop**: per-source session-start caps, `context-monitor`, the
  `stop-format-typecheck` gate, `StopFailure` and `InstructionsLoaded` logs, handoff template.
- **Dispatcher**: UserPromptSubmit runs the router as link `router`; crit memory profile with
  `crit_exempt`; MODEL_ROUTING router category; `test_dispatch_config_schema.py`.
- **Library**: zero-cost ECC vault (358 indexed entries), router LIBRARY lines, `validate_imports` G7,
  go-live runner with a two-layer secrets scan, replica sync.
- **Agents and skills**: agent frontmatter contracts (turn caps, short descriptions), ECC reference
  grafts, skill text contracts.
- **Turn caps**: sized to the job (`turn_caps` in `model-policy.json`; santa 80, spec/plan/audit/qa 60,
  debug 80, security 50), SubagentStart deliver-by line, `## Turn budget` protocol, chunked review
  scopes with retry-once in `build`/`review`/`invoke`.
- **Doctrine**: drafts applied (`CLAUDE.md` 6,256 -> 4,000 chars), directives checklist
  (`docs/DIRECTIVES.md`), caveman output style, `skillOverrides`, machines-file split, cost meter
  (`docs/TOKEN-BUDGET.md`: doctrine 38,476 -> 18,409 chars).
- **Hooks hygiene and mod**: `lib/gate_state`, anchored skip list, one tdd-guard init mode, state
  retention families, mod memory view, model caps, monitor relay, resume lock.
- **Continuous learning**: `observe-log` link, `instincts.py` (evolve on the `OLLAMA_HOST` ollama,
  status/export/import), `skills/instincts`, `docs/LEARNING.md`; never the Claude quota; failed calls
  arrive through PostToolUseFailure and are logged `ok: false` with the clipped error.
- **Integrate**: template env caps (`CLAUDE_CODE_TOOL_MEMORY_LIMIT` 6G, concurrent subagents 5,
  workflow agents 4, MCP description 600), `maxEffortLevel` xhigh, StopFailure/InstructionsLoaded
  registrations, SubagentStop/PostCompact registrations dropped; deletions with their supersets
  (`ponytail-caveman-guard.py` -> `session-start-aggregator.py`; the weights loop ->
  `scripts/skill_health.py`); manifest 4.3.0 (higgsfield MCP removed, gitleaks pinned,
  sequential-thinking `alwaysLoad`, five post-steps); render post-steps; daily self-heal +7 steps;
  `check_ownership.py`; grep gate G7; CI runs the library and workflows checks.

Deviations from the merge plan (integrate):

- Hook registrations stay shell strings `{{PYTHON}} {{CLAUDE_DIR}}/hooks/dispatch.py <event>`; the
  exec-form `args` / `if` groups were not adopted (`doctor_hook.py` and the render tests pin the form).
- No `fallbackModel` / `model` in the template: `render.py` adds them per tier. `maxEffortLevel` added.
- `higgsfield` leaves the manifest; the live registration is removed at go-live (`golive.py mcp-remove`).
- `budgets.instructions-loaded.ms` = 800.
- `.gitignore` gets three lines; `state/` already covers every state path the plan listed.
- `skillOverrides` leaves out the `lean-ctx` entry: any `lean-ctx` string in settings re-arms
  lean-ctx's injector.
- G7 and the CI step scan `library/` and `agents/` only until `validate_imports.py` learns an
  allowlist for upstream-locked skills and test fixtures.

Dox cells over 800 chars moved here verbatim (`docs/merge/dox-trim.md`); each dox row keeps its
first sentence and a pointer.

### dox history moved 2026-10 — hooks/CLAUDE.md dispatch.py

per-event chain runner + link declarations (12 events, 43 enabled links; types gate/mutator/advisory/exec, `async` exec); a link's optional `command_re` (searched in `tool_input.command`) skips it for every other shell command (`index-git-reprobe` spawns only on `git`); `dispatch.py <event> --only <ids>` runs just those links (the mercy mod's bridge). Pass order: gates + mutators sequential in declared order, then execs, then advisories in parallel. `"defer": true` advisories run detached and land on the session's next PreToolUse/PostToolUse (`--only` keeps them sync). A deny ends the chain and carries earlier gate notes; an ask is held while later gates run. A lean-ctx call on several files runs once per path; the returned deny/ask carries the other paths' context (deferred advisories included). The char cap cuts on a line and appends `[truncated]`, gate notes first. Raw stdout counts only on exit 0. `ctx_shell`/`shell`/`ctx_patch`/`ctx_call` pass through every gate. Retired links stay declared with `"enabled": false` (`weights-loop`, `session-lifecycle-subagent`, `session-lifecycle-postcompact`). Async exec links and deferred advisories start through `plat.spawn_worker` (`CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session` on POSIX: the old no-op flag killed self-heal children with `0xC0000142`); every synchronous link runs with a hidden console so its git / npm children open no window. Windows PowerShell tool calls reach the same links as Bash.

### dox history moved 2026-10 — hooks/CLAUDE.md hard-completion-gate.py

Stop gates, ≤1 block per turn (`lib/turns.py`). The suite gate enforces only skills whose `paths`/one-sided surface match the turn's writes; generic or `enforce:"soft"` pushes become an advisory queued for the model's next prompt (`dispatch_support.enqueue`, drained at user-prompt-submit and tool events); hcg's pass advisories and same-turn override note go the same way. A Stop `systemMessage` shows only to the user, who cannot act on it (CLAUDE.md §11). A turn key "?" never persists nags or grants hcg's same-turn override. Every gate text is an instruction the MODEL runs now ("dispatch the docs-sync-agent now"), never a command for the user; hcg's Gate 7 (`lib/memory_gate.py`) blocks once when the human prompt said remember / going forward / we decided / from now on / always.. / never.. and the turn saved no memory. hcg's `CONSENT_RE` also takes `just`, `skip (the) verify/verification` and curly apostrophes (same clauses as the mercy mod's `consent.ts`).

### dox history moved 2026-10 — hooks/CLAUDE.md index-lifecycle.py

event-driven jcodemunch/jdocmunch/graphify/dox freshness, active repo only, no daemons; the jcodemunch db is the one whose recorded `source_root` is this checkout (same-named clones get their own); `_doc_name_for(root)` does the same for jdocmunch: the bare basename only when the manifest's `source_root` is this checkout (or absent), else `<name>-<sha1(realpath)[:8]>`. `reprobe --root <abs>` (CLI; the mercy mod and the graphify hooks call it) probes one root like session-start, claims locks, spawns the detached builders and prints ONE JSON line `{"surfaces": {...}, "spawned": [...]}` in ~2 s (non-git/NEVER_INDEX root: empty maps; UNAVAILABLE is reported FAILED plus an `unavailable` list). `post-write` also spawns one detached reprobe for a Bash/PowerShell `git commit/pull/merge/checkout/switch/rebase/reset/cherry-pick/revert/am/stash pop` (dispatch link `index-git-reprobe`). `build_fail` telemetry carries `err` (last 400 chars of the builder's stderr, `Deprecated:` banner lines dropped so jcodemunch's stdout JSON error shows; secrets scrubbed). An incremental jcodemunch flush runs `index-file` only when the checkout has a db, else a full `index` ("No indexed folder found"). The jdocmunch probe counts untracked docs (`--others --exclude-standard`) and skips `graphify-out/` (a committed graph re-staled the docs on every graph build). `_build_graphify` skips (FAILED backoff, `build_deferred` telemetry) while `MemAvailable` is under `GRAPHIFY_MIN_AVAIL_MB` (12 GB: 8 GB still let it start beside agents' vitest) and, where `systemd-run` and the user bus exist, runs `graphify update` in its own scope (`MemoryMax=5G`, no swap): its 4.4 GB run on site-sync-vista was the OOM victim that stopped whole terminal scopes on 2026-10-26. After a successful graph build `_prune_graph_backups` keeps the newest `GRAPH_BACKUPS_KEEP` (3) `graphify-out/YYYY-MM-DD/` snapshots (graphify writes one per day for a curated graph and never prunes; 2026-10-08 sweep freed 505 MB); a dir git tracks is never deleted. The per-repo state file is only written under `platform.locked_update` (`_update_state`): post-write appends to the journal and flushes inside the lock, a flush clears only what it flushed, and probes / builders persist just the surface records they computed (`_save_surfaces`), so concurrent hooks keep every journal entry (4 processes x 120 post-writes: 120 of 480 kept before, 480 of 480 after). `_load_state` retries a `PermissionError` 3 x 20 ms, then returns a blank flagged `_unreadable` that nothing persists.

### dox history moved 2026-10 — hooks/lib/CLAUDE.md platform.py

OS detection, interpreter/token resolution; `ollama_url()` = the one reader of `OLLAMA_HOST` (`host`, `host:port` or URL → `http://host:port`; bare host → 11434, a spelled-out scheme → 80/443 like ollama's client; `localhost`/`0.0.0.0` → `127.0.0.1`; unset → `http://127.0.0.1:11434`; with no `environ` passed and the key absent from `os.environ` (a terminal `install.py` / `doctor.py`) it reads `settings.user.json` `env` itself, a set-but-empty value = the default, which is how both conftests keep the live file out) and `is_loopback_url`, used by `../index-lifecycle.py` and the installer (`{OLLAMA_URL}` token, remote mode); `telemetry_dir()` / `state_dir()` honour `CLAUDE_HOOK_TELEMETRY_DIR` / `CLAUDE_HOOK_STATE_DIR` (test isolation). **Process:** `run` decodes UTF-8 (`errors="replace"`), starts with `CREATE_NO_WINDOW` on Windows, and sends a `.cmd`/`.bat` target (or the bare-name shim fallback) through cmd.exe as ONE line from `shell_cmdline` (args with whitespace or `& | < > ( ) ^` quoted; an arg with `%`, `!`, CR/LF or an odd `"` returns a 127 result and starts nothing; an even number of `"` goes as `""`); `passes_cmd_exe(cmd)` answers that before an irreversible step. `spawn_worker(cmd, stdin_text=, cwd=, env=)` = the one detached start (Windows `CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP`, never `DETACHED_PROCESS`, so no console window; POSIX `start_new_session`); `stdin_text` reaches the child as a delete-on-close temp file (UTF-8, `errors="replace"`), never a pipe: a Windows pipe holds 4 KB, so a bigger payload blocked the caller until the child read it (every Write/Edit JSON through `spawn_deferred`: 100-140 ms, seconds on a slow start); temp file unavailable = the old pipe write; `spawn_detached` is it without stdin; `no_window_kwargs()`, `popen_new_group`, `kill_tree`; `pid_alive` uses ctypes `OpenProcess` on Windows (no `tasklist` spawn). Import sets `NoDefaultCurrentDirectoryInExePath=1` on Windows. **Files:** `atomic_write` / `replace_file` retry `os.replace` while a reader holds the target (Windows `PermissionError`); `append_line(path, bytes)` = locked append (no lost or CRLF rows; waits 1 s, then appends anyway); `locked_update(path, fn)` = read-modify-write of a shared per-session JSON state file under an exclusive lock on `<path>.lock` with an atomic write (security-scan-gate, security-semgrep-tracker, first-write-skill-gate, fullstack-skills-reminder, desloppify-cleanup use it); on Windows it polls up to 10 s, and on timeout applies and writes NOTHING, returns the file's current content, and records a `platform/locked_update_timeout` telemetry row (`locked_update_ok` returns `(data, written)`). A file that exists but stays unreadable (`PermissionError` after 3 tries 20 ms apart) is not "missing": `fn` is not applied, nothing is written, row `platform/locked_update_unreadable` (a torn or corrupt file still restarts from `default`); a failed `atomic_write` leaves `platform/locked_update_write_failed`, so a lost write (Gate 3 evidence, index journal) is never silent.

### dox history moved 2026-10 — hooks/tools/CLAUDE.md state-cleanup.py

session-start async exec: bounded retention purge of `telemetry/` and `state/` files. `run(base, now, dotstate)`; families: `state/*.stack.json` and `state/persist-dedup/*.json` >14 d, `state/.tmp-*.swap` >1 d, `hooks/.state/taste-dials/*` >7 d, `hooks/.state/index/*.flush-*.txt` >1 d, `hooks/.state/index/<key>.json` whose `repo_root` is gone >1 d, `hooks/.telemetry/*.suite-gate.json` >14 d; family `orphan-lock`: a `*.json.lock` / `*.jsonl.lock` sidecar (`platform.locked_update` / `append_line`) whose data file is gone, in `state/`, `state/advisory-queue/`, `telemetry/` and `hooks/.telemetry` >1 d (a lock beside a live file and fixed locks such as `selfheal-daily.lock` stay). Test residue is a name with `e2e-` at the start of a segment (`t-e2e-…`, `e2e-repo`), never a session UUID with `…8e2e-…` inside. Test-named sessions (`audit-*`, `ma-{heavy,light}-{live,shadow}-*`, `t<N>-*`, `t-iso-*`, `dryrun-*`, `isg-*`, `t-<32 hex>`) in `state/`, `telemetry/`, `hooks/.state`, `hooks/.telemetry` and fixture stack caches `state/{go,vite,wt}-<8 hex>.stack.json` go after 1 d (matched on the id before the first dot; a real session UUID never matches). `run()` returns `{family: n}`; a run that removed anything appends one `{ts,total,purged}` JSON line to `state/state-cleanup.log`.

### dox history moved 2026-10 — hooks/tools/CLAUDE.md selfheal-daily.py

session-start async exec (autonomy WP-D): the once-a-day self-heal. Independent steps `STEPS` = `mcp` (`deps.register_mcps` re-adds a manifest server missing from `~/.claude.json`, then `reconcile_mcp_pins` + `reconcile_mcp_env`; the lock lives in `daily_lock.py`), `deps` (`basetools.ensure_base_tools` = node/claude/uv/gh in `~/.local` on POSIX, git/node/claude/uv/gh in the Windows tools dir through `wintools`; then `install_deps(skip_optional=True)`: installs absent required CLIs, never upgrades, skips `optional` entries so an absent optional dep is not retried every day), `settings` (`selfheal._ensure_settings` when the template/manifest is newer, settings.json is missing, or a command's absolute interpreter path in `statusLine` / `hooks` is no longer a file: `selfheal._stale`), `vendor` (`scripts/vendor_skill.py --all` only when `--all --check` exits 1 = DRIFT; BEHIND is ignored), `ponytail-board` (`node <ponytail installPath>/hooks/ponytail-band-import.js` from `plugins/installed_plugins.json`, 300 s cap: past sessions into `~/.config/ponytail/band/`, the ones already there skipped; run through `_IDLE_ONLY`, a `node -e` wrapper that hides transcripts written in the last 24 h from the import's `fs.readdirSync`, because the import never revisits a row and a live session would stay half-counted; no plugin or no node = no row). Stamp + summary `state/selfheal-daily.json` = `{"at","changed","errors","reported"}` (the aggregator reports it once; nothing to say ⇒ `reported` true; unreported lines carry over). When every step failed (`Ctx.steps_ok == 0`) the summary is still written with its errors (`reported:false`) but WITHOUT `at`, so the next session retries (bounded by the lock) instead of waiting 24 h, non-blocking lock `state/selfheal-daily.lock`, log `state/selfheal-daily.log` (names, specs, return codes: no env, no tokens). No-op under `CLAUDE_HOOK_DOCTOR`, under pytest (`PYTEST_CURRENT_TEST` unless `SELFHEAL_DAILY_ALLOW_TEST=1`: a test firing the session-start chain must never heal the LIVE install) and for link-doctor's probe payload (`session_id` `link-doctor`; running `link-doctor.py` by hand does not set the doctor env). `--dry-run` prints the plan and writes nothing.

### dox history moved 2026-10 — mods/CLAUDE.md mods Autonomy

no command needed (CLAUDE.md §11): ports scanned every minute (Linux `ss`; Windows `netstat -ano -p TCP` + `-p TCPv6` + `tasklist /FO CSV /NH`, listening = foreign `0.0.0.0:0` / `[::]:0`, locale-proof; a failed scan keeps the last rows and shows `port scan failed: <reason>` in pane, card and `/ports`, never "nothing listening"; toast when a dev server comes up or stops; pane tab p), npm outdated once a day per package folder (`$.store` `deps:<root>`; a rejected npm, exit ≥ 2 or `{"error":…}` is never stored as "all current": `/deps` answers `/deps failed: …` and `/mercy status` notes it; pane tab d; toast on majors), today's standup at the first session of the day (`standup:<root>`; pane tab s, copy key y; Monday looks back to Friday), the session recap saved after every main turn (`recap:<root>`; the next session's overview shows it), compaction between turns once context ≥ `autoCompact` (85 %, at most every 10 min, keeps plan/tasks/unverified files); `deck.tsx` re-probes the indexes (`index-lifecycle.py reprobe`) when HEAD moves, terminal commits included.

### dox history moved 2026-10 — mods/CLAUDE.md mods mercy tests

lib units, bridge policy, prompt context, engine-level hook tests, auto-resume end to end and `/mercy`; `winshell.test.ts` (Windows wrapper table, PowerShell tool through the engine; the engine's tool-name union is generated per machine and has no `PowerShell` off Windows, so the test passes it as `POWERSHELL`, cast once, or `tsc` fails on Linux), `ports.test.ts` (netstat / tasklist fixtures, scan failure, `/deps` failure parsing), `toast.test.ts` (hostile strings never reach argv, sanitising, flags); `deck.test.ts` (pure deck parsers and rules), `ui.test.tsx` (pane views on terminal and desktop, band, alerts, task list, cards, restyles; JSX because the test's own `ui.render` hooks stand for the engine) (an engine test that needs the interactive path raises `$.session.start({ isInteractive: true })`: the test's own import of `lib/runtime` is not the plugin's copy).

### dox history moved 2026-10 — scripts/CLAUDE.md statusline.py

Claude Code status line (settings `statusLine`, run on every refresh): reads the payload JSON on stdin, prints one line (model+effort │ ctx bar │ $ │ 5h/7d limits │ git │ ⏱ │ ±lines). Git cached 5 s in `$CLAUDE_STATUSLINE_CACHE_DIR` / `$XDG_RUNTIME_DIR` / `$TMPDIR` `$TEMP` `$TMP` when that directory exists, else `tempfile.gettempdir()` (imported only on that path; no `hashlib`: the cache key is crc32+adler32, so the warm path skips OpenSSL start-up); a failed `os.replace` removes its tmp file. Windows: git timeout 1.5 s (0.5 s elsewhere) and a real bound: `Popen` + `communicate(timeout)`, then the whole process tree is killed (`taskkill /T /F`; POSIX: own session + `killpg`), because `subprocess.run(timeout=)` kills only git and then waits for every child holding the stdout pipe (a fsmonitor hook, the `cmd\git.exe` launcher): 3.3 s per refresh became 2.2 s on a 3 s git. `GIT_ARGV` is the module constant tests point at a fake. On a timeout the entry is re-stamped and the last good summary is kept only while < 60 s old, else no git segment. stdin read as `utf-8-sig` (BOM), stdout UTF-8 (`errors="replace"`: a lone surrogate prints `?`) with LF newlines even without `PYTHONUTF8`. Rendered as `{{PYTHON_EXE}} scripts/statusline.py` (direct interpreter, no `py` launcher; hooks keep `{{PYTHON}}`). `NO_COLOR` and `COLUMNS` honoured; never raises (fallback `◆ Claude`). The file stays one module on purpose (a sibling import costs start-up on the 10 s hot path). Tests: `tests/test_statusline.py`, `tests/test_statusline_win.py`.

### dox history moved 2026-10 — tests/CLAUDE.md test_statusline.py

`scripts/statusline.py` run as a subprocess the way Claude Code runs it (git cache in `CLAUDE_STATUSLINE_CACHE_DIR`): model/effort, context bar, cost, 5-hour/7-day windows, git counts, `NO_COLOR`, `COLUMNS`; no wall-clock test (the warm path is pinned structurally: the `-X importtime` list has no hashlib / tempfile / subprocess, a fresh cache entry makes zero git calls); the Windows file: crc32/adler32 cache key (no hashlib, no tempfile on a usable `TEMP`; a dead or unset `TEMP` falls back to `tempfile.gettempdir()`), no `*.json.<pid>` leak when `os.replace` fails, 1.5 s Windows git timeout keeps the last good summary only while < 60 s old and kills the whole git tree (a grandchild holding the pipe cannot extend the refresh), LF output, UTF-8 without `PYTHONUTF8` and a lone surrogate printed as `?`, BOM stdin.

### dox history moved 2026-10 — tests/CLAUDE.md test_wintools.py

Windows base tools (`wintools` / `winutil` / `winollama` / `winpath`) on `winfakes` (no network, no registry): user-space node / git / claude / uv / gh with pinned hashes, a git on PATH reused only with its `bash.exe` (4 layouts, `CLAUDE_CODE_GIT_BASH_PATH` in process / HKCU / HKLM, never overwritten when valid), cwd-planted binaries never run, Authenticode refusal, `AGENTIC_MERCY_SANDBOX` keeps the tools dir in the profile and `AGENTIC_MERCY_TOOLS_DIR` outside it warns, user PATH / env / Run-key helpers, Windows ollama zip + autostart + disk preflight, `deps` `skip_optional` / `{HOME}` / `&&` steps / Store-stub Python, `basetools.ensure_base_tools` wiring. Audit #2: `winfakes.short_limit` (autouse once imported) makes the fixtures independent of the pytest basetemp length; `test_winlock.py` (one install per tools dir, across processes; busy run changes nothing, a live peer's tmp dir survives), `test_wintools_repair.py` (npm prefix repaired on re-run, undeletable leftovers are not failures, a failed extraction keeps the verified archive and the retry downloads nothing, one `CLAUDE_CODE_GIT_BASH_PATH` reader), `deps` `_win_shell_wrap` never registers a bare shim, `check_prereqs` counts `sys.executable` and the tools-dir python and never a cwd `py` or cwd `git`, `deps.py` has no raw `shutil.which` (AST), the doctor `base-tools` row reads the bash variable from the registry, an ollama zip without `ollama.exe` is kept for the retry.

### dox history moved 2026-10 — tests/CLAUDE.md test_install_entry.py

one-click entry: `install.cmd` → `install.ps1` (parsed on Windows PowerShell 5.1: `-Ci` / `--ci` never installs Python, Find-Python by exit code, pinned + Authenticode Python, sandbox refusal), `bootstrap` / `relocation` (fatal copy failures, no Mark-of-the-Web spread, git-absent message, PATH hint); contained ZIP extraction (device names, drive, `..`, symlink flag, MAX_PATH); `download` https-only, 64-hex hash required with `require_hash`, a denied rename retried, only a dead pid's `<dest>.tmp-*` swept. `test_install_entry_run.py` (Windows only) runs `install.ps1` under PowerShell 5.1 and `install.cmd` under cmd.exe on scratch copies, each behind TWO guards (`AGENTIC_MERCY_SANDBOX=1` and a scratch manifest whose Python pin is `https://127.0.0.1:9/x.exe` with a zero hash): bracket / `%` clone paths, no `PSExecutionPolicyPreference` in the child, nothing unblocked outside the workbench, the pause only for Explorer's `/c ""path" "`.

## v4.2.0 — 2026-10-21 ponytail 5

Why: ponytail sat at 4.12.0 (its marketplace stays `autoUpdate: false`, A-03). 5.x rewrote the
prompt, rebuilt `/ponytail-review` and `/ponytail-audit` into full quality reviews and added a band
and a board inside Claude Code. This release takes 5.3.2 (`09c434a`) and wires it in, plus the two
change sets below that were waiting for a release.

### 2026-10-21 ponytail 5.3.2

- **Plugin**: 4.12.0 → 5.3.2 by hand (`claude plugin marketplace update ponytail`, then
  `claude plugin update ponytail@ponytail`). SessionStart now carries the v5 rules (smallest
  complete change, a closing line on what was skipped and any risk, `shortcut:` comments instead of
  `ponytail:`) and a 2 KB codebase map (`PONYTAIL_MAP=0` turns it off); a compaction keeps the live
  level. `PONYTAIL_SUBAGENT_MATCHER` still scopes the rules to the executor agents.
- **Band**: ponytail's band (cost, tokens, agent time, reuse, tests; level, Review, Audit and Board
  buttons) shares the AbovePrompt slot with mercy's. mercy's pulse band now draws the bands beneath
  it (`next(e)`) instead of replacing them: before, whichever handler ran first hid the other.
- **Board without a command**: the daily self-heal gets a `ponytail-board` step that runs the
  plugin's `ponytail-band-import.js` (what `/ponytail band import` does), so sessions the live band
  missed (one that started with mods switched off) still reach `~/.config/ponytail/band/`. The
  import skips sessions already there; a run over 6 GB of transcripts took 20 s. It never revisits
  a row, so transcripts written in the last 24 h are hidden from it (Santa finding: a manual run
  froze three live sessions at partial numbers, and the band then counted them a second time
  under its own key).
- **Review and audit**: santa-reviewer's BREAKER takes v5's two new checks (risky logic without a
  test; scale judged against the load the repo expects) and reads a `shortcut:` comment as a
  decision. audit-specialist can load `ponytail:ponytail-audit` for a fix-first ranking. Router
  probes after the index rebuild: "review my PR" still lands on santa-review, "audit this codebase"
  on audit-specialist, "list the shortcuts" on ponytail-debt.
- **Style**: the SessionStart directive (`ponytail-caveman-guard.py`) and CLAUDE.md §9 describe v5;
  `skills-index.json` is rebuilt from the new skill descriptions.
- **Engine types**: `mods/mercy/tests/bridge.test.ts` answered `env.set` with `{ value: undefined }`;
  Claude Code 2.1.306 types that value as an object, so `tsc -p mods/mercy` (doctor row
  `mods-runtime`) failed.
- `.ponytail-band` (the band's hide flag) and `/policy-limits.json` (Claude Code's account policy
  cache) are gitignored.

### 2026-10-21 ollama on another machine

Why: the user moved ollama (jcodemunch AI summaries, jcodemunch / jdocmunch embeddings) to an
always-on office machine and uninstalled it locally. Editing `~/.claude.json` alone would not have
held: the daily self-heal rewrote the MCP env back to 127.0.0.1, reinstalled ollama into `~/.local`,
started a local server and re-pulled the weights.

- **One knob, `OLLAMA_HOST`** (ollama's own variable), set per machine in `settings.user.json`
  `env`; unset keeps the old 127.0.0.1:11434 behavior. `lib/platform.ollama_url()` is its one reader
  (ollama's default-port rule, `localhost` / `0.0.0.0` → 127.0.0.1); a process Claude Code did not
  start (`install.py` / `doctor.py` from a terminal) reads it from `settings.user.json` directly, so a
  manual install cannot revert the move either (Santa finding).
- **MCP env**: the manifest's jcodemunch / jdocmunch URLs are the `{OLLAMA_URL}` token, resolved at
  registration and by the daily `reconcile_mcp_env`; jcodemunch gets
  `JCODEMUNCH_ALLOW_REMOTE_SUMMARIZER=1` (≥1.108.319 ignores a non-localhost `OPENAI_API_BASE`
  without it and silently falls back to signature summaries).
- **Installer / self-heal**: a non-loopback `OLLAMA_HOST` installs no binary, starts no server and
  keeps no weights here (row `ollama REMOTE(<url>)`); missing models are pulled on that host over
  `POST /api/pull`.
- **Probes**: the index-lifecycle summarizer healthcheck and the doctor's ollama row follow
  `OLLAMA_HOST` (the literal URLs left `index-lifecycle.config.json` and `doctor_probes`).
- **Doc embeddings in hook builds**: the hook ran `jdocmunch-mcp index-local` without the MCP
  server's embedding env, so no automatic doc rebuild ever added vectors (site-sync-vista: 12k of
  29k sections, stale since 2026-10-05). The CLI now runs with `mcpServers.jdocmunch.env`
  (provider, telemetry off). A doc index that already has a vector sidecar embeds its changed
  docs, with a 900 s cap (`jdocmunch_embed`; a new `OLLAMA_HOST` re-embeds the whole corpus)
  and the jcodemunch ollama-down DEFER. Every other doc
  index runs `--embeddings off` (a first embed of CONCORD-WEBSITE's 295k sections cannot finish in
  a hook). Live: a site-sync-vista hook build embedded 2,846 new sections in 41 s, coverage 99.9%.

### 2026-10-08 code-intel wiring audit

Why: an end-to-end check of the jcodemunch / jdocmunch / graphify / dox wiring found the graphify MCP
answering from an empty graph in sessions launched from `~`, index build errors logged as a
deprecation banner, and branch switches never reaching the indexes.

- **graphify**: the MCP keeps the graph it started with (an empty placeholder when the session began
  outside the repo). Router, graphify-enforce, subagent protocol, `rules/00` and
  `codebase-intel-first` now name `project_path=<repo root>`; graphify-enforce resolves the repo
  from the payload `cwd` instead of the launch dir and never pushes an infra dir's stale graph.
- **index-lifecycle**: `build_fail` rows drop jcodemunch's `Deprecated:` stderr banner so the stdout
  JSON error is kept; an incremental flush with no index db runs a full index instead of failing
  `index-file`; the doc-index probe counts untracked docs and ignores `graphify-out/`; a graph build
  keeps the newest 3 `graphify-out/YYYY-MM-DD/` backups (never git-tracked ones). One sweep freed
  505 MB (GO_UDP 524 → 235 MB, gatepass 287 → 98 MB). The db lookup also scans every index db
  by recorded `source_root`: repos whose db is named after the git remote (SubStore,
  SubStore-laneCI, Software Updater Docketrun, JASHN EVENTS AND ENTERTAINMENT) probed MISSING and
  fully rebuilt every session. A flush no longer retries a surface in FAILED backoff. The git
  trigger also sees `git.exe` and quoted / absolute git paths (PowerShell).
- **One infra-root list**: `lib/code_files.is_infra_root` replaces three copies (the read gate's
  had drifted and missed `~/.codex`).
- **`~/.claude` stays unindexed** (2026-08-16 directive). Its stale July graph went to the Trash and
  its two stale jdocmunch indexes (`local/.claude`, `local/claude-workbench-docs`) were deleted, so
  nothing answers from them.
- **dispatch**: new `command_re` link filter; async link `index-git-reprobe` sends
  `git checkout/pull/commit/...` (Bash and PowerShell) to the reprobe that was written but never wired.
- **jcodemunch gate**: a bare `Grep pattern` (no path) in a repo counts as a code search; outside a
  repo it passes; the block names the pattern.
- **dox**: a code write into a documented leaf dir whose `CLAUDE.md` does not name the file gets one
  advisory per dir per session (tests skipped).
- **router**: the jdocmunch line finds `<name>-<sha8>` doc indexes and never promises an index build in
  `~`, `~/.claude` or `~/.codex`.

## v4.1.0 — 2026-10-06 Windows parity

Why: v4.0 was built on Ubuntu. On the Windows replica the `PowerShell` tool bypassed every gate, the UI
deck had no sound, toast or port scan, background index builds opened console windows, semgrep could
not scan, and a fresh Windows machine could not be installed. Two audits (7 areas each), three review
rounds (Santa + security) and test-first fixes later (plans in `plans/windows-parity-v4/`, gitignored):

- **Gates**: `PowerShell` is a shell tool in every settings matcher, dispatch link and gate; new
  PowerShell / cmd destructive patterns (`Remove-Item -Recurse`, `rd /s`, `del /s`, `Format-Volume`,
  `git clean -f`, pipelines, `[IO.Directory]::Delete`, backtick and `\` continuations) and write
  cmdlets; the gate matches in linear time (worst 50 KB input 59 s → 0.12 s); commit doc gate reads
  Windows paths.
- **Mod (mercy)**: OS flag from `$.env.get('OS')` (a mod has no `process`); the guard, ledger and verify
  gate see PowerShell commands, `.exe/.cmd` suffixes and `cmd /c`, `powershell -c`, `Start-Process`,
  `iex`, `wsl` wrappers; Windows sound (`SoundPlayer`), WinRT toasts (text only through env,
  XML-escaped), ports via `netstat` + `tasklist` (locale-proof), absolute System32 paths; `/deps` no
  longer reads an npm error as "all current".
- **Hooks**: background spawns use `CREATE_NO_WINDOW` (visible console windows during a reindex
  6 → 0); retrying `atomic_write`, locked appends (queue and telemetry lost 4-10 % of lines before),
  bounded `locked_update`, `pid_alive` via ctypes, `localhost` → `127.0.0.1` for ollama probes,
  cmd.exe argument quoting/refusal for `.cmd` shims, UTF-8 subprocess output.
- **Render**: `EIO_BACKEND` dropped on Windows (semgrep scans work), spaced profile paths quoted,
  status line runs the direct interpreter (`{{PYTHON_EXE}}`): Windows p95 133 → ~120 ms.
- **Doctor**: Windows `secret-perms` (SID-based SDDL from `icacls /save`; never changes ACLs),
  `base-tools`, `hook-command` and `statusline` rows, load-aware `mods-runtime`, UTF-8 helpers.
- **One-click Windows install**: `install.cmd` → `install.ps1` (Python bootstrap, pinned + Authenticode)
  → `install.py`; `installer/wintools.py` installs PortableGit, Node, Claude Code, uv, gh and ollama per
  user with pinned SHA-256, contained zip extraction, `HKCU` PATH (`REG_EXPAND_SZ`), reuse of tools
  already present, `-Ci` plans only, `AGENTIC_MERCY_SANDBOX=1` blocks every registry write and drops
  inherited `UV_TOOL_*` / `NPM_CONFIG_PREFIX` / `PIPX_*` (a rehearsal once installed into the real uv
  and npm dirs); a git reused through `CLAUDE_CODE_GIT_BASH_PATH` but off PATH gets its `cmd` dir on
  PATH; a dir already on the user PATH keeps the user's order; unknown `install.ps1` flags stop first.
- **CI**: the Windows workbench legs (py 3.12 + 3.14) gate the build; `install.ps1 -Ci` is rehearsed
  in a sandboxed profile; the mods job runs on Windows too (informational) and proves the pinned CLI.
- **Tests**: Windows-only branches are exercised on Ubuntu by injecting the OS (`IS_WINDOWS`
  monkeypatch sites 1 → 60); `tests/conftest.py` restores `os.environ` after each test.
- Proof: Windows pytest 2005 passed / 3 skipped; mod tests 261 passed; CI Ubuntu 3.10/3.12/3.14 and
  Windows 3.12/3.14 green; live headless E2E 8 PASS (guards for Bash and PowerShell, subagent commit,
  secret write, bridge, model tools, status line p95 189 ms, 0 console windows); fresh-profile
  one-click install 0 FAIL, re-run 74 s; doctor 0 FAIL on the replica; grep gates 5/5.

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

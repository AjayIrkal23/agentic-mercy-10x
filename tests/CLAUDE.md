<!-- dox:child v1 -->
# `tests/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename tests.

## What lives here

Repo-level tests for the installer, doctor, settings template/render, skills catalog and
portability. Hook unit tests live in `../hooks/tests/`. `fixtures/hook-events/*.json` are
synthetic event payloads (one per event, incl. subagent-start, teammate-idle,
post-tool-use-failure, post-compact, config-change).

## Local conventions

- Run: `python3 -m pytest tests -q` (CI runs it on Ubuntu + Windows).
- Tests must not touch the live `~/.claude`: sandbox `HOME`/`CLAUDE_CONFIG_DIR` and set
  `CLAUDE_HOOK_DOCTOR=1`. `conftest.py` (here and in `hooks/tests/`) points
  `CLAUDE_HOOK_TELEMETRY_DIR` and `CLAUDE_HOOK_STATE_DIR` at temp dirs for the whole run;
  scripts derive `hooks/.telemetry` from their own path, so HOME alone never isolated them.
- A SessionStart replay against the live `dispatch.py` (fixtures, verifier drivers) MUST set
  `CLAUDE_HOOK_STATE_DIR` to a scratch dir, else it writes `state/live-sessions/<sid>.json`
  bound to the nearest live claude pid (O6; the ledger now drops non-UUID sids).
- No PyYAML or other non-stdlib imports (the CI interpreter is bare).
- Tests that load installer modules with `_load()` replace `sys.modules[...]`; a test that
  monkeypatches a module `selfheal` imports lazily must pin it with
  `monkeypatch.setitem(sys.modules, …)` (see `test_selfheal_wp7` `box`).
- Doctor/installer sandboxes hide `claude` and `tsc` from `shutil.which` (I-17).
- `conftest.py`: temp telemetry/state dirs are created only when the env var is not preset
  and removed at session end; the autouse `_restore_environ` guard puts `os.environ` back
  after every test (installer code writes it directly: `CLAUDE_CONFIG_DIR`, the relocation
  guard); it also sets `OLLAMA_HOST=""` (set-but-empty = the default) so no test follows a machine's remote ollama or reads the live `settings.user.json`; the `symlink_ok` fixture skips when the account cannot create symlinks (Windows
  without Developer Mode). `winfakes.py` holds the shared Windows fakes (registry, downloader
  pieces, tools-dir world); import it, do not copy.
- Windows branches are tested on every OS by stubbing the flag (`plat.IS_WINDOWS`,
  `os_arch`); real cmd.exe / PowerShell 5.1 / `Zone.Identifier` tests run on Windows only.
  Fixture drive letters are `D:` / `E:` (G2/G3 bans `C:` + backslash).

## Key files

| File | Role |
|------|------|
| `test_installer.py`, `test_doctor.py` | installer + doctor smoke, read-only doctor in a sandbox; `model-routing` invariant (judges on Opus, no executor pinned) |
| `test_render_settings.py`, `test_template_contract.py` | render equivalence; template has no MCP block, no home literal, no "lean-ctx"; Windows `CLAUDE_DIR` = the rendered checkout; `{{MOD_DIRS}}` → absolute `CLAUDE_CODE_PLUGIN_DIRS` joined with `os.pathsep` |
| `test_render_win.py` | Windows render: `EIO_BACKEND` dropped on Windows only (`--check` agrees both ways), `{{PYTHON_EXE}}` per OS and in `machine_subs` / `--emit-template`, a spaced or shell-hostile profile dir (`A&B`, `O'Brien`, non-ASCII) quoted as ONE word in every hook and the statusLine, `"` / `$` / backtick values refused (`ValueError`), POSIX literals and `{{MOD_DIRS}}` untouched |
| `test_statusline.py`, `test_statusline_win.py` | `scripts/statusline.py` run as a subprocess the way Claude Code runs it (git cache in `CLAUDE_STATUSLINE_CACHE_DIR`): model/effort, context bar, cost, 5-hour/7-day windows, git counts, `NO_COLOR`, `COLUMNS`; the Windows file covers the cache key, git timeout and encodings. history: `docs/CHANGELOG.md` v4.3.0 § test_statusline.py |
| `test_semgrep_env.py` | the TEMPLATE env sets `EIO_BACKEND=posix` (semgrep-core's io_uring dies under the 8 MB memlock limit); the Windows render drops it (`test_render_win.py`) |
| `test_envelope_precedence.py` | any skill or `rules/backend.md` that prescribes a nested `error:{…}` envelope also says "the project contract wins" |
| `test_timeout_ladder.py` | each event's worst dispatch path (sequential gates/mutators/sync execs + parallel advisories, priority>0 skipped past `budgets.ms`) stays 1 s under its settings `timeout` |
| `test_mods_contract.py` | `manifest.mods` shape; every enabled mod passes `validate_mods.py` static M1–M6; the M3 scan ignores comments |
| `test_settings_wp8.py` | template contract (A-03): marketplaces `karpathy-skills`, `nateherk`, `ponytail` carry `autoUpdate: false` (hook-running plugins from personal repos update by hand); `superpowers-marketplace` stays true |
| `test_skills_wp2.py` | new skills' frontmatter, curated keywords, router recall for the C-13 prompts, core-skill-set budget, rule and skill `paths:` globs vs representative project and infra paths |
| `test_skills_wp2_refs.py` | no stale plugin/skill/rules names or broken relative links in skills, router cap in docs = `max_skill_pushes`, Higgsfield/kokonutui listing ≤420 chars, workflow-audit lean + user-only, baseline/verification/dead-code text contracts |
| `test_autonomy_wpd.py`, `test_autonomy_wpd_daily.py`, `test_autonomy_wpd_fixtures.py` | autonomy WP-D: `deps.reconcile_mcp_pins` (swap/restore/skip/idempotent/env-never-logged), doctor roster FAIL-when-repairable + `_repair` route, exact manifest pins, the dispatch link; `selfheal-daily.py` (24 h stamp, lock, independent steps, summary contract, probe/doctor no-op, `--dry-run`, the `ponytail-board` step with a fake import script; node comes from the real PATH, `box` trims it). The fixtures module puts a fake `claude` on PATH that records argv and edits `$HOME/.claude.json` (plus a `claude.cmd` shim on Windows, which runs no shebangs); no real CLI or network |
| `test_userspace.py`, `test_ostools.py`, `test_ollama_setup.py`, `test_headless_install.py`, `test_pyyaml_dep.py`, `test_npm_pack.py` | one-command fresh-Ubuntu install: node/claude/uv/gh in `~/.local` (SHA check, pinned claude, npm fallback), apt tools via root / `sudo -n` / one batched line, ollama + models, `--headless` vs `--ci`, install order + the end-of-run checklist, PyYAML via uv, `lean-ctx-bin` through a tarball, graphify `mcp` pin. Downloads, subprocesses and HOME are injected (set `USERPROFILE` beside `HOME`: `Path.home()` reads it on Windows; force `os_arch` to linux to test the POSIX install logic there); `conftest.py` sets `AGENTIC_MERCY_SKIP_BASE_TOOLS=1` suite-wide |
| `test_wintools.py`, `test_wintools_reuse.py`, `test_wintools_deps.py`, `test_wintools_ollama.py`, `test_wintools_wiring.py`, `test_wintools_repair.py`, `test_winlock.py`, `test_winpath.py` | Windows base tools (`wintools` / `winutil` / `winollama` / `winpath`) on `winfakes` (no network, no registry): user-space node / git / claude / uv / gh with pinned hashes, git reuse only with its `bash.exe`, cwd-planted binaries never run, Authenticode refusal, install lock, repair on re-run, `basetools.ensure_base_tools` wiring (no gitleaks row on Windows). history: `docs/CHANGELOG.md` v4.3.0 § test_wintools.py |
| `test_doctor_fx3.py`, `live_interpreter.py` | audit #2 doctor / self-heal: row `statusline` (injected runner, real runner), `_repair` re-render routes for `statusline` / `hook-command`, `selfheal._stale` + the daily settings step on a gone interpreter, `secret-perms` SKIP over zero files, `doctor.main` on a cp1252 pipe (child process), the load-only classifier (typed errors / assertions never load); `live_interpreter.pin(monkeypatch)` makes `detect._python_exe` answer the live `settings.json`'s interpreter (or an injected one) and runs the `hook-command` / `statusline` rows with the real `HOME`/`USERPROFILE` (the POSIX render says `${HOME}/.claude/...`; a sandboxed HOME made them exit 2), so `test_doctor_is_green`, `test_doctor_deterministic_checks_pass` and `test_render_semantically_equals_live` pass under any Python |
| `test_doctor_basetools.py`, `test_doctor_win.py`, `test_doctor_win_mods.py`, `test_npx_cache.py` | doctor on Windows with injected inputs: row `base-tools` (FAIL on an empty machine, git without bash = WARN, SKIP under `AGENTIC_MERCY_SKIP_BASE_TOOLS` / `--ci`, a remote `OLLAMA_HOST` needs no local ollama); `secret-perms` by SDDL (letter pairs, NULL DACL, `CodexSandboxUsers` = WARN, System32 `icacls`); `hook-command` row; `mods-runtime` load-only retry/WARN; junctions; UTF-8 helper decoding (AST: no `text=` without `encoding=`); npx cache prune (half-written `_npx/<hash>` entries only, entries newer than 10 min kept) and sequential warm after a pin change |
| `test_install_entry.py`, `test_install_entry_run.py`, `test_install_bootstrap.py`, `test_safe_fetch_zip.py`, `test_safe_fetch_download.py` | one-click entry: `install.cmd` → `install.ps1`, `bootstrap` / `relocation`, contained ZIP extraction, https-only pinned `download`; `test_install_entry_run.py` (Windows only, behind two sandbox guards) runs the real entry scripts on scratch copies. history: `docs/CHANGELOG.md` v4.3.0 § test_install_entry.py |
| `test_win_branches.py` | Windows-only code paths run on every OS by flag stubbing: `detect` (`py -3` / forward-slash interpreter), `deps` post-steps and `install_windows`, `graphify_launcher` venv layout, `ntpath` case folding in the write / enforce gates, the `$HOME` + `.git` ceiling |
| `test_machine_overlay.py` | `settings_install.seed_machine_overlay`: `OLLAMA_HOST`, the RAM-sized tool memory limit and agent floors, the fresh-install permission mode (`acceptEdits` unless `AGENTIC_MERCY_PERMISSION_MODE`), mode 0600, render carries them |
| `test_router_replay.py` | `scripts/router_replay.py` on a synthetic transcript tree: report shape (counts only), skips, `--check` exit codes |
| `test_ui_checklist.py` | the visual installer prints the end-of-run checklist and the PATH hint to its console (DU-9) |
| `test_installer_preserve.py`, `test_userspace_safety.py`, `test_ollama_safety.py` | Santa installer review: `*.pre-install` copies on relocation, first-install settings merge, symlink / hardlink containment, Windows-style absolute / climbing tar names skipped on every OS, verified downloads + pinned hashes, partial ollama repair, systemd unit ownership |
| `test_settings_carry.py` | the re-render keeps `/plugin`, marketplace and permission-rule additions (template wins shared keys, lean-ctx injections never carried), `--check` ignores additions, settings-safety on user deny rules, atomic write |
| `test_doctor_wp7.py` | doctor rows added or hardened by WP7 (mods version/runtime, MCP roster pins, installed plugins, secret-file modes, lean-ctx zero injection) on injected inputs: no claude CLI, no network |
| `test_manifest_wp7.py` | manifest invariants: `manifest.version` = the CHANGELOG head, the Windows github launcher and the playwright post-step follow the manifest pins, python tools pinned, ponytail is the mandatory plugin, ollama URLs are the `{OLLAMA_URL}` token (default `127.0.0.1`, never `localhost`: 2 s per connection), jcodemunch carries `JCODEMUNCH_ALLOW_REMOTE_SUMMARIZER=1`, and `deps.reconcile_mcp_env` picks up an old URL or a new `OLLAMA_HOST` (only the three URL keys move) |
| `test_render_wp7.py` | `render.py` / `backups.py` fixes (bounded backups, `--check` with `--out/--user`, Claude-managed seed keys) in tmp dirs |
| `test_selfheal_wp7.py` | `self_heal` / relocate / `install.py --ci` rehearsed in a sandbox with a subprocess recorder |
| `test_ci_wp7.py` | text checks that the CI workflow keeps its steps (matrix, SHA-pinned actions, mods job, sandboxed `install.py --ci`) |
| `test_grep_gates_wp7.py` | gate G6: no machine home literals in tracked Markdown |
| `test_jcodemunch_config.py` | JSONC read, required keys, list union, `config set`-only writes with backup, dry-run |
| `test_mcp_secret_transport.py` | secret-safe MCP registrations |
| `test_mcp_restore_shim.py` | SANTA1C-03: with `claude` only a `.cmd` shim, an entry whose JSON holds `%`, `!` or an escaped `"` is skipped (`WARN(cannot pass cmd.exe; left as is)`) BEFORE `claude mcp remove`; a real `claude.exe` carries any JSON (faked `which` / `subprocess.run`) |
| `test_deps_sub.py`, `test_detect_fields.py` | `deps._sub` keeps a Python path with spaces as one argv element (`py -3` still splits); `detect.Env` has no pipx field |
| `test_deps_npm_pkg.py` | a bin-less global npm dep (`npm_pkg`) is probed under `npm root -g`; a sandbox install gets `--prefix $HOME/.npm-global` |
| `test_settings_tier_first.py` | a fresh install detects the plan tier before the first settings render |
| `test_vendor_marker_stable.py` | re-vendoring an unchanged sha keeps `.vendored.json` `vendored_at` |
| `test_validate_skills.py`, `test_vendor_sources.py` | skill validation (incl. R13 WARN on inert lowercase intents); vendored skills match `skills-sources.json` + R10 |
| `test_build_skills_index_plugins.py` | `build_skills_index` leaves out skills of plugins the template disables (`claude-session-driver`); enabled plugins stay indexed (NEW-08) |
| `test_ci_portability.py`, `test_portability_gate.py` | CI-green regressions; portability grep-gates |
| `test_dox_tree.py` | every directory `CLAUDE.md` names each tracked file beside it |
| `test_agent_frontmatter.py` | agent frontmatter and body contracts: `maxTurns` (from `turn_caps` in `model-policy.json`), `## Turn budget` on the 7 report agents, description <= 1,200 chars with one example, tier models |
| `test_skill_text_contracts.py` | skill text agrees with the always-on rules: no remote-script installers, no commit/reset imperatives, no server starts, dead helpers stay deleted |
| `test_claude_wrapper.py` | `bin/claude` (scope + launch caps) and `bin/claude-tmux` with fake binaries; subcommands pass through; both launchers' MemoryHigh |
| `test_doctor_real_claude.py` | F3: the doctor's `real_claude()` skips bin/claude; mods-runtime runs the real binary |
| `test_npm_bins.py` | F1: npm CLIs are linked into `~/.local/bin` from npm's own prefix (dangling links replaced, a user's file kept); PRESENT in the prefix is not reinstalled |
| `test_doctor_cli_on_path.py` | F1: doctor row `cli-on-path` (stdio MCP commands and linked npm CLIs on the `$SHELL -lic` PATH; a FAIL re-runs the deps step) |
| `test_leanctx_pinned.py` | F2: lean-ctx installs with `--ignore-scripts` plus the pinned sha256-checked release binary; config merged after deps; `lean-ctx-runtime` row |
| `test_askpass_seed.py` | F8: `seed_askpass` copies the example helper (mode 700) only on the owner's opt-in; the helper reads `.env` only |
| `test_oomguard_setup.py` | `installer/oomguard_setup.ensure()` and `installer/doctor_oomguard.rows()`, every seam faked |
| `test_oomguard_integration.py` | the OOM guard against the real user manager and journal (skipped without a systemd user bus: Windows replica, CI) + hermetic `attach_live()` unit cases; the one real OOM kill (`test_capped_scope_dies_alone_and_the_kernel_line_parses`) is opt-in `CLAUDE_TEST_LIVE_OOM=1` and tags its scope `claude-test-oom-<pid>` |
| `test_statusline_mem.py` | `scripts/statusline.py` OOM guard parts: `seg_mem`, plan tier, usage guard, session bridge, ledger heartbeat |
| `test_restore_sessions.py` | `scripts/restore_sessions.py` with fake `tmux` / `claude` on PATH; ledger, tier file, cursor and locks in a tmp dir |
| `test_plan_tier.py` | `lib/plan_tier.py` + `hooks/plan-tier-detect.py` from fixture credentials (never the machine's): state file, notice, render overrides, ceilings, no token material logged; a tier change spawns `installer/render.py` (fallback `scripts/build_workflows.py`) |
| `test_workflows_lib.py` | generated workflow library: `node --check`, forbidden globals, meta literal, tier literals, `build_workflows.py --check` drift, pro render, stub runs under `fixtures/workflows/stub.mjs` (skipped without node), incl. chunked review and retry-once scenarios (build, review, invoke); REVIEW2 shared fixes: review fan-out bound (`MAX_CHUNKS` 8), `packages listed:` count log, XL `review:2` keeps an incomplete review's verdict and marks the result incomplete, impl retries per sub-step on a mixed surface, per-agent notes files (`notes/santa-<id>-<tag>.md`, `notes/verify-<id>.md`) |
| `test_context_budget.py`, `test_directives.py` | always-on context regrowth guard (doctrine <= 20k chars, `CLAUDE.md` <= 4k, `alwaysLoad` only on sequential-thinking); every TEXT/SOFT directive key sits in an always-on file (`DIRECTIVES_ROOT` swaps in drafts) |
| `test_measure_context_cost.py`, `test_skill_health.py`, `test_split_machines_file.py` | `measure_context_cost.py` (TOKEN-BUDGET), `skill_health.py` (report + skillOverrides map), `split_machines_file.py` (split, check, exact undo) |
| `test_golive_plan.py`, `test_secrets_scan.py`, `test_replica_sync.py` | `golive.py` step plan + preflight helpers (`ostools.apt_available`, `basetools.ensure_gitleaks`); secrets layer 2 (key names only in output); replica sync with a fake ssh |
| `test_library_index.py`, `test_validate_imports.py` | `vendor_library.py` (copy, sanitise, header, self-validate) + `build_library_index.py` (`--check`); `validate_imports.py` classes U P V W S M |
| `fixtures/` | `hook-events/` (one payload per dispatch chain, incl. `stop-failure.json` and `instructions-loaded.json`; smoke-run by the doctor), `ledger/`, `plan-tier/`, `secrets/`, `validate_imports/`, `workflows/`, `machines.sample.md` (synthetic, TEST-NET only), `oomguard.off.json` |

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none

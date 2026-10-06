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
- No PyYAML or other non-stdlib imports (the CI interpreter is bare).
- Tests that load installer modules with `_load()` replace `sys.modules[...]`; a test that
  monkeypatches a module `selfheal` imports lazily must pin it with
  `monkeypatch.setitem(sys.modules, …)` (see `test_selfheal_wp7` `box`).
- Doctor/installer sandboxes hide `claude` and `tsc` from `shutil.which` (I-17).
- `conftest.py`: temp telemetry/state dirs are created only when the env var is not preset
  and removed at session end; the autouse `_restore_environ` guard puts `os.environ` back
  after every test (installer code writes it directly: `CLAUDE_CONFIG_DIR`, the relocation
  guard); the `symlink_ok` fixture skips when the account cannot create symlinks (Windows
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
| `test_statusline.py`, `test_statusline_win.py` | `scripts/statusline.py` run as a subprocess the way Claude Code runs it (git cache in `CLAUDE_STATUSLINE_CACHE_DIR`): model/effort, context bar, cost, 5-hour/7-day windows, git counts, `NO_COLOR`, `COLUMNS`; no wall-clock test (the warm path is pinned structurally: the `-X importtime` list has no hashlib / tempfile / subprocess, a fresh cache entry makes zero git calls); the Windows file: crc32/adler32 cache key (no hashlib, no tempfile on a usable `TEMP`; a dead or unset `TEMP` falls back to `tempfile.gettempdir()`), no `*.json.<pid>` leak when `os.replace` fails, 1.5 s Windows git timeout keeps the last good summary only while < 60 s old and kills the whole git tree (a grandchild holding the pipe cannot extend the refresh), LF output, UTF-8 without `PYTHONUTF8` and a lone surrogate printed as `?`, BOM stdin |
| `test_semgrep_env.py` | the TEMPLATE env sets `EIO_BACKEND=posix` (semgrep-core's io_uring dies under the 8 MB memlock limit); the Windows render drops it (`test_render_win.py`) |
| `test_envelope_precedence.py` | any skill or `rules/backend.md` that prescribes a nested `error:{…}` envelope also says "the project contract wins" |
| `test_timeout_ladder.py` | each event's worst dispatch path (sequential gates/mutators/sync execs + parallel advisories, priority>0 skipped past `budgets.ms`) stays 1 s under its settings `timeout` |
| `test_mods_contract.py` | `manifest.mods` shape; every enabled mod passes `validate_mods.py` static M1–M6; the M3 scan ignores comments |
| `test_settings_wp8.py` | template contract (A-03): marketplaces `karpathy-skills`, `nateherk`, `ponytail` carry `autoUpdate: false` (hook-running plugins from personal repos update by hand); `superpowers-marketplace` stays true |
| `test_skills_wp2.py` | new skills' frontmatter, curated keywords, router recall for the C-13 prompts, core-skill-set budget, rule and skill `paths:` globs vs representative project and infra paths |
| `test_skills_wp2_refs.py` | no stale plugin/skill/rules names or broken relative links in skills, router cap in docs = `max_skill_pushes`, Higgsfield/kokonutui listing ≤420 chars, workflow-audit lean + user-only, baseline/verification/dead-code text contracts |
| `test_autonomy_wpd.py`, `test_autonomy_wpd_daily.py`, `test_autonomy_wpd_fixtures.py` | autonomy WP-D: `deps.reconcile_mcp_pins` (swap/restore/skip/idempotent/env-never-logged), doctor roster FAIL-when-repairable + `_repair` route, exact manifest pins, the dispatch link; `selfheal-daily.py` (24 h stamp, lock, independent steps, summary contract, probe/doctor no-op, `--dry-run`). The fixtures module puts a fake `claude` on PATH that records argv and edits `$HOME/.claude.json` (plus a `claude.cmd` shim on Windows, which runs no shebangs); no real CLI or network |
| `test_userspace.py`, `test_ostools.py`, `test_ollama_setup.py`, `test_headless_install.py`, `test_pyyaml_dep.py`, `test_npm_pack.py` | one-command fresh-Ubuntu install: node/claude/uv/gh in `~/.local` (SHA check, pinned claude, npm fallback), apt tools via root / `sudo -n` / one batched line, ollama + models, `--headless` vs `--ci`, install order + the end-of-run checklist, PyYAML via uv, `lean-ctx-bin` through a tarball, graphify `mcp` pin. Downloads, subprocesses and HOME are injected (set `USERPROFILE` beside `HOME`: `Path.home()` reads it on Windows; force `os_arch` to linux to test the POSIX install logic there); `conftest.py` sets `AGENTIC_MERCY_SKIP_BASE_TOOLS=1` suite-wide |
| `test_wintools.py`, `test_wintools_reuse.py`, `test_wintools_deps.py`, `test_wintools_ollama.py`, `test_wintools_wiring.py`, `test_wintools_repair.py`, `test_winlock.py`, `test_winpath.py` | Windows base tools (`wintools` / `winutil` / `winollama` / `winpath`) on `winfakes` (no network, no registry): user-space node / git / claude / uv / gh with pinned hashes, a git on PATH reused only with its `bash.exe` (4 layouts, `CLAUDE_CODE_GIT_BASH_PATH` in process / HKCU / HKLM, never overwritten when valid), cwd-planted binaries never run, Authenticode refusal, `AGENTIC_MERCY_SANDBOX` keeps the tools dir in the profile and `AGENTIC_MERCY_TOOLS_DIR` outside it warns, user PATH / env / Run-key helpers, Windows ollama zip + autostart + disk preflight, `deps` `skip_optional` / `{HOME}` / `&&` steps / Store-stub Python, `basetools.ensure_base_tools` wiring. Audit #2: `winfakes.short_limit` (autouse once imported) makes the fixtures independent of the pytest basetemp length; `test_winlock.py` (one install per tools dir, across processes; busy run changes nothing, a live peer's tmp dir survives), `test_wintools_repair.py` (npm prefix repaired on re-run, undeletable leftovers are not failures, a failed extraction keeps the verified archive and the retry downloads nothing, one `CLAUDE_CODE_GIT_BASH_PATH` reader), `deps` `_win_shell_wrap` never registers a bare shim, `check_prereqs` counts `sys.executable` and the tools-dir python and never a cwd `py` or cwd `git`, `deps.py` has no raw `shutil.which` (AST), the doctor `base-tools` row reads the bash variable from the registry, an ollama zip without `ollama.exe` is kept for the retry |
| `test_doctor_fx3.py`, `live_interpreter.py` | audit #2 doctor / self-heal: row `statusline` (injected runner, real runner), `_repair` re-render routes for `statusline` / `hook-command`, `selfheal._stale` + the daily settings step on a gone interpreter, `secret-perms` SKIP over zero files, `doctor.main` on a cp1252 pipe (child process), the load-only classifier (typed errors / assertions never load); `live_interpreter.pin(monkeypatch)` makes `detect._python_exe` answer the live `settings.json`'s interpreter (or an injected one) and runs the `hook-command` / `statusline` rows with the real `HOME`/`USERPROFILE` (the POSIX render says `${HOME}/.claude/...`; a sandboxed HOME made them exit 2), so `test_doctor_is_green`, `test_doctor_deterministic_checks_pass` and `test_render_semantically_equals_live` pass under any Python |
| `test_doctor_basetools.py`, `test_doctor_win.py`, `test_doctor_win_mods.py`, `test_npx_cache.py` | doctor on Windows with injected inputs: row `base-tools` (FAIL on an empty machine, git without bash = WARN, SKIP under `AGENTIC_MERCY_SKIP_BASE_TOOLS` / `--ci`); `secret-perms` by SDDL (letter pairs, NULL DACL, `CodexSandboxUsers` = WARN, System32 `icacls`); `hook-command` row; `mods-runtime` load-only retry/WARN; junctions; UTF-8 helper decoding (AST: no `text=` without `encoding=`); npx cache prune (half-written `_npx/<hash>` entries only, entries newer than 10 min kept) and sequential warm after a pin change |
| `test_install_entry.py`, `test_install_entry_run.py`, `test_install_bootstrap.py`, `test_safe_fetch_zip.py`, `test_safe_fetch_download.py` | one-click entry: `install.cmd` → `install.ps1` (parsed on Windows PowerShell 5.1: `-Ci` / `--ci` never installs Python, Find-Python by exit code, pinned + Authenticode Python, sandbox refusal), `bootstrap` / `relocation` (fatal copy failures, no Mark-of-the-Web spread, git-absent message, PATH hint); contained ZIP extraction (device names, drive, `..`, symlink flag, MAX_PATH); `download` https-only, 64-hex hash required with `require_hash`, a denied rename retried, only a dead pid's `<dest>.tmp-*` swept. `test_install_entry_run.py` (Windows only) runs `install.ps1` under PowerShell 5.1 and `install.cmd` under cmd.exe on scratch copies, each behind TWO guards (`AGENTIC_MERCY_SANDBOX=1` and a scratch manifest whose Python pin is `https://127.0.0.1:9/x.exe` with a zero hash): bracket / `%` clone paths, no `PSExecutionPolicyPreference` in the child, nothing unblocked outside the workbench, the pause only for Explorer's `/c ""path" "` |
| `test_win_branches.py` | Windows-only code paths run on every OS by flag stubbing: `detect` (`py -3` / forward-slash interpreter), `deps` post-steps and `install_windows`, `graphify_launcher` venv layout, `ntpath` case folding in the write / enforce gates, the `$HOME` + `.git` ceiling |
| `test_installer_preserve.py`, `test_userspace_safety.py`, `test_ollama_safety.py` | Santa installer review: `*.pre-install` copies on relocation, first-install settings merge, symlink / hardlink containment, Windows-style absolute / climbing tar names skipped on every OS, verified downloads + pinned hashes, partial ollama repair, systemd unit ownership |
| `test_settings_carry.py` | the re-render keeps `/plugin`, marketplace and permission-rule additions (template wins shared keys, lean-ctx injections never carried), `--check` ignores additions, settings-safety on user deny rules, atomic write |
| `test_doctor_wp7.py` | doctor rows added or hardened by WP7 (mods version/runtime, MCP roster pins, installed plugins, secret-file modes, lean-ctx zero injection) on injected inputs: no claude CLI, no network |
| `test_manifest_wp7.py` | manifest invariants: `manifest.version` = the CHANGELOG head, the Windows github launcher and the playwright post-step follow the manifest pins, python tools pinned, ponytail is the mandatory plugin, ollama URLs are `127.0.0.1` (never `localhost`: 2 s per connection) and `deps.reconcile_mcp_env` picks the change up |
| `test_render_wp7.py` | `render.py` / `backups.py` fixes (bounded backups, `--check` with `--out/--user`, Claude-managed seed keys) in tmp dirs |
| `test_selfheal_wp7.py` | `self_heal` / relocate / `install.py --ci` rehearsed in a sandbox with a subprocess recorder |
| `test_ci_wp7.py` | text checks that the CI workflow keeps its steps (matrix, SHA-pinned actions, mods job, sandboxed `install.py --ci`) |
| `test_grep_gates_wp7.py` | gate G6: no machine home literals in tracked Markdown |
| `test_jcodemunch_config.py` | JSONC read, required keys, list union, `config set`-only writes with backup, dry-run |
| `test_mcp_secret_transport.py` | secret-safe MCP registrations |
| `test_mcp_restore_shim.py` | SANTA1C-03: with `claude` only a `.cmd` shim, an entry whose JSON holds `%`, `!` or an escaped `"` is skipped (`WARN(cannot pass cmd.exe; left as is)`) BEFORE `claude mcp remove`; a real `claude.exe` carries any JSON (faked `which` / `subprocess.run`) |
| `test_deps_sub.py`, `test_detect_fields.py` | `deps._sub` keeps a Python path with spaces as one argv element (`py -3` still splits); `detect.Env` has no pipx field |
| `test_validate_skills.py`, `test_vendor_sources.py` | skill validation (incl. R13 WARN on inert lowercase intents); vendored skills match `skills-sources.json` + R10 |
| `test_build_skills_index_plugins.py` | `build_skills_index` leaves out skills of plugins the template disables (`claude-session-driver`); enabled plugins stay indexed (NEW-08) |
| `test_ci_portability.py`, `test_portability_gate.py` | CI-green regressions; portability grep-gates |
| `test_dox_tree.py` | every directory `CLAUDE.md` names each tracked file beside it |

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none

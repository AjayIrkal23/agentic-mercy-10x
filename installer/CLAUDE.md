# `installer/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename an installer module or change the flow.

## What lives here

The **one-command, UI-only, fully-automatic** installer for the `~/.claude`
workbench. Entry points at the repo root (`install.py`, `install-ui.py`,
`install.sh`, `install.ps1`, `install.cmd`) all funnel through `bootstrap.py` → the visual UI →
the self-heal loop. Windows one-click: `install.cmd` → `install.ps1` (finds Python or installs the
pinned, hash- and Authenticode-checked python.org build; forwards args, keeps the exit code) →
`install.py`; every other tool is `wintools.py`'s job. There is **no CLI install path** and **no user interaction** —
the user runs one command and everything else (relocate → install → repair →
re-check) happens automatically until the doctor reports 0 FAIL.

## The flow (what runs, in order)

1. **`bootstrap.py`** — auto-detect canonical `~/.claude` (`$CLAUDE_CONFIG_DIR`
   else `~/.claude`). If this clone is elsewhere: `git checkout` the clone to
   pristine committed bytes (fixes Windows autocrlf drift at the *source*; no git = says so
   and skips), merge-copy the bundle into `~/.claude` (`relocation.py`: overwrite bundle
   files, **preserve** user runtime — projects/, todos/, memory/, state/, settings.user.json;
   exclude `.git`; a failed copy of a read-only or locked file is FATAL and listed, never OK;
   no `Zone.Identifier` stream), then **re-launch** from the target (guard env
   `AGENTIC_MERCY_RELOCATED` prevents an infinite loop). Otherwise launch the UI in place.
   A Windows checklist starts with "open a new terminal" (user PATH changed); the
   `export PATH=…` hint is POSIX only.
2. **`ui.py`** — stdlib web server on `127.0.0.1`. Auto-starts the self-heal loop
   on boot (no button); serves `ui.html`; `/api/progress` streams every step,
   `/api/status` is the live preflight grid (from `verify.collect`).
3. **`selfheal.py`** — the loop: install pass once (**base tools** via `basetools.py`:
   apt OS tools, node, claude, uv, gh on POSIX; `wintools.py` git, node, claude, uv, gh
   plus user PATH on Windows → prereqs → deps → ollama + models → `claude mcp add`
   from `manifest.mcp_servers` → MCP env reconcile → marketplaces + plugins →
   lean-ctx `config.toml` merge → render `settings.json` → post-steps) → doctor →
   repair FAILs → repeat until 0 FAIL or `max_rounds`. Success == 0 doctor FAIL. The
   result carries `todo`: the ONE batched end-of-run message (sudo command if any + the
   human-only steps), printed by `bootstrap._run_headless` and emitted as `todo` rows.
4. **`--headless`** (`install.sh --headless`): the REAL install without the browser (fresh
   server, container, ssh): the same loop, console output, then the checklist.
   **`--ci`** (`install.py --ci`): the same flow headless, no web UI; every network
   step is planned (`WOULD-*`), local repo steps really run (the read-only plan is
   `deps.py`'s). Used by CI and the
   fresh-machine rehearsal (sandbox `HOME`; `git init` the sandbox parent when it
   lives inside this repo, or repo-scoped hooks will sweep the live tree).
   On Windows `install.ps1 -Ci` and `install.cmd --ci` are the same mode (`--ci` lands in
   `$Rest`): plan only, and it STOPS when no Python is found instead of running the python.org
   installer. Rehearse with `AGENTIC_MERCY_SANDBOX=1` + scratch `USERPROFILE`/`HOME`/`LOCALAPPDATA`:
   real installer steps refuse or `SKIP(sandbox)` (Python installer, `claude.exe install`).

## Local conventions

- **MCP source of truth** = `manifest.json.mcp_servers` → user-scope `~/.claude.json`.
  The template has NO `mcpServers`. Secrets only via `env_from` (installer env).
- **Windows MCP commands:** Claude Code spawns MCP stdio servers without a shell, so on
  Windows `deps._mcp_argv` registers `npx` and any `.cmd`/`.bat` shim as `cmd /c …`
  (`.exe` and `py` stay direct). A `posix_only` server with a `windows_add` (github →
  `scripts/github-mcp-launcher.py`) registers that command instead of being skipped.
- **Settings path token on Windows is forward-slash** (`detect.py` → `C:/Users/<you>/.claude`):
  backslashes break the rendered JSON and Git Bash hook commands. `render.machine_subs()` is
  the one source of this machine's tokens (render CLI, `check_equivalence`, tests); a
  concrete (Windows) `CLAUDE_DIR` is pinned to the checkout being rendered (`_ROOT`), so
  a sandboxed HOME never moves it. `{{PYTHON_EXE}}` (direct interpreter, forward slashes;
  `Env.python_exe`, added by `machine_subs`, NOT in `detect().tokens`) is for `statusLine`
  only (no `py` launcher start-up cost); hooks keep `{{PYTHON}}`. `settings_install._subs(env)` adds
  it for the install-time render (else `statusLine.command` fell back to `python3` and
  `render-equivalence` FAILed). `settings_diff.fill_token` quotes a token with a space or shell-special
  character as ONE word and raises `ValueError` for `"`, `$`, a backtick. The Windows render drops
  `env.EIO_BACKEND` (no posix backend; it kills every semgrep scan), `--check` applies the same
  transform; the template still carries it. `PowerShell` is in the template's three shell matchers.
- **Config outside `~/.claude` is the installer's job too:** lean-ctx `config.toml` and
  jcodemunch `config.jsonc` carry manifest keys (merge, never clobber, backup first).
- **Never a "lean-ctx" string in settings.json/template** — lean-ctx ≥3.10 re-injects
  hooks/statusLine/deny when it sees one. `render()` raises; doctor `settings-safety` FAILs.
- **Never set `CLAUDE_CONFIG_DIR` to the default `~/.claude`** (`selfheal.pin_config_dir`):
  the claude CLI would then write `~/.claude/.claude.json` instead of `~/.claude.json`.
- **Mods load through the render.** `manifest.mods.enabled` → `render.mod_dirs()` →
  template token `{{MOD_DIRS}}` → `env.CLAUDE_CODE_PLUGIN_DIRS` (absolute forward-slash
  paths joined with `os.pathsep`; key dropped when empty). Claude Code accepts only
  absolute or `~` paths there. `_normalized` compares the list as a set, and
  `pluginConfigs` (per-mod settings Claude Code writes) is carried over like the other
  Claude-managed keys. Post-step `validate-mods` and doctor row `mods` check them.
- **Claude-managed template keys are first-install seeds** (A-07, A-08): `theme`,
  `effortLevel`, `contextWindow`, `autoCompactWindow`, `remoteControlAtStartup`,
  `agentPushNotifEnabled`, `skipDangerousModePermissionPrompt`. `render.py` carries the live
  values afterwards and `--check` ignores them. `VALIDATION_CLIENT=sdk` pins tdd-guard's
  current default; `RETICLE_TELEMETRY=0` also covers non-MCP `npx @reticlehq/server` runs.
- **Marketplace auto-update (A-03):** `karpathy-skills`, `nateherk` and `ponytail` are
  `autoUpdate: false` in the template (their plugins run hooks every session from personal
  repos); update them by hand, then run the doctor. `superpowers-marketplace` stays true.
- **Pinned tool versions:** every npx MCP server, the lean-ctx npm install and the semgrep /
  jcodemunch-mcp / graphify installs carry an exact version in `manifest.json`. Drift between a
  live registration and an exact pin is repaired, not just reported: `deps.reconcile_mcp_pins`
  (remove → `claude mcp add-json` → restore on failure; env copied verbatim; OAuth/http servers,
  unpinned manifest entries and non-npx/uvx live entries skipped; runs after
  `reconcile_mcp_env` in `selfheal._install_pass` and from `_repair` on a `mcp-roster` FAIL).
  `doctor_mcp.roster_status` returns FAIL for that drift when the claude CLI is present (the
  self-heal repairs it), WARN when no reconcile is possible; the deprecated-github note stays a WARN.
  `doctor_mcp.pin_drift` / `swap_spec` are the one parse shared by doctor and reconcile.
  `hooks/tools/selfheal-daily.py` (async session-start link) runs the reconcile, missing-CLI
  installs, stale-settings re-render and DRIFT re-vendor once a day. The lean-ctx config is
  written before lean-ctx is installed.
- **Counts are computed** (skills/agents), never pinned in the manifest.
- **Fresh Ubuntu, no sudo (2026-10-05).** `manifest.user_space` + `basetools.py` take a user
  with only git/curl/python3 to doctor 0 FAIL: node from the official tarball
  (`userspace.install_node`, SHA-256 checked, into `~/.local`), Claude Code via Anthropic's
  installer pinned to `mods.claude_version` (npm fallback), uv, gh, ollama as a user-space tarball
  (+ a `systemctl --user` unit or one detached `ollama serve`) with `all-minilm` and
  `qwen2.5-coder:3b` pulled. apt packages (`ostools.py`: canberra, notify-send, ss, pipewire,
  curl) are installed as root or through `sudo -n`; otherwise ONE `sudo apt-get install -y …`
  line goes in the final checklist. Never a failure. `AGENTIC_MERCY_SKIP_BASE_TOOLS=1` skips
  all of it (offline machines; `tests/conftest.py` sets it). macOS is untouched
  (`ensure_userspace` returns nothing off POSIX); Windows has its own branch below.
- **Fresh Windows, no admin (v4.1).** `basetools.ensure_base_tools` routes to
  `wintools.ensure_wintools` (no apt): git (PortableGit), node, claude (`claude.exe install`,
  pinned), uv, gh from `manifest.user_space.windows` (version + SHA-256 per arch) into
  `winpath.tools_dir()` (`AGENTIC_MERCY_TOOLS_DIR`, else `%LOCALAPPDATA%\Programs\agentic-mercy`,
  kept inside the profile under `AGENTIC_MERCY_SANDBOX=1`; a dir outside it adds a `tools-dir`
  WARN row, never a refusal). `winpath.py` edits HKCU `Path` / env / Run key through an injectable
  `WinRegistry`. **Git reuse rule (`winutil.git_bash`, shared with the doctor):** a git on PATH is
  PRESENT only with `<root>\bin\bash.exe` within 3 parent levels of `git.exe`, or when
  `CLAUDE_CODE_GIT_BASH_PATH` (process, HKCU, HKLM) names an existing `bash.exe`; `finish` sets
  that variable only when none of the three names an existing file, so a valid one is never
  overwritten. `winutil.which` drops a cwd hit (py 3.10/3.11 would run a planted `claude.exe`);
  `pick_python` rejects the Store stub. Downloads need a hash (`require_hash`); `claude.exe` must be
  Authenticode-Valid and signed `Anthropic, PBC`; PortableGit has no signer pin (the hash is the
  control). `winollama.py`: zip, completeness marker, disk preflight, Run-key autostart. Serve venv,
  semgrep, jcodemunch-mcp, jdocmunch-mcp install through `uv` (`install_windows`, `&&` split into
  steps, `{HOME}` token); no winget, pipx or `irm | iex`. `install_deps(skip_optional=True)` hides
  `optional: true` entries (daily self-heal). Row `base-tools` stops a false green on an empty machine.
  **Re-runs repair, one install at a time (audit #2):** `winlock.InstallLock` (`<tools>\.install.lock`,
  non-blocking file lock, taken lazily so an all-PRESENT run never creates the dir) around every write
  step of `ensure_wintools` and the ollama unpack: a second installer or the daily self-heal gets
  `SKIP(another install is running; nothing was changed)` and changes nothing (`selfheal` does not yet
  stop the rest of its pass on that row). A zip is deleted only after the install worked: a failed
  extraction keeps the verified archive and the retry reuses it when its SHA-256 still matches the
  pin (`winutil.sha256_ok`), an undeletable leftover (`winutil.drop`) is never a failure, and executable
  installers (PortableGit SFX, `claude.exe`) are always removed. The npm prefix of OUR node is its own
  idempotent step (`npm config get prefix`, set again when wrong; row `npm-prefix` on failure). An MCP
  command that is not a resolved `.exe` registers through `cmd /c` (`deps._win_shell_wrap`), never as
  a bare shim name. `winutil.bash_values(environ, registry)` is the one reader of
  `CLAUDE_CODE_GIT_BASH_PATH` (process, HKCU, HKLM) for the installer AND doctor row `base-tools`
  (`check_base_tools(..., registry=)`; a real call on Windows reads the registry, read-only). `deps.py`
  never calls `shutil.which` itself (AST test): every lookup is the cwd-safe `winutil.which`.
  `install.ps1` takes every path with
  `-LiteralPath` (a clone under `claude [work]`), checks `installer\manifest.json` before it
  unblocks anything, and drops `PSExecutionPolicyPreference` before it starts Python; `install.cmd`
  pauses only for Explorer's argument-less `/c ""path" "`. `install.py --ci` ends `install (plan only): OK`.
- **Hard-won fresh-install fixes:** PyYAML is REQUIRED (uv `--target {USER_SITE}`: no pip, PEP
  668), the graphify serve venv pins `mcp==1.28.1` (2.x dropped `mcp.types.AnyUrl`),
  `lean-ctx-bin` installs through `npm_pack.py` (its preinstall `pkill -f lean-ctx` kills the
  npm that runs it), and a `settings.json` that lean-ctx's first run injected into is always
  re-rendered (`carry` never brings `lean-ctx` entries back).
- **The install never destroys what the user already has** (Santa installer review):
  on the FIRST install (bundle items missing at the target; a re-run from the clone would flag the
  files the installer regenerated) `relocation._put` keeps a differing existing file once as
  `<name>.pre-install` before the relocation overwrites it (never overwritten later; one summary line
  is printed); `settings_install.preserve_existing` runs FIRST in the install pass (lean-ctx's postinstall
  injects into settings.json during the deps step) and keeps a permanent `settings.json.pre-install`
  (the dated `.bak-*` rotate) and, for a settings.json we did not write, seeds `settings.user.json` from the
  user's env (provider / proxy / auth keys win a clash), `apiKeyHelper`, `model`,
  `permissions.defaultMode` and own hooks (`settings_seed`; `render` appends overlay hooks after the
  workbench's, never twice; lean-ctx injections are never seeded).
- **Downloads and archives are contained** (`safe_fetch.py`): `download` is https-only (redirects
  too; `fetch` keeps http for 127.0.0.1), checks Content-Length and a pinned SHA-256
  (`manifest.user_space.gh/ollama/windows`: pinned version + hash per arch, a given hash must be 64
  hex, `require_hash=True` makes it mandatory; node on Linux is checked against SHASUMS256) into
  `<dest>.part` and renames only after that; `extract_zip_prefix` is the ZIP twin (refuses `..`,
  drive, device names `CON`/`NUL`/`COM¹`…, symlink flag, over-long `MAX_PATH`; merges into an
  existing dir); `extract_prefix` refuses names
  and symlink / hardlink targets that leave the prefix, also through links made earlier in the same
  archive. Tar names are judged as POSIX paths on every OS (`_absolute` / `_escapes`: a leading `/`,
  any drive, `..` with either separator): Windows' native `Path` took `/abs/x` as relative. ollama counts as installed only with `lib/ollama/.agentic-mercy-complete` (a binary without
  its libs is repaired on the next run); its systemd user unit is created only when none exists and
  the binary is ours, never rewritten or re-enabled; `ostools` prints the exact `sudo -n env … apt-get`
  line before running it. `npm_pack` removes only dangling links into the lean-ctx install.
- **Re-render keeps the user's additions** (`settings_diff.carry`): `permissions.allow/deny/ask`
  (union), plugins enabled through `/plugin`, extra marketplaces; the template wins a shared key,
  `render.py --check` ignores additions the template lacks, settings.json is written atomically.
  `mcp_restore.replace_entry` checks the restore of a failed `mcp add-json` (`FAIL(unregistered)`;
  the daily run re-adds a missing manifest server), and before the remove it asks
  `platform.passes_cmd_exe` for both entries: with `claude` only a Windows `.cmd` shim, JSON that
  cmd.exe cannot carry (`%`, `!`, an escaped `"`) leaves the server as is (`WARN(cannot pass cmd.exe; left as is)`).
- **Doctor on Windows (24 rows; `--ci` SKIPs the machine rows):** `secret-perms` is SID-based
  (`icacls /save` SDDL from System32; owner, SYSTEM, Administrators, CREATOR OWNER trusted; any other
  readable ALLOW or a NULL DACL is a WARN naming the SID; letter pairs like `CC` count; an unknown token
  counts as read; covers `settings.json` + its copies, `settings.user.json`, `~/.claude.json`; no file
  to check = SKIP "no secret files found", never PASS); the
  `CodexSandboxUsers` grant is reported, the workbench never changes ACLs. `mods-runtime` calls a failure
  load-only only when no assertion text and no typed error (`TypeError`, `ReferenceError` ...) appears and
  every `(fail)` test has its own `timed out after` line or the known teardown rejection (`a rejection
  nothing handled` + `no hooks module of that name is loaded`); retry once, WARN only when the re-run is
  load-only too, any other rejection is a FAIL. `selfheal._repair` matches the failed row by whole name, so
  `mods-runtime` re-renders nothing. `hook-command` and `statusline` (the rendered `statusLine.command`
  with a sample payload: exit 0 + a non-empty line; 127 = the pinned interpreter moved) run under `--ci`
  too when a rendered `settings.json` exists; a FAIL of either routes `_repair` to a forced re-render, and
  `selfheal._stale` (so the daily self-heal) also re-renders when a command's absolute interpreter path is
  no longer a file. `doctor.py` switches stdout/stderr to UTF-8 (`errors=replace`) so a piped cp1252 console
  cannot crash on a non-ANSI profile path. Helpers decode UTF-8 (`encoding=`, never `text=True`); junctions count as
  links; `tsc` runs with `cwd` = the mod folder; the ollama probe is `127.0.0.1` (`localhost` tries `::1`).
- **npx cache self-heal (`npx_cache.py`):** after `reconcile_mcp_pins` changed a server,
  `prune_npx_cache` deletes half-written `_npx/<hash>` entries (`node_modules`, no `package.json`, newest
  mtime of entry / `node_modules` / children older than 10 min) and `warm_npx` runs `npx -y <pin>
  --version` one server at a time from the home dir (a repo `.npmrc` cannot steer it). Skipped offline
  (`AGENTIC_MERCY_SKIP_BASE_TOOLS`) unless a runner is injected.
- **No CLI verbs.** Only `--ci` and `--headless`. Never re-add `install`/`update`/`doctor`/`verify`
  verbs to the entry points — they were removed on purpose. Internal engine modules
  (`doctor`, `deps`, `verify`, `render`) stay importable; only the user-facing
  surface is UI. Unsupported entry-point arguments fail closed before the UI
  starts; run `python installer/doctor.py` for the read-only doctor.
- **Never guess line endings.** R10 (`dir_content_hash`) reads raw BYTES and the
  committed baseline legitimately mixes LF and CRLF in third-party sources. The primary fix is
  `git_restore_worktree` (exact committed bytes); the fallback
  `repair_r10_drift` normalizes CRLF→LF per locked dir and **reverts** if the dir
  hash doesn't then match its baseline — so it can never corrupt a dir.
- **Relocation is merge-overwrite, never delete.** Keep every extra file at the target.
- Success is **0 doctor FAIL**. MCP/plugin registration is *attempted* (`platform.run`'s
  Windows shell fallback runs the `claude` `.cmd` shim) but stays a non-blocking WARN when
  the `claude` CLI / network is absent.

## Key files

| File | Role |
|------|------|
| `bootstrap.py` | auto-detect + relocate (merge, git-restore, re-launch) + launch UI — the single entry |
| `selfheal.py` | install→repair→re-check loop; `git_restore_worktree`; the R10 heal itself moved to `r10_repair.py` |
| `r10_repair.py` | R10 heal split from selfheal: `repair_r10_drift`, `heal_line_endings` |
| `backups.py` | `backup(path)`: dated `<name>.bak-<UTC stamp>` copies (mode 600), newest 3 kept by mtime, `.bak-latest` points at the newest and never dangles; hand-named backups are never pruned |
| `settings_diff.py` | pure settings helpers behind `render.py`: tokenize, overlay merge, the semantic comparison of `render.py --check` (which honours `--out` / `--user`) |
| `ui.py` / `ui.html` | stdlib visual installer; auto-runs the loop on boot; live progress + status |
| `deps.py` | idempotent deps/MCP/plugins/post-steps from `manifest.json` (post-step script = first `.py` arg — NOT `cmd[1]`; `{PYTHON}`→`py -3` shifts the index on Windows) |
| `doctor.py` | health verifier, 24 rows (link-doctor, render, hook-command, statusline, settings-safety, lean-ctx-config, jcodemunch-config, plugins-contract, plugins-installed, generated-in-sync, R9/R10, base-tools, mcp-roster, ollama, secret-perms, mods, mods-runtime …); `--ci` skips machine rows; its 0-FAIL is the loop's success gate. Doctor/installer sandboxes hide `claude` and `tsc` from `shutil.which` (I-17) |
| `doctor_host.py` | host rows: `plugins-installed`, `secret-perms` (POSIX modes; Windows SDDL), lean-ctx floor + unmanaged-keys note |
| `doctor_basetools.py` | row `base-tools`: git (with `bash.exe`), node, claude, uv, gh present on Windows (same `winutil.git_bash` / `winutil.bash_values` / `winutil.which` as the installer); SKIP under `--ci` and `AGENTIC_MERCY_SKIP_BASE_TOOLS`; git without bash = WARN |
| `doctor_hook.py`, `npx_cache.py` | rows `hook-command` (runs the rendered PreToolUse command once with a synthetic payload: Git Bash via `CLAUDE_CODE_GIT_BASH_PATH`, else the bash beside git, else cmd.exe; `sh -c` on POSIX; SKIP only without a rendered `settings.json`) and `statusline` (same shell, `statusLine.command`, throwaway cwd + cache dir); `prune_npx_cache` / `warm_npx` / `maintenance` (re-exported by `deps`) |
| `doctor_mcp.py` | `mcp-roster`: extras, pin drift against the manifest, deprecated packages, needs-auth servers |
| `doctor_mods.py` | `mods` (version policy: the manifest pin is a same-minor minimum) and `mods-runtime` (plugin test, `tsc`) |
| `jcodemunch_config.py` | keeps `~/.code-index/config.jsonc` on `manifest.jcodemunch_config.keys` (tool_surface full, AI summaries, trusted home); writes only via `jcodemunch-mcp config set` (install pass + repair of row `jcodemunch-config`); also deletes indexes rooted at `$HOME`/`~/.claude`/`~/.codex` (they swallow every repo below them) |
| `verify.py` | read-only workflow status → the UI's live preflight sections (version probes run with stdin closed: `tdd-guard` has no `--version` and waits on stdin, and on Windows the timeout only kills the `.cmd` shim) |
| `doctor_checks.py` | source-derived doctor rows shared with `doctor.py` (palette counts, locked-source links, model-routing, hook fixtures) |
| `basetools.py` | the fresh-machine part of the install pass: `before_deps` (apt tools, then node/claude/uv/gh; re-detects env) and `after_deps` (ollama + models); `ensure_base_tools(env, manifest, ci, dry_run)` is the one entry (POSIX `userspace` / Windows `wintools`), also called by the daily self-heal and `_repair` |
| `userspace.py` | no-sudo installs into `~/.local`: node (tarball + SHA-256), Claude Code (official installer, pinned), uv, gh; `extract_prefix` (safe tar extraction); all return status rows, never raise |
| `ollama_setup.py`, `zst_untar.py` | user-space ollama (tar.zst via stdlib zstd / `zstd` / `uv --with zstandard`), user unit or detached serve, model pulls |
| `ostools.py` | apt-only optional OS tools: root or `sudo -n`, else the one batched sudo line; `checklist()` builds the end-of-run message from `manifest.user_space.human_only` |
| `safe_fetch.py`, `safe_tar.py` | `download` (https-only, Content-Length + pinned SHA-256, `.part` then rename), `fetch`, `extract_zip_prefix` (contained ZIP; extraction dir renamed with a ~10 s PermissionError retry, stale `<dest>.tmp-<pid>` swept only for dead pids); `safe_tar.extract_prefix` (contained tar extraction; re-exported here and by `userspace`) |
| `wintools.py`, `winprobe.py`, `winlock.py`, `winutil.py` | Windows base tools (`ensure_wintools`: git/node/claude/uv/gh into the tools dir, rows `PRESENT` / `INSTALLED` / `WOULD-INSTALL(user-space, no admin)`, PATH + `CLAUDE_CODE_GIT_BASH_PATH` via `finish`, the npm-prefix repair); `winprobe.Probe` = "already there and working?"; `winlock.InstallLock` = one install per tools dir; helpers: `git_bash` + `bash_values` (the one git-reuse rule and its env reader), `which` (no cwd hit), `pick_python`, `signature_problem` (Authenticode), `sha256_ok` / `drop` |
| `winpath.py`, `winollama.py`, `relocation.py` | `tools_dir` / sandbox flag, `WinRegistry` (HKCU Path, env, Run key; read-only HKLM); Windows ollama (zip, marker, disk preflight, autostart); the bundle merge-copy split out of `bootstrap` (`relocate`, `.pre-install` keep, `fatal_failures`) |
| `settings_install.py`, `settings_seed.py`, `settings_stale.py` | the settings.json step of the loop (`selfheal._ensure_settings` delegates): permanent `settings.json.pre-install`, first-install overlay seed, atomic write; `seed_overlay` / `append_hooks` / `is_workbench_file`; `settings_stale` also calls settings stale when a rendered hook / statusLine interpreter no longer exists |
| `npm_pack.py` | installs `lean-ctx-bin` from a tarball whose path hides the name (its preinstall `pkill -f lean-ctx` kills a plain `npm install -g`) |
| `mcp_restore.py` | remove + `add-json` with a CHECKED restore (`FAIL(unregistered)`); used by `deps.reconcile_mcp_env/pins` |
| `detect.py`, `render.py`, `links.py`, `manifest.json` | env detection · settings.json render (equivalence gate) · skill links · install contract |

## Gotchas / fragile spots

- The doctor header prints `=== ~/.claude doctor ===` but actually checks the dir
  it runs *from* (`_ROOT`). A green run inside a clone folder ≠ installed for
  Claude Code — Claude Code only reads `~/.claude`. Bootstrap's relocate is what
  makes it real.
- `render-equivalence` / `interpreters` read via `read_text` (newline-normalized)
  → CRLF-immune. **Only R10 is byte-sensitive** — that is the sole line-ending
  repair target.
- `git_restore_worktree` refuses a dirty tree and this repo itself; the heal loop
  restores only CLEAN locked skill dirs. User customizations belong in
  `settings.user.json`, never in tracked bundle files.
- Render is SEMANTIC and carries Claude-managed keys (theme, tui, voice…) over; a
  forced re-render writes `settings.json.bak-<ts>` first.
- `.gitignore` rules must stay root-anchored (`/package-lock.json`, `/feedback/`):
  vendored skills ship such files and R10 hashes them.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
- Related: `../hooks/lib/platform.py` (the Windows `.cmd` shell fallback), root
  `install.py` / `install-ui.py` / `install.sh` / `install.ps1` (thin launchers).

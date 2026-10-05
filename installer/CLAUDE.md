# `installer/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename an installer module or change the flow.

## What lives here

The **one-command, UI-only, fully-automatic** installer for the `~/.claude`
workbench. Entry points at the repo root (`install.py`, `install-ui.py`,
`install.sh`, `install.ps1`) all funnel through `bootstrap.py` → the visual UI →
the self-heal loop. There is **no CLI install path** and **no user interaction** —
the user runs one command and everything else (relocate → install → repair →
re-check) happens automatically until the doctor reports 0 FAIL.

## The flow (what runs, in order)

1. **`bootstrap.py`** — auto-detect canonical `~/.claude` (`$CLAUDE_CONFIG_DIR`
   else `~/.claude`). If this clone is elsewhere: `git checkout` the clone to
   pristine committed bytes (fixes Windows autocrlf drift at the *source*),
   merge-copy the bundle into `~/.claude` (overwrite bundle files, **preserve**
   user runtime — projects/, todos/, memory/, state/, settings.user.json; exclude
   `.git`), then **re-launch** from the target (guard env `AGENTIC_MERCY_RELOCATED`
   prevents an infinite loop). Otherwise launch the UI in place.
2. **`ui.py`** — stdlib web server on `127.0.0.1`. Auto-starts the self-heal loop
   on boot (no button); serves `ui.html`; `/api/progress` streams every step,
   `/api/status` is the live preflight grid (from `verify.collect`).
3. **`selfheal.py`** — the loop: install pass once (**base tools** via `basetools.py`:
   apt OS tools, node, claude, uv, gh → prereqs → deps → ollama + models → `claude mcp add`
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
  a sandboxed HOME never moves it.
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
  all of it (offline machines; `tests/conftest.py` sets it). Windows and macOS branches are
  untouched (`ensure_userspace` returns nothing off POSIX; Windows is the user's later job).
- **Hard-won fresh-install fixes:** PyYAML is REQUIRED (uv `--target {USER_SITE}`: no pip, PEP
  668), the graphify serve venv pins `mcp==1.28.1` (2.x dropped `mcp.types.AnyUrl`),
  `lean-ctx-bin` installs through `npm_pack.py` (its preinstall `pkill -f lean-ctx` kills the
  npm that runs it), and a `settings.json` that lean-ctx's first run injected into is always
  re-rendered (`carry` never brings `lean-ctx` entries back).
- **The install never destroys what the user already has** (Santa installer review):
  on the FIRST install (bundle items missing at the target; a re-run from the clone would flag the
  files the installer regenerated) `bootstrap._put` keeps a differing existing file once as
  `<name>.pre-install` before the relocation overwrites it (never overwritten later; one summary line
  is printed); `settings_install.preserve_existing` runs FIRST in the install pass (lean-ctx's postinstall
  injects into settings.json during the deps step) and keeps a permanent `settings.json.pre-install`
  (the dated `.bak-*` rotate) and, for a settings.json we did not write, seeds `settings.user.json` from the
  user's env (provider / proxy / auth keys win a clash), `apiKeyHelper`, `model`,
  `permissions.defaultMode` and own hooks (`settings_seed`; `render` appends overlay hooks after the
  workbench's, never twice; lean-ctx injections are never seeded).
- **Downloads and archives are contained** (`safe_fetch.py`): `download` checks Content-Length and a
  pinned SHA-256 (`manifest.user_space.gh/ollama`: pinned version + hash per arch; node is checked
  against SHASUMS256) into `<dest>.part` and renames only after that; `extract_prefix` refuses names
  and symlink / hardlink targets that leave the prefix, also through links made earlier in the same
  archive. ollama counts as installed only with `lib/ollama/.agentic-mercy-complete` (a binary without
  its libs is repaired on the next run); its systemd user unit is created only when none exists and
  the binary is ours, never rewritten or re-enabled; `ostools` prints the exact `sudo -n env … apt-get`
  line before running it. `npm_pack` removes only dangling links into the lean-ctx install.
- **Re-render keeps the user's additions** (`settings_diff.carry`): `permissions.allow/deny/ask`
  (union), plugins enabled through `/plugin`, extra marketplaces; the template wins a shared key,
  `render.py --check` ignores additions the template lacks, settings.json is written atomically.
  `mcp_restore.replace_entry` checks the restore of a failed `mcp add-json` (`FAIL(unregistered)`;
  the daily run re-adds a missing manifest server).
- **No CLI verbs.** Only `--ci` and `--headless`. Never re-add `install`/`update`/`doctor`/`verify`
  verbs to the entry points — they were removed on purpose. Internal engine modules
  (`doctor`, `deps`, `verify`, `render`) stay importable; only the user-facing
  surface is UI. Unsupported entry-point arguments fail closed before the UI
  starts; run `python installer/doctor.py` for the read-only doctor.
- **Never guess line endings.** R10 (`dir_content_hash`) reads raw BYTES and the
  committed baseline legitimately mixes LF and CRLF in third-party sources.
  scripts/search.py`, `data/motion.csv`). The primary fix is
  `git_restore_worktree` (exact committed bytes); the fallback
  `repair_r10_drift` normalizes CRLF→LF per locked dir and **reverts** if the dir
  hash doesn't then match its baseline — so it can never corrupt a dir.
- **Relocation is merge-overwrite, never delete.** Copy the bundle in; keep every
  extra file the user already has at the target.
- Success is defined as **0 doctor FAIL**. MCP/plugin registration is *attempted*
  automatically (the `platform.run` Windows shell fallback runs the `claude` `.cmd`
  shim), but stays a non-blocking WARN when the `claude` CLI / network is absent —
  it never gates success.

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
| `doctor.py` | health verifier, 21 rows (link-doctor, render, settings-safety, lean-ctx-config, jcodemunch-config, plugins-contract, plugins-installed, generated-in-sync, R9/R10, mcp-roster, ollama, secret-perms, mods, mods-runtime …); `--ci` skips machine rows; its 0-FAIL is the loop's success gate. Doctor/installer sandboxes hide `claude` and `tsc` from `shutil.which` (I-17) |
| `doctor_host.py` | host rows: `plugins-installed`, `secret-perms`, lean-ctx floor + unmanaged-keys note |
| `doctor_mcp.py` | `mcp-roster`: extras, pin drift against the manifest, deprecated packages, needs-auth servers |
| `doctor_mods.py` | `mods` (version policy: the manifest pin is a same-minor minimum) and `mods-runtime` (plugin test, `tsc`) |
| `jcodemunch_config.py` | keeps `~/.code-index/config.jsonc` on `manifest.jcodemunch_config.keys` (tool_surface full, AI summaries, trusted home); writes only via `jcodemunch-mcp config set` (install pass + repair of row `jcodemunch-config`); also deletes indexes rooted at `$HOME`/`~/.claude`/`~/.codex` (they swallow every repo below them) |
| `verify.py` | read-only workflow status → the UI's live preflight sections (version probes run with stdin closed: `tdd-guard` has no `--version` and waits on stdin, and on Windows the timeout only kills the `.cmd` shim) |
| `doctor_checks.py` | source-derived doctor rows shared with `doctor.py` (palette counts, locked-source links, model-routing, hook fixtures) |
| `basetools.py` | the fresh-machine part of the install pass: `before_deps` (apt tools, then node/claude/uv/gh; re-detects env) and `after_deps` (ollama + models) |
| `userspace.py` | no-sudo installs into `~/.local`: node (tarball + SHA-256), Claude Code (official installer, pinned), uv, gh; `extract_prefix` (safe tar extraction); all return status rows, never raise |
| `ollama_setup.py`, `zst_untar.py` | user-space ollama (tar.zst via stdlib zstd / `zstd` / `uv --with zstandard`), user unit or detached serve, model pulls |
| `ostools.py` | apt-only optional OS tools: root or `sudo -n`, else the one batched sudo line; `checklist()` builds the end-of-run message from `manifest.user_space.human_only` |
| `safe_fetch.py` | `download` (Content-Length + pinned SHA-256, `.part` then rename), `fetch`, `extract_prefix` (contained tar extraction; re-exported by `userspace`) |
| `settings_install.py`, `settings_seed.py` | the settings.json step of the loop (`selfheal._ensure_settings` delegates): permanent `settings.json.pre-install`, first-install overlay seed, atomic write; `seed_overlay` / `append_hooks` / `is_workbench_file` |
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

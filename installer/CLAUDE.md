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
3. **`selfheal.py`** — the loop: install pass once (prereqs → deps → `claude mcp add`
   from `manifest.mcp_servers` → MCP env reconcile → marketplaces + plugins →
   lean-ctx `config.toml` merge → render `settings.json` → post-steps) → doctor →
   repair FAILs → repeat until 0 FAIL or `max_rounds`. Success == 0 doctor FAIL.
4. **`--ci`** (`install.py --ci`): the same flow headless, no web UI; every network
   step is planned (`WOULD-*`), local steps really run. Used by CI and the
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
- **Counts are computed** (skills/agents), never pinned in the manifest.
- **No CLI verbs.** Only `--ci`. Never re-add `install`/`update`/`doctor`/`verify`
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
| `selfheal.py` | install→repair→re-check loop; R10 heal (`git_restore_worktree` / `repair_r10_drift`) |
| `ui.py` / `ui.html` | stdlib visual installer; auto-runs the loop on boot; live progress + status |
| `deps.py` | idempotent deps/MCP/plugins/post-steps from `manifest.json` (post-step script = first `.py` arg — NOT `cmd[1]`; `{PYTHON}`→`py -3` shifts the index on Windows) |
| `doctor.py` | health verifier (link-doctor, render, settings-safety, lean-ctx-config, jcodemunch-config, plugins-contract, generated-in-sync, R9/R10, mcp-roster, ollama …); `--ci` skips machine rows; its 0-FAIL is the loop's success gate |
| `jcodemunch_config.py` | keeps `~/.code-index/config.jsonc` on `manifest.jcodemunch_config.keys` (tool_surface full, AI summaries, trusted home); writes only via `jcodemunch-mcp config set` (install pass + repair of row `jcodemunch-config`); also deletes indexes rooted at `$HOME`/`~/.claude`/`~/.codex` (they swallow every repo below them) |
| `verify.py` | read-only workflow status → the UI's live preflight sections (version probes run with stdin closed: `tdd-guard` has no `--version` and waits on stdin, and on Windows the timeout only kills the `.cmd` shim) |
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

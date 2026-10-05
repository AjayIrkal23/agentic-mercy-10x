# Prerequisites — install these BEFORE running the installer

> **Ubuntu 24.04+ (2026-10-05): only `git`, `curl` and `python3` are needed.** Node, the
> Claude Code CLI, uv, gh, ollama and every package below are installed by the installer into
> `~/.local`, without sudo (`install.sh`, or `install.sh --headless` in a console). The
> table below is still the manual route, and what macOS / Windows need today.

The installer (one automatic, visual, self-healing command — driven by
`installer/manifest.json`) auto-installs and auto-registers everything it can —
`uv`, `pipx`, `semgrep`, `lean-ctx`, `tdd-guard`, `jcodemunch-mcp`,
`jdocmunch-mcp`, `graphify`, **all MCP servers**, and the **plugins** — then
repairs and re-checks itself until every health check is green. But a few base
tools can't be reliably auto-installed cross-platform, so **you install these
four first**, then run the one command. The installer's live status panel (and a
read-only `python check.py`) always tells you exactly what's still missing.

## No root / sudo / Administrator needed

`~/.claude` is your **user home** — `/home/<you>/.claude` (Ubuntu/macOS) or
`C:\Users\<you>\.claude` (Windows) — **not** `/root`, `Program Files`, or any
system directory. The installer writes only to user-owned locations:

- **Ubuntu / macOS:** `~/.claude`, `~/.claude.json`, `~/.local` (uv/pipx/uv-tools), your npm prefix (`~/.npm-global` or nvm)
- **Windows:** `%USERPROFILE%\.claude`, `%APPDATA%\npm` (npm -g), `%USERPROFILE%\.local` (uv/pipx)

So **`install.sh` / `install.ps1` / `install.py` need no sudo and no Administrator.**
(`powershell -ExecutionPolicy Bypass -File install.ps1` runs unelevated — `Bypass`
is per-process, not a system change.)

**The one caveat — `npm install -g` (lean-ctx, tdd-guard):**
- **Ubuntu / macOS:** needs sudo *only* if Node was installed system-wide (`apt install nodejs`, prefix `/usr`). Avoid it: install Node via **nvm** (user prefix, recommended below), or run `npm config set prefix ~/.npm-global` once and add `~/.npm-global/bin` to `PATH`.
- **Windows:** `npm -g` goes to `%APPDATA%\npm` (user) — **never** needs Administrator.

The only Windows UAC prompts come from the **prereq installers** (`winget install
Python/Node/Git` machine-wide) — the base-tool step, not the workbench installer.
`python check.py` shows a **PRIVILEGES** line confirming both `~/.claude` and your
`npm -g` prefix are user-writable.

## Required (4)

| Tool | Why | Ubuntu / macOS | Windows |
|---|---|---|---|
| **Python ≥ 3.10** | The installer is Python; hooks run on it | `sudo apt install python3 python3-pip` · `brew install python@3.12` | `winget install Python.Python.3.12` (ships the `py -3` launcher) |
| **Node.js LTS (+ npm)** | `lean-ctx`, `tdd-guard`, and 9 npx-launched MCP servers (exact versions pinned in the manifest) | nvm: `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && nvm install --lts` · or `apt`/`brew` | `winget install OpenJS.NodeJS.LTS` · or nvm-windows |
| **Git** | Repo clone + line-ending self-repair + hook git calls | `sudo apt install git` · `brew install git` | `winget install Git.Git` |
| **Claude Code CLI** | Registers MCP servers + installs plugins | `npm install -g @anthropic-ai/claude-code` | `npm install -g @anthropic-ai/claude-code` |

> `uv` and `pipx` are **auto-installed** by the installer (uv via the official
> script, pipx via `pip`). If `uv` isn't on `PATH` right after, reopen your shell.

## Then install — one automatic command

**Clone anywhere and run one line.** The installer auto-detects your `~/.claude`,
moves the clone into it (preserving your data), opens the visual installer, and
**installs + self-repairs in a loop until 100%** — no folder picker, no flags,
nothing to click.

**Ubuntu / macOS**
```bash
git clone https://github.com/AjayIrkal23/agentic-mercy-10x ~/agentic-mercy
~/agentic-mercy/install.sh          # = python3 ~/agentic-mercy/install.py  ·  (cloning into ~/.claude works too)
```

**Windows** (PowerShell)
```powershell
git clone https://github.com/AjayIrkal23/agentic-mercy-10x $env:USERPROFILE\agentic-mercy
powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\agentic-mercy\install.ps1   # or: py -3 ...\agentic-mercy\install-ui.py
```

`install.py`, `install-ui.py`, `install.sh`, and `install.ps1` are all the **same
one automatic installer** — nothing to configure (the only flag is `--ci`).
It opens a local web page (127.0.0.1, stdlib only — no Node/Electron) that
**auto-runs** the whole install: a live panel shows prerequisites · privileges ·
deps · MCP servers · plugins · wiring turning green as each step and repair round
completes, ending in a **WORKFLOW ACTIVE — 100%** banner.

## Check status any time (optional)

```bash
python check.py
```
The installer's own panel already shows this live, but `check.py` gives a headless
report — **PREREQUISITES · DEPENDENCY BINARIES · MCP SERVERS · PLUGINS · WORKFLOW
WIRING (router LIVE) · PALETTE**, with an exact fix command on every gap. Exit 0 =
everything green.

**What one click reproduces:** CLI deps (uv tools semgrep / `jcodemunch-mcp[openai]` /
`jdocmunch-mcp[openai]` / graphifyy + the graphify serve venv; npm lean-ctx-bin,
tdd-guard, pyright (symlinked into `~/.local/bin`), mmx-cli). The
`~/.config/lean-ctx/config.toml` merge (no hooks / rules / skill injection, no updates
or telemetry, `shadow_mode=false`) runs FIRST, before lean-ctx is installed or
registered → 16 user-scope MCP servers from `installer/manifest.json` (every `npx`
package pinned to an exact version, telemetry-off env) → 5 marketplaces (autoUpdate on)
+ 12 plugins → rendered `settings.json` (never contains the string `lean-ctx`; a
re-render keeps the newest 3 dated `settings.json.bak-*`) → re-vendored skills,
generated `/invoke` skills + agent skill blocks, indexes, skill + mod validators →
doctor 0 FAIL.

Headless / CI: `python3 install.py --ci` plans the network and everything outside the
checkout (WOULD-*), but the local repo steps run for real (render, generators,
validator), so it is not read-only. The read-only plan is `python3 installer/deps.py`.

**Mods:** `mods/<id>/` (manifest `mods.enabled`) load through
`env.CLAUDE_CODE_PLUGIN_DIRS`. `mods.claude_version` is the minimum verified Claude
Code release: the doctor passes later patches of that minor and warns below it or on a
newer minor. Re-verify with `python3 scripts/validate_mods.py` (plugin validate + mod
tests) and bump the pin.

## The only things the installer can't do for you

- **OAuth MCPs** — `higgsfield` and `openart` are registered as HTTP MCPs; run
  `/mcp` inside Claude Code once to authorize them.
- **GitHub** — `gh auth login` once (the github MCP reads `gh auth token` at launch).
- **Context7 key (optional)** — `export CONTEXT7_API_KEY=...` before installing.
- **Semantic search (optional)** — install [ollama](https://ollama.com) and
  `ollama pull all-minilm qwen2.5-coder:3b` (embeddings + jcodemunch AI summaries; the
  doctor WARNs until both are present; search falls back to lexical).
- **Private files** — keep `.env*`, `CLAUDE.machines.local.md`, `.credentials.json` and
  `settings.user.json` at mode 600; the doctor's `secret-perms` row prints the `chmod`.
- **Escape hatch** — if a hook ever misbehaves: `claude --safe-mode`.

> **Everything else is automatic**, including MCP-server + plugin registration
> (on Windows the `claude` `.cmd` shim is run through the shell so it actually
> completes).
> Anything that needs the `claude` CLI or the network but can't reach it shows as
> a non-blocking **WARN** — it never gates the "100%" success and self-completes on
> the next launch once the prerequisite is in place.

## Optional (only if you use them)

`ripgrep` · `golangci-lint` (Go TDD) · a read-only DB MCP per project
(`python3 ~/.claude/scripts/add-db-mcp.py`, template `templates/mcp/db-readonly.mcp.json`).

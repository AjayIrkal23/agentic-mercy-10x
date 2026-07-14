# Prerequisites — install these BEFORE running the installer

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
| **Node.js LTS (+ npm)** | `lean-ctx`, `tdd-guard`, and 7 npx-launched MCP servers | nvm: `curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && nvm install --lts` · or `apt`/`brew` | `winget install OpenJS.NodeJS.LTS` · or nvm-windows |
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
one automatic installer** — there is no CLI install path and nothing to configure.
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

## The only things the installer can't do for you

- **claude.ai connectors** — `higgsfield` and `penpot` are OAuth connectors: add
  them in the **claude.ai → Connectors UI**, not via any CLI.
- **API keys / secrets** — never shipped. Export `GITHUB_TOKEN` etc. in your shell
  profile; `~/.claude.json` (per-machine) holds your MCP + credential config.

> **Everything else is automatic**, including MCP-server + plugin registration
> (on Windows the `claude` `.cmd` shim is run through the shell so it actually
> completes) and GSD (`get-shit-done`) via `npx -y get-shit-done-cc@latest`.
> Anything that needs the `claude` CLI or the network but can't reach it shows as
> a non-blocking **WARN** — it never gates the "100%" success and self-completes on
> the next launch once the prerequisite is in place.

## Optional (only if you use them)

`bun` (gstack build) · `ripgrep` · `golangci-lint` (Go TDD) · the `ast-grep` MCP
(`git clone` + `uv sync` in `ast-grep-mcp/`, offered by `install.sh`).

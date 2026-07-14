# Prerequisites — install these BEFORE running the installer

The installer (`install.py`, driven by `installer/manifest.json`) auto-installs
everything it can — `uv`, `pipx`, `semgrep`, `lean-ctx`, `tdd-guard`,
`jcodemunch-mcp`, `jdocmunch-mcp`, `graphify`, **all MCP servers**, and the
**plugins**. But a few base tools can't be reliably auto-installed cross-platform,
so **you install these four first**, then run the installer. `python check.py`
(or `install.py verify`) will always tell you exactly what's still missing.

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
| **Git** | Repo clone + `install.py update` + hook git calls | `sudo apt install git` · `brew install git` | `winget install Git.Git` |
| **Claude Code CLI** | Registers MCP servers + installs plugins | `npm install -g @anthropic-ai/claude-code` | `npm install -g @anthropic-ai/claude-code` |

> `uv` and `pipx` are **auto-installed** by the installer (uv via the official
> script, pipx via `pip`). If `uv` isn't on `PATH` right after, reopen your shell.

## Then install

**Ubuntu / macOS**
```bash
git clone https://github.com/AjayIrkal23/agentic-mercy-10x ~/.claude   # or clone elsewhere
~/.claude/install.sh            # copies workspace + runs install.py
#   (or run the cross-platform core directly:)
python3 ~/.claude/install.py install
```

**Windows** (PowerShell)
```powershell
git clone https://github.com/AjayIrkal23/agentic-mercy-10x $env:USERPROFILE\.claude
powershell -ExecutionPolicy Bypass -File $env:USERPROFILE\.claude\install.ps1
#   (or:)  py -3 $env:USERPROFILE\.claude\install.py install
```

## Prefer a visual installer?

```bash
python install.py ui            # or:  python install-ui.py   (Windows: py -3 install-ui.py)
```
Opens a local web page (127.0.0.1, stdlib only — no Node/Electron) that **auto-detects
your global `.claude`**, lets you **Browse** to a different folder and Continue, shows a
**live preflight** (prerequisites · privileges · deps · MCP servers · plugins · wiring),
then installs **everything step-by-step** with each step turning green/amber/red as it
runs — ending in a **WORKFLOW ACTIVE** banner. Same engine as the CLI; nothing extra to
install; identical on Ubuntu and Windows.

## Then verify (any time)

```bash
python check.py                 # or: python install.py verify
```
It reports **PREREQUISITES · DEPENDENCY BINARIES · MCP SERVERS · PLUGINS ·
WORKFLOW WIRING (router LIVE) · PALETTE**, with an exact fix command on every
gap. Exit 0 = everything green.

## Manual / UI steps the CLI can't do

- **claude.ai connectors** — `higgsfield` and `penpot` are OAuth connectors: add
  them in the **claude.ai → Connectors UI**, not via the CLI.
- **GSD (get-shit-done)** — the `gsd-*` agent + skill suite (its `/gsd:*` commands
  ship as skills). The installer **auto-installs it best-effort** via
  `npx -y get-shit-done-cc@latest` when absent (skipped if already present, so it
  never disturbs an existing install). If that step WARNs (the upstream installer
  wants interaction, or you're offline), run `npx get-shit-done-cc@latest` yourself,
  then `/gsd-update`. Node/npm is the only requirement.
- **API keys / secrets** — never shipped. Export `GITHUB_TOKEN` etc. in your shell
  profile; `~/.claude.json` (per-machine) holds your MCP + credential config.

## Optional (only if you use them)

`bun` (gstack build) · `ripgrep` · `golangci-lint` (Go TDD) · the `ast-grep` MCP
(`git clone` + `uv sync` in `ast-grep-mcp/`, offered by `install.sh`).

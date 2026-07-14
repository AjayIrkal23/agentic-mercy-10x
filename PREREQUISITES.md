# Prerequisites — install these BEFORE running the installer

The installer (`install.py`, driven by `installer/manifest.json`) auto-installs
everything it can — `uv`, `pipx`, `semgrep`, `lean-ctx`, `tdd-guard`,
`jcodemunch-mcp`, `jdocmunch-mcp`, `graphify`, **all MCP servers**, and the
**plugins**. But a few base tools can't be reliably auto-installed cross-platform,
so **you install these four first**, then run the installer. `python check.py`
(or `install.py verify`) will always tell you exactly what's still missing.

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
- **GSD (get-shit-done)** — the `gsd-*` command/agent suite. Distribution is
  upstream-uncertain; install best-effort (`npx get-shit-done-cc` or the GSD
  installer), then run `/gsd-update`.
- **API keys / secrets** — never shipped. Export `GITHUB_TOKEN` etc. in your shell
  profile; `~/.claude.json` (per-machine) holds your MCP + credential config.

## Optional (only if you use them)

`bun` (gstack build) · `ripgrep` · `golangci-lint` (Go TDD) · the `ast-grep` MCP
(`git clone` + `uv sync` in `ast-grep-mcp/`, offered by `install.sh`).

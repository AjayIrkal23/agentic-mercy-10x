# Prerequisites

> **Ubuntu 24.04+: only `git`, `curl` and `python3` are needed, and no sudo.**
> `sudo apt-get install -y git curl python3 tmux` covers a bare box (tmux is optional: it is
> what restores sessions after an OOM kill). Node, the native Claude Code CLI, uv, gh, ollama
> and every package below are installed by the installer into `~/.local`.

| OS | Install yourself first | The installer adds |
|---|---|---|
| Ubuntu 24.04+ | `git`, `curl`, `python3` (>= 3.10) | Node 22, Claude Code (native, `claude.ai/install.sh`), uv, gh, ollama, every package and MCP server |
| macOS | `git`, `python3` (`brew install python@3.12`), Node LTS (nvm or brew), Claude Code (`curl -fsSL https://claude.ai/install.sh \| bash`) | uv, packages, MCP servers, plugins |
| Windows 10/11 | nothing: double-click `install.cmd` | a pinned Python, PortableGit (Git Bash), Node 22, Claude Code, uv, gh, ollama, per user |

The installer (one automatic, self-healing command driven by `installer/manifest.json`)
installs and registers everything it can: `uv`, `semgrep`, `lean-ctx`, `tdd-guard`,
`jcodemunch-mcp`, `jdocmunch-mcp`, `graphify`, all MCP servers and the plugins. It then repairs
and re-checks itself until the doctor reports 0 FAIL. The live status panel (and a read-only
`python check.py`) tells you what is still missing.

## No root, sudo or Administrator needed

`~/.claude` is your user home (`/home/<you>/.claude` on Ubuntu/macOS,
`C:\Users\<you>\.claude` on Windows), not `/root`, `Program Files` or a system directory. The
installer writes only to user-owned places:

- **Ubuntu / macOS:** `~/.claude`, `~/.claude.json`, `~/.local` (base tools, uv tools), your npm prefix
- **Windows:** `%USERPROFILE%\.claude`, `%LOCALAPPDATA%\Programs\agentic-mercy`, `%APPDATA%\npm`

So `install.sh`, `install.cmd`, `install.ps1` and `install.py` need no sudo and no
Administrator. On Ubuntu the installer's own Node 22 lives in `~/.local`, so `npm install -g`
never needs sudo either. On macOS, a system-wide Node (prefix `/usr`) would: use nvm or
`npm config set prefix ~/.npm-global`.

## Using another machine's ollama

Set `OLLAMA_HOST` before the install command:

```bash
OLLAMA_HOST=http://<host>:11434 ~/agentic-mercy/install.sh --headless
```

The installer saves it into `~/.claude/settings.user.json` (mode 600;
`settings.user.example.json` shows the shape), installs no local ollama, points the jcodemunch /
jdocmunch MCP env and the doctor at that host, and pulls missing models there. The remote must
listen beyond 127.0.0.1 (`OLLAMA_HOST=0.0.0.0:11434` in its unit). With a remote `OLLAMA_HOST`,
jcodemunch AI summaries send source snippets and the learning step sends scrubbed command digests
and file paths to that host over plain HTTP; use a host you trust, or leave it unset.

## Then install: one command

```bash
git clone https://github.com/AjayIrkal23/agentic-mercy-10x ~/agentic-mercy
~/agentic-mercy/install.sh              # visual installer (opens a browser tab)
~/agentic-mercy/install.sh --headless   # real install in the console (servers, SSH, containers)
~/agentic-mercy/install.sh --ci         # plan only (network steps planned, local repo steps run)
```

Windows: `install.cmd` (or `install.cmd -Headless` in a console; `install.cmd -Ci` only plans).
Cloning straight into `~/.claude` works too and keeps `git pull --ff-only` for updates; a clone
elsewhere is merged into `~/.claude` together with its `.git`.

`install.py`, `install-ui.py`, `install.sh`, `install.cmd` and `install.ps1` are the same
installer. The visual mode opens a local page (127.0.0.1, stdlib only) that runs the whole
install and shows prerequisites, privileges, deps, MCP servers, plugins and wiring turning green.
Both modes print the same end-of-run checklist to the console.

On a bare box (no `settings.json` before) the permission mode is `acceptEdits`, not the
template's `bypassPermissions`: the installer writes `permissions.defaultMode` into
`settings.user.json` and prints one checklist line. To keep bypass, set
`AGENTIC_MERCY_PERMISSION_MODE=bypassPermissions` for the install command. A machine that
already had a `settings.json` keeps its mode.

A small or headless machine (16 GB, no desktop, linger off): read
[docs/OOM-GUARD.md § Small or headless machine](docs/OOM-GUARD.md#small-or-headless-machine).

## Check status any time (optional)

```bash
python check.py
```

A headless report of prerequisites, dependency binaries, MCP servers, plugins, workflow wiring
(router live) and palette, with the fix command on every gap. Exit 0 = everything green.

**What one run reproduces:** CLI deps (uv tools semgrep, `jcodemunch-mcp[openai]`,
`jdocmunch-mcp[openai]`, graphifyy and the graphify serve venv; npm lean-ctx-bin, tdd-guard,
pyright (symlinked into `~/.local/bin`), mmx-cli, all pinned). The
`~/.config/lean-ctx/config.toml` merge (no hooks, rules or skill injection, no updates or
telemetry, `shadow_mode=false`) runs first, before lean-ctx is installed or registered; then
15 user-scope MCP servers from `installer/manifest.json` (every `npx` package pinned, telemetry
off), 5 marketplaces (autoUpdate on) and 11 plugins, the rendered `settings.json` (never
contains the string `lean-ctx`; a re-render keeps the newest 3 dated `settings.json.bak-*`),
re-vendored skills, generated `/invoke` skills and agent skill blocks, indexes, skill and mod
validators, and a doctor run with 0 FAIL.

`--ci` plans the network and everything outside the checkout (WOULD-*), but the local repo steps
run for real (render, generators, validator), so it is not read-only. The read-only plan is
`python3 installer/deps.py`.

**Mods:** `mods/<id>/` (manifest `mods.enabled`) load through `env.CLAUDE_CODE_PLUGIN_DIRS`.
`mods.claude_version` is the minimum verified Claude Code release: the doctor passes later
patches of that minor and warns below it or on a newer minor. Re-verify with
`python3 scripts/validate_mods.py` (plugin validate + mod tests) and bump the pin.

## The only things the installer cannot do for you

- **Sign in:** run `claude` once.
- **OAuth MCPs:** `openart` is registered as an HTTP MCP; run `/mcp` inside Claude Code once to
  authorize it. Higgsfield is the claude.ai connector (`mcp__claude_ai_higgsfield__*`), enabled
  at claude.ai, not an MCP here.
- **GitHub:** `gh auth login` once (the github MCP reads `gh auth token` at launch).
- **PATH:** open a new terminal so `~/.claude/bin` and `~/.local/bin` are on `PATH`.
- **Context7 key (optional):** `export CONTEXT7_API_KEY=...` before installing.
- **Semantic search (optional):** a local or remote ollama with `all-minilm` and
  `qwen2.5-coder:3b` (embeddings and jcodemunch AI summaries; the doctor WARNs until both are
  present; search falls back to lexical). The learning pipeline (`docs/LEARNING.md`) uses the
  same `OLLAMA_HOST`, defers when it is down and never spends Claude quota.
- **OOM guard (Linux, on by default):** needs a systemd user manager (`systemctl --user`); the
  installer writes `~/.config/systemd/user.conf.d/10-oom.conf`, two user units and a PATH block,
  and turns on lingering (`loginctl enable-linger`, no sudo). When swap is under half of RAM the
  checklist prints a one-time zram command (sudo); the installer never runs it. Details:
  `docs/OOM-GUARD.md`.
- **Secrets scan before a push:** `gitleaks` 8.30.1 lands in `~/.local/bin` from the pinned
  release (sha256-checked, no sudo); Windows skips it.
- **Private files:** keep `.env*`, `CLAUDE.machines.local.md`, `.credentials.json`,
  `settings.user.json`, `settings.local.json` and `scripts/sudo-askpass.sh` at mode 600; the
  doctor's `secret-perms` row prints the `chmod`. `CLAUDE.machines.local.md` is per machine and
  gitignored: copy it by hand or write your own. A machine whose owner lets agents use sudo puts
  `LOCAL_SUDO_PASS` in `~/.claude/.env` (mode 600); the installer then copies
  `scripts/sudo-askpass.example.sh` to `scripts/sudo-askpass.sh` (mode 700), which reads the
  password from that file only.
- **Escape hatch:** if a hook ever misbehaves, `claude --safe-mode`.

> **Everything else is automatic,** including MCP server and plugin registration (on Windows
> the `claude` `.cmd` shim runs through the shell so it completes). Anything that needs the
> `claude` CLI or the network but cannot reach it shows as a non-blocking WARN; it never gates
> success and completes on the next launch once the prerequisite is in place.

## Optional (only if you use them)

`ripgrep` · `golangci-lint` (Go TDD) · a read-only DB MCP per project
(`python3 ~/.claude/scripts/add-db-mcp.py`, template `templates/mcp/db-readonly.mcp.json`).

#!/usr/bin/env bash
# ============================================================================
#  claude-workflow — one-command launcher. UI-ONLY, AUTOMATIC, zero interaction.
#
#  Usage:
#     git clone https://github.com/<you>/claude-workflow ~/agentic-mercy
#     ~/agentic-mercy/install.sh
#
#  Finds python3 and runs install-ui.py. That auto-detects ~/.claude,
#  auto-relocates this clone into it (merge — nothing you own is deleted), and
#  opens the visual installer, which configures lean-ctx, installs deps, registers
#  15 MCP servers (user scope), adds 5 marketplaces + 11 plugins, renders
#  settings.json, regenerates skills/indexes, then repairs + re-checks until the
#  doctor reports 0 FAIL. Idempotent — safe to re-run.
#  Headless real install (servers, containers, ssh):  ./install.sh --headless
#  CI plan only:  ./install.sh --ci   (no web UI; network steps planned, local repo
#  steps run). Read-only plan: python3 installer/deps.py
#  Fresh Ubuntu: needs only git, curl and python3 (>= 3.10) and NO sudo — node, the
#  claude CLI, uv, gh, ollama + models are installed into ~/.local; apt-only optional OS
#  tools use root / `sudo -n` or come back as ONE command in the final checklist.
#  Another machine's ollama: OLLAMA_HOST=http://<host>:11434 ./install.sh --headless
#  (saved into ~/.claude/settings.user.json, mode 600).
#  Steps only you can do; the installer prints them at the end (also in the visual
#  mode's console): run `claude` once and sign in; run /mcp and authorize openart;
#  enable the Higgsfield connector at claude.ai; `gh auth login`; open a new terminal
#  so ~/.claude/bin and ~/.local/bin are on PATH. Optional: `export CONTEXT7_API_KEY=...`
#  before installing. Escape
#  hatch if a hook misbehaves: `claude --safe-mode`. Health: python3 ~/.claude/installer/doctor.py
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

c_bold=$'\033[1m'; c_ylw=$'\033[33m'; c_red=$'\033[31m'; c_off=$'\033[0m'
say()  { printf '%s\n' "${c_bold}==>${c_off} $*"; }
warn() { printf '%s\n' "  ${c_ylw}!!${c_off}  $*"; }
err()  { printf '%s\n' "  ${c_red}xx${c_off}  $*" >&2; }

command -v python3 >/dev/null 2>&1 || { err "python3 (>= 3.10) is required — install it and re-run."; exit 1; }

say "claude-workflow installer — automatic, visual"
exec python3 "$REPO_DIR/install-ui.py" "$@"

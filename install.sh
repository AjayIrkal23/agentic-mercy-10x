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
#  16 MCP servers (user scope), adds 5 marketplaces + 12 plugins, renders
#  settings.json, regenerates skills/indexes, then repairs + re-checks until the
#  doctor reports 0 FAIL. Idempotent — safe to re-run.
#  Headless real install (servers, containers, ssh):  ./install.sh --headless
#  CI plan only:  ./install.sh --ci   (no web UI; network steps planned, local repo
#  steps run). Read-only plan: python3 installer/deps.py
#  Fresh Ubuntu: needs only git, curl and python3 (>= 3.10) and NO sudo — node, the
#  claude CLI, uv, gh, ollama + models are installed into ~/.local; apt-only optional OS
#  tools use root / `sudo -n` or come back as ONE command in the final checklist.
#  Afterwards (you): sign in to claude; /mcp to authorize higgsfield + openart;
#  `gh auth login`; optional `export CONTEXT7_API_KEY=...` before installing. Escape
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

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
#  opens the visual installer, which installs + repairs + re-checks in a loop
#  until every check is green. You do nothing. Idempotent — safe to re-run.
#  Requires: python3 (>= 3.10).
# ============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

c_bold=$'\033[1m'; c_ylw=$'\033[33m'; c_red=$'\033[31m'; c_off=$'\033[0m'
say()  { printf '%s\n' "${c_bold}==>${c_off} $*"; }
warn() { printf '%s\n' "  ${c_ylw}!!${c_off}  $*"; }
err()  { printf '%s\n' "  ${c_red}xx${c_off}  $*" >&2; }

command -v python3 >/dev/null 2>&1 || { err "python3 (>= 3.10) is required — install it and re-run."; exit 1; }

say "claude-workflow installer — automatic, visual"
exec python3 "$REPO_DIR/install-ui.py"

#!/usr/bin/env bash
# One-click jDocMunch (docs index) installer — mirrors the jcodemunch wiring.
#
#   ./install-jdocmunch.sh            install + register + index configured roots
#   ./install-jdocmunch.sh --no-index skip the indexing step
#
# What it does:
#   1. Installs jdocmunch-mcp as a uv tool  (binary: ~/.local/bin/jdocmunch-mcp)
#   2. Registers the MCP server user-scope  (claude mcp add jdocmunch)
#   3. Indexes every root in hooks/jdocmunch-index-guard.config.json
#
# The SessionStart staleness guard (hooks/jdocmunch-index-guard.py) and the
# post-write auto-reindex (hooks/jdocmunch-reindex-hook.py, chained in
# post-write-aggregator.py) ship with this repo — nothing else to install.
#
# NOTE: jDocMunch is free for NON-COMMERCIAL use only; commercial use needs a
# paid license — https://j.gravelle.us/jCodeMunch/descriptions.php
set -euo pipefail

CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$CLAUDE_DIR/hooks/jdocmunch-index-guard.config.json"

echo "==> 1/3 installing jdocmunch-mcp (uv tool)"
if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found — install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi
uv tool install --upgrade jdocmunch-mcp
JDM="$(command -v jdocmunch-mcp || echo "$HOME/.local/bin/jdocmunch-mcp")"
"$JDM" --version

echo "==> 2/3 registering MCP server (user scope)"
if claude mcp get jdocmunch >/dev/null 2>&1; then
  echo "already registered — skipping"
else
  claude mcp add --scope user jdocmunch -- jdocmunch-mcp
fi

if [[ "${1:-}" == "--no-index" ]]; then
  echo "==> 3/3 skipped (--no-index)"
  exit 0
fi

echo "==> 3/3 indexing project roots from $CONFIG"
python3 - "$CONFIG" <<'EOF' | while IFS= read -r root; do
import json, sys
cfg = json.load(open(sys.argv[1]))
for r in cfg.get("project_roots", []):
    print(r)
EOF
  if [[ -d "$root" ]]; then
    name="$(basename "$root")"
    echo "--- indexing $name ($root)"
    "$JDM" index-local --path "$root" --name "$name" >/dev/null || echo "WARN: index failed for $root"
  else
    echo "--- skipping missing root: $root"
  fi
done

echo "done. verify inside Claude Code with: mcp__jdocmunch__doc_list_repos"

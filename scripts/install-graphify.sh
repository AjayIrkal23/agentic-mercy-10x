#!/usr/bin/env bash
# One-click graphify (dependency-graph MCP) installer — CLAUDE-NATIVE, mirrors
# the jcodemunch/jdocmunch wiring.
#
#   ./install-graphify.sh              install CLI + serve venv + register MCP
#   ./install-graphify.sh --no-cli     skip the graphify CLI uv-tool step
#
# What it does:
#   1. Installs the graphify CLI (uv tool 'graphifyy')      -> ~/.local/bin/graphify
#   2. Creates a CLAUDE-OWNED serve venv (graphifyy + mcp)   -> ~/.local/share/claude-graphify-venv
#      (relocated off the old shared cursor venv, 2026-07-14 — pure Claude Code)
#   3. Registers the graphify MCP server user-scope, pointed at the portable,
#      fail-open launcher: hooks/graphify_launcher.py
#
# Ships with this repo (nothing else to install):
#   - hooks/graphify_launcher.py     portable launcher; validates the served
#                                    graph belongs to the OPEN repo (git-remote
#                                    identity) and fails open on a missing graph
#   - hooks/graphify-enforce.py      pre-tool-use advisory + query-time freshness
#   - hooks/graphify-index-guard.py  SessionStart freshness (via index-lifecycle.py)
#   - hooks/lib/repo_context.py      shared git-identity helpers
#
# Build a repo's graph any time with:  graphify update <repo-root>
set -euo pipefail

CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$CLAUDE_DIR/hooks/graphify_launcher.py"
VENV="${GRAPHIFY_VENV:-$HOME/.local/share/claude-graphify-venv}"
PIN="graphifyy==0.9.18"   # pinned serve version (bump intentionally)

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found — install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [[ "${1:-}" != "--no-cli" ]]; then
  echo "==> 1/3 installing graphify CLI (uv tool 'graphifyy', pinned to match serve)"
  uv tool install --force "$PIN" || echo "WARN: graphifyy uv-tool install failed (CLI is optional if the serve venv works)"
  if command -v graphify >/dev/null 2>&1; then echo "  graphify CLI: $(command -v graphify)"; else echo "  (graphify CLI not on PATH yet — add ~/.local/bin)"; fi
else
  echo "==> 1/3 skipped CLI (--no-cli)"
fi

echo "==> 2/3 creating claude-owned serve venv ($VENV)"
uv venv --clear "$VENV"
uv pip install --python "$VENV/bin/python" "$PIN" mcp
"$VENV/bin/python" - <<'PY'
import importlib.util as u, importlib.metadata as m
print(f"  graphifyy {m.version('graphifyy')} | mcp {m.version('mcp')} | "
      f"graphify.serve {'OK' if u.find_spec('graphify.serve') else 'MISSING'}")
PY
chmod +x "$LAUNCHER" 2>/dev/null || true

echo "==> 3/3 registering MCP server (user scope) -> $LAUNCHER"
if command -v claude >/dev/null 2>&1; then
  if claude mcp get graphify >/dev/null 2>&1; then
    echo "  graphify already registered — leaving as-is (ensure its command is $LAUNCHER)"
  else
    claude mcp add --scope user graphify -- "$LAUNCHER" \
      && echo "  registered" \
      || echo "WARN: 'claude mcp add' failed — add graphify manually with command=$LAUNCHER, args=[]"
  fi
else
  echo "  'claude' CLI not found — add this to ~/.claude.json mcpServers manually:"
  echo "    \"graphify\": { \"command\": \"$LAUNCHER\", \"args\": [] }"
fi

echo "done. Build a repo's graph with: graphify update <repo-root>"
echo "verify inside Claude Code: mcp__graphify__graph_stats"

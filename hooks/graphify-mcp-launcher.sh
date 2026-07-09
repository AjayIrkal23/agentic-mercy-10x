#!/usr/bin/env bash
# Resolve graphify-out/graph.json for the active workspace, then start the MCP server.
# Fails closed when no workspace graph exists unless GRAPHIFY_GRAPH is set explicitly.

set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="${HOOKS_DIR}/graphify-runner.sh"

find_graph() {
  local dir candidate

  if [[ -n "${GRAPHIFY_GRAPH:-}" && -f "${GRAPHIFY_GRAPH}" ]]; then
    echo "${GRAPHIFY_GRAPH}"
    return 0
  fi

  for var in CURSOR_PROJECT_DIR CLAUDE_PROJECT_DIR WORKSPACE_FOLDER_PATHS; do
    candidate="${!var:-}"
    [[ -z "$candidate" ]] && continue
    if [[ "$var" == "WORKSPACE_FOLDER_PATHS" && "$candidate" == \[* ]]; then
      candidate="$(python3 -c "import json,sys; p=json.loads(sys.argv[1]); print(p[0] if p else '')" "$candidate" 2>/dev/null || true)"
    fi
    if [[ -n "$candidate" && -f "$candidate/graphify-out/graph.json" ]]; then
      echo "$candidate/graphify-out/graph.json"
      return 0
    fi
    # Auto-build if project exists but graph doesn't
    if [[ -n "$candidate" && -d "$candidate" && ! -f "$candidate/graphify-out/graph.json" ]]; then
      graphify update "$candidate" >/dev/null 2>&1 || true
      if [[ -f "$candidate/graphify-out/graph.json" ]]; then
        echo "$candidate/graphify-out/graph.json"
        return 0
      fi
    fi
  done

  # Walk up from PWD to find a project with graph.json
  dir="$PWD"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/graphify-out/graph.json" ]]; then
      echo "$dir/graphify-out/graph.json"
      return 0
    fi
    dir="$(dirname "$dir")"
  done

  # Fallback: if PWD is under /DATA/CODE_FILES/, auto-build the graph
  if [[ "$PWD" == /DATA/CODE_FILES/* ]]; then
    # Find the project root (first dir under /DATA/CODE_FILES/ with .git)
    dir="$PWD"
    while [[ "$dir" != "/DATA/CODE_FILES" && "$dir" != "/" ]]; do
      if [[ -d "$dir/.git" ]]; then
        graphify update "$dir" >/dev/null 2>&1 || true
        if [[ -f "$dir/graphify-out/graph.json" ]]; then
          echo "$dir/graphify-out/graph.json"
          return 0
        fi
        break
      fi
      dir="$(dirname "$dir")"
    done
  fi

  return 1
}

GRAPH="$(find_graph)" || {
  echo "error: Graph file not found for the active workspace." >&2
  echo "Build one in your project root:" >&2
  echo "  graphify update <project-path>" >&2
  echo "Expected: <workspace>/graphify-out/graph.json" >&2
  echo "Override: export GRAPHIFY_GRAPH=/path/to/graph.json" >&2
  exit 1
}

exec "$RUNNER" -m graphify.serve "$GRAPH"

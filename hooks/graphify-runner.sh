#!/usr/bin/env bash
# Run graphify with a known-good interpreter + site-packages when the agent shell
# sets PYTHONEXECUTABLE to Cursor/AppImage (which breaks bare venv shebangs).

set -euo pipefail

VROOT="${GRAPHIFY_VENV:-$HOME/.local/share/cursor-graphify-venv}"

if [[ -n "${GRAPHIFY_SITE_PACKAGES:-}" ]]; then
  SITE_PACKAGES="$GRAPHIFY_SITE_PACKAGES"
else
  SITE_PACKAGES=""
  while IFS= read -r _d; do
    SITE_PACKAGES="$_d"
    break
  done < <(find "$VROOT/lib" -maxdepth 2 -type d -name site-packages 2>/dev/null | sort -V)
fi

PYTHON_BIN="${GRAPHIFY_PYTHON:-/usr/bin/python3.13}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3.13 || command -v python3 || echo /usr/bin/python3)"
fi

export PYTHONPATH="${SITE_PACKAGES}${PYTHONPATH:+:$PYTHONPATH}"
unset PYTHONEXECUTABLE PYTHONHOME || true

# Per-repo dynamic graph resolution. Claude Code launches this MCP server with cwd
# set to the active project root, so when invoked as `graphify.serve` with no explicit
# graph.json arg, walk up from $PWD to the nearest graphify-out/graph.json and pass it.
# Falls back to serve's own cwd-relative default ("graphify-out/graph.json") when none
# is found. Any explicit *.json arg is respected untouched.
_is_serve=0; _has_json=0
for _a in "$@"; do
  [[ "$_a" == "graphify.serve" ]] && _is_serve=1
  [[ "$_a" == *.json ]] && _has_json=1
done
if [[ "$_is_serve" == 1 && "$_has_json" == 0 ]]; then
  _dir="$PWD"
  while [[ -n "$_dir" && "$_dir" != "/" ]]; do
    if [[ -f "$_dir/graphify-out/graph.json" ]]; then
      exec "${PYTHON_BIN}" "$@" "$_dir/graphify-out/graph.json"
    fi
    _dir="$(dirname "$_dir")"
  done
fi

exec "${PYTHON_BIN}" "$@"

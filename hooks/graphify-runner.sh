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
exec "${PYTHON_BIN}" "$@"

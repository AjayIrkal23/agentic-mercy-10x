#!/usr/bin/env bash
# Optional: film-stock looks. Creates the venv with Spectral Film LUT (MIT) and generates the LUTs into library/luts/
# (6 looks: full LUTs + split negative/grain/print LUTs for the grain, ~25 MB, gitignored like the rest of library/).
# Applying a look afterwards needs only ffmpeg (scripts/film_look.py). Transitions (scripts/transitions.py) need no setup.
#   bash scripts/setup_looks.sh            -> ~/.venvs/ghost-looks (override with LOOKS_VENV=/path), library/luts/*.cube
set -euo pipefail
S="$(cd "$(dirname "$0")/.." && pwd)"
V="${LOOKS_VENV:-$HOME/.venvs/ghost-looks}"
PY="${PYTHON311:-$(command -v python3.11 || echo /opt/homebrew/bin/python3.11)}"
[ -x "$V/bin/python" ] || "$PY" -m venv "$V"
"$V/bin/pip" install -q --upgrade pip
"$V/bin/pip" install -q "spectral_film_lut==0.18.12"
"$V/bin/python" "$S/scripts/gen_luts.py" "$@"
n=$(ls "$S"/library/luts/*.cube 2>/dev/null | wc -l | tr -d ' ')
echo "film looks ready: $n LUTs in $S/library/luts (venv $V)"

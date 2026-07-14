#!/usr/bin/env python3
"""grep_gates.py — portability grep-gates for the live hook/installer surface (P6-T1/P6-T7).

Enforces the cross-platform invariants that keep ``~/.claude`` runnable on both
Ubuntu and Windows. Pure stdlib; scans on-disk source and prints a PASS/FAIL
table. Exit 0 when every gate passes, 1 otherwise. Runnable standalone (CI step)
and imported by ``tests/test_portability_gate.py``.

Gates (Charter §7 portability; Spec C §3):
  G1  no ``sys.platform`` outside ``hooks/lib/platform.py`` — it is the ONE OS
      branching point (the ``lib`` package __init__/docstrings that merely NAME
      it are exempt).
  G2  no machine-absolute home literals (``/home/<user>/``, ``/Users/<user>/``,
      ``C:\\Users\\``) — paths derive from ``~``/``CLAUDE_DIR``. Redacted doc
      placeholders (``/home/.../``) are not real paths and are ignored.
  G3  no ``C:\\`` drive literals in code.
  G4  no NEW ``.sh`` under ``hooks/`` beyond the grandfathered legacy set (which
      is retained only for the 30-day flip-back window and retires in P7).

Scan scope = the code THIS overhaul owns and ships: ``hooks/`` (py+js),
``scripts/``, ``installer/``, ``install.py``, ``tests/`` (py). Excluded:
upstream/vendored trees, attic, plugin cache, node_modules, __pycache__, the
frozen ``legacy-*.json`` snapshots, and JSON fixtures.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"
PLATFORM_PY = HOOKS / "lib" / "platform.py"

# Files that legitimately NAME sys.platform (the platform lib package itself).
_SYSPLATFORM_EXEMPT = {
    (HOOKS / "lib" / "platform.py").resolve(),
    (HOOKS / "lib" / "__init__.py").resolve(),
}

# .sh files under hooks/ that predate the overhaul, kept as bash-port originals.
# The LIVE dispatch chain no longer invokes any of them (all repointed to .py/.js
# ports in P6-T2). Flip-back was retired 2026-07-14 (git is the recovery path);
# discovery-skills-reminder.sh was deleted with the legacy UPS stack. No NEW .sh here.
_LEGACY_SH_GRANDFATHER = {
    "gsd-phase-boundary.sh",
    "gsd-session-state.sh",
    "gsd-validate-commit.sh",
    "tdd-guard-launcher.sh",
    # graphify-runner.sh retired 2026-07-14 (tri-tool rework): the LIVE hook,
    # settings.json, AND ~/.claude.json all now point graphify's MCP at
    # graphify_launcher.py, and the .sh file is deleted. Entry removed.
}

_EXCLUDE_DIR_PARTS = {
    "attic", "__pycache__", "node_modules", ".git", "fixtures",
    "plugins", "gstack", ".state", ".telemetry", ".agents",
}

# Files that NAME the banned patterns by design (this gate + its test document
# every rule in prose/regex) — exempt them from the literal scan.
_SELF_EXEMPT = {
    (ROOT / "scripts" / "grep_gates.py").resolve(),
    (ROOT / "tests" / "test_portability_gate.py").resolve(),
}

# machine-absolute home literals (real paths, not ~ / CLAUDE_DIR derived).
# The (?!\.\.\.) negative-lookahead skips redacted doc placeholders like /home/...
_HOME_RE = re.compile(r"/home/(?!\.\.\.)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/")
_CDRIVE_RE = re.compile(r"C:\\")  # any C:\ drive literal (one or escaped backslash)


def _scan_files() -> list[Path]:
    out: list[Path] = []
    roots = [
        (HOOKS, ("*.py", "*.js")),
        (ROOT / "scripts", ("*.py",)),
        (ROOT / "installer", ("*.py",)),
        (ROOT / "tests", ("*.py",)),
    ]
    for base, globs in roots:
        if not base.exists():
            continue
        for pat in globs:
            for p in base.rglob(pat):
                if any(part in _EXCLUDE_DIR_PARTS for part in p.parts):
                    continue
                # skip frozen legacy snapshots (data, not live code)
                if p.name.startswith("legacy-"):
                    continue
                out.append(p)
    single = ROOT / "install.py"
    if single.exists():
        out.append(single)
    return out


def run_gates() -> tuple[list[str], list[str]]:
    """Return (failures, passes) as human-readable lines."""
    failures: list[str] = []
    passes: list[str] = []
    files = _scan_files()

    # G1: sys.platform
    g1 = []
    for p in files:
        if p.resolve() in _SYSPLATFORM_EXEMPT or p.resolve() in _SELF_EXEMPT or p.suffix != ".py":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "sys.platform" in line:
                g1.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    if g1:
        failures.append("G1 sys.platform outside platform.py:\n    " + "\n    ".join(g1))
    else:
        passes.append("G1 sys.platform confined to platform.py")

    # G2/G3: home + C:\ literals
    g2 = []
    for p in files:
        if p.resolve() == PLATFORM_PY.resolve() or p.resolve() in _SELF_EXEMPT:
            continue  # platform.py + this gate document these patterns in prose
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if _HOME_RE.search(line) or _CDRIVE_RE.search(line):
                g2.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
    if g2:
        failures.append("G2/G3 machine-absolute path literals:\n    " + "\n    ".join(g2))
    else:
        passes.append("G2/G3 no machine-absolute home/drive literals")

    # G4: no new .sh under hooks/
    stray = []
    for p in HOOKS.rglob("*.sh"):
        if any(part in _EXCLUDE_DIR_PARTS for part in p.parts):
            continue
        if p.name not in _LEGACY_SH_GRANDFATHER:
            stray.append(str(p.relative_to(ROOT)))
    if stray:
        failures.append("G4 new .sh under hooks/ (not in grandfather set):\n    " + "\n    ".join(stray))
    else:
        passes.append(f"G4 no new .sh under hooks/ ({len(_LEGACY_SH_GRANDFATHER)} legacy grandfathered)")

    return failures, passes


def main(argv: list[str]) -> int:
    failures, passes = run_gates()
    print("=== portability grep-gates ===")
    for line in passes:
        print(f"  OK  {line}")
    for line in failures:
        print(f"  XX  {line}")
    print(f"=== {len(passes)} pass, {len(failures)} FAIL ===")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

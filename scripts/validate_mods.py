#!/usr/bin/env python3
"""validate_mods.py — contract check for the Claude Code mods in ``mods/<id>/``.

Static checks (stdlib, every OS, CI included) for each id in
``installer/manifest.json`` → ``mods.enabled``:

  M1  ``mods/<id>/.claude-plugin/plugin.json`` exists, parses, and its ``name`` == id   [HARD]
  M2  ``hooks/hooks.json`` names ≥1 module that exists with a loadable suffix          [HARD]
  M3  no ``import(``, ``require(``, ``console.``, ``setTimeout(``/``setInterval(``
      in hook sources (the mod environment has none of them)                         [HARD]
  M4  the declared ``types`` contract exists                                          [HARD]
  M5  at least one ``*.test.ts[x]``                                                   [WARN]
  M6  no file of the engine-laid ``.claude-plugin/types/`` is tracked by git          [HARD]

Then, unless ``--static`` or the ``claude`` CLI is absent: ``claude plugin validate
--json [--strict] <dir>`` must report success, and ``claude plugin test <dir>`` must
exit 0 (skipped with ``--no-tests``; only a WARN while Claude Code's remote rollout switch
has mods off, since nothing loads then). Exit non-zero on any HARD failure.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "installer" / "manifest.json"
SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
FORBIDDEN = re.compile(r"\bimport\s*\(|\brequire\s*\(|\bconsole\.|\bset(?:Timeout|Interval)\s*\(")
ROLLOUT_OFF = "hooks modules are turned off"  # `claude plugin test` when the remote switch is off


def enabled_mods(manifest: Path = MANIFEST) -> list[str]:
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [m for m in (data.get("mods") or {}).get("enabled") or [] if isinstance(m, str)]


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(^|[^:])//[^\n]*", r"\1", src)


def static_problems(mod_id: str, root: Path = ROOT) -> tuple[list[str], list[str]]:
    """Returns (hard, warn) problem lines for one mod."""
    hard: list[str] = []
    warn: list[str] = []
    folder = root / "mods" / mod_id
    manifest = folder / ".claude-plugin" / "plugin.json"
    try:
        plugin = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"M1 {manifest}: {type(exc).__name__}"], warn
    if plugin.get("name") != mod_id:
        hard.append(f"M1 plugin.json name {plugin.get('name')!r} != folder {mod_id!r}")
    try:
        modules = json.loads((folder / "hooks" / "hooks.json").read_text(encoding="utf-8")).get("modules") or []
    except (OSError, ValueError, AttributeError) as exc:
        modules = []
        hard.append(f"M2 hooks/hooks.json: {type(exc).__name__}")
    if not modules:
        hard.append("M2 hooks/hooks.json names no module")
    for rel in modules:
        target = (folder / "hooks" / rel).resolve()
        if target.suffix not in SUFFIXES or not target.is_file():
            hard.append(f"M2 module {rel!r} is missing or has an unloadable suffix")
    for src in sorted((folder / "hooks").rglob("*")):
        if src.suffix in SUFFIXES and FORBIDDEN.search(_strip_comments(src.read_text(encoding="utf-8"))):
            hard.append(f"M3 {src.relative_to(folder)} uses import()/require/console/timers")
    types = plugin.get("types")
    if types and not (folder / types).is_file():
        hard.append(f"M4 declared types {types!r} not found")
    if not list(folder.rglob("*.test.ts")) + list(folder.rglob("*.test.tsx")):
        warn.append("M5 no *.test.ts[x] files")
    tracked = _git_tracked(folder / ".claude-plugin" / "types", root)
    if tracked:
        hard.append(f"M6 engine-laid types are tracked by git: {tracked[:3]}")
    return hard, warn


def _git_tracked(path: Path, root: Path) -> list[str]:
    git = shutil.which("git")
    if not git or not path.exists():
        return []
    try:
        out = subprocess.run([git, "-C", str(root), "ls-files", "--", str(path)], capture_output=True,
                             encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in out.stdout.splitlines() if line.strip()]


def cli_problems(mod_id: str, strict: bool, run_tests: bool, root: Path = ROOT,
                 warn: list[str] | None = None) -> list[str]:
    claude = shutil.which("claude")
    if not claude:
        return []
    folder = str(root / "mods" / mod_id)
    problems: list[str] = []
    cmd = [claude, "plugin", "validate", "--json"] + (["--strict"] if strict else []) + [folder]
    try:
        out = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120)
        report = json.loads(out.stdout or "{}")
        if not report.get("success"):
            kinds = ("errors", "warnings") if strict else ("errors",)
            errs = [e.get("message", "") for c in report.get("contents", []) for k in kinds for e in c.get(k, [])]
            errs += [e.get("message", "") for e in (report.get("manifest") or {}).get("errors", [])]
            problems.append(f"validate: {'; '.join(errs)[:400] or 'failed'}")
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        problems.append(f"validate could not run: {type(exc).__name__}")
    if run_tests:
        try:
            test = subprocess.run([claude, "plugin", "test", folder], capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=300)
            output = test.stdout + test.stderr
            if ROLLOUT_OFF in output:
                # mods are off on this machine (whatever the exit code): nothing loaded, nothing
                # was tested, and dispatch.py runs every link
                if warn is not None:
                    warn.append("tests skipped: Claude Code's rollout switch has mods off here")
            elif test.returncode != 0:
                problems.append("tests failed: " + " | ".join(output.strip().splitlines()[-6:]))
        except (OSError, subprocess.SubprocessError) as exc:
            problems.append(f"tests could not run: {type(exc).__name__}")
    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Contract check for the Claude Code mods in mods/<id>/")
    ap.add_argument("--static", action="store_true", help="static checks only (no claude CLI)")
    ap.add_argument("--strict", action="store_true", help="claude plugin validate --strict")
    ap.add_argument("--no-tests", action="store_true", help="skip claude plugin test")
    args = ap.parse_args(argv)
    mods = enabled_mods()
    if not mods:
        print("OK   no mods enabled")
        return 0
    failed = False
    for mod_id in mods:
        hard, warn = static_problems(mod_id)
        if not args.static and not hard:
            hard += cli_problems(mod_id, args.strict, not args.no_tests, warn=warn)
        for line in warn:
            print(f"WARN {mod_id}: {line}")
        for line in hard:
            print(f"FAIL {mod_id}: {line}")
        if not hard:
            print(f"OK   {mod_id}")
        failed = failed or bool(hard)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

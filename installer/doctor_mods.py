"""Doctor rows for the Claude Code mods (manifest ``mods``).

  mods          static contract (scripts/validate_mods.py) + `claude plugin validate`;
                the manifest ``claude_version`` is the MINIMUM verified release: same
                major.minor and >= it -> PASS; below it or a newer minor -> WARN
                (audit A-06/I-07: an exact pin WARNed after every auto-update).
  mods-runtime  `tsc -p mods/<id> --noEmit` (needs the engine-laid
                .claude-plugin/types/) + `claude plugin test mods/<id>` (I-04).
                WARN, not FAIL, while Claude Code's rollout switch has mods off, and when
                the tests only time out under CPU load (re-run once; A6-02).

Every external call goes through injectable ``which`` / ``run`` so tests never need
the CLI. Pure stdlib.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
ROLLOUT_OFF = "hooks modules are turned off"  # same marker as scripts/validate_mods.py


def _vt(s: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", s or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def version_status(have: str, want: str) -> tuple[str, str]:
    h, w = _vt(have), _vt(want)
    if not h or not w:
        return PASS, ""
    if h < w:
        return WARN, f"claude {have} is below the verified minimum {want}: update Claude Code"
    if h[:2] != w[:2]:
        return WARN, (f"claude {have} is a newer minor than the verified {want}: run "
                      "`python3 scripts/validate_mods.py`, then bump manifest mods.claude_version")
    return PASS, ""


def _run(argv: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:  # utf-8 whatever the console code page: a cp1252 decode loses the whole output
        cp = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace",
                            timeout=300, check=False, cwd=cwd)
        return cp.returncode, (cp.stdout or "") + (cp.stderr or "")
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"{type(exc).__name__}: {exc}"


# a loaded box, not a broken mod: bun's 5 s test timeout, and the one rejection a slow run leaves behind
# (a test's `$.state.set` outliving the engine's teardown). Any other rejection text is a real bug (A6v2-01).
_TEARDOWN = "no hooks module of that name is loaded"
_ASSERT_SIGNS = ("expect(", "Expected", "Received", "AssertionError")
_TYPED = re.compile(r"\b(?:Type|Reference|Range|Syntax|Eval|URI)Error\b")


_RESULT = re.compile(r"\s*\((?:pass|fail|skip|todo)\)")


def _is_load_line(line: str) -> bool:
    return "timed out after" in line or ("a rejection nothing handled" in line and _TEARDOWN in line)


def _load_only(out: str) -> bool:
    """The `plugin test` output is CPU-load timeouts and nothing else: no assertion text and no typed
    error (`TypeError`, `ReferenceError` ...) anywhere, at least one `(fail)` line, and EVERY `(fail)`
    test explained by its own timeout / known teardown rejection line (P1: a signature elsewhere in the
    output must not vouch for a test that failed another way). The line sits on the test's result line
    or between it and its neighbouring result lines (bun prints a test's error above its `(fail)`
    line); one signature line explains one test."""
    if any(s in out for s in _ASSERT_SIGNS) or _TYPED.search(out):
        return False
    lines = out.splitlines()
    marks = [i for i, ln in enumerate(lines) if _RESULT.match(ln)]
    used: set[int] = set()
    fails = 0
    for k, i in enumerate(marks):
        if not lines[i].lstrip().startswith("(fail)"):
            continue
        fails += 1
        lo, hi = (marks[k - 1] + 1 if k else 0), (marks[k + 1] if k + 1 < len(marks) else len(lines))
        hit = next((j for j in range(lo, hi) if j not in used and _is_load_line(lines[j])), None)
        if hit is None:
            return False
        used.add(hit)
    return fails > 0


def _tail(out: str, n: int = 3) -> str:
    return " | ".join(out.strip().splitlines()[-n:])[:160]


def _load_validate_mods(root: Path):
    spec = importlib.util.spec_from_file_location("validate_mods", root / "scripts" / "validate_mods.py")
    vm = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(vm)  # type: ignore[union-attr]
    return vm


def check_mods(root: Path, mods: dict, ci: bool,
               claude_version: Callable[[], str]) -> tuple[str, str]:
    enabled = [m for m in mods.get("enabled") or [] if isinstance(m, str)]
    if not enabled:
        return PASS, "no mods enabled"
    try:
        vm = _load_validate_mods(root)
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"validate_mods.py: {type(exc).__name__}: {exc}"
    problems = []
    for mod_id in enabled:
        hard, _warn = vm.static_problems(mod_id, root)
        if not hard and not ci:
            hard = vm.cli_problems(mod_id, strict=False, run_tests=False, root=root)
        problems += [f"{mod_id}: {p}" for p in hard]
    if problems:
        return FAIL, "; ".join(problems)[:200]
    have = "" if ci else claude_version()
    status, note = version_status(have, mods.get("claude_version", ""))
    if status != PASS:
        return status, f"{len(enabled)} mod(s) valid, but {note}"
    return PASS, f"{len(enabled)} mod(s): {', '.join(enabled)}" + (f" on claude {have}" if have else "")


def check_mods_runtime(root: Path, enabled: list[str], ci: bool,
                       which: Callable | None = None,
                       run: Callable = _run) -> tuple[str, str]:
    if ci:
        return SKIP, "--ci (needs the claude CLI and the engine-laid types)"
    if not enabled:
        return PASS, "no mods enabled"
    which = which or shutil.which  # resolved per call so a test can patch shutil.which
    tsc, claude = which("tsc"), which("claude")
    problems, notes, ran, rollout_off, loaded = [], [], [], False, []
    for mod_id in enabled:
        folder = Path(root) / "mods" / mod_id
        if claude:
            cmd = [claude, "plugin", "test", str(folder)]
            rc, out = run(cmd)
            if rc != 0 and _load_only(out):  # bun's 5 s test timeout under CPU load: once more
                rc, out = run(cmd)
                if rc != 0 and _load_only(out):
                    loaded.append(mod_id)
                    rc = 0
            ran.append("plugin test")
            if ROLLOUT_OFF in out:
                rollout_off = True
            elif rc != 0:
                problems.append(f"{mod_id} tests: {_tail(out)}")
        if tsc and (folder / "tsconfig.json").is_file() and (folder / ".claude-plugin" / "types").is_dir():
            # no path in argv: tsc is a .cmd shim on Windows and cmd.exe parses an `&` in a path
            rc, out = run([tsc, "-p", ".", "--noEmit"], cwd=folder)
            ran.append("tsc")
            if rc != 0:
                problems.append(f"{mod_id} tsc: {_tail(out)}")
        elif tsc:
            notes.append(f"{mod_id}: types not laid yet (start claude once)")
    if rollout_off:
        return WARN, "rollout switch has mods off here: nothing loads, tests skipped" + (
            f"; {problems[0]}" if problems else "")
    if problems:
        return FAIL, "; ".join(problems)[:240]
    if loaded:
        return WARN, f"load-sensitive, re-run when idle: {', '.join(loaded)} tests timed out twice (CPU load)"
    if not ran:
        return WARN, "claude and tsc not on PATH: mod tests and type-check not run" + (
            f" ({notes[0]})" if notes else "")
    return PASS, f"{', '.join(sorted(set(ran)))} ok for {', '.join(enabled)}" + (f"; {notes[0]}" if notes else "")

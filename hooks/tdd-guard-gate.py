#!/usr/bin/env python3
"""tdd-guard-gate.py — validate a write against TDD in WARN mode, scoped to the project.

Invoked by tdd_guard_launcher.py (only for active git projects with a test stack; never
HOME). Reads the hook payload on stdin and:

  1. SCOPE — an edited file OUTSIDE the active project root is allowed silently.
  2. VALIDATE — one validator per run; a bare run that exits non-zero falls back to the
     binary once, inside the same 15 s budget:

       | validator | when                                                        | timeout |
       |-----------|-------------------------------------------------------------|---------|
       | bare      | `claude` on PATH AND ANTHROPIC_API_KEY set AND TDD_GUARD_VALIDATOR != "binary" | 12 s |
       | binary    | else the `tdd-guard` npm binary on PATH (its Agent SDK call) | 15 s    |
       | none      | neither → exit 0 silently                                    |   -     |

     ``bare`` runs ``claude -p --bare --model haiku --max-turns 1 --output-format json``
     (``--bare`` skips hooks, plugins and CLAUDE.md, and needs an API-key env, not the
     OAuth file). The prompt goes on stdin (a Windows ``.cmd`` shim mangles multi-line
     argv): the validator instructions (``~/.claude/tdd-guard/data/instructions.md``,
     capped 6 KB, else a built-in rule set), the edit (each text capped 2 KB), up to 10
     failing tests from ``<root>/.claude/tdd-guard/data/test.json``, and the required
     answer ``{"decision":"allow"|"block","reason":"<one sentence>"}``.
  3. WARN, don't pause — a block becomes a non-blocking advisory (reason ≤ 300 chars,
     whole additionalContext ≤ 500 chars).

Never blocks. Fails OPEN: any error, a non-zero validator exit or unparseable output →
no output. exit 0 always. UTF-8 subprocess I/O both ways; ``shutil.which`` resolves the
npm ``.cmd`` shims on Windows.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

FILE_TOOLS = {"Write", "Edit", "MultiEdit"}
# Sonnet via the Agent SDK takes 4-7.3 s per call (2026-09-30); 7 s dropped the slow
# tail silently. Launcher and dispatch link timeouts must stay above this.
TDD_TIMEOUT_S = 15
BARE_TIMEOUT_S = 12
# `claude -p --bare` reads only ANTHROPIC_API_KEY (or an apiKeyHelper), never CLAUDE_CODE_OAUTH_TOKEN
API_KEY_ENVS = ("ANTHROPIC_API_KEY",)
_REASON_CAP = 300
_ADVISORY_CAP = 500
_TEXT_CAP = 2048
_INSTR_CAP = 6144
_MAX_FAILING = 10

_BUILTIN_RULES = """You validate one code edit against test-driven development.
Rules:
1. New behaviour needs a failing test first; implementation without one is a violation.
2. Adding or editing a test file is always allowed.
3. Implementation may only make the currently failing tests pass, nothing more.
4. Refactoring with all tests green is allowed when behaviour does not change.
5. Adding more than one new test at a time is a violation.
6. Stubs, types, imports and interfaces that a failing test needs are allowed.
7. Formatting, comments and renames with no behaviour change are allowed.
8. Config, docs and generated files are allowed.
9. Deleting dead code is allowed.
10. When unsure, allow.
11. Judge only this edit and the failing tests listed.
12. Answer with JSON only."""


def _within(path: str, root: str) -> bool:
    try:
        p = Path(path).resolve()
        r = Path(root).resolve()
        return r == p or r in p.parents
    except Exception:
        return True  # uncertain -> don't skip on scope grounds


def _extract_file_path(tool_input: dict) -> str:
    for k in ("file_path", "path", "filePath", "notebook_path"):
        v = tool_input.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _is_block(stdout: str, rc: int) -> tuple[bool, str]:
    """Detect a tdd-guard binary block and extract its reason."""
    reason = ""
    try:
        obj = json.loads(stdout) if stdout.strip() else {}
    except Exception:
        obj = {}
    if isinstance(obj, dict):
        hso = obj.get("hookSpecificOutput")
        if isinstance(hso, dict):
            if str(hso.get("permissionDecision", "")).lower() == "deny":
                return True, str(hso.get("permissionDecisionReason") or "")
        if str(obj.get("permissionDecision", "")).lower() == "deny":
            return True, str(obj.get("permissionDecisionReason") or obj.get("reason") or "")
        if str(obj.get("decision", "")).lower() in ("block", "deny"):
            return True, str(obj.get("reason") or obj.get("message") or "")
        reason = str(obj.get("reason") or obj.get("message") or "")
    if rc == 2:  # exit code 2 is the Claude Code "block" convention
        return True, reason or stdout.strip()
    return False, reason


def _advisory(reason: str) -> str:
    reason = (reason or "TDD violation").strip()
    if len(reason) > _REASON_CAP:
        reason = reason[:_REASON_CAP] + "…"
    msg = (
        "TDD GUARD (advisory, not blocking): " + reason +
        "\nPreferred path: write the failing test first (test-driven-development skill), "
        "run it red with the project's test command, then implement. Proceeding as requested."
    )
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": msg[:_ADVISORY_CAP],
        }
    })


# --------------------------------------------------------------------------- #
# Validator choice
# --------------------------------------------------------------------------- #
def _validator_argv() -> list[str] | None:
    """The bare argv (prompt goes on stdin), or None when the bare path is unavailable."""
    if os.environ.get("TDD_GUARD_VALIDATOR") == "binary":
        return None
    if not any(os.environ.get(k) for k in API_KEY_ENVS):
        return None
    claude = shutil.which("claude")
    if not claude:
        return None
    return [claude, "-p", "--bare", "--model", "haiku", "--max-turns", "1", "--output-format", "json"]


def _validator(root) -> tuple[str, list[str]] | None:
    bare = _validator_argv()
    if bare:
        return "bare", bare
    tg = shutil.which("tdd-guard")
    return ("binary", [tg]) if tg else None


def _cap(text, n: int = _TEXT_CAP) -> str:
    s = str(text or "")
    return s if len(s) <= n else s[:n] + "\n…(truncated)"


def _instructions() -> str:
    p = Path.home() / ".claude" / "tdd-guard" / "data" / "instructions.md"
    try:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return _cap(text, _INSTR_CAP)
    except OSError:
        pass
    return _BUILTIN_RULES


def _failing_tests(root) -> list[str]:
    p = Path(root) / ".claude" / "tdd-guard" / "data" / "test.json"
    out: list[str] = []
    try:
        data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        for mod in data.get("testModules") or []:
            for t in (mod or {}).get("tests") or []:
                if isinstance(t, dict) and t.get("state") != "passed" and t.get("fullName"):
                    out.append(str(t["fullName"])[:200])
                    if len(out) >= _MAX_FAILING:
                        return out
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return out


def _prompt(root, payload: dict) -> str:
    ti = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(ti, dict):
        ti = {}
    fp = _extract_file_path(ti)
    try:
        rel = os.path.relpath(fp, str(root)) if fp else ""
    except ValueError:
        rel = fp
    parts = [_instructions(), "", f"Tool: {payload.get('tool_name') or ''}", f"File: {rel or fp}"]
    if "content" in ti:
        parts += ["New file content:", _cap(ti.get("content"))]
    else:
        parts += ["Old text:", _cap(ti.get("old_string")), "New text:", _cap(ti.get("new_string"))]
    failing = _failing_tests(root)
    parts += ["Failing tests:", "\n".join(f"- {n}" for n in failing) if failing else "(none recorded)"]
    parts += ["", 'Reply with JSON only: {"decision":"allow"|"block","reason":"<one sentence>"}']
    return "\n".join(parts)


def _parse_bare(stdout: str) -> tuple[bool, str]:
    """``--output-format json`` wraps the answer text in ``{"result": "..."}``; the answer
    is the first ``{...}`` object inside it. Anything else → not blocked."""
    try:
        outer = json.loads(stdout)
        text = outer.get("result") if isinstance(outer, dict) else None
        if not isinstance(text, str):
            return False, ""
        start = text.find("{")
        if start < 0:
            return False, ""
        inner, _ = json.JSONDecoder().raw_decode(text[start:])
        if isinstance(inner, dict) and str(inner.get("decision", "")).lower() == "block":
            return True, str(inner.get("reason") or "")
    except (ValueError, AttributeError, TypeError):
        pass
    return False, ""


def main() -> int:
    raw = sys.stdin.read() or "{}"
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    tool = payload.get("tool_name") or payload.get("tool") or ""
    tool_input = payload.get("tool_input") or payload.get("input") or {}

    # 1. Scope: external files (outside the active project) -> allow silently.
    if tool in FILE_TOOLS and isinstance(tool_input, dict):
        fpath = _extract_file_path(tool_input)
        if fpath and not _within(fpath, root):
            return 0

    v = _validator(root)
    if v is None:
        return 0
    kind, argv = v
    budget = TDD_TIMEOUT_S  # the launcher waits 16 s, so bare + fallback share this
    try:
        if kind == "bare":
            t0 = time.monotonic()
            proc = subprocess.run(argv, input=_prompt(root, payload), capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=BARE_TIMEOUT_S)
            if proc.returncode == 0:
                blocked, reason = _parse_bare(proc.stdout)
                out = ""
            else:
                # no usable key or a CLI error: try the binary once with what is left
                tg = shutil.which("tdd-guard")
                budget = TDD_TIMEOUT_S - (time.monotonic() - t0)
                if not tg or budget < 2:
                    return 0
                kind, argv = "binary", [tg]
        if kind == "binary":
            proc = subprocess.run(argv, input=raw, capture_output=True,
                                  encoding="utf-8", errors="replace", timeout=budget)
            out = proc.stdout
            blocked, reason = _is_block(out, proc.returncode)
    except Exception:
        return 0  # fail open

    # 3. Warn, don't pause.
    if blocked:
        sys.stdout.write(_advisory(reason))
    elif out.strip():
        sys.stdout.write(out)  # binary passthrough allow / state-capture output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

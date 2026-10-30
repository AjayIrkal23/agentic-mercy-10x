#!/usr/bin/env python3
"""config-protection-gate.py — PreToolUse ask on Write|Edit|MultiEdit|NotebookEdit when the target is an
EXISTING linter/formatter config (ECC config-protection, ported as an ask with a prompt escape).

Agents under pressure weaken a lint config to go green; the fix belongs in the code. So an edit to an
existing eslint / prettier / biome / ruff / stylelint / markdownlint / shellcheck config, a split config
(`eslint.config.base.mjs`) or an ignore file asks, unless the turn's human prompt names the file, its tool
family or a lint-config phrase. Build configs (vite, jest, tsconfig, pyproject, package.json) are not
protected; a new config file is free; anything inside ~/.claude is exempt. An interactive ask repeats until approved
(a declined ask is no allow on the retry). When nobody can answer (subagent, restored session, `-p` run,
workflow script) the ask downgrades to a logged advisory (lib/gate_mode), once per file per session
(lib/gate_mode.once_per_file: this gate has no post-tool-use ack link).
Never denies; prints {} on every quiet path; exit 0 always. Stdlib only, no subprocess.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from tool_compat import WRITE_TOOLS, tool_name  # noqa: E402

GATE = "config-protection"
PROTECTED = frozenset({  # ECC list, lower-case; ignore files included (the cheapest way to silence a check)
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml",
    "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", "eslint.config.ts", "eslint.config.mts",
    "eslint.config.cts",
    ".prettierrc", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.json", ".prettierrc.yml", ".prettierrc.yaml",
    "prettier.config.js", "prettier.config.cjs", "prettier.config.mjs",
    "biome.json", "biome.jsonc", ".biome.json", ".biome.jsonc", ".ruff.toml", "ruff.toml", ".shellcheckrc",
    ".stylelintrc", ".stylelintrc.json", ".stylelintrc.yml", ".stylelintrc.yaml", ".stylelintrc.js",
    ".stylelintrc.cjs", ".stylelintrc.mjs",
    "stylelint.config.js", "stylelint.config.cjs", "stylelint.config.mjs", "stylelint.config.ts",
    "stylelint.config.mts", "stylelint.config.cts",
    ".markdownlint.json", ".markdownlint.jsonc", ".markdownlint.yaml", ".markdownlint.yml", ".markdownlint.cjs",
    ".markdownlint.mjs", ".markdownlintrc",
    ".markdownlint-cli2.jsonc", ".markdownlint-cli2.yaml", ".markdownlint-cli2.cjs", ".markdownlint-cli2.mjs",
    ".eslintignore", ".prettierignore", ".stylelintignore", ".markdownlintignore",
})
_SPLIT_CONFIG = (  # eslint.config.base.mjs, .prettierrc.shared.yml (ECC PROTECTED_PATTERNS)
    re.compile(r"^(eslint|prettier|stylelint|commitlint|oxlint)\.config(\.[a-z0-9_-]+)*\.(js|mjs|cjs|ts|mts|cts)$"),
    re.compile(r"^\.(eslintrc|prettierrc|stylelintrc|markdownlint)(\.[a-z0-9_-]+)*\.(js|cjs|mjs|json|jsonc|ya?ml|toml)$"),
)
_FAMILIES = ("eslint", "prettier", "biome", "ruff", "shellcheck", "stylelint", "markdownlint", "oxlint", "commitlint")
_GENERIC_ESCAPE = ("lint config", "linter config", "lint rule", "formatter config", "format config", "lint settings")
_PATH_KEYS = ("file_path", "notebook_path", "path", "target_file")


def protected_basename(path: str):
    base = str(path).replace("\\", "/").rsplit("/", 1)[-1].lower()
    if base in PROTECTED or any(rx.match(base) for rx in _SPLIT_CONFIG):
        return base
    return None


def family_of(base: str) -> str:
    for fam in _FAMILIES:
        if fam in base:
            return fam
    return base


def exists_lstat(path: str) -> bool:
    try:
        os.lstat(path)  # a dangling symlink to a protected name still counts (ECC)
        return True
    except (OSError, ValueError):
        return False


def prompt_escapes(transcript_path, base: str) -> bool:
    """The last human prompt names the file, its tool family or a lint-config phrase."""
    try:
        from lib.turns import last_user_turn
        _, text = last_user_turn(transcript_path)
    except Exception:  # noqa: BLE001
        return False
    if not text:
        return False
    t = text.lower()
    return base in t or family_of(base) in t or any(p in t for p in _GENERIC_ESCAPE)


def _target(ti: dict) -> str:
    for key in _PATH_KEYS:
        v = ti.get(key)
        if isinstance(v, str) and v:
            return v
    for e in ti.get("edits") or []:  # MultiEdit shapes that carry the path per edit
        if isinstance(e, dict) and isinstance(e.get("file_path"), str) and e["file_path"]:
            return e["file_path"]
    return ""


def _inside_claude_dir(abs_path: str) -> bool:
    try:
        from lib import platform as plat
        cdir = os.path.normcase(os.path.abspath(str(plat.claude_dir())))
    except Exception:  # noqa: BLE001
        return False
    p = os.path.normcase(abs_path)
    return p == cdir or p.startswith(cdir.rstrip(os.sep) + os.sep)


def _decide(payload) -> tuple:
    try:
        from lib import gate_mode
        return gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001 - oom-sentinel absent or broken: plain ask
        return "ask", "interactive"


def _once(sid: str, path: str) -> bool:
    try:
        from lib import gate_mode
        return gate_mode.once_per_file(sid, GATE, path)
    except Exception:  # noqa: BLE001
        return True


def _telemetry(**fields) -> None:
    try:
        from lib import hook_telemetry
        hook_telemetry.record("PreToolUse", GATE, **fields)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        print("{}")
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0
    tool = tool_name(payload)
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool not in WRITE_TOOLS and tool != "NotebookEdit":
        print("{}")
        return 0
    path = _target(ti)
    base = protected_basename(path) if path else None
    if not base:
        print("{}")
        return 0
    cwd = str(payload.get("cwd") or "")
    full = os.path.expanduser(path)
    if cwd and not os.path.isabs(full):
        full = os.path.join(cwd, full)
    abs_path = os.path.abspath(full)
    if _inside_claude_dir(abs_path) or not exists_lstat(full):
        print("{}")
        return 0
    sid = str(payload.get("session_id") or payload.get("conversation_id") or "")
    if prompt_escapes(payload.get("transcript_path"), base):
        _telemetry(decision="escape", file=base, session=sid)
        print("{}")
        return 0
    reason = (f"`{base}` is a linter/formatter config. Fix the source so the check passes instead of weakening "
              "the config; if the config change is the task, approve.")
    decision, why = _decide(payload)
    if decision == "ask":  # repeats until approved: a declined ask is no allow on the retry (REVIEW2 Fix 3)
        _telemetry(decision="ask", file=base, session=sid)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                 "permissionDecisionReason": reason}}))
        return 0
    if not _once(sid, abs_path):  # the advisory: once per file per session
        print("{}")
        return 0
    _telemetry(decision="ask_downgraded", reason=why, file=base, session=sid)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                      reason + f" (ask downgraded: {why}; unattended session, continuing)"}}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - fail open: a broken gate must not block writes
        print("{}")
        raise SystemExit(0)

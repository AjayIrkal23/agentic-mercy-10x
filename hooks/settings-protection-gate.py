#!/usr/bin/env python3
"""settings-protection-gate.py — PreToolUse ask on Write|Edit|MultiEdit|NotebookEdit of a file that
grants permissions or routes models: any `.claude/settings.json`, `.claude/settings.local.json`,
`.claude/settings.user.json` (repo or ~/.claude), `~/.claude/hooks/model-policy.json`, `~/.claude.json`,
and on a Bash/PowerShell command that writes one (redirect, tee, cp/mv/install/ln/rsync target,
sed/perl -i, interpreter write). Case-folded on Windows (NTFS).

New files count (an agent creating settings.local.json with Bash(*) is the threat). An interactive
session gets `ask`. When nobody can answer (subagent, restored, CLAUDE_WORKBENCH_UNATTENDED, workflow
script: lib/gate_mode; or a headless `claude -p`, CLAUDE_CODE_SESSION_ATTENDED=0) the gate DENIES:
live r3 showed `-p --permission-mode bypassPermissions` lets an `ask` through with no denial, and
Claude Code's own settings check does not run under bypassPermissions (R2-F2). Escape: the turn's human
prompt names the file (`.claude/settings…` path for the settings files; basename for `.claude.json` /
`model-policy.json`) or a permission-rule phrase (`permission rule`, `allow rule`, `permissions.allow`,
...: lib/turns.PERMISSION_PHRASES).
Differs from config-protection-gate on purpose: new files count, ~/.claude is in scope, never downgraded
to an advisory. {} on every quiet path; exit 0 always. Stdlib only, no subprocess.
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

from lib import platform as plat  # noqa: E402
from tool_compat import SHELL_TOOLS, WRITE_TOOLS, tool_name  # noqa: E402

GATE = "settings-protection"
_SETTINGS = frozenset({"settings.json", "settings.local.json", "settings.user.json"})
_PATH_KEYS = ("file_path", "notebook_path", "path", "target_file")

# a protected basename as a shell token (no quotes, spaces or shell metachars inside)
_PROT_TOK = r"(?P<path>[^\s'\"|;&<>()`]*(?:settings(?:\.local|\.user)?\.json|\.claude\.json|model-policy\.json))"
# write shapes whose TARGET is the token: redirects (both heredoc orders), tee, copy-like last arg,
# in-place editors, PowerShell writers. A read (`cat settings.json`, `jq . settings.json > /tmp/x`) is not one.
_SHELL_WRITE_RES = (
    re.compile(r">>?\s*['\"]?" + _PROT_TOK),
    re.compile(r"\btee\b(?:\s+-\S+)*\s+['\"]?" + _PROT_TOK),
    re.compile(r"\b(?:cp|mv|install|ln|rsync)\b[^|;&\n]*?\s['\"]?" + _PROT_TOK + r"['\"]?\s*(?:$|[|;&\n])"),
    re.compile(r"\b(?:sed|perl|ruby)\b(?:\s+-\S+)*?\s+-[A-Za-z]*i\S*[^|;&\n]*?\s['\"]?" + _PROT_TOK),
    re.compile(r"(?:Set-Content|Out-File|Add-Content|\[(?:System\.)?IO\.File\]::Write\w*)[^\n]*?" + _PROT_TOK),
)
# an interpreter one-liner / heredoc that writes: every protected token in it is a target
_INTERP_WRITE_RE = re.compile(r"\b(?:python3?(?:\.\d+)?|node|ruby|perl|php|deno|bun)\b.*?"
                              r"(?:\bopen\(|write_text|writeFile|\.write\b|json\.dump\b)", re.S)
_ANY_PROT_RE = re.compile(_PROT_TOK)


def _shell_targets(cmd: str) -> list[str]:
    hits = [m.group("path") for rx in _SHELL_WRITE_RES for m in rx.finditer(cmd)]
    if _INTERP_WRITE_RE.search(cmd):
        hits += [m.group("path") for m in _ANY_PROT_RE.finditer(cmd)]
    return [h.replace("${HOME}", "~").replace("$HOME", "~") for h in hits if h]


def _target(ti: dict) -> str:
    for k in _PATH_KEYS:
        v = ti.get(k)
        if isinstance(v, str) and v:
            return v
    for e in ti.get("edits") or []:
        if isinstance(e, dict) and isinstance(e.get("file_path"), str) and e["file_path"]:
            return e["file_path"]
    return ""


def protected(abs_path: str) -> str | None:
    """The protected basename, or None."""
    fold = str.lower if plat.IS_WINDOWS else (lambda s: s)  # NTFS: Settings.json is the same file
    p = abs_path.replace("\\", "/")
    parts = p.rsplit("/", 2)
    base = fold(parts[-1])
    parent = parts[-2] if len(parts) >= 2 else ""
    if base in _SETTINGS and fold(parent) == ".claude":
        return base
    home = Path.home().as_posix().rstrip("/")
    if fold(p) in {fold(f"{home}/.claude.json"), fold(f"{home}/.claude/hooks/model-policy.json")}:
        return base
    return None


def prompt_escapes(transcript_path, base: str) -> bool:
    """The last human prompt names the file (`.claude/settings…` path for the settings files; basename for
    `.claude.json` / `model-policy.json`) or a permission-rule phrase. Bare "settings"/"permission" no longer
    escape (live r3: "the user settings page"), nor does a bare `settings.json` (VS Code's `.vscode/` file)."""
    b = base.lower()
    names = (b,) if b in (".claude.json", "model-policy.json") else (".claude/settings", ".claude\\settings")
    try:
        from lib.turns import PERMISSION_PHRASES, prompt_names
        return prompt_names(transcript_path, names, PERMISSION_PHRASES)
    except Exception:  # noqa: BLE001
        return False


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
    if tool in SHELL_TOOLS:
        paths = _shell_targets(str(ti.get("command") or ""))
    elif tool in WRITE_TOOLS or tool == "NotebookEdit":
        paths = [_target(ti)]
    else:
        paths = []
    cwd = str(payload.get("cwd") or "")
    base = None
    for path in paths:
        if not path:
            continue
        full = os.path.expanduser(path)
        if cwd and not os.path.isabs(full):
            full = os.path.join(cwd, full)
        base = protected(os.path.abspath(full))
        if base:
            break
    if not base:
        print("{}")
        return 0
    sid = str(payload.get("session_id") or payload.get("conversation_id") or "")
    if prompt_escapes(payload.get("transcript_path"), base):
        _telemetry(decision="escape", file=base, session=sid)
        print("{}")
        return 0
    reason = (f"`{base}` grants permissions, wires hooks or routes models (CLAUDE.md: no agent message can "
              "authorize changing permission settings or configuration).")
    unattended = _unattended(payload)
    if unattended:
        decision = "deny"
        reason += (f" No one can confirm in this {unattended} session: leave the change for the user, or name the "
                   "file by its `.claude/` path (or a permission-rule phrase) in the prompt that asks for it.")
    else:
        decision = "ask"
        reason += " Approve only if you asked for this change."
    _telemetry(decision=decision, file=base, session=sid, **({"reason": unattended} if unattended else {}))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}}))
    return 0


def _unattended(payload: dict) -> str:
    """Why nobody can answer an ask ('' when someone can): lib/gate_mode's reasons, or a headless -p run."""
    if os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "0":
        return "unattended (headless -p)"
    try:
        from lib import gate_mode
        decision, why = gate_mode.decide(payload, "ask")
    except Exception:  # noqa: BLE001 - gate_mode unavailable: keep the ask
        return ""
    return "" if decision == "ask" else why


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - fail open: a broken gate must not block writes
        print("{}")
        raise SystemExit(0)

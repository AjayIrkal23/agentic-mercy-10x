#!/usr/bin/env python3
"""settings-protection-gate.py — PreToolUse ask on Write|Edit|MultiEdit|NotebookEdit of a file that
grants permissions or routes models: any `.claude/settings.json`, `.claude/settings.local.json`,
`.claude/settings.user.json` (repo or ~/.claude), `~/.claude/hooks/model-policy.json`, `~/.claude.json`,
and the gates' own wiring under the Claude config dir (`hooks/dispatch.config.json`, every
`hooks/*-gate.py`, `settings.template.json`, `installer/manifest.json`, `.blast-bypass`; audit2 SP-2),
and on a Bash/PowerShell command that writes one (redirect, tee, cp/mv/install/ln/rsync/touch/truncate
target, sed/perl -i, interpreter write; a read-only `open(path)` is not one). Case-folded on Windows (NTFS).
A move, delete or restore is a write too (FIX2 item 1, REVERIFY R3): the file as ANY argument of
mv/rm/unlink/truncate/shred (Remove-Item, Move-Item, del, ...), `dd of=`, `git checkout|restore|rm|mv`;
a copy into a directory (`cp x ~/.claude/hooks/`); the config dir itself and `hooks/` as a mv/rm
source; relative paths resolve after a `cd`/`git -C` earlier in the command, and the state dir's
`dispatch.config.lkg.json` (the dispatcher's fallback) is wiring too.
Residual: `hooks/dispatch.py` and `hooks/lib/*.py` are not protected (that would ask on most workbench edits),
nor are a `git checkout <branch>` or `git stash` that swap the whole tree.

New files count (an agent creating settings.local.json with Bash(*) is the threat). An interactive
session gets `ask`. When nobody can answer (subagent, restored, CLAUDE_WORKBENCH_UNATTENDED, workflow
script: lib/gate_mode; or a headless `claude -p`, CLAUDE_CODE_SESSION_ATTENDED=0) the gate DENIES:
live r3 showed `-p --permission-mode bypassPermissions` lets an `ask` through with no denial, and
Claude Code's own settings check does not run under bypassPermissions (R2-F2). Escape: the turn's human
prompt names the file (`.claude/settings…` path for the settings files; basename for `.claude.json` /
`model-policy.json` and the wiring files) or a permission-rule phrase (`permission rule`, `allow rule`, `permissions.allow`,
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
# the gates' own wiring under the Claude config dir (SP-2): a change here can switch a gate off
_WIRING = ("hooks/dispatch.config.json", "settings.template.json", "installer/manifest.json", ".blast-bypass",
           "state/dispatch.config.lkg.json")
_WIRING_BASENAMES = frozenset(w.rsplit("/", 1)[-1] for w in _WIRING)
_GATE_RE = re.compile(r"^hooks/[\w-]+-gate\.py$")

# a protected basename as a shell token (no quotes, spaces or shell metachars inside)
_PROT_TOK = (r"(?P<path>[^\s'\"|;&<>()`]*(?:settings(?:\.local|\.user|\.template)?\.json|\.claude\.json"
             r"|model-policy\.json|dispatch\.config(?:\.lkg)?\.json|manifest\.json|\.blast-bypass|[\w-]+-gate\.py))")
# write shapes whose TARGET is the token: redirects (both heredoc orders), tee, copy-like last arg
# (touch/truncate create or empty a file: same family), in-place editors, PowerShell writers.
# A read (`cat settings.json`, `jq . settings.json > /tmp/x`) is not one.
_SHELL_WRITE_RES = (
    re.compile(r">>?\s*['\"]?" + _PROT_TOK),
    re.compile(r"\btee\b(?:\s+-\S+)*\s+['\"]?" + _PROT_TOK),
    re.compile(r"\b(?:cp|mv|install|ln|rsync|touch|truncate)\b[^|;&\n]*?\s['\"]?" + _PROT_TOK
               + r"['\"]?\s*(?:$|[|;&\n])"),
    re.compile(r"\b(?:sed|perl|ruby)\b(?:\s+-\S+)*?\s+-[A-Za-z]*i\S*[^|;&\n]*?\s['\"]?" + _PROT_TOK),
    re.compile(r"(?:Set-Content|Out-File|Add-Content|\[(?:System\.)?IO\.File\]::Write\w*)[^\n]*?" + _PROT_TOK),
)
# an interpreter one-liner / heredoc that writes: every protected token in it is a target. A read-only
# `open(path)` / `open(path, "r")` is not a write (RT-1); a write mode, os.O_* write flags or a writer call is.
_INTERP_WRITE_RE = re.compile(r"\b(?:python3?(?:\.\d+)?|node|ruby|perl|php|deno|bun)\b.*?"
                              r"(?:\bopen\([^)]*?,\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+]"
                              r"|os\.O_(?:WRONLY|RDWR|CREAT|APPEND|TRUNC)"
                              r"|write_text|write_bytes|writeFile|appendFile|createWriteStream|\.write\b"
                              r"|json\.dump\b)", re.S)
_ANY_PROT_RE = re.compile(_PROT_TOK)


def _shell_targets(cmd: str) -> list[str]:
    hits = [m.group("path") for rx in _SHELL_WRITE_RES for m in rx.finditer(cmd)]
    if _INTERP_WRITE_RE.search(cmd):
        hits += [m.group("path") for m in _ANY_PROT_RE.finditer(cmd)]
    return [h.replace("${HOME}", "~").replace("$HOME", "~") for h in hits if h]


# FIX2 item 1 (REVERIFY R3): every argument of these is a target (a removed or moved SOURCE switches a gate off)
_ANY_ARG = frozenset({"mv", "rm", "unlink", "truncate", "shred", "remove-item", "ri", "del", "erase", "move-item",
                      "mi", "move", "rename-item", "ren", "rni", "clear-content", "clc"})
# the last argument may be a directory: `cp x ~/.claude/hooks/` writes hooks/<basename of x>
_COPY_LIKE = frozenset({"cp", "mv", "install", "ln", "rsync", "copy-item", "cpi", "copy", "move-item", "mi", "move"})
_GIT_PATH_SUBS = frozenset({"checkout", "restore", "rm", "mv"})
_WRAPPERS = frozenset({"sudo", "doas", "env", "command", "exec", "nohup", "time", "nice", "builtin"})
_ASSIGN_RE = re.compile(r"^[A-Za-z_]\w*=")
_FALLBACK_SEP = re.compile(r"&&|\|\||[;&|\n(){}]")


def _segs(cmd: str, segments) -> list:
    try:
        return segments(cmd)
    except ValueError:  # an unbalanced quote must not switch the walk off: split by hand
        return [[t.strip("'\"") for t in s.split()] for s in _FALLBACK_SEP.split(cmd) if s.strip()]


def _walk_targets(cmd: str, cwd: str, depth: int = 0) -> list[str]:
    """Paths a command moves, removes, empties or restores, and the redirect/cp-family targets of a segment
    that runs after a `cd` (R3). Uses commit_docs_check's tokenizer (newlines, `{}`, PowerShell, `cd`)."""
    try:
        from commit_docs_check import (_DIR_COMMANDS, _GIT_OPTS_WITH_VALUE, _dir_arg, _join, _payload,
                                       _program, _segments)
    except Exception:  # noqa: BLE001 - the regex families above still ran on the raw text
        return []
    start = here = cwd
    out: list[str] = []
    for seg in _segs(cmd.replace("${HOME}", "~").replace("$HOME", "~"), _segments):
        while seg and (_ASSIGN_RE.match(seg[0]) or _program(seg[0]) in _WRAPPERS):
            seg = seg[1:]
            while seg and seg[0].startswith("-"):  # sudo -n, env -i
                seg = seg[1:]
        if not seg:
            continue
        head, args = _program(seg[0]), seg[1:]
        if head in _DIR_COMMANDS:
            d = _dir_arg(args)
            here = _join(here, d) if d else here
            continue
        body = _payload(head, args) if depth < 2 else None
        if body:  # bash -c '…', eval, cmd /c, powershell -c
            out += _walk_targets(body if isinstance(body, str) else " ".join(body), here, depth + 1)
            continue
        words = [a for a in args if not a.startswith("-")]
        base, found = here, []
        if head in _ANY_ARG:
            found += words
        if head in _COPY_LIKE and len(words) >= 2:
            dest = words[-1]
            if dest.endswith(("/", "\\")) or os.path.isdir(_join(here, dest)):
                found += [dest.rstrip("/\\") + "/" + os.path.basename(w.rstrip("/\\")) for w in words[:-1]]
        if head == "dd":
            found += [a[3:] for a in args if a.startswith("of=")]
        if head == "git":
            i = 0
            while i < len(args) and args[i].startswith("-"):
                opt = args[i].split("=", 1)[0]
                if opt in _GIT_OPTS_WITH_VALUE and "=" not in args[i]:
                    if opt == "-C" and i + 1 < len(args):
                        base = _join(base, args[i + 1])
                    i += 2
                else:
                    i += 1
            if i < len(args) and args[i].lower() in _GIT_PATH_SUBS:
                found += [a for a in args[i + 1:] if not a.startswith("-")]
        if here != start:  # the regex families, now that the directory is known
            found += _shell_targets(" ".join(seg))
        for w in found:
            out.append(_join(base, w))
            if base != start and not os.path.isabs(os.path.expanduser(w)):
                out.append(_join(start, w))  # a `cd` inside `( … )` does not last: judge both readings
    return out


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
    cd = plat.claude_dir().as_posix().rstrip("/")
    if fold(p.rstrip("/")) == fold(cd):  # the config dir itself as a mv/rm/restore target (R3)
        return ".claude/"
    if fold(p).startswith(fold(cd) + "/"):
        rel = p[len(cd) + 1:].rstrip("/")
        if fold(rel) == "hooks":  # hooks/ itself: every gate goes with it (R3)
            return "hooks/"
        if fold(rel) in {fold(w) for w in _WIRING} or _GATE_RE.match(rel):
            return rel.rsplit("/", 1)[-1]
    return None


def prompt_escapes(transcript_path, base: str) -> bool:
    """The last human prompt names the file (`.claude/settings…` path for the settings files; the basename
    for `.claude.json`, `model-policy.json` and the gate wiring) or a permission-rule phrase. Bare
    "settings"/"permission" no longer escape (live r3: "the user settings page"), nor does a bare
    `settings.json` (VS Code's `.vscode/` file)."""
    b = base.lower()
    if b.endswith("/"):  # the config dir or hooks/ moved or removed: no prompt wording opens that (R3)
        return False
    by_name = b in (".claude.json", "model-policy.json") or b in _WIRING_BASENAMES or b.endswith("-gate.py")
    names = (b,) if by_name else (".claude/settings", ".claude\\settings")
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
    cwd = str(payload.get("cwd") or "")
    if tool in SHELL_TOOLS:
        cmd = str(ti.get("command") or "")
        paths = _shell_targets(cmd) + _walk_targets(cmd, cwd)
    elif tool in WRITE_TOOLS or tool == "NotebookEdit":
        paths = [_target(ti)]
    else:
        paths = []
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
    # 2026-10-31 (owner): never auto-deny. A remote/app session runs with CLAUDE_CODE_SESSION_ATTENDED=0
    # while the owner is present, and subagents work for an attended parent; the ask goes to Claude
    # Code's own permission flow (prompt, SDK host callback, or the session's permission mode).
    unattended = _unattended(payload)
    decision = "ask"
    reason += " Approve only if you asked for this change."
    if unattended:
        reason += f" ({unattended} context: the session's permission mode decides.)"
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

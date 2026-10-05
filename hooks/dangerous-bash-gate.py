#!/usr/bin/env python3
"""dangerous-bash-gate.py — PreToolUse hook on Bash.

Detects and blocks destructive shell commands before they execute.
Hard-blocks on first detection. Second attempt within same conversation is allowed
(logged as an intentional override — the model has been forced to acknowledge danger).

Patterns blocked:
  - rm -rf  (anywhere; suppressed only when every rm -rf segment targets temp paths)
  - payloads of `bash|sh -c '…'`, `eval '…'` and quoted SQL/JS given to a DB client
    (psql, mysql, sqlite3, mongosh, …) are scanned too
  - MongoDB dropDatabase() / db.<coll>.drop(); dd of=/dev/…; mkfs; curl|wget … | sh
  - rm --no-preserve-root (root filesystem destruction)
  - rm $VAR / rm ${VAR} (shell variable expansion bypass)
  - git push --force / git push -f
  - git reset --hard
  - DROP TABLE, DROP DATABASE, TRUNCATE TABLE (case-insensitive)
  - kubectl delete ns / namespace
  - aws s3 rm --recursive
  - chmod -R 777
  - find <path> -delete

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0 (never crash session).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# State directory (shared with other hooks)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")


# ---------------------------------------------------------------------------
# Destructive command pattern registry
# Each entry: (compiled_regex, human_name, safe_suppression_fn | None)
# safe_suppression_fn(command) -> bool: return True to SKIP the block
# ---------------------------------------------------------------------------

_RMRF_RE = re.compile(
    # Combined flags: rm -rf, rm -fr, rm -rfv, rm -vfr, etc.
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*(?:\s|$)"
    r"|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*(?:\s|$)"
    # Separated flags: rm -r -f, rm -f -r
    r"|\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+-[a-zA-Z]*r[a-zA-Z]*"
    r"|\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f[a-zA-Z]*"
    # Long flags
    r"|\brm\s+--recursive\s+--force|\brm\s+--force\s+--recursive",
    re.IGNORECASE,
)
_SAFE_RM_PREFIXES = ("/tmp/", "/var/tmp/", "$TMPDIR", "${TMPDIR}", "$(mktemp")
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\n|\|")
_REDIRECT_RE = re.compile(r"\d*&?>>?\s*&?\S+|<\s*\S+")


def _rm_is_safe(cmd: str) -> bool:
    """Suppress the rm -rf block only when EVERY rm -rf segment deletes nothing but
    temp paths (test scaffolding). Judged per segment and per argument, so
    `rm -rf /tmp/x && rm -rf ~/src` or `rm -rf /tmp/../etc` is not safe."""
    for seg in _SEGMENT_SPLIT.split(cmd):
        if not _RMRF_RE.search(seg):
            continue
        seg = _REDIRECT_RE.sub(" ", seg)  # `2>/dev/null`, `>/dev/null 2>&1` are not targets
        m = re.search(r"\brm\b(.*)", seg)
        args = [a.strip("'\"") for a in (m.group(1).split() if m else []) if not a.startswith("-")]
        if not args or not all(a.startswith(_SAFE_RM_PREFIXES) and ".." not in a for a in args):
            return False
    return True


def _git_push_force_is_safe(cmd: str) -> bool:
    """Suppress for pushes to known backup remote branch patterns."""
    # Allow: git push origin backup/* or git push origin archive/*
    safe_patterns = (
        r"backup/",
        r"archive/",
        r"bak/",
        r"wip/",
    )
    for pat in safe_patterns:
        if pat in cmd:
            return True
    return False


# `git` plus any global options before the subcommand (`-C <dir>`, `-c k=v`,
# `--git-dir <x>`, `--no-pager`, `--work-tree=<x>`), so `git -C repo reset --hard` is
# still caught. `\w` first keeps each token unambiguous (no exponential backtracking).
_GIT = (r"\bgit\s+(?:(?:-[Cc]\s+\S+|--(?:git-dir|work-tree|namespace|config-env)\s+\S+"
        r"|--?\w[\w.-]*(?:=\S+)?)\s+)*")

DANGEROUS_PATTERNS: list[tuple[re.Pattern, str, object]] = [
    (
        _RMRF_RE,
        "rm -rf (recursive force delete)",
        _rm_is_safe,
    ),
    (
        re.compile(
            # `--force(?![-\w])`: --force-with-lease / --force-if-includes refuse to
            # overwrite work the pusher has not seen; only a bare --force does (WP3)
            _GIT + r"push\s+(?:\S+\s+)*(?:--force(?![-\w])|-f\b)",
            re.IGNORECASE,
        ),
        "git push --force (overwrites remote history)",
        _git_push_force_is_safe,
    ),
    (
        re.compile(_GIT + r"reset\s+--hard\b", re.IGNORECASE),
        "git reset --hard (discards uncommitted changes)",
        None,
    ),
    (
        re.compile(
            r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)\b",
            re.IGNORECASE,
        ),
        "SQL DROP statement (irreversible schema destruction)",
        None,
    ),
    (
        re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE),
        "TRUNCATE TABLE (deletes all rows, may not be transactional)",
        None,
    ),
    (
        re.compile(
            r"\bkubectl\s+delete\s+(?:ns|namespace)\b",
            re.IGNORECASE,
        ),
        "kubectl delete namespace (destroys all resources in namespace)",
        None,
    ),
    (
        re.compile(
            r"\baws\s+s3\s+(?:rm|delete)\b.*--recursive\b"
            r"|\baws\s+s3\s+(?:rm|delete)\b.*--recursive",
            re.IGNORECASE,
        ),
        "aws s3 rm --recursive (bulk S3 object deletion)",
        None,
    ),
    (
        re.compile(r"\bchmod\s+-R\s+777\b", re.IGNORECASE),
        "chmod -R 777 (world-writable recursive permission change)",
        None,
    ),
    (
        re.compile(
            r"\bfind\b.{0,80}\s-delete\b",
            re.IGNORECASE,
        ),
        "find -delete (recursive file deletion via find)",
        None,
    ),
    (
        re.compile(r"\brm\s+.*--no-preserve-root\b", re.IGNORECASE),
        "rm --no-preserve-root (root filesystem destruction)",
        None,  # no safe-suppression
    ),
    (
        re.compile(r"\brm\s+(?:\$\w+|\$\{[^}]+\})", re.IGNORECASE),
        "rm with shell variable expansion (potential bypass)",
        None,
    ),
    (
        re.compile(r"\bdropDatabase\s*\(|\bdb\.\S*\.drop\s*\(\s*\)", re.IGNORECASE),
        "MongoDB drop (irreversible collection/database destruction)",
        None,
    ),
    (
        re.compile(r"\bdd\b[^\n;&|]*\bof=/dev/(?!null\b|zero\b|stdout\b|stderr\b)", re.IGNORECASE),
        "dd onto a device (overwrites a disk)",
        None,
    ),
    (
        re.compile(r"(?:^|[;&|(]\s*|\bsudo\s+)mkfs(?:\.\w+)?\b", re.IGNORECASE),
        "mkfs (formats a filesystem)",
        None,
    ),
    (
        re.compile(r"\b(?:curl|wget)\b[^\n;&]*\|\s*(?:sudo\s+)?(?:ba|z|da|k)?sh\b", re.IGNORECASE),
        "download piped to a shell (runs unreviewed remote code)",
        None,
    ),
]

# Quoted payloads that DO execute: `bash -c '…'`, `eval '…'`, SQL/JS handed to a DB
# client. Quote-stripping hid them; the head is matched on the stripped text so a
# commit message that merely mentions psql never qualifies.
_PAYLOAD_HEAD_RE = re.compile(  # standalone words only: not `eval-harness`, `db/mongo`
    r"(?<![\w./-])(?:(?:ba|z|da|k)?sh\s+(?:-[a-zA-Z]+\s+)*-c|eval|psql|mysql|mariadb|sqlite3|sqlcmd"
    r"|clickhouse-client|mongosh|mongo)(?![\w./-])", re.IGNORECASE)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.dangerous-bash.json"


def _load_state(cid: str) -> dict:
    if not cid:
        return {"overridden_commands": []}
    p = _state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"overridden_commands": []}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(cid).write_text(json.dumps(state), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Detection + output
# ---------------------------------------------------------------------------

def _fingerprint(cmd: str, pattern_name: str) -> str:
    """Stable fingerprint of the FULL whitespace-normalised command + pattern name.

    The old 80-char prefix let `cd /long/path && rm -rf A` pre-authorise
    `cd /long/path && rm -rf B` (A03-B14). Only the identical command re-run
    matches now."""
    import hashlib
    norm = re.sub(r"\s+", " ", cmd.strip())
    return f"{pattern_name}::{hashlib.sha256(norm.encode('utf-8', 'replace')).hexdigest()[:24]}"


_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)
_DQUOTE_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_SQUOTE_RE = re.compile(r"'[^']*'")


def _strip_quoted(cmd: str) -> str:
    """Remove heredoc bodies and single/double-quoted strings before matching, so
    `git commit -m "switch from rm -rf to trash"` or a heredoc that merely
    mentions `DROP TABLE` is not a destructive command."""
    try:
        s = _HEREDOC_RE.sub(" ", cmd)
        s = _DQUOTE_RE.sub('""', s)
        s = _SQUOTE_RE.sub("''", s)
        return s
    except Exception:
        return cmd


def _emit_deny(pattern_name: str, cmd: str) -> None:
    reason = (
        f"DANGEROUS COMMAND BLOCKED: `{pattern_name}` detected.\n"
        f"Command: {cmd[:200]}\n\n"
        "This command is irreversible or high-risk. To proceed intentionally:\n"
        "  - Re-run the exact same command in this conversation (override accepted once).\n"
        "  - The second attempt will be allowed through and logged.\n\n"
        "If this was unintentional, choose a safer alternative."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _emit_allow_with_log(pattern_name: str, cmd: str) -> None:
    """Second attempt — allow but emit advisory context."""
    # Cannot emit additionalContext + permissionDecision in same response.
    # Just emit empty (allow) — the prior deny message already warned the model.
    print("{}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    try:
        tool = str(payload.get("tool_name") or payload.get("tool") or "")
        if tool not in ("Bash", "Shell"):
            print("{}")
            return 0

        ti = payload.get("tool_input") or {}
        cmd = str(ti.get("command") or "")
        if not cmd.strip():
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        state = _load_state(cid)
        overridden = set(state.get("overridden_commands") or [])

        scan = _strip_quoted(cmd)
        if _PAYLOAD_HEAD_RE.search(scan):
            bodies = [q[1:-1] for q in _DQUOTE_RE.findall(cmd) + _SQUOTE_RE.findall(cmd)]
            scan = scan + "\n" + "\n".join(bodies)
        for pattern, name, suppress_fn in DANGEROUS_PATTERNS:
            if not pattern.search(scan):
                continue

            # Check safe-suppression predicate
            if suppress_fn is not None and suppress_fn(cmd):
                continue

            # Generate fingerprint for override tracking
            fp = _fingerprint(cmd, name)

            if fp in overridden:
                # Second attempt — allow through, log in stderr
                print(
                    f"[dangerous-bash-gate] Override accepted for '{name}': {cmd[:100]}",
                    file=sys.stderr,
                )
                _emit_allow_with_log(name, cmd)
                return 0

            # First occurrence — block and record in state
            overridden.add(fp)
            state["overridden_commands"] = list(overridden)
            _save_state(cid, state)

            _emit_deny(name, cmd)
            return 0

        # No dangerous pattern found
        print("{}")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[dangerous-bash-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

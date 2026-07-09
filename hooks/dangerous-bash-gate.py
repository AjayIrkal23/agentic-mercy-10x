#!/usr/bin/env python3
"""dangerous-bash-gate.py — PreToolUse hook on Bash.

Detects and blocks destructive shell commands before they execute.
Hard-blocks on first detection. Second attempt within same conversation is allowed
(logged as an intentional override — the model has been forced to acknowledge danger).

Patterns blocked:
  - rm -rf  (anywhere; smart-suppressed for /tmp/ paths)
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
STATE_DIR = SCRIPT_DIR / ".state"


# ---------------------------------------------------------------------------
# Destructive command pattern registry
# Each entry: (compiled_regex, human_name, safe_suppression_fn | None)
# safe_suppression_fn(command) -> bool: return True to SKIP the block
# ---------------------------------------------------------------------------

def _rm_is_safe(cmd: str) -> bool:
    """Suppress rm -rf block for /tmp/ paths — frequent in test scaffolding."""
    # Allow: rm -rf /tmp/... or rm -rf /var/tmp/...
    safe_prefixes = (r"/tmp/", r"/var/tmp/", r"$TMPDIR", r"$(mktemp")
    for prefix in safe_prefixes:
        # Pattern: rm [flags] /tmp/ or rm [flags] "$TMPDIR"
        if re.search(
            r"\brm\s+(?:-[a-zA-Z]+\s+)*" + re.escape(prefix), cmd
        ):
            return True
    return False


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


DANGEROUS_PATTERNS: list[tuple[re.Pattern, str, object]] = [
    (
        re.compile(
            # Combined flags: rm -rf, rm -fr, rm -rfv, rm -vfr, etc.
            r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*(?:\s|$)"
            r"|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*(?:\s|$)"
            # Separated flags: rm -r -f, rm -f -r
            r"|\brm\s+-[a-zA-Z]*f[a-zA-Z]*\s+-[a-zA-Z]*r[a-zA-Z]*"
            r"|\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+-[a-zA-Z]*f[a-zA-Z]*"
            # Long flags
            r"|\brm\s+--recursive\s+--force|\brm\s+--force\s+--recursive",
            re.IGNORECASE,
        ),
        "rm -rf (recursive force delete)",
        _rm_is_safe,
    ),
    (
        re.compile(
            r"\bgit\s+push\s+(?:\S+\s+)*--force\b"
            r"|\bgit\s+push\s+(?:\S+\s+)*-f\b"
            r"|\bgit\s+push\s+-f\s+",
            re.IGNORECASE,
        ),
        "git push --force (overwrites remote history)",
        _git_push_force_is_safe,
    ),
    (
        re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
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
]


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
    """Create a stable fingerprint for this command+pattern combo for ack tracking."""
    # Use the first 80 chars of the command + pattern name — enough to distinguish
    # "rm -rf src/" from "rm -rf tests/" without storing entire commands
    key_part = re.sub(r"\s+", " ", cmd.strip())[:80]
    return f"{pattern_name}::{key_part}"


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

        for pattern, name, suppress_fn in DANGEROUS_PATTERNS:
            if not pattern.search(cmd):
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

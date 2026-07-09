#!/usr/bin/env python3
"""bash-write-gate.py — PreToolUse hook on Bash.

Detects heredoc/tee writes to source files that bypass Write|Edit|MultiEdit hooks.
Patterns detected:
  - cat <<'EOF' > target.ts  (heredoc redirect)
  - cat <<EOF > target.py    (heredoc redirect, unquoted)
  - tee target.go            (tee write)
  - echo 'content' > target.js  (echo redirect to source file)

Action: followup_message (advisory) by default. Set BASH_WRITE_GATE_HARD_BLOCK=1
to enable permissionDecision:"deny" mode (may cause false positives on migration scripts).

Blast-radius check: same logic as gateguard-write-gate.py — counts import references.
THRESHOLD=5 importers triggers the warning.

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0 (never crash session).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
THRESHOLD = 5  # same as gateguard-write-gate.py
HARD_BLOCK = os.environ.get("BASH_WRITE_GATE_HARD_BLOCK", "").strip() == "1"

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"

# Source file extensions to monitor. Lock files, configs, docs are excluded.
SOURCE_EXTENSIONS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
    ".sh", ".bash",
})

# Stems too common to bother checking blast radius for
_SHORT_STEMS = frozenset({
    "app", "main", "index", "types", "routes",
    "gorm", "db", "api", "lib", "util",
})


# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

# Heredoc redirect: cat <<'EOF' > path or cat << EOF > path (with optional space)
_HEREDOC_RE = re.compile(
    r"""cat\s+<<\s*['"]?(\w+)['"]?\s+>\s*(?P<path>[^\s;|&>]+)""",
    re.IGNORECASE,
)

# Tee write: tee path (possibly with -a for append)
_TEE_RE = re.compile(
    r"""\btee\s+(?:-a\s+)?(?P<path>[^\s;|&>]+)""",
    re.IGNORECASE,
)

# Echo redirect: echo ... > path or printf ... > path
_ECHO_RE = re.compile(
    r"""(?:echo|printf)\s+.{0,200}?>\s*(?P<path>[^\s;|&]+)""",
    re.IGNORECASE | re.DOTALL,
)


def _extract_target_paths(cmd: str) -> list[str]:
    """Extract target file paths from bash write patterns."""
    paths: list[str] = []

    for m in _HEREDOC_RE.finditer(cmd):
        p = m.group("path").strip("'\"")
        if p:
            paths.append(p)

    for m in _TEE_RE.finditer(cmd):
        p = m.group("path").strip("'\"")
        if p and p not in ("/dev/null", "/dev/stderr", "/dev/stdout"):
            paths.append(p)

    for m in _ECHO_RE.finditer(cmd):
        p = m.group("path").strip("'\"")
        if p and p not in ("/dev/null", "/dev/stderr", "/dev/stdout"):
            paths.append(p)

    return [p for p in paths if p.strip()]


def _is_source_file(file_path: str) -> bool:
    """Return True if the target path is a source file we care about."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in SOURCE_EXTENSIONS


def _stem_is_short(file_path: str) -> bool:
    stem = os.path.splitext(os.path.basename(file_path))[0].lower()
    return stem in _SHORT_STEMS or len(stem) < 6


# ---------------------------------------------------------------------------
# Blast-radius check (mirrors gateguard-write-gate.py)
# ---------------------------------------------------------------------------

def _find_project_root(file_path: str) -> str:
    current = os.path.dirname(os.path.abspath(file_path))
    for _ in range(15):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.dirname(os.path.abspath(file_path))


def _count_references(file_path: str) -> int:
    """Count how many other files import/reference this file."""
    if _stem_is_short(file_path):
        return 0

    basename = os.path.basename(file_path)
    stem = os.path.splitext(basename)[0]
    search_root = _find_project_root(file_path)
    ext = os.path.splitext(basename)[1].lower()

    try:
        if ext == ".go":
            pattern = f'".*/{stem}"|package {stem}'
            result = subprocess.run(
                ["grep", "-rl", "--include=*.go",
                 "--exclude-dir=node_modules", "--exclude-dir=.git",
                 "--exclude-dir=dist", "--exclude-dir=build",
                 "-E", pattern, search_root],
                capture_output=True, text=True, timeout=8,
            )
        else:
            pattern = "from.*/" + stem + "|require.*/" + stem
            result = subprocess.run(
                ["grep", "-rl",
                 "--include=*.ts", "--include=*.tsx",
                 "--include=*.js", "--include=*.jsx",
                 "--exclude-dir=node_modules", "--exclude-dir=.git",
                 "--exclude-dir=dist", "--exclude-dir=build",
                 "-E", pattern, search_root],
                capture_output=True, text=True, timeout=8,
            )
        if result.returncode != 0:
            return 0
        files = [
            f for f in result.stdout.strip().split("\n")
            if f and os.path.abspath(f) != os.path.abspath(file_path)
        ]
        return len(files)
    except (subprocess.TimeoutExpired, OSError):
        return 0


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _emit_deny(file_path: str, ref_count: int, cmd_preview: str) -> None:
    basename = os.path.basename(file_path)
    reason = (
        f"BASH-WRITE-GATE: Heredoc/tee write to `{basename}` (blast radius: {ref_count} importers) "
        f"detected in Bash command. This bypasses the Write hook safety checks.\n"
        f"Command preview: {cmd_preview[:120]}\n\n"
        f"Verify:\n"
        f"  1. All {ref_count} importing files still compile after this change.\n"
        f"  2. No exported signatures changed unintentionally.\n"
        f"Re-run after verification — this block will not repeat for `{basename}` in this conversation."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _emit_advisory(file_path: str, ref_count: int, cmd_preview: str) -> None:
    basename = os.path.basename(file_path)
    msg = (
        f"⚠️ BASH-WRITE-GATE: Heredoc/tee write to `{basename}` detected "
        f"(blast radius: {ref_count} importer(s)). This bypasses Write hook safety checks.\n"
        f"Command: {cmd_preview[:120]}\n"
        f"Verify all {ref_count} importing files still compile after this change."
    )
    print(json.dumps({"followup_message": msg}))


def _emit_injection_advisory(file_path: str, cmd_preview: str) -> None:
    """Warn about bash writes to .planning/ (injection vector)."""
    basename = os.path.basename(file_path)
    msg = (
        f"⚠️ BASH-WRITE-GATE: Bash command writes to .planning/{basename} — "
        "review content for embedded instructions that could manipulate agent context."
    )
    print(json.dumps({"followup_message": msg}))


# ---------------------------------------------------------------------------
# Conversation state (for blast-radius dedup, same as gateguard)
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _load_state(cid: str) -> dict:
    if not cid:
        return {}
    p = STATE_DIR / f"{_safe_cid(cid)}.bash-write-gate.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(cid: str, state: dict) -> None:
    if not cid:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / f"{_safe_cid(cid)}.bash-write-gate.json").write_text(
            json.dumps(state), encoding="utf-8"
        )
    except OSError:
        pass


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

        # Extract potential target paths from the command
        target_paths = _extract_target_paths(cmd)
        if not target_paths:
            print("{}")
            return 0

        # Filter to source files only
        source_targets = [p for p in target_paths if _is_source_file(p)]
        if not source_targets:
            # Check for .planning/ writes (injection advisory, regardless of extension)
            planning_targets = [p for p in target_paths if ".planning/" in p or ".planning\\" in p]
            if planning_targets:
                _emit_injection_advisory(planning_targets[0], cmd[:200])
                return 0
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        state = _load_state(cid)
        acked = set(state.get("acked_files") or [])

        for file_path in source_targets:
            abs_path = os.path.abspath(file_path)

            # Already acked — skip
            if abs_path in acked:
                continue

            # Blast-radius check
            ref_cache = state.get("ref_cache") or {}
            if abs_path in ref_cache:
                ref_count = int(ref_cache[abs_path])
            else:
                ref_count = _count_references(file_path)
                ref_cache[abs_path] = ref_count
                state["ref_cache"] = ref_cache

            if ref_count >= THRESHOLD:
                acked.add(abs_path)
                state["acked_files"] = list(acked)
                _save_state(cid, state)

                cmd_preview = cmd[:200]
                if HARD_BLOCK:
                    _emit_deny(file_path, ref_count, cmd_preview)
                else:
                    _emit_advisory(file_path, ref_count, cmd_preview)
                return 0

            if ref_count == 0:
                # New file (zero importers) — emit lower-severity advisory
                # without denying, so new-module heredoc writes are flagged.
                acked.add(abs_path)
                state["acked_files"] = list(acked)
                _save_state(cid, state)

                basename = os.path.basename(file_path)
                msg = (
                    f"BASH-WRITE-GATE (advisory): New source file `{basename}` written "
                    f"via Bash heredoc/tee — this bypasses Write hook safety checks. "
                    f"Consider verifying with `incremental-implementation` skill if this "
                    f"is a non-trivial new module."
                )
                print(json.dumps({"followup_message": msg}))
                return 0

        # No high-blast-radius source targets found
        _save_state(cid, state)  # persist ref_cache updates
        print("{}")
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[bash-write-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

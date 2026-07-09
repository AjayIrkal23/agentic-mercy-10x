#!/usr/bin/env python3
"""
codex-capture.py — PostToolUse hook (Write|Edit|MultiEdit)

Fires after "significant" file writes and injects an advisory to update CODEX.md
if the change represents a new project pattern or architectural decision.

Significance criteria:
  - The file is newly created (tool_name == "Write")
  - OR the diff/content has >= SIGNIFICANT_LINE_THRESHOLD lines affected
  - AND the file path matches HIGH_SIGNAL_PATTERNS

Rate limiting: Only fires ONCE per conversation (per session) using a filesystem
sentinel at STATE_DIR/{safe_cid}.codex-capture.flag. Sentinels expire naturally
via the 24h STATE_DIR TTL cleanup.

Always exits 0 — advisory only, never blocks.
Output: JSON {hookSpecificOutput: {hookEventName: "PostToolUse", followup_message: "..."}}
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

SIGNIFICANT_LINE_THRESHOLD = 30  # lines in content/diff to count as "significant"

# State dir shared with other hooks (24h TTL cleanup keeps sentinels fresh)
STATE_DIR = Path(__file__).resolve().parent / ".state"

# Glob-style prefix patterns for high-signal files (matched against file_path)
HIGH_SIGNAL_PATTERNS = [
    # Frontend state and API
    "src/api/",
    "src/store/",
    "src/redux/",
    "src/lib/",
    "src/services/",
    "src/hooks/",
    "src/context/",
    # Backend service layer
    "server/src/services/",
    "server/src/models/",
    "server/src/routes/",
    "server/src/utils/",
    "server/src/middleware/",
    "server/src/jobs/",
    # Mobile
    "sitesync-mobile-native/app/",
    "sitesync-mobile-native/src/",
]

# File extensions that carry architecture signal
HIGH_SIGNAL_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx",
    ".go", ".py",
}

# Paths to always skip (lock files, generated output, docs that are not decisions)
SKIP_PATTERNS = [
    "node_modules/",
    "dist/",
    ".expo/",
    "graphify-out/",
    "bun.lockb",
    "package-lock.json",
    ".tsbuildinfo",
]

CODEX_FILENAME = "CODEX.md"

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_high_signal_path(file_path: str) -> bool:
    """Return True if the file_path matches a high-signal pattern."""
    if not file_path:
        return False
    # Normalise: strip leading slashes for relative matching
    norm = file_path.lstrip("/")
    # Check skip patterns first
    for skip in SKIP_PATTERNS:
        if skip in norm:
            return False
    # Check extension
    _, ext = os.path.splitext(norm)
    if ext.lower() not in HIGH_SIGNAL_EXTENSIONS:
        return False
    # Check signal patterns (relative path suffix match)
    for pattern in HIGH_SIGNAL_PATTERNS:
        if pattern in norm:
            return True
    return False


def count_content_lines(tool_input: dict, tool_name: str) -> int:
    """Estimate number of lines affected by this write/edit."""
    if tool_name == "Write":
        content = tool_input.get("content", "")
        return content.count("\n") + 1
    elif tool_name in ("Edit", "MultiEdit"):
        # For Edit: count lines in new_string
        new_str = tool_input.get("new_string", "")
        edits = tool_input.get("edits", [])
        if edits:  # MultiEdit
            return sum(
                e.get("new_string", "").count("\n") + 1
                for e in edits
            )
        return new_str.count("\n") + 1
    return 0


def find_codex(workspace: str) -> str | None:
    """Return CODEX.md path if it exists in workspace root or immediate parent."""
    if not workspace:
        return None
    candidates = [
        os.path.join(workspace, CODEX_FILENAME),
        # fallback: one level up (for monorepo sub-package sessions)
        os.path.join(os.path.dirname(workspace.rstrip("/")), CODEX_FILENAME),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _sentinel_path(cid: str) -> Path:
    """Return the per-session sentinel path for this conversation."""
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", cid) if cid else "unknown"
    return STATE_DIR / f"{safe}.codex-capture.flag"


def emit_advisory(file_path: str, tool_name: str, codex_path: str) -> None:
    """Write the advisory JSON to stdout."""
    rel = os.path.basename(file_path) if file_path else "this file"
    codex_rel = os.path.relpath(codex_path) if codex_path else CODEX_FILENAME

    if codex_path:
        msg = (
            f"CODEX CAPTURE: You just made a significant change to `{rel}`. "
            f"If this introduces a new pattern, decision, or \"do not use X\" rule, "
            f"append it to `{codex_rel}` under the appropriate section "
            f"(Architecture Decisions / Patterns We Use / Things We Tried / Known Fragile Areas). "
            f"Format: `- [YYYY-MM-DD] <what>. <why>. <what was rejected>.`"
        )
    else:
        msg = (
            f"CODEX CAPTURE: Significant change to `{rel}`. "
            f"No CODEX.md found in project root. "
            f"Consider creating one from `~/.claude/templates/CODEX.md.template` "
            f"and recording this decision."
        )

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "followup_message": msg,
        }
    }
    sys.stdout.write(json.dumps(output))
    sys.stdout.flush()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)
        payload = json.loads(raw)
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path", "") or tool_input.get("path", "")

    # Skip if not a high-signal path
    if not is_high_signal_path(file_path):
        sys.exit(0)

    # Skip very small edits — only flag "significant" changes
    is_new_file = tool_name == "Write"
    line_count = count_content_lines(tool_input, tool_name)

    if not is_new_file and line_count < SIGNIFICANT_LINE_THRESHOLD:
        sys.exit(0)

    # ── Per-session rate limiting ──────────────────────────────────────────────
    # Only fire once per conversation. Sentinel file persists until the 24h TTL
    # cleanup removes it, so a new conversation (different cid) always fires.
    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    sentinel = _sentinel_path(cid)
    if sentinel.exists():
        # Already fired this session — stay silent
        print("{}")
        sys.exit(0)

    # Find CODEX.md relative to session workspace
    workspace = payload.get("cwd", "") or os.getcwd()
    codex_path = find_codex(workspace)

    # Emit advisory
    emit_advisory(file_path, tool_name, codex_path)

    # Write sentinel so subsequent writes in this session are suppressed
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(
            json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "path": file_path}),
            encoding="utf-8",
        )
    except Exception:
        pass  # sentinel write failure is non-fatal — advisory was already emitted

    sys.exit(0)


if __name__ == "__main__":
    main()

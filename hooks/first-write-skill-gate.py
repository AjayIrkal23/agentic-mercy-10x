#!/usr/bin/env python3
"""first-write-skill-gate.py — PreToolUse hook on Write|Edit|MultiEdit.

Blocks the first code write in a session if mandatory skills have not been
surfaced via fullstack-skills-reminder.py. After one block, subsequent writes
pass through (skills_gate_cleared flag written to state).

Reads: {cid}.fullstack.json (frontend_start_sent, backend_start_sent, fullstack_start_sent)
Writes: {cid}.fullstack.json (skills_gate_cleared flag ONLY — never modifies other keys)

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"

# File extensions that are "code files" (not config/lock/docs/assets)
CODE_EXTENSIONS = frozenset({
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
})

# Path segments that indicate non-code files safe to skip
SKIP_SEGMENTS = (
    ".planning/",
    "node_modules/",
    ".claude/hooks/",    # hooks are infra, not application code
    ".claude/hooks/",
    ".state/",
    "server_docs/",
    "frontend_docs/",
    "docs/",
    "migrations/",       # migration files are procedural, not orientation-requiring
    ".env",
    ".config.",
    "package.json",
    "tsconfig",
    "eslint",
    "jest.config",
    "vite.config",
    "tailwind.config",
    "postcss.config",
)

# Top-3 mandatory skills to surface per surface type
# These are the highest-priority cross-cutting skills from agent-lifecycle-routing.md
MANDATORY_FE_SKILLS = [
    "frontend-standards-always-follow",
    "project-reference-linkage",
    "architect-system-design",
]
MANDATORY_BE_SKILLS = [
    "backend-standards-always-follow",
    "project-reference-linkage",
    "architect-system-design",
]
MANDATORY_CROSS_SKILLS = [
    "project-reference-linkage",
    "dead-code-and-change-audit",
    "codebase-start-point-guide",
]


# ---------------------------------------------------------------------------
# File classification helpers
# ---------------------------------------------------------------------------

def _is_code_file(file_path: str) -> bool:
    """Return True if the target is a source code file (not config/lock/docs)."""
    if not file_path:
        return False
    fp_lower = file_path.replace("\\", "/").lower()

    # Skip known non-code paths
    for seg in SKIP_SEGMENTS:
        if seg.lower() in fp_lower:
            return False

    ext = os.path.splitext(file_path)[1].lower()
    return ext in CODE_EXTENSIONS


def _infer_surface(file_path: str) -> str:
    """Infer 'frontend', 'backend', or 'unknown' from path."""
    fp = file_path.replace("\\", "/").lower()

    fe_segments = (
        "client/", "frontend/", "apps/web", "/src/components/",
        "/src/pages/", "/src/hooks/", "/src/store/", "/src/app/",
        ".tsx", ".jsx",
    )
    be_segments = (
        "server/", "backend/", "api/", "internal/", "cmd/",
        "pkg/", ".go",
    )

    fe_score = sum(1 for s in fe_segments if s in fp)
    be_score = sum(1 for s in be_segments if s in fp)

    if fe_score > be_score:
        return "frontend"
    if be_score > fe_score:
        return "backend"
    return "unknown"


# ---------------------------------------------------------------------------
# State helpers (integrates with fullstack-skills-reminder.py state)
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _fullstack_state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.fullstack.json"


def _load_fullstack_state(cid: str) -> dict:
    p = _fullstack_state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _set_gate_cleared(cid: str, state: dict) -> None:
    """Write skills_gate_cleared to the EXISTING state file without overwriting other keys."""
    state["skills_gate_cleared"] = True
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _fullstack_state_path(cid).write_text(
            json.dumps(state, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[first-write-skill-gate] Could not write state: {exc}", file=sys.stderr)


def _skills_have_been_surfaced(state: dict) -> bool:
    """Return True if mandatory skills were already surfaced this conversation."""
    return bool(
        state.get("frontend_start_sent")
        or state.get("backend_start_sent")
        or state.get("fullstack_start_sent")
        or state.get("skills_gate_cleared")  # gate already fired once
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _skill_path(name: str) -> str:
    """Return the path hint for a skill (for display in the deny message)."""
    p = Path.home() / ".claude" / "skills" / name / "SKILL.md"
    if p.exists():
        return str(p)
    # Fallback to cursor skills path
    p2 = Path.home() / ".claude" / "skills" / name / "SKILL.md"
    return str(p2) if p2.exists() else name


def _emit_deny(file_path: str, surface: str) -> None:
    if surface == "frontend":
        skills = MANDATORY_FE_SKILLS
        surface_label = "frontend"
    elif surface == "backend":
        skills = MANDATORY_BE_SKILLS
        surface_label = "backend"
    else:
        skills = MANDATORY_CROSS_SKILLS
        surface_label = "this"

    skill_lines = "\n".join(
        f"  - Invoke `/{s}` or read {_skill_path(s)}"
        for s in skills
    )

    reason = (
        f"SKILL GATE: First code write to `{os.path.basename(file_path)}` blocked — "
        f"mandatory {surface_label} skills not yet surfaced this session.\n\n"
        f"Invoke these skills BEFORE writing code:\n"
        f"{skill_lines}\n\n"
        f"After skills are read, your next write to any file will proceed automatically.\n"
        f"(This gate fires at most once per conversation.)"
    )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


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
        if tool not in ("Write", "Edit", "MultiEdit", "StrReplace"):
            print("{}")
            return 0

        ti = payload.get("tool_input") or {}

        # Extract file path from tool input (handles Write, Edit, MultiEdit)
        file_path = (
            ti.get("file_path")
            or ti.get("path")
            or ti.get("target_file")
            or ""
        )
        if isinstance(file_path, list):
            # MultiEdit may pass an array — check first element
            file_path = str(file_path[0]) if file_path else ""
        file_path = str(file_path)

        # Only gate source code files
        if not _is_code_file(file_path):
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        if not cid:
            # No conversation ID — can't track state, allow through
            print("{}")
            return 0

        # Load state from fullstack-skills-reminder
        state = _load_fullstack_state(cid)

        # Check if skills were already surfaced
        if _skills_have_been_surfaced(state):
            print("{}")
            return 0

        # Skills not surfaced — emit deny and mark gate as cleared
        # (mark BEFORE emitting so subsequent writes in same conversation pass)
        _set_gate_cleared(cid, state)

        surface = _infer_surface(file_path)
        _emit_deny(file_path, surface)
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[first-write-skill-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""first-write-skill-gate.py — PreToolUse hook on Write|Edit|MultiEdit.

On the first code write of a surface (frontend / backend / unknown) with NO evidence
that a baseline skill was loaded, it ALLOWS the write and adds context naming the
baseline SKILL.md files to Read (absolute paths). It never denies: the old one-shot
deny cost a turn and the retry passed without loading anything (audit 2026-10-05,
e2e S1-S4/S6/S8). The Stop-time invoke-suite-gate stays the enforcer. Evidence (any
one suffices):
  * fullstack-skills-reminder state flags (frontend/backend/fullstack_start_sent), or
  * a baseline skill in `.telemetry/{cid}.skill-invocations.jsonl` (Skill tool or a
    `via: read` record written by the tracker).

Once per session per surface. Code-file classification is `lib.code_files.is_code_file`,
so scratchpad, /tmp, hooks, docs and config writes are never touched (A14 §3).

Reads:  {cid}.fullstack.json, .telemetry/{cid}.skill-invocations.jsonl
Writes: {cid}.fullstack.json (skills_hint_surfaces list ONLY)

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")
TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or SCRIPT_DIR / ".telemetry")
SKILLS_DIR = SCRIPT_DIR.parent / "skills"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
try:
    from lib.code_files import is_code_file  # noqa: E402
except Exception:  # pragma: no cover - fail-open (nothing is a code file → allow)
    def is_code_file(path):  # type: ignore
        return False
from lib.platform import locked_update  # noqa: E402
try:
    from lib.skill_aliases import canonical as _canonical  # noqa: E402  (WP-3 lib)
except Exception:  # pragma: no cover
    def _canonical(name):  # type: ignore
        return name

# The two canonical baseline skills per surface — named in the hint.
BASELINE = {
    "frontend": ["frontend-standards-always-follow", "project-reference-linkage"],
    "backend": ["backend-standards-always-follow", "project-reference-linkage"],
    "unknown": ["codebase-intel-first", "project-reference-linkage"],
}
# Any of these having been loaded counts as evidence for every surface.
BASELINE_ANY = frozenset(
    {s for skills in BASELINE.values() for s in skills}
    | {"architect-system-design", "dead-code-and-change-audit",
       "codebase-start-point-guide", "project-structure-map"}
)


def _infer_surface(file_path: str) -> str:
    fp = file_path.replace("\\", "/").lower()
    fe = ("client/", "frontend/", "apps/web", "/src/components/", "/src/pages/",
          "/src/hooks/", "/src/store/", "/src/app/", ".tsx", ".jsx")
    be = ("server/", "backend/", "api/", "internal/", "cmd/", "pkg/", ".go")
    fe_score = sum(1 for s in fe if s in fp)
    be_score = sum(1 for s in be if s in fp)
    if fe_score > be_score:
        return "frontend"
    if be_score > fe_score:
        return "backend"
    return "unknown"


# ---------------------------------------------------------------------------
# State / evidence
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


def _mark_hinted(cid: str, state: dict, surface: str) -> None:
    """fullstack-skills-reminder writes the same file: locked RMW of the one key
    this hook owns (audit J-01)."""
    def add(fresh: dict) -> dict:
        fresh["skills_hint_surfaces"] = sorted(
            set(fresh.get("skills_hint_surfaces") or []) | {surface})
        return fresh
    state.update(locked_update(_fullstack_state_path(cid), add))


def _baseline_skill_loaded(cid: str) -> bool:
    """True when the skill-invocation telemetry shows any baseline skill loaded."""
    p = TELEMETRY_DIR / f"{_safe_cid(cid)}.skill-invocations.jsonl"
    if not p.is_file():
        return False
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            name = str(r.get("skill") or "").split(":", 1)[-1].strip().lower()
            if name and _canonical(name) in BASELINE_ANY:
                return True
    except OSError:
        pass
    return False


def _evidence(cid: str, state: dict) -> bool:
    return bool(
        state.get("frontend_start_sent")
        or state.get("backend_start_sent")
        or state.get("fullstack_start_sent")
        or _baseline_skill_loaded(cid)
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _skill_path(name: str) -> str:
    """Absolute SKILL.md path (the file the model should Read)."""
    return str(SKILLS_DIR / name / "SKILL.md")


def _emit_hint(file_path: str, surface: str) -> None:
    """Allow the write and name the skills to read. A deny here only cost a turn: the
    retry passed without any skill loaded (e2e S2-S4), so the Stop-time suite gate
    stays the enforcer and this link only points the way."""
    skills = BASELINE[surface]
    label = surface if surface != "unknown" else "this"
    lines = "\n".join(f"  - Read {_skill_path(s)}" for s in skills)
    msg = (
        f"SKILL CHECK: first {label} code write (`{os.path.basename(file_path)}`) with no "
        f"baseline skill loaded this session. Before your next code write:\n{lines}\n"
        f"The Stop-time suite gate checks that these were read."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": msg,
    }}))


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
        file_path = ti.get("file_path") or ti.get("path") or ti.get("target_file") or ""
        if isinstance(file_path, list):
            file_path = str(file_path[0]) if file_path else ""
        file_path = str(file_path)

        if not is_code_file(file_path):
            print("{}")
            return 0

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        if not cid:
            print("{}")
            return 0

        state = _load_fullstack_state(cid)
        surface = _infer_surface(file_path)
        hinted = state.get("skills_hint_surfaces") or []
        if surface in hinted or _evidence(cid, state):
            print("{}")
            return 0

        # No evidence — allow, name the skills once per session per surface.
        _mark_hinted(cid, state, surface)
        _emit_hint(file_path, surface)
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[first-write-skill-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

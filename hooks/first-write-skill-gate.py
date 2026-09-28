#!/usr/bin/env python3
"""first-write-skill-gate.py — PreToolUse hook on Write|Edit|MultiEdit.

Blocks the FIRST code write in a session only when there is NO evidence that the
baseline skills for the touched surface were loaded. Evidence (any one suffices):
  * fullstack-skills-reminder state flags (frontend/backend/fullstack_start_sent), or
  * a baseline skill in `.telemetry/{cid}.skill-invocations.jsonl` (Skill tool or a
    `via: read` record written by the tracker).

One-shot: after one deny the gate marks itself cleared and never fires again in the
conversation. Code-file classification is `lib.code_files.is_code_file`, so
scratchpad, /tmp, hooks, docs and config writes are never gated (A14 §3).

Reads:  {cid}.fullstack.json, .telemetry/{cid}.skill-invocations.jsonl
Writes: {cid}.fullstack.json (skills_gate_cleared flag ONLY)

Python 3.8+ stdlib only. Exit 0 always. Exception → stderr, exit 0.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR / ".state"
TELEMETRY_DIR = SCRIPT_DIR / ".telemetry"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
try:
    from lib.code_files import is_code_file  # noqa: E402
except Exception:  # pragma: no cover - fail-open (nothing is a code file → allow)
    def is_code_file(path):  # type: ignore
        return False
try:
    from lib.skill_aliases import canonical as _canonical  # noqa: E402  (WP-3 lib)
except Exception:  # pragma: no cover
    def _canonical(name):  # type: ignore
        return name

# The two canonical baseline skills per surface — named in the deny message.
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


def _set_gate_cleared(cid: str, state: dict) -> None:
    state["skills_gate_cleared"] = True
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _fullstack_state_path(cid).write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"[first-write-skill-gate] Could not write state: {exc}", file=sys.stderr)


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
        or state.get("skills_gate_cleared")  # gate already fired once
        or _baseline_skill_loaded(cid)
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _skill_path(name: str) -> str:
    p = Path.home() / ".claude" / "skills" / name / "SKILL.md"
    return str(p) if p.exists() else name


def _emit_deny(file_path: str, surface: str) -> None:
    skills = BASELINE[surface]
    label = surface if surface != "unknown" else "this"
    skill_lines = "\n".join(f"  - Invoke `/{s}` or read {_skill_path(s)}" for s in skills)
    reason = (
        f"SKILL GATE: First code write to `{os.path.basename(file_path)}` blocked — "
        f"no baseline {label} skill has been loaded this session.\n\n"
        f"Invoke these skills BEFORE writing code:\n{skill_lines}\n\n"
        f"Your next write will proceed (this gate fires at most once per conversation)."
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
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
        if _evidence(cid, state):
            print("{}")
            return 0

        # No evidence — deny once and mark cleared so the retry passes.
        _set_gate_cleared(cid, state)
        _emit_deny(file_path, _infer_surface(file_path))
        return 0

    except Exception as exc:  # noqa: BLE001
        print(f"[first-write-skill-gate] Error: {exc}", file=sys.stderr)
        print("{}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

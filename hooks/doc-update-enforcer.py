#!/usr/bin/env python3
"""PostToolUse(Write) hook: After every code write, remind about doc updates.

Fixes applied (2026-05-16 audit):
- C2: Store full relative paths, not basenames (collision fix)
- H1: Only count doc writes when code files already exist (order fix)
- H2: Per-surface doc tracking (be/fe/linkages separate)
- H5: Track .py files
- M4: Aligned doc segments with fullstack-skills-reminder
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

CODE_EXTENSIONS = {".go", ".ts", ".tsx", ".js", ".jsx", ".py"}
CODE_PATH_SEGMENTS = [
    "/src/", "/internal/", "/cmd/", "/pkg/", "/controllers/",
    "/services/", "/schemas/", "/models/", "/routes/", "/middleware/",
    "/components/", "/hooks/", "/api/", "/store/", "/types/", "/lib/",
    "/utils/", "/helpers/",
]

DOC_PATH_SEGMENTS = [
    "server_docs/", "frontend_docs/", "PROJECT_LINKAGES",
    "AGENTS.md", "/docs/",
]

BE_DOC_SEGMENTS = ["server_docs/"]
FE_DOC_SEGMENTS = ["frontend_docs/"]
LINKAGE_SEGMENTS = ["PROJECT_LINKAGES"]
REPO_MARKERS = ["/UDP_PLATFORM/", "/GO_UDP/"]


def _load_doc_config() -> None:
    """Override the doc-marker constants from doc-enforcement.config.json (P4-T4).

    Defaults above are byte-identical to the historic GO_UDP literals, so a
    missing/partial config changes nothing. Never raises.
    """
    global DOC_PATH_SEGMENTS, BE_DOC_SEGMENTS, FE_DOC_SEGMENTS, LINKAGE_SEGMENTS, REPO_MARKERS
    try:
        import json as _json
        cfg_path = SCRIPT_DIR / "doc-enforcement.config.json"
        if not cfg_path.is_file():
            return
        cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
        DOC_PATH_SEGMENTS = cfg.get("doc_path_segments", DOC_PATH_SEGMENTS)
        BE_DOC_SEGMENTS = cfg.get("backend_doc_segments", BE_DOC_SEGMENTS)
        FE_DOC_SEGMENTS = cfg.get("frontend_doc_segments", FE_DOC_SEGMENTS)
        LINKAGE_SEGMENTS = cfg.get("linkage_segments", LINKAGE_SEGMENTS)
        REPO_MARKERS = cfg.get("repo_markers", REPO_MARKERS)
    except Exception:  # noqa: BLE001 - config errors must never break the hook
        pass


_load_doc_config()

SKIP_PATTERNS = [
    ".claude/", "node_modules/", ".git/", "dist/", "build/",
    "__pycache__", ".state/", "graphify-out/", "plan-",
]

BE_INDICATORS = ["/server/", "/internal/", "/cmd/", "/pkg/", ".go"]
FE_INDICATORS = ["/client/", "/src/", ".tsx", ".ts", ".jsx", ".js"]


def _state_path(cid: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    d = SCRIPT_DIR / ".state"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{safe}.doc-enforcer.json"


def _load_state(cid: str) -> dict:
    p = _state_path(cid)
    if not p.is_file():
        return {
            "code_files": [],
            "be_touched": False, "fe_touched": False,
            "be_docs_written": False, "fe_docs_written": False,
            "linkages_written": False,
            "reminder_sent_for_backend": False,
            "reminder_sent_for_frontend": False,
        }
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "code_files": [],
            "be_touched": False, "fe_touched": False,
            "be_docs_written": False, "fe_docs_written": False,
            "linkages_written": False,
            "reminder_sent_for_backend": False,
            "reminder_sent_for_frontend": False,
        }


def _save_state(cid: str, state: dict) -> None:
    _state_path(cid).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _is_code_file(fp: str) -> bool:
    norm = fp.replace("\\", "/")
    ext = os.path.splitext(fp)[1].lower()
    if ext in CODE_EXTENSIONS:
        return True
    return any(seg in norm for seg in CODE_PATH_SEGMENTS)


def _is_doc_file(fp: str) -> bool:
    norm = fp.replace("\\", "/")
    return any(seg in norm for seg in DOC_PATH_SEGMENTS)


def _should_skip(fp: str) -> bool:
    return any(skip in fp for skip in SKIP_PATTERNS)


def _dir_of(fp: str) -> str:
    norm = fp.replace("\\", "/")
    return norm.rsplit("/", 1)[0] if "/" in norm else ""


def _is_dox_doc(fp: str) -> bool:
    """A dox-tree documentation file (per-folder CLAUDE.md or its AGENTS.md pointer)."""
    base = fp.replace("\\", "/").rsplit("/", 1)[-1]
    return base in ("CLAUDE.md", "AGENTS.md")


def _relative_path(fp: str) -> str:
    norm = fp.replace("\\", "/")
    for m in REPO_MARKERS:
        idx = norm.find(m)
        if idx >= 0:
            return norm[idx + 1:]
    parts = norm.rstrip("/").split("/")
    return "/".join(parts[-3:]) if len(parts) >= 3 else norm


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        print("{}")
        return 0

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ""

    if not fp or _should_skip(fp):
        print("{}")
        return 0

    norm = fp.replace("\\", "/")
    is_code = _is_code_file(fp)
    is_doc = _is_doc_file(fp)

    state = _load_state(cid)

    # dox tree: record CLAUDE.md / AGENTS.md updates (the Phase-7 "update local docs"
    # signal the Stop gate reads). Matched before the GO_UDP doc/code branches.
    if _is_dox_doc(fp):
        state["claude_md_written"] = True
        d = _dir_of(norm)
        dirs = state.get("claude_md_dirs", [])
        if d and d not in dirs:
            dirs.append(d)
            state["claude_md_dirs"] = dirs
        _save_state(cid, state)
        print("{}")
        return 0

    if is_doc:
        code_files = state.get("code_files", [])
        if code_files:
            if any(seg in norm for seg in BE_DOC_SEGMENTS):
                state["be_docs_written"] = True
            if any(seg in norm for seg in FE_DOC_SEGMENTS):
                state["fe_docs_written"] = True
            if any(seg in norm for seg in LINKAGE_SEGMENTS):
                state["linkages_written"] = True
        _save_state(cid, state)
        print("{}")
        return 0

    if not is_code:
        print("{}")
        return 0

    rel_path = _relative_path(fp)
    code_files = state.get("code_files", [])
    if rel_path not in code_files:
        code_files.append(rel_path)
    state["code_files"] = code_files

    # dox tree: remember the directory of each touched code file so the Stop gate
    # can require its local CLAUDE.md to be updated (Phase 7).
    cdir = _dir_of(norm)
    code_dirs = state.get("code_dirs", [])
    if cdir and cdir not in code_dirs:
        code_dirs.append(cdir)
        state["code_dirs"] = code_dirs

    if any(seg in norm for seg in BE_INDICATORS):
        state["be_touched"] = True
    if any(seg in norm for seg in FE_INDICATORS):
        state["fe_touched"] = True

    _save_state(cid, state)

    # Build the pending doc-update list across every surface (be / fe / linkages / dox),
    # each debounced once per session so the reminder doesn't repeat on every write.
    pending: list[str] = []

    current_be = state.get("be_touched") and not state.get("be_docs_written")
    current_fe = state.get("fe_touched") and not state.get("fe_docs_written")
    if current_be and not state.get("reminder_sent_for_backend"):
        pending.append("server_docs/")
        state["reminder_sent_for_backend"] = True
    if current_fe and not state.get("reminder_sent_for_frontend"):
        pending.append("frontend_docs/")
        state["reminder_sent_for_frontend"] = True
    if (state.get("be_touched") or state.get("fe_touched")) and not state.get("linkages_written"):
        if not state.get("reminder_sent_for_linkages"):
            pending.append("PROJECT_LINKAGES.md")
            state["reminder_sent_for_linkages"] = True

    # dox tree (Phase 7): touched code dirs whose local CLAUDE.md hasn't been updated.
    touched_dirs = state.get("code_dirs", [])
    documented = set(state.get("claude_md_dirs", []))
    pending_dox = [d for d in touched_dirs if d not in documented]
    if pending_dox and not state.get("reminder_sent_for_dox"):
        state["reminder_sent_for_dox"] = True
        shown = pending_dox[:6]
        extra = len(pending_dox) - len(shown)
        tail = f" (+{extra} more)" if extra else ""
        pending.append(
            "dox CLAUDE.md in " + ", ".join(f"{d}/" for d in shown) + tail
        )

    _save_state(cid, state)

    if not pending:
        print("{}")
        return 0

    n = len(code_files)
    msg = (
        f"[DOC-UPDATE ENFORCER — MANDATORY] {n} code file(s) modified. "
        f"Before completing, update: {'; '.join(pending)}. "
        f"The Stop gate BLOCKS completion until docs — including the dox CLAUDE.md for "
        f"changed dir(s) — are updated. Phase 7 in mandatory-skill-protocol is non-negotiable."
    )

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": msg}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

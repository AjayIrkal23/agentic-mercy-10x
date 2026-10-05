#!/usr/bin/env python3
"""PreToolUse(Bash) hook: Block git commit when documentation hasn't been updated.

Scoped to the repo being committed (``git -C dir`` and ``cd dir &&`` honoured; the
command is tokenised, so ``git commit-tree`` and an ``--amend`` inside a ``-m``
message are not commits/amends — audit 2026-10-05 B1-10):

  * any repo with ``server_docs/`` or ``frontend_docs/`` at its root: the files going
    into the commit (staged, plus working-tree changes for ``-a`` or a same-line
    ``git add``) decide. Backend code (``server/``, ``backend/``, ``api/``) needs a
    ``server_docs/`` change, frontend code (``src/``, ``client/``, ...) a
    ``frontend_docs/`` change, and ``PROJECT_LINKAGES.md`` when the repo has one
    (``commit_docs_check.py``).
  * ``repo_markers`` repos (GO_UDP layout): the session state doc-update-enforcer.py
    writes, as before.

Committing ~/.claude after touching another repo is never blocked (A03-B12).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from commit_docs_check import git_commits, missing_docs, repo_root
from tool_compat import is_shell_tool, tool_name

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")

GIT_COMMIT_RE = re.compile(r"\bgit\b.*\bcommit\b", re.DOTALL)

# Doc labels shown in the deny message — byte-identical GO_UDP defaults,
# overridable via doc-enforcement.config.json (P4-T4). Never raises.
_BE_LABEL, _FE_LABEL, _LINK_LABEL = "server_docs/", "frontend_docs/", "PROJECT_LINKAGES.md"
_REPO_MARKERS = ["/UDP_PLATFORM/", "/GO_UDP/"]
try:
    _cfg = json.loads((SCRIPT_DIR / "doc-enforcement.config.json").read_text(encoding="utf-8"))
    _BE_LABEL = _cfg.get("backend_doc_label", _BE_LABEL)
    _FE_LABEL = _cfg.get("frontend_doc_label", _FE_LABEL)
    _LINK_LABEL = _cfg.get("linkage_label", _LINK_LABEL)
    _REPO_MARKERS = list(_cfg.get("repo_markers", _REPO_MARKERS))
except Exception:  # noqa: BLE001
    pass


def _norm_dir(directory: str) -> str:
    """Resolved, "/"-separated, trailing slash (marker matching)."""
    try:
        directory = str(Path(os.path.expanduser(directory)).resolve())
    except Exception:
        pass
    return directory.replace("\\", "/") + "/"


def _in_marker_repo(directory: str) -> bool:
    return any(m in directory for m in _REPO_MARKERS)


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.doc-enforcer.json"


def _load_state(cid: str) -> dict | None:
    p = _state_path(cid)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _deny(reason: str) -> None:
    # PreToolUse requires the hookSpecificOutput wrapper (matches the working
    # dox-write-gate.py); the bare top-level form is recognized by no event and
    # silently fails open.
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _allow() -> None:
    print("{}")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        _allow()
        return 0

    if not is_shell_tool(tool_name(payload)):
        _allow()
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not GIT_COMMIT_RE.search(command):
        _allow()  # cheap pre-filter; the tokenised parse below decides
        return 0

    base = str(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    commits, add_seen = git_commits(command, base)
    # amends were committed once already; `--amend` must be a real argument (B1-10)
    commits = [(args, d) for args, d in commits if "--amend" not in args]
    if not commits:
        _allow()
        return 0

    for args, directory in commits:
        root = repo_root(directory)
        if root and not _in_marker_repo(root.replace("\\", "/") + "/"):
            missing = missing_docs(root, args, add_seen)
            if missing:
                _deny("BLOCKED: Cannot commit without documentation updates.\n\n"
                      f"Repo {root} keeps doc trees, and this commit changes code without them.\n"
                      "Missing documentation:\n" + "\n".join(missing)
                      + "\n\nUpdate and stage these before committing (rules/02-lifecycle.md Phase 7).")
                return 0

    # Marker repos (GO_UDP layout) keep the session-state check below.
    if not any(_in_marker_repo(_norm_dir(d)) for _, d in commits):
        _allow()
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        _allow()
        return 0

    state = _load_state(cid)
    if state is None:
        # No state tracked → no code files written this session → allow
        _allow()
        return 0

    be_touched = state.get("be_touched", False)
    fe_touched = state.get("fe_touched", False)
    be_docs_written = state.get("be_docs_written", False)
    fe_docs_written = state.get("fe_docs_written", False)
    linkages_written = state.get("linkages_written", False)
    code_files: list[str] = state.get("code_files", [])

    if not be_touched and not fe_touched:
        # No code surface touched → allow
        _allow()
        return 0

    missing: list[str] = []
    if be_touched and not be_docs_written:
        missing.append(f"- {_BE_LABEL} (backend code changed)")
    if fe_touched and not fe_docs_written:
        missing.append(f"- {_FE_LABEL} (frontend code changed)")
    if (be_touched or fe_touched) and not linkages_written:
        missing.append(f"- {_LINK_LABEL}")

    if not missing:
        _allow()
        return 0

    surfaces: list[str] = []
    if be_touched:
        be_count = sum(1 for f in code_files if "/server/" in f or ".go" in f)
        surfaces.append(f"backend ({be_count} file(s))")
    if fe_touched:
        fe_count = sum(1 for f in code_files if "/client/" in f or "/src/" in f)
        surfaces.append(f"frontend ({fe_count} file(s))")

    reason = (
        "BLOCKED: Cannot commit without documentation updates.\n\n"
        f"Code surfaces touched: {', '.join(surfaces)}\n"
        "Missing documentation:\n"
        + "\n".join(missing)
        + "\n\nUpdate these files before committing. "
        "Phase 7 (documentation update) is mandatory."
    )

    _deny(reason)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Fail open — never crash the hook and block all commits
        print("{}")
        raise SystemExit(0)

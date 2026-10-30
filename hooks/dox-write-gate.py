#!/usr/bin/env python3
"""dox-write-gate.py — PreToolUse hook on Write|Edit|MultiEdit.

Root gate for the dox CLAUDE.md documentation tree: a CODE file is about to be
written in a GIT repo (HOME-guarded, never `$HOME`, never `exemptRepos`) that has
NO root CLAUDE.md → deny once per repo per session (fingerprint = the repo root,
B1-19); the retry and every later code write in that repo pass.

ALWAYS ALLOWED (never gated): writes to docs/scaffold — *.md, CLAUDE.md, AGENTS.md,
CODEX.md, and anything under a .claude/ directory. This keeps scaffolding (and the
override itself) always possible, and keeps hooks/skills/rules editable.

AD-HOC NOTE ADVISORY (once per session, allow): a ``Write`` of NOTES/TODO/SCRATCH/TEMP/
DRAFT/BRAINSTORM/SPIKE/DEBUG/WIP ``.md|.txt`` inside a repo but outside docs/, .claude/,
notes/, wiki/, adr/ gets one line pointing at the reply or docs/ (ECC doc-file-warning).
State: lib.gate_state (locked write).

Fails OPEN. Exit 0 always. Python 3.8+ stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or SCRIPT_DIR / ".state")
CONFIG_PATH = SCRIPT_DIR / "dox-write-gate.config.json"
ROOT_DOC = "CLAUDE.md"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
try:
    from lib.code_files import git_root, is_home  # noqa: E402
except Exception:  # pragma: no cover - fail-open (no root → allow)
    def git_root(path):  # type: ignore
        return None

    def is_home(root):  # type: ignore
        return True
try:
    from tool_compat import WRITE_TOOLS as _WRITE_TOOLS  # noqa: E402
except Exception:  # noqa: BLE001
    _WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "StrReplace"})
try:
    from lib import gate_state as _gs  # noqa: E402
    from lib import code_files as _cf  # noqa: E402
except Exception:  # noqa: BLE001
    _gs = _cf = None

# ECC doc-file-warning name list: loose report files at the repo root or in code dirs.
_ADHOC = re.compile(r"^(NOTES|TODO|SCRATCH|TEMP|DRAFT|BRAINSTORM|SPIKE|DEBUG|WIP)\.(md|txt)$")
_ADHOC_OK_DIRS = (".claude", "notes", "wiki", "adr")

DEFAULTS = {
    "enabled": True,
    "exemptRepos": [],
    "documentAllDirs": False,
    "docFilenames": ["CLAUDE.md", "AGENTS.md", "CODEX.md"],
    "codeExtensions": [
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".py", ".go", ".rs", ".java", ".kt",
        ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".swift", ".scala",
    ],
}


# --------------------------------------------------------------------------- #
# Config / state
# --------------------------------------------------------------------------- #
def _config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        if CONFIG_PATH.is_file():
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update(user)
    except Exception:
        pass
    return cfg


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.dox-gate.json"


def _adhoc_note(file_path: str, tool: str, cid: str, state: dict) -> "str | None":
    """Once per session: a ``Write`` of NOTES.md / TODO.md / … outside docs/, .claude/,
    notes/, wiki/, adr/ inside a git repo gets an advisory (allow, never deny)."""
    if tool != "Write" or not cid or _cf is None or state.get("adhoc_hinted"):
        return None
    norm = file_path.replace("\\", "/")
    base = os.path.basename(norm)
    if not _ADHOC.match(base):
        return None
    abs_path = _abspath(file_path)
    root = _git_root(abs_path)
    if root is None:
        return None
    try:
        rel = "/" + os.path.relpath(str(abs_path), str(root)).replace("\\", "/")
    except ValueError:
        return None
    if rel.startswith("/..") or _cf.is_skipped(rel, extra_dirs=_ADHOC_OK_DIRS):
        return None
    state["adhoc_hinted"] = True
    _save_state(cid, state)
    return (f"Ad-hoc note file `{base}`: CLAUDE.md asks for findings in the reply or in docs/, "
            "not loose report files. Allowed; move it if it is not meant to stay.")


def _load_state(cid: str) -> dict:
    if not cid:
        return {"overridden": [], "asked_dirs": []}
    p = _state_path(cid)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"overridden": [], "asked_dirs": []}


def _save_state(cid: str, state: dict) -> None:
    if not cid or _gs is None:
        return
    _gs.save_json(_state_path(cid), state)


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #
def _allow() -> int:
    print("{}")
    return 0


def _deny(reason: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    return 0


def _git_root(start: Path) -> "Path | None":
    """HOME-guarded: `$HOME` and non-repos → None (lib.code_files)."""
    root = git_root(start)
    if root is None or is_home(root):
        return None
    return root


def _abspath(file_path: str) -> Path:
    p = Path(file_path)
    if p.is_absolute():
        return p
    base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return (Path(base) / p).resolve()


def _is_doc_or_scaffold(file_path: str, cfg: dict) -> bool:
    fp = file_path.replace("\\", "/")
    if ".claude" in fp.split("/"):          # anything under a .claude/ dir
        return True
    base = os.path.basename(fp)
    if base in set(cfg.get("docFilenames") or DEFAULTS["docFilenames"]):
        return True
    return os.path.splitext(fp)[1].lower() == ".md"


def _is_code_file(file_path: str, cfg: dict) -> bool:
    exts = set(cfg.get("codeExtensions") or DEFAULTS["codeExtensions"])
    return os.path.splitext(file_path)[1].lower() in exts


def _is_exempt(root: Path, cfg: dict) -> bool:
    try:
        rp = root.resolve()
        for ex in cfg.get("exemptRepos") or []:
            try:
                if rp == Path(str(ex)).expanduser().resolve():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return _allow()

    try:
        cfg = _config()
        if not cfg.get("enabled", True):
            return _allow()

        tool = str(payload.get("tool_name") or payload.get("tool") or "")
        ti = payload.get("tool_input") or {}

        # Resolve the write target (Write/Edit only — the Bash redirect path was
        # retired 2026-09-27: 5,318 runs, 0 denies).
        if tool in _WRITE_TOOLS:
            file_path = (
                ti.get("file_path") or ti.get("path") or ti.get("target_file") or ""
            )
            if isinstance(file_path, list):
                file_path = str(file_path[0]) if file_path else ""
            file_path = str(file_path)
        else:
            return _allow()

        if not file_path:
            return _allow()

        cid = str(payload.get("conversation_id") or payload.get("session_id") or "")
        adhoc = cid and _ADHOC.match(os.path.basename(file_path.replace("\\", "/")))
        note = _adhoc_note(file_path, tool, cid, _load_state(cid)) if adhoc else None
        if note:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "additionalContext": note}}))
            return 0

        # Doc/scaffold writes are ALWAYS allowed (escape valve).
        if _is_doc_or_scaffold(file_path, cfg):
            return _allow()
        # Only gate real code files.
        if not _is_code_file(file_path, cfg):
            return _allow()

        abs_path = _abspath(file_path)
        root = _git_root(abs_path)
        if root is None or _is_exempt(root, cfg):
            return _allow()  # not a git repo (or exempt) — out of scope

        state = _load_state(cid)
        root_doc = root / ROOT_DOC

        # ---- Root gate: hard deny when no root CLAUDE.md exists ----
        if not root_doc.exists():
            # once per REPO, not per file (B1-19): N files in an undocumented repo
            # used to cost N denies
            fp = f"missing-root::{root}"
            if fp in set(state.get("overridden") or []):
                return _allow()  # override accepted (any later code write in this repo)
            ov = list(state.get("overridden") or [])
            ov.append(fp)
            state["overridden"] = ov
            _save_state(cid, state)
            return _deny(
                f"DOX GATE: no root `CLAUDE.md` in `{root.name}` "
                f"({root}). Code work is blocked until the dox tree's root exists.\n\n"
                "Fix (preferred): invoke the `dox-doc-tree` skill and scaffold the root "
                "(+ the area you're touching). Writing `CLAUDE.md`/`*.md` is always allowed.\n"
                "Override: re-issue the edit to proceed anyway; the gate then stays quiet "
                "for this repo for the rest of the session (logged)."
            )

        return _allow()

    except Exception as exc:  # noqa: BLE001
        print(f"[dox-write-gate] Error: {exc}", file=sys.stderr)
        return _allow()


if __name__ == "__main__":
    raise SystemExit(main())

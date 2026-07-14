#!/usr/bin/env python3
"""jdocmunch-enforce.py — steer doc-SET reads to the jDocMunch section index.

The docs twin of jcodemunch-enforce.py, but ADVISORY (fail-open, never blocks):
when the agent is about to read a whole documentation file (.md/.rst/.adoc/…) in
a repo whose docs jDocMunch has indexed (``~/.doc-index/local/<repo>.json``),
remind it to use ``mcp__jdocmunch__search_sections`` / ``get_toc`` /
``get_section`` instead — the section index returns the relevant slice instead of
a whole file.

Never fires on source code, single small configs, or the dox ``CLAUDE.md`` tree
(those are read directly by design / gated by jcodemunch-enforce). Throttled per
session like graphify-enforce.

Mode (sys.argv[1]):
  pre-tool-use    → PreToolUse on Read + lean-ctx ctx_read
"""

import json
import os
import sys
from pathlib import Path

HOME = Path.home()
INDEX_DIR = HOME / ".doc-index" / "local"
HOOKS_DIR = Path(__file__).parent
CONFIG_PATH = HOOKS_DIR / "jdocmunch-enforce.config.json"
STATE_DIR = HOOKS_DIR / ".state"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {
            "doc_exts": [".md", ".mdx", ".markdown", ".rst", ".adoc"],
            "skip_names": ["CLAUDE.md", "AGENTS.md"],
            "max_reminders_per_session": 6,
        }


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / f"{cid}.jdocmunch-enforce.json"


def _load_state(cid: str) -> dict:
    try:
        return json.loads(_state_path(cid).read_text())
    except Exception:
        return {"remind_count": 0}


def _save_state(cid: str, state: dict):
    try:
        _state_path(cid).write_text(json.dumps(state))
    except Exception:
        pass


def _repo_root() -> Path:
    cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        from lib.repo_context import git_root
        r = git_root(cwd)
        if r is not None:
            return r
    except Exception:
        pass
    return Path(cwd)


def _has_doc_index(root: Path) -> bool:
    """True iff jDocMunch has an index for this repo (~/.doc-index/local/<name>.json).

    jDocMunch names the index after the repo folder; check the raw name and the
    sanitized name (shared helper) so a folder with spaces still resolves."""
    name = root.name
    cands = [f"{name}.json"]
    try:
        from lib.repo_context import sanitize_name
        s = sanitize_name(name)
        if s and s != name:
            cands.append(f"{s}.json")
    except Exception:
        pass
    return any((INDEX_DIR / c).is_file() for c in cands)


def _target_path(tool_input: dict) -> str | None:
    for key in ("file_path", "path", "notebook_path"):
        v = tool_input.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _is_doc_file(path: str, cfg: dict) -> bool:
    p = Path(path)
    if p.name in set(cfg.get("skip_names", [])):
        return False
    return p.suffix.lower() in set(cfg.get("doc_exts", []))


def _under(target: str, root: Path) -> bool:
    """True iff the doc being read is INSIDE the open repo (its section index applies)."""
    try:
        Path(target).resolve().relative_to(Path(root).resolve())
        return True
    except Exception:
        return False


def _reminder(root: Path) -> str:
    return (
        "[jDocMunch] This repo's docs are indexed at the section level — prefer "
        "them over whole-file reads:\n"
        '    mcp__jdocmunch__search_sections "<q>" · get_toc · get_section <id> · '
        "get_document_outline <file>\n"
        "  The section index returns the relevant slice; reading a whole doc file "
        "burns tokens. (Single small config/env reads: keep using your normal read.)"
    )


def handle_pre_tool_use():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        json.dump({"continue": True}, sys.stdout)
        return

    tool_input = hook_input.get("tool_input", {}) or {}
    session_id = hook_input.get("session_id", "unknown")
    cfg = _load_config()

    target = _target_path(tool_input)
    if not target or not _is_doc_file(target, cfg):
        json.dump({"continue": True}, sys.stdout)
        return

    root = _repo_root()
    if not _under(target, root) or not _has_doc_index(root):
        json.dump({"continue": True}, sys.stdout)
        return

    state = _load_state(session_id)
    if state.get("remind_count", 0) >= cfg.get("max_reminders_per_session", 6):
        json.dump({"continue": True}, sys.stdout)
        return

    state["remind_count"] = state.get("remind_count", 0) + 1
    _save_state(session_id, state)
    json.dump({"continue": True, "additionalContext": _reminder(root)}, sys.stdout)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "pre-tool-use":
            handle_pre_tool_use()
        else:
            json.dump({"continue": True}, sys.stdout)
    except Exception:
        json.dump({"continue": True}, sys.stdout)

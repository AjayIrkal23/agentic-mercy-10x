#!/usr/bin/env python3
"""jdocmunch-enforce.py — steer doc-SET reads to the jDocMunch section index.

The docs twin of jcodemunch-enforce.py: one deny per agent per user turn (naming
``search_sections(repo="local/<name>", …)``), then advisory; fail-open (B-05). It
needs the link type ``gate`` in dispatch.config.json (an advisory link drops a deny):
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
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HOME = Path.home()
INDEX_DIR = HOME / ".doc-index" / "local"
HOOKS_DIR = Path(__file__).resolve().parent
CONFIG_PATH = HOOKS_DIR / "jdocmunch-enforce.config.json"
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or HOOKS_DIR / ".state")
if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))
try:
    from lib import gate_state as _gs
except Exception:  # noqa: BLE001 - fail open: no state helper → no throttle state
    _gs = None


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "doc_exts": [".md", ".mdx", ".markdown", ".rst", ".adoc"],
            "skip_names": ["CLAUDE.md", "AGENTS.md", "CODEX.md"],
            "min_bytes": 6000,
            "max_reminders_per_session": 6,
        }


def _noop():
    json.dump({}, sys.stdout)


def _small_or_sliced(target: str, tool_input: dict, cfg: dict) -> bool:
    """A sliced read or a doc under min_bytes gains nothing from the index."""
    if tool_input.get("offset") or tool_input.get("limit"):
        return True
    try:
        return Path(target).stat().st_size < int(cfg.get("min_bytes", 2000))
    except (OSError, ValueError):
        return False


def _state_path(cid: str) -> Path:
    safe = _gs.safe_cid(cid) if _gs is not None else cid
    return STATE_DIR / f"{safe}.jdocmunch-enforce.json"


def _load_state(cid: str) -> dict:
    try:
        return json.loads(_state_path(cid).read_text(encoding="utf-8"))
    except Exception:
        return {"remind_count": 0}


def _save_state(cid: str, state: dict):
    if _gs is not None:
        _gs.save_json(_state_path(cid), state)


def _repo_root(payload: dict | None = None) -> Path:
    """Payload ``cwd`` first: ``CLAUDE_PROJECT_DIR`` is the launch dir (often ``~``)."""
    cwd = (payload or {}).get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    try:
        from lib.repo_context import git_root
        r = git_root(cwd)
        if r is not None:
            return r
    except Exception:
        pass
    return Path(cwd)


def _doc_repo_id(root: Path) -> str:
    """jDocMunch's id for this repo's doc index (``local/<name>``), "" when none.

    jDocMunch names the index after the repo folder; check the raw name and the
    sanitized name (shared helper) so a folder with spaces still resolves, then the
    ``<name>-<sha8>`` form index-lifecycle uses for a same-named second checkout."""
    name = root.name
    cands = [name]
    try:
        from lib.repo_context import sanitize_name
        s = sanitize_name(name)
        if s and s != name:
            cands.append(s)
    except Exception:
        pass
    for c in cands:
        if (INDEX_DIR / f"{c}.json").is_file():
            return f"local/{c}"
    try:
        from lib import mcp_ids
        return mcp_ids.ids(str(root))["jdocmunch"]
    except Exception:
        return ""


def _cid(payload: dict) -> str:
    """Per agent (B-03): a subagent's payload carries the parent's session id + agent_id."""
    sid, aid = str(payload.get("session_id") or "unknown"), str(payload.get("agent_id") or "")
    return f"{sid}.{aid}" if aid else sid


def _turn(payload: dict) -> str:
    try:
        from lib.turns import turn_key
        tp = payload.get("transcript_path")
        return turn_key(tp) if tp else "?"
    except Exception:
        return "?"


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
        "  The section index finds the relevant sections across every doc, which one "
        "whole file does not. (Single small config/env reads: keep using your normal read.)"
    )


def handle_pre_tool_use():
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
        _noop()
        return

    try:
        from lib.agent_kinds import is_egm_lean
        if is_egm_lean(hook_input.get("agent_type")):
            _noop()  # EGM goldfish reviewers read blind by design (plan Step 6)
            return
    except Exception:
        pass
    tool_input = hook_input.get("tool_input", {}) or {}
    session_id = _cid(hook_input)
    cfg = _load_config()

    target = _target_path(tool_input)
    if not target or not _is_doc_file(target, cfg) or _small_or_sliced(target, tool_input, cfg):
        _noop()
        return

    root = _repo_root(hook_input)
    doc_id = _doc_repo_id(root) if _under(target, root) else ""
    if not doc_id:
        _noop()
        return

    # B-05: the first whole read of a large indexed doc per agent per user turn is
    # denied once with the exact call; every later read passes (with a reminder).
    state, turn = _load_state(session_id), _turn(hook_input)
    if state.get("denied_turn") != turn:
        state["denied_turn"] = turn
        _save_state(session_id, state)
        call = f'mcp__jdocmunch__search_sections(repo="{doc_id}", query="{Path(target).stem}")'
        why = (f"call {call} first, then get_section on the hits. The section index finds the relevant "
               "sections across every doc in the repo, not just this file.")
        # additionalContext too: while the link is still typed `advisory` the dispatcher drops the deny
        json.dump({"permissionDecision": "deny", "additionalContext": f"[jDocMunch] {why}",
                   "permissionDecisionReason": f"BLOCKED (once per agent per turn): {why} "
                                               "Then retry: the next read passes."}, sys.stdout)
        return
    if state.get("remind_count", 0) >= cfg.get("max_reminders_per_session", 6):
        _noop()
        return

    state["remind_count"] = state.get("remind_count", 0) + 1
    _save_state(session_id, state)
    json.dump({"additionalContext": _reminder(root)}, sys.stdout)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "pre-tool-use":
            handle_pre_tool_use()
        else:
            _noop()
    except Exception:
        _noop()

#!/usr/bin/env python3
"""Session lifecycle hook (audit 2026-10-05 B2-09..B2-12, NEW-03).

  session-start  this repo's last-session breadcrumb + `.continue-here.md`. The
                 breadcrumb is keyed by git root (else the cwd) and never falls back
                 to another repo's (B2-10). `compact`: only the pre-compact handoff
                 (this is its single injector, B2-09). `resume`: nothing, the resumed
                 transcript already holds it (NEW-03).
  stop           (async) writes the per-repo breadcrumb.
  pre-compact    writes {cid}.precompact-handoff.json and prints {}: PreCompact
                 output never reaches the model.
  post-compact, subagent-stop
                 retired no-ops (B2-11, B2-12): they print {} and write nothing, so a
                 link that is still enabled stays harmless.

argv[1]: one of the modes above. stdin: hook JSON payload. Exit 0 always (fail open).
Honors CLAUDE_HOOK_DOCTOR (no disk writes, prints {}).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or HOOK_DIR / ".state")

if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))
try:
    from lib.repo_context import git_root as _git_root  # noqa: E402
except Exception:  # pragma: no cover - fail open
    _git_root = None


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _payload() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _workspace(payload: dict) -> Path | None:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    try:
        return Path(os.getcwd())
    except OSError:
        return None


def _breadcrumb_path(workspace: Path | None) -> Path | None:
    """{key}.breadcrumb.json, key = sha1(git root, else the workspace itself)."""
    if workspace is None:
        return None
    root = _git_root(workspace) if _git_root is not None else None
    key = hashlib.sha1(str(root or workspace).encode()).hexdigest()[:12]
    return STATE_DIR / f"{key}.breadcrumb.json"


def _decisions_summary(workspace: Path | None) -> str:
    """Last git commit subject + last 10 lines of CODEX.md if present."""
    parts: list[str] = []
    try:
        subject = subprocess.run(["git", "log", "-1", "--format=%s"],
                                 cwd=str(workspace) if workspace else None,
                                 capture_output=True, text=True, timeout=5).stdout.strip()
        if subject:
            parts.append(f"last_commit: {subject}")
    except (OSError, subprocess.TimeoutExpired):
        pass
    codex = workspace / "CODEX.md" if workspace else None
    if codex is not None and codex.is_file():
        try:
            tail = "\n".join(codex.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]).strip()
            if tail:
                parts.append(f"codex_tail: {tail}")
        except OSError:
            pass
    return " | ".join(parts)


def _breadcrumb_text(bc: dict) -> str:
    lines = [f"LAST SESSION CONTEXT (breadcrumb from {bc.get('timestamp', '?')}):",
             f"  workspace: {bc.get('workspace', '?')}",
             f"  {bc.get('summary', 'no summary')}",
             f"  decisions: {bc.get('decisions_summary') or 'none'}"]
    go = bc.get("gate_outcomes") or {}
    # hard-completion-gate keeps failed_gates after a block or an override and
    # clears it on a passing Stop, so a non-empty list means "still failing".
    forced = go.get("forced_gates") or go.get("failed_gates") or []
    if forced:
        lines.append(f"  WARNING: completion gates still failing at the last Stop: "
                     f"[{', '.join(map(str, forced))}]. Consider addressing these first.")
    sec = bc.get("security_outcomes") or {}
    if sec.get("security_files_count", 0) > 0 and not sec.get("semgrep_ran"):
        lines.append(f"  NOTE: Last session touched {sec['security_files_count']} security-sensitive "
                     "file(s) but semgrep was not run. Consider running: semgrep scan --config auto")
    return "\n".join(lines)


def _handoff_text(payload: dict) -> str:
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    h = _read_json(STATE_DIR / f"{_safe_cid(cid)}.precompact-handoff.json") if cid else {}
    if not h:
        return ""
    return "\n".join(["RESUMED FROM PRE-COMPACT SNAPSHOT:"] + [
        f"  {k}: {h.get(k)}" for k in ("write_count", "failed_gates", "semgrep_ran",
                                        "security_files_count") if k in h])


def _emit(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": text}}) if text else "{}")


def session_start(payload: dict | None = None) -> None:
    payload = _payload() if payload is None else payload
    source = payload.get("source")
    if source == "compact":  # the only channel that reaches the model after compaction
        _emit(_handoff_text(payload))
        return
    if source == "resume":  # the resumed transcript already holds it all (NEW-03)
        print("{}")
        return
    workspace = _workspace(payload)
    parts: list[str] = []
    continue_md = workspace / ".continue-here.md" if workspace else None
    if continue_md is not None and continue_md.is_file():
        try:
            snippet = continue_md.read_text(encoding="utf-8", errors="replace")[:1000].strip()
            parts.append("RESUME PROMPT (.continue-here.md):\n" + snippet)
        except OSError:
            pass
    bc_path = _breadcrumb_path(workspace)
    bc = _read_json(bc_path) if bc_path is not None else {}
    if bc:
        parts.append(_breadcrumb_text(bc))
    _emit("\n\n".join(parts))


def _session_facts(safe: str) -> dict:
    """Live facts other hooks keep for this conversation (empty when unknown)."""
    if not safe:
        return {}
    doc = _read_json(STATE_DIR / f"{safe}.doc-enforcer.json")
    sec = _read_json(STATE_DIR / f"{safe}.security-scan.json")
    return {
        "surfaces": [s for s, keys in (("frontend", ("fe_touched", "frontend_touched")),
                                       ("backend", ("be_touched", "backend_touched")))
                     if any(doc.get(k) for k in keys)],
        "write_count": _read_json(STATE_DIR / f"{safe}.desloppify.json").get("code_writes", 0),
        "failed_gates": _read_json(STATE_DIR / f"{safe}.completion-gate.json").get("failed_gates") or [],
        "semgrep_ran": bool(sec.get("semgrep_ran")),
        "security_files_count": len(sec.get("security_files") or []),
    }


def stop(payload: dict) -> None:
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    workspace = _workspace(payload)
    facts = _session_facts(_safe_cid(cid) if cid else "")
    surfaces = facts.get("surfaces") or []
    n = facts.get("write_count", 0)
    breadcrumb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace) if workspace else "",
        "exit_status": payload.get("status", "unknown"),
        "surfaces_touched": surfaces,
        "code_files_count": n,
        "summary": f"Worked on {' and '.join(surfaces) or 'codebase'} ({n} code files)",
        "decisions_summary": _decisions_summary(workspace),
        "gate_outcomes": {"forced_gates": facts["failed_gates"]} if facts.get("failed_gates") else {},
        "security_outcomes": ({"semgrep_ran": facts["semgrep_ran"],
                               "security_files_count": facts["security_files_count"]}
                              if facts.get("security_files_count") else {}),
    }
    path = _breadcrumb_path(workspace)
    if path is not None:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(breadcrumb, indent=2), encoding="utf-8")
        except OSError:
            pass
    print("{}")


def pre_compact(payload: dict) -> None:
    """Snapshot live session facts for session_start (source=compact)."""
    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    safe = _safe_cid(cid) if cid else ""
    if safe:
        facts = _session_facts(safe)
        facts.pop("surfaces", None)
        handoff = {"event": "pre-compact", "timestamp": datetime.now(timezone.utc).isoformat(),
                   "conversation_id": cid, **facts}
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            (STATE_DIR / f"{safe}.precompact-handoff.json").write_text(
                json.dumps(handoff, indent=2), encoding="utf-8")
        except OSError:
            pass
    print("{}")


def run(mode: str) -> None:
    try:
        if os.environ.get("CLAUDE_HOOK_DOCTOR"):
            print("{}")
            return
        payload = _payload()
        if mode == "session-start":
            session_start(payload)
        elif mode == "stop":
            stop(payload)
        elif mode == "pre-compact":
            pre_compact(payload)
        else:  # post-compact, subagent-stop (retired) and unknown modes
            print("{}")
    except Exception:  # noqa: BLE001 - fail open
        print("{}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "session-start")
    sys.exit(0)

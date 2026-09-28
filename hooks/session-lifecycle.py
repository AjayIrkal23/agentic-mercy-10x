#!/usr/bin/env python3
"""Session lifecycle hook: SessionStart (last-session breadcrumb; handoff re-injection
when source == "compact") + Stop (breadcrumb saving) + PreCompact (handoff snapshot) +
PostCompact (no-op; its output is display-only) + SubagentStop (subagent records).

argv[1]: "session-start" | "stop" | "pre-compact" | "post-compact" | "subagent-stop"
stdin:   Claude Code hook JSON payload
stdout:  JSON with hookSpecificOutput; exit always 0 (fail open)
Honors CLAUDE_HOOK_DOCTOR (no disk writes, prints {}).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"
BREADCRUMB = STATE_DIR / "session-breadcrumb.json"


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _workspace(payload: dict) -> Path | None:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    try:
        return Path(os.getcwd())
    except OSError:
        return None


def _decisions_summary(workspace: Path | None) -> str:
    """Return last git commit subject + last 10 lines of CODEX.md if present."""
    parts: list[str] = []
    # Last git commit subject
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=str(workspace) if workspace else None,
            capture_output=True,
            text=True,
            timeout=5,
        )
        subject = result.stdout.strip()
        if subject:
            parts.append(f"last_commit: {subject}")
    except (OSError, subprocess.TimeoutExpired):
        pass
    # Last 10 lines of CODEX.md
    if workspace:
        codex = workspace / "CODEX.md"
        if codex.is_file():
            try:
                lines = codex.read_text(encoding="utf-8", errors="replace").splitlines()
                tail = "\n".join(lines[-10:]).strip()
                if tail:
                    parts.append(f"codex_tail: {tail}")
            except OSError:
                pass
    return " | ".join(parts) if parts else ""


def _gate_outcomes(safe_cid: str) -> dict:
    """Read {cid}.completion-gate.json for deny_count and failed_gates."""
    gate_file = STATE_DIR / f"{safe_cid}.completion-gate.json"
    if not gate_file.is_file():
        return {}
    try:
        data = json.loads(gate_file.read_text(encoding="utf-8"))
        return {
            "deny_count": data.get("deny_count", 0),
            "failed_gates": data.get("failed_gates", []),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def session_start() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    workspace = _workspace(payload)
    parts: list[str] = []

    # Post-compaction re-injection: SessionStart(source=="compact") is the only
    # compaction-time channel whose additionalContext reaches the model (PostCompact
    # output is display-only).
    if payload.get("source") == "compact":
        handoff = _load_handoff(payload)
        if handoff:
            parts.append(_handoff_summary(handoff, "RESUMED FROM PRE-COMPACT SNAPSHOT:"))

    if workspace:
        # .continue-here.md — resume prompt
        continue_md = workspace / ".continue-here.md"
        if continue_md.is_file():
            try:
                snippet = continue_md.read_text(encoding="utf-8", errors="replace")[:1000].strip()
                parts.append("RESUME PROMPT (.continue-here.md):\n" + snippet)
            except OSError:
                pass

    # 3. Last-session breadcrumb
    # Prefer the per-workspace-keyed breadcrumb when workspace is known.
    _bc_workspace_key = (
        hashlib.sha1(str(workspace).encode()).hexdigest()[:12]
        if workspace
        else None
    )
    _bc_path = (
        STATE_DIR / f"{_bc_workspace_key}.breadcrumb.json"
        if _bc_workspace_key and (STATE_DIR / f"{_bc_workspace_key}.breadcrumb.json").is_file()
        else BREADCRUMB
    )
    if _bc_path.is_file():
        try:
            bc = json.loads(_bc_path.read_text(encoding="utf-8"))
            bc_lines = [
                f"LAST SESSION CONTEXT (breadcrumb from {bc.get('timestamp', '?')}):",
                f"  workspace: {bc.get('workspace', '?')}",
                f"  {bc.get('summary', 'no summary')}",
                f"  decisions: {bc.get('decisions_summary', 'none')}",
            ]

            # Surface gate override warnings if any gates were bypassed
            gate_outcomes = bc.get("gate_outcomes", {})
            if gate_outcomes:
                deny_count = gate_outcomes.get("deny_count", 0)
                still_failing = gate_outcomes.get("override_still_failing", [])
                failed_gates = gate_outcomes.get("failed_gates", [])

                if deny_count >= 2 and still_failing:
                    # Session ended with an override that didn't resolve the gates
                    bc_lines.append(
                        f"  WARNING: Last session had {deny_count - 1} gate override(s). "
                        f"Gates forced past without resolution: [{', '.join(still_failing)}]. "
                        f"Consider addressing these before proceeding."
                    )
                elif failed_gates and deny_count == 0:
                    # Gates were triggered but session completed cleanly
                    bc_lines.append(
                        f"  Gates triggered last session: [{', '.join(failed_gates)}] (resolved before completion)."
                    )

            # Surface security scan gaps
            security_outcomes = bc.get("security_outcomes", {})
            if security_outcomes:
                sec_count = security_outcomes.get("security_files_count", 0)
                semgrep_ran = security_outcomes.get("semgrep_ran", False)
                if sec_count > 0 and not semgrep_ran:
                    bc_lines.append(
                        f"  NOTE: Last session touched {sec_count} security-sensitive file(s) "
                        f"but semgrep was not run. Consider running: semgrep scan --config auto"
                    )

            parts.append("\n".join(bc_lines))
        except (json.JSONDecodeError, OSError):
            pass

    if not parts:
        print("{}")
        return

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": "\n\n".join(parts),
    }}))


def stop() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    # Accept any exit status — breadcrumb is always useful.
    # "completed", "stopped", "interrupted", or absent all save the breadcrumb.
    status = payload.get("status", "unknown")

    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    workspace = _workspace(payload)
    safe = _safe_cid(cid) if cid else ""

    surfaces: list[str] = []
    code_files_count = 0

    if safe:
        # Doc-enforcer state → surfaces touched
        doc_file = STATE_DIR / f"{safe}.doc-enforcer.json"
        if doc_file.is_file():
            try:
                doc_state = json.loads(doc_file.read_text(encoding="utf-8"))
                if doc_state.get("fe_touched") or doc_state.get("frontend_touched"):
                    surfaces.append("frontend")
                if doc_state.get("be_touched") or doc_state.get("backend_touched"):
                    surfaces.append("backend")
            except (json.JSONDecodeError, OSError):
                pass

        # Desloppify state → write count
        deslop_file = STATE_DIR / f"{safe}.desloppify.json"
        if deslop_file.is_file():
            try:
                code_files_count = json.loads(deslop_file.read_text(encoding="utf-8")).get("code_writes", 0)
            except (json.JSONDecodeError, OSError):
                pass

    # Gate outcomes — read from completion gate state file
    gate_outcomes: dict = {}
    if safe:
        gate_file = STATE_DIR / f"{safe}.completion-gate.json"
        if gate_file.is_file():
            try:
                gate_data = json.loads(gate_file.read_text(encoding="utf-8"))
                deny_count = gate_data.get("deny_count", 0)
                failed_gates = gate_data.get("failed_gates", [])
                override_still_failing = gate_data.get("override_still_failing", [])
                override_ts = gate_data.get("override_ts")
                if deny_count > 0 or failed_gates:
                    gate_outcomes = {
                        "deny_count": deny_count,
                        "failed_gates": failed_gates,
                        "override_still_failing": override_still_failing,
                        "override_ts": override_ts,
                    }
            except (json.JSONDecodeError, OSError):
                pass

    # Security scan outcomes — read from security scan state file
    security_outcomes: dict = {}
    if safe:
        scan_file = STATE_DIR / f"{safe}.security-scan.json"
        if scan_file.is_file():
            try:
                scan_data = json.loads(scan_file.read_text(encoding="utf-8"))
                semgrep_ran = scan_data.get("semgrep_ran", False)
                security_files = scan_data.get("security_files", [])
                if security_files:
                    security_outcomes = {
                        "semgrep_ran": semgrep_ran,
                        "security_files_count": len(security_files),
                    }
            except (json.JSONDecodeError, OSError):
                pass

    surface_str = " and ".join(surfaces) if surfaces else "codebase"

    # Richer fields: decisions summary
    decisions = _decisions_summary(workspace)

    breadcrumb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace) if workspace else "",
        "exit_status": status,
        "surfaces_touched": surfaces,
        "code_files_count": code_files_count,
        "summary": f"Worked on {surface_str} ({code_files_count} code files)",
        "decisions_summary": decisions,
        "gate_outcomes": gate_outcomes,
        "security_outcomes": security_outcomes,
    }

    # Per-workspace-keyed file (not singleton) so multi-project users don't overwrite each other.
    workspace_key = hashlib.sha1(str(workspace).encode()).hexdigest()[:12] if workspace else "global"
    breadcrumb_path = STATE_DIR / f"{workspace_key}.breadcrumb.json"

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        breadcrumb_path.write_text(json.dumps(breadcrumb, indent=2), encoding="utf-8")
        # Also write the legacy singleton so session_start() (which reads BREADCRUMB) still works.
        BREADCRUMB.write_text(json.dumps(breadcrumb, indent=2), encoding="utf-8")
    except OSError:
        pass

    print("{}")


def pre_compact() -> None:
    """PreCompact hook: emit a handoff snapshot so state survives auto-compaction.

    Reads state files for the active conversation and writes a compact JSON handoff
    to STATE_DIR/{safe_cid}.precompact-handoff.json. Emits that file's content as
    additionalContext so it is included in the compaction summary Claude sees.
    """
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return

    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    safe = _safe_cid(cid) if cid else ""
    if not safe:
        print("{}")
        return

    handoff: dict = {
        "event": "pre-compact",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conversation_id": cid,
    }

    # --- Write count (from desloppify state) ---
    deslop_file = STATE_DIR / f"{safe}.desloppify.json"
    if deslop_file.is_file():
        try:
            handoff["write_count"] = json.loads(
                deslop_file.read_text(encoding="utf-8")
            ).get("code_writes", 0)
        except (json.JSONDecodeError, OSError):
            pass

    # --- Last 5 skill reminders (from fullstack-skills-reminder state) ---
    fullstack_file = STATE_DIR / f"{safe}.fullstack.json"
    if fullstack_file.is_file():
        try:
            fs_state = json.loads(fullstack_file.read_text(encoding="utf-8"))
            reminded = fs_state.get("reminded_skills", [])
            handoff["last_skill_reminders"] = reminded[-5:] if reminded else []
            handoff["frontend_start_sent"] = fs_state.get("frontend_start_sent", False)
            handoff["backend_start_sent"] = fs_state.get("backend_start_sent", False)
        except (json.JSONDecodeError, OSError):
            pass

    # --- Gate states ---
    gate_file = STATE_DIR / f"{safe}.completion-gate.json"
    if gate_file.is_file():
        try:
            g = json.loads(gate_file.read_text(encoding="utf-8"))
            handoff["gate_states"] = {
                "deny_count": g.get("deny_count", 0),
                "failed_gates": g.get("failed_gates", []),
                "doc_gate_cleared": g.get("doc_gate_cleared", False),
                "santa_gate_cleared": g.get("santa_gate_cleared", False),
            }
        except (json.JSONDecodeError, OSError):
            pass

    # --- Security scan state ---
    security_file = STATE_DIR / f"{safe}.security-scan.json"
    if security_file.is_file():
        try:
            sec = json.loads(security_file.read_text(encoding="utf-8"))
            handoff["semgrep_ran"] = sec.get("semgrep_ran", False)
        except (json.JSONDecodeError, OSError):
            pass

    # Write handoff file
    handoff_path = STATE_DIR / f"{safe}.precompact-handoff.json"
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")
    except OSError:
        pass

    # Emit as additionalContext so it's included in the compaction summary
    print(json.dumps({"additionalContext": _handoff_summary(
        handoff, "PRE-COMPACT STATE SNAPSHOT (SessionStart source=compact re-injects this):")}))


def _handoff_summary(handoff: dict, title: str) -> str:
    return "\n".join([
        title,
        f"  conversation_id: {handoff.get('conversation_id', '')}",
        f"  write_count: {handoff.get('write_count', 0)}",
        f"  last_skill_reminders: {handoff.get('last_skill_reminders', [])}",
        f"  gate_states: {handoff.get('gate_states', {})}",
        f"  semgrep_ran: {handoff.get('semgrep_ran', False)}",
    ])


def _load_handoff(payload: dict) -> dict:
    """The pre-compact handoff for this conversation, or {}."""
    cid = (payload.get("conversation_id") or payload.get("session_id") or "")
    safe = _safe_cid(cid) if cid else ""
    handoff_path = STATE_DIR / f"{safe}.precompact-handoff.json"
    if not safe or not handoff_path.is_file():
        return {}
    try:
        data = json.loads(handoff_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def post_compact() -> None:
    """PostCompact hook: no-op. Its stdout is display-only (never reaches the model);
    the handoff is re-injected by session_start() when source == "compact"."""
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass
    print("{}")


def subagent_stop() -> None:
    """SubagentStop hook: append a record to {cid}.subagents.json."""
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        return
    cid = payload.get("conversation_id") or payload.get("session_id") or "unknown"
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", cid)
    state_file = STATE_DIR / f"{safe}.subagents.json"
    # Claude Code SubagentStop payload fields (2.1.x): agent_id, agent_type,
    # agent_transcript_path.
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent_id": payload.get("agent_id", ""),
        "agent_type": payload.get("agent_type", ""),
        "agent_transcript_path": payload.get("agent_transcript_path", ""),
    }
    try:
        existing = []
        if state_file.exists():
            existing = json.loads(state_file.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        existing.append(record)
        # Keep last 50 records
        existing = existing[-50:]
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else "session-start"
        if os.environ.get("CLAUDE_HOOK_DOCTOR"):
            print("{}")
        elif mode == "session-start":
            session_start()
        elif mode == "stop":
            stop()
        elif mode == "pre-compact":
            pre_compact()
        elif mode == "post-compact":
            post_compact()
        elif mode == "subagent-stop":
            subagent_stop()
        else:
            print("{}")
    except Exception:
        print("{}")
    sys.exit(0)

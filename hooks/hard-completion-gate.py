#!/usr/bin/env python3
"""Stop hook: hard completion gate using the Stop schema {"decision":"block","reason":...}.

Replaces advisory-only stop-verification-gate.py and santa-method-review.py
with a gate that actually blocks completion on first failure.

Behavior:
- First deny in a conversation: decision=block with specific instructions.
- Second+ attempt: allow with followup_message warning (override accepted).
- All-pass: output {} (silent allow).

Gate summary:
  Gate 1 (tests)     — advisory, always PASS (best-effort reminder only)
  Gate 2 (docs)      — HARD BLOCK — missing server_docs/frontend_docs/PROJECT_LINKAGES
  Gate 3 (security)  — SEMI-HARD — semgrep not run on security-sensitive files
  Gate 4 (santa)     — SEMI-HARD — adversarial review not dispatched for 3+ writes
  Gate 5 (dead code) — SEMI-HARD — dead-code audit not recorded for 2+ writes

State files read (all under STATE_DIR / {safe_cid}.*):
  .desloppify.json    — code_writes count
  .doc-enforcer.json  — be_touched, fe_touched, be_docs_written, fe_docs_written, linkages_written
  .security-scan.json — security_files list, reminded flag
  .santa.json         — fired flag

Own state file:
  .completion-gate.json — {"deny_count": N, "failed_gates": [...], "last_deny_time": null}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"

MIN_WRITES_SANTA = 2   # code_writes threshold to require santa method (code review)
MIN_WRITES_DEAD  = 2   # code_writes threshold to require dead-code audit

# Cursor config/hook paths — Santa adversarial review not required (verify-hooks.sh instead)
_INFRA_PATH_MARKERS = (
    # deduped (P4-T6): the ".claude/x/" forms are substrings of the "/.claude/x/"
    # forms, so `marker in n` matches identically — one clean set, same behavior.
    ".claude/hooks/",
    ".claude/rules/",
    ".claude/scripts/",
    ".claude/docs/",
    ".claude/mcp.profiles/",
)


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lower()


def _is_infra_path(path: str) -> bool:
    n = _normalize_path(path)
    return any(marker in n for marker in _INFRA_PATH_MARKERS)


def _is_infra_only_session(cid: str) -> bool:
    """True when every tracked code write is under ~/.claude config (hooks, rules, etc.)."""
    safe = _safe_cid(cid)
    doc_path = STATE_DIR / f"{safe}.doc-enforcer.json"
    doc_files = _load_json(doc_path).get("code_files", [])
    if doc_files:
        return all(_is_infra_path(str(f)) for f in doc_files)

    deslop_path = STATE_DIR / f"{safe}.desloppify.json"
    deslop = _load_json(deslop_path)
    paths = deslop.get("code_paths") or []
    if paths:
        return all(_is_infra_path(str(p)) for p in paths)

    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _load_gate_state(cid: str) -> dict:
    p = STATE_DIR / f"{_safe_cid(cid)}.completion-gate.json"
    data = _load_json(p)
    return {
        "deny_count": data.get("deny_count", 0),
        "failed_gates": data.get("failed_gates", []),
        "last_deny_time": data.get("last_deny_time"),
        "pass_advisories_sent": bool(data.get("pass_advisories_sent")),
    }


def _save_gate_state(cid: str, state: dict) -> None:
    p = STATE_DIR / f"{_safe_cid(cid)}.completion-gate.json"
    _save_json(p, state)


def _code_writes(cid: str) -> int:
    p = STATE_DIR / f"{_safe_cid(cid)}.desloppify.json"
    return _load_json(p).get("code_writes", 0)


def _git_root_of(path: str) -> "Path | None":
    """Walk up from an absolute path to its enclosing git repo root."""
    try:
        cur = Path(path)
        if not cur.is_absolute():
            return None
        cur = cur if cur.is_dir() else cur.parent
        for _ in range(30):
            if (cur / ".git").exists():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
    except Exception:
        return None
    return None


def _session_dox_repos(cid: str) -> list:
    """Repos touched this session (via tracked code dirs) that carry a root CLAUDE.md.

    Derives the repo from the actual dirs that were edited, so the dox requirement
    fires even when the Stop payload omits workspace_roots.
    """
    safe = _safe_cid(cid)
    st = _load_json(STATE_DIR / f"{safe}.doc-enforcer.json")
    roots = set()
    for d in (st.get("code_dirs") or []):
        r = _git_root_of(str(d))
        if r is not None and (r / "CLAUDE.md").is_file():
            roots.add(str(r))
    return sorted(roots)


# ---------------------------------------------------------------------------
# Individual Gates
# ---------------------------------------------------------------------------

def gate1_tests(cid: str, code_writes: int) -> tuple[bool, str, str]:
    """Gate 1: Tests — always PASS, advisory reminder only."""
    if code_writes >= 3:
        reminder = f"Reminder: {code_writes} code files written — verify tests ran."
        return True, "Gate 1 (tests)", reminder
    return True, "Gate 1 (tests)", ""


def _repo_doc_expectations(workspace_roots: list) -> tuple[bool, bool, bool]:
    """Return whether this session's workspace(s) define BE docs, FE docs, or linkages trees."""
    has_be = has_fe = has_link = False
    for root in workspace_roots:
        if not isinstance(root, str) or not root.strip():
            continue
        r = Path(root)
        if (r / "server_docs").is_dir():
            has_be = True
        if (r / "frontend_docs").is_dir():
            has_fe = True
        if (r / "PROJECT_LINKAGES.md").is_file():
            has_link = True
    return has_be, has_fe, has_link


def gate2_docs(cid: str, workspace_roots: list | None = None) -> tuple[bool, str, str]:
    """Gate 2: Documentation — HARD when repo has doc trees; skip when absent (home/general)."""
    p = STATE_DIR / f"{_safe_cid(cid)}.doc-enforcer.json"
    st = _load_json(p)

    code_files = st.get("code_files", [])
    if not code_files:
        return True, "Gate 2 (docs)", ""

    if _is_infra_only_session(cid):
        return True, "Gate 2 (docs)", ""

    roots = workspace_roots if isinstance(workspace_roots, list) else []
    expect_be, expect_fe, expect_link = _repo_doc_expectations(roots)

    be_touched = st.get("be_touched", False)
    fe_touched = st.get("fe_touched", False)
    be_docs = st.get("be_docs_written", False)
    fe_docs = st.get("fe_docs_written", False)
    linkages = st.get("linkages_written", False)

    missing: list[str] = []
    if be_touched and expect_be and not be_docs:
        missing.append("server_docs/")
    if fe_touched and expect_fe and not fe_docs:
        missing.append("frontend_docs/")
    if (be_touched or fe_touched) and expect_link and not linkages:
        missing.append("PROJECT_LINKAGES.md")

    # dox CLAUDE.md-tree requirement (Phase 7), ALWAYS evaluated: if code was edited
    # in a repo that carries a root CLAUDE.md, at least one CLAUDE.md must be updated
    # this session. Independent of the GO_UDP doc dirs above, and robust to a missing
    # workspace_roots payload — the repo is derived from the dirs actually touched.
    ws_has_dox = any(
        isinstance(r, str) and r.strip() and (Path(r) / "CLAUDE.md").is_file()
        for r in roots
    )
    touched_dox = _session_dox_repos(cid)
    if (ws_has_dox or touched_dox) and not st.get("claude_md_written"):
        missing.append(
            "dox CLAUDE.md (Phase 7 — update the CLAUDE.md for the dir(s) you changed)"
        )

    if not missing:
        return True, "Gate 2 (docs)", ""

    detail = (
        f"{len(code_files)} code file(s) written but docs not updated. "
        f"Missing: {', '.join(missing)}. "
        f"Fix: dispatch the docs-sync-agent specialist (Agent tool, subagent_type "
        f"\"docs-sync-agent\") or run /invoke-docs."
    )
    return False, "Gate 2 (docs)", detail


def gate3_security(cid: str) -> tuple[bool, str, str]:
    """Gate 3: Security — semi-hard when auth/API files changed and semgrep not run."""
    if _is_infra_only_session(cid):
        return True, "Gate 3 (security)", ""

    p = STATE_DIR / f"{_safe_cid(cid)}.security-scan.json"
    st = _load_json(p)
    files = st.get("security_files", [])
    if not files:
        return True, "Gate 3 (security)", ""

    semgrep_ran = st.get("semgrep_ran", False)
    if semgrep_ran:
        findings = st.get("semgrep_findings", 0)
        if findings:
            reminder = (
                f"Semgrep reported {findings} finding(s) on security-sensitive files. "
                "Resolve HIGH/CRITICAL before shipping."
            )
            return True, "Gate 3 (security)", reminder
        return True, "Gate 3 (security)", ""

    detail = (
        f"{len(files)} security-sensitive file(s) modified but semgrep not verified. "
        "Fix: dispatch the security-sentinel specialist (Agent tool, subagent_type "
        "\"security-sentinel\") or run /invoke-security — or run `semgrep scan --config auto` "
        "on the changed auth/API files yourself, then retry."
    )
    return False, "Gate 3 (security)", detail


def gate4_santa(cid: str, code_writes: int) -> tuple[bool, str, str]:
    """Gate 4: Santa Method — SEMI-HARD BLOCK if 3+ writes but review not done."""
    if _is_infra_only_session(cid):
        return True, "Gate 4 (santa)", ""

    if code_writes < MIN_WRITES_SANTA:
        return True, "Gate 4 (santa)", ""

    p = STATE_DIR / f"{_safe_cid(cid)}.santa.json"
    st = _load_json(p)
    fired = st.get("fired", False)

    if fired:
        return True, "Gate 4 (santa)", ""

    detail = (
        f"{code_writes} code file(s) written. "
        "Santa Method adversarial review not dispatched. "
        "Fix: run /santa-review (or dispatch the santa-reviewer agent — Agent tool, "
        "subagent_type \"santa-reviewer\") to run the BREAKER + SIMPLIFIER + VERIFIER "
        "passes on the diff and confirm real bugs before completing."
    )
    return False, "Gate 4 (santa)", detail


def _deadcode_done(cid: str) -> bool:
    """True once a dead-code audit signal was recorded (jcodemunch find_dead_code etc.)."""
    p = STATE_DIR / f"{_safe_cid(cid)}.deadcode.json"
    return bool(_load_json(p).get("fired", False))


def gate5_dead_code(cid: str, code_writes: int) -> tuple[bool, str, str]:
    """Gate 5: Dead-code audit — SEMI-HARD BLOCK when 2+ writes but no audit recorded."""
    if code_writes < MIN_WRITES_DEAD:
        return True, "Gate 5 (dead code)", ""

    if _is_infra_only_session(cid):
        return True, "Gate 5 (dead code)", ""

    if _deadcode_done(cid):
        return True, "Gate 5 (dead code)", ""

    detail = (
        f"{code_writes} code file(s) written but no dead-code audit recorded. "
        "Fix: dispatch the deadcode-reaper specialist (Agent tool, subagent_type "
        "\"deadcode-reaper\") or run /invoke-clean — or run "
        "mcp__jcodemunch__find_dead_code / get_dead_code_v2 on your changes yourself."
    )
    return False, "Gate 5 (dead code)", detail


def gate6_decision_capture(cid: str, code_writes: int) -> tuple[bool, str, str]:
    """Gate 6: Decision capture — advisory only, always PASS.

    Fires when code_writes >= 3 AND none of these are true:
      - An ADR / CODEX.md / ARCHITECTURE.md write was detected
      - A memory MCP write was recorded (memory-write.json fired=true)

    Emits an advisory followup_message only — never blocks.
    """
    if code_writes < 3:
        return True, "Gate 6 (decision capture)", ""

    if _is_infra_only_session(cid):
        return True, "Gate 6 (decision capture)", ""

    safe = _safe_cid(cid)

    # Check: did any ADR / decision doc get written?
    doc_path = STATE_DIR / f"{safe}.doc-enforcer.json"
    doc_state = _load_json(doc_path)
    code_files = doc_state.get("code_files", [])

    _ADR_PATTERNS = (
        "docs/adr/",
        "adr/",
        "ADR-",
        "ARCHITECTURE.md",
        "CODEX.md",
        "decisions.md",
        "DECISIONS.md",
    )
    adr_written = any(
        any(pattern.lower() in str(f).lower() for pattern in _ADR_PATTERNS)
        for f in code_files
    )
    if adr_written:
        return True, "Gate 6 (decision capture)", ""

    # Check: did a memory MCP write occur?
    memory_path = STATE_DIR / f"{safe}.memory-write.json"
    memory_state = _load_json(memory_path)
    if memory_state.get("fired", False):
        return True, "Gate 6 (decision capture)", ""

    # No decision record written — emit advisory
    reminder = (
        f"{code_writes} file(s) changed but no decision record written. "
        "Consider: update CODEX.md with any new patterns or decisions, "
        "or call `mcp__memory__add_observations` to persist key facts."
    )
    return True, "Gate 6 (decision capture)", reminder


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        raw = sys.stdin.read() or "{}"
        payload = json.loads(raw)
    except Exception:
        sys.stdout.write("{}")
        return 0

    # Stop payloads arrive with status 'completed', 'stopped', 'interrupted', or
    # (commonly) no status field at all. Only skip for genuinely non-stop states;
    # the original `!= "completed"` silently disabled the gate on every normal stop.
    _status = payload.get("status")
    if _status not in (None, "", "completed", "stopped", "interrupted"):
        sys.stdout.write("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        sys.stdout.write("{}")
        return 0

    try:
        code_writes = _code_writes(cid)
        gate_state = _load_gate_state(cid)

        # Run all gates
        workspace_roots = payload.get("workspace_roots") or []
        results = [
            gate1_tests(cid, code_writes),
            gate2_docs(cid, workspace_roots),
            gate3_security(cid),
            gate4_santa(cid, code_writes),
            gate5_dead_code(cid, code_writes),
            gate6_decision_capture(cid, code_writes),
        ]

        # Separate hard failures from advisory reminders
        hard_failures = [(ok, label, detail) for ok, label, detail in results if not ok]
        advisories    = [detail for ok, label, detail in results if ok and detail]

        if not hard_failures:
            # All gates pass — reset override counter; emit pass advisories once per session
            gate_state["deny_count"] = 0
            gate_state["failed_gates"] = []
            out: dict = {}
            if advisories and not gate_state.get("pass_advisories_sent"):
                reminder_text = "\n".join(f"- {a}" for a in advisories)
                out = {
                    "followup_message": (
                        f"Completion gate: all checks passed.\n\n{reminder_text}"
                    ),
                }
                gate_state["pass_advisories_sent"] = True
            _save_gate_state(cid, gate_state)
            sys.stdout.write(json.dumps(out))
            return 0

        # There are hard failures
        failed_labels = [label for ok, label, detail in hard_failures]
        deny_count = gate_state.get("deny_count", 0)

        if deny_count >= 1:
            # C-07 fix: capture prior failed gates BEFORE overwriting with current run's failures
            original_failed = set(gate_state.get("failed_gates", []))

            gate_state["deny_count"] = deny_count + 1
            gate_state["failed_gates"] = failed_labels
            _save_gate_state(cid, gate_state)

            # Patched: re-evaluate which gates resolved before granting override
            if deny_count == 1:
                current_failed = set(failed_labels)
                resolved = original_failed - current_failed
                still_failing = original_failed & current_failed

                # Record override audit trail in gate state (read by breadcrumb enrichment)
                gate_state["override_ts"] = datetime.now(timezone.utc).isoformat()
                gate_state["override_still_failing"] = sorted(still_failing)
                gate_state["override_resolved"] = sorted(resolved)
                # C-08 fix: persist override fields — prior _save_gate_state ran before these
                # were assigned, so they were never written to disk without this second save.
                _save_gate_state(cid, gate_state)

                advisory_text = ""
                if advisories:
                    advisory_text = "\n" + "\n".join(f"- {a}" for a in advisories)

                if still_failing:
                    skipped = ", ".join(sorted(still_failing))
                    resolved_str = (
                        f" ({', '.join(sorted(resolved))} resolved)" if resolved else ""
                    )
                    msg = (
                        f"Completion gate: override accepted — no issues resolved. "
                        f"Forced past: [{skipped}]{resolved_str}. "
                        f"Override logged in gate state.{advisory_text}"
                    )
                else:
                    msg = (
                        f"Completion gate: override accepted "
                        f"(all originally failing gates now pass). "
                        f"Originally failed: [{', '.join(sorted(original_failed))}]."
                        f"{advisory_text}"
                    )

                sys.stdout.write(json.dumps({"followup_message": msg}))
                return 0

            # Attempt 3+ with unfixed failures — deny again (no silent allow)
            lines: list[str] = ["[COMPLETION GATE: STILL BLOCKED]", "", "Failed gates:"]
            for ok, label, detail in hard_failures:
                lines.append(f"- {label}: {detail}")
            lines.append("")
            lines.append("Fix the issues above before completing.")
            reason = "\n".join(lines)
            out = {
                "decision": "block",
                "reason": reason,
            }
            sys.stdout.write(json.dumps(out))
            return 0

        # First denial — build deny reason
        lines: list[str] = ["[COMPLETION GATE: BLOCKED]", "", "Failed gates:"]
        for ok, label, detail in hard_failures:
            lines.append(f"- {label}: {detail}")

        if advisories:
            lines.append("")
            lines.append("Advisory reminders:")
            for a in advisories:
                lines.append(f"- {a}")

        lines.append("")
        lines.append(
            "Fix the issues listed above, then try completing again. "
            "The second attempt will be allowed with a warning."
        )

        reason = "\n".join(lines)

        # Update state
        gate_state["deny_count"] = 1
        gate_state["failed_gates"] = failed_labels
        gate_state["last_deny_time"] = datetime.now(timezone.utc).isoformat()
        _save_gate_state(cid, gate_state)

        out = {
            "decision": "block",
            "reason": reason,
        }
        sys.stdout.write(json.dumps(out))
        return 0

    except Exception:
        # Fail open — never block on an exception
        sys.stdout.write("{}")
        return 0


if __name__ == "__main__":
    sys.exit(main())

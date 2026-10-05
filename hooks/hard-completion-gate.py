#!/usr/bin/env python3
"""Stop hook: hard completion gate using the Stop schema {"decision":"block","reason":...}.

Behavior (2026-09-27 rework — A03-B6/B7/B8/B15, A14 §3):
- `stop_hook_active` in the payload → {} (the harness is already re-running us
  after a block; never chain-block).
- User consent: the last user prompt is "stop" / "don't do anything" / "leave it" /
  "no more changes" → {} (the user's word beats the gate).
- At most ONE block per turn (turn = last real user prompt, `lib.turns`). The second
  Stop in the same turn is allowed and emits a `systemMessage` naming the gates that
  were forced past. A new turn starts fresh.
- All-pass → {} (plus pass advisories once per session via `systemMessage`).

Gate summary:
  Gate 1 (tests)     — advisory, always PASS (best-effort reminder only)
  Gate 2 (docs)      — HARD BLOCK — missing server_docs/frontend_docs/PROJECT_LINKAGES
  Gate 3 (security)  — SEMI-HARD — security-sensitive files changed and no scan evidence
                       (semgrep CLI/MCP, a security-sentinel dispatch, or a fresh
                       SECURITY-REPORT.md all count)
  Gate 4 (santa)     — SEMI-HARD — review not dispatched for >= 3 unique code files
  Gate 5 (dead code) — SEMI-HARD — dead-code audit not recorded for >= 3 unique code files
  Gate 7 (memory)    — the human prompt said remember / going forward / we decided /
                       from now on / always.. / never.. and the turn saved nothing
                       (lib/memory_gate.py; Gate 6 stays advisory)

Thresholds count UNIQUE code files (desloppify `code_files`, classified by
`lib.code_files.is_code_file`), never raw write counts, and never ~/.claude infra
paths (`_INFRA_PATH_MARKERS`, audit B2-05). An unknown turn key ("?") gets no
same-turn override (santa-diff P5).

State files read (all under STATE_DIR / {safe_cid}.*):
  .desloppify.json    — code_files (unique paths; legacy code_paths honoured)
  .doc-enforcer.json  — be_touched, fe_touched, be_docs_written, fe_docs_written, linkages_written
  .security-scan.json — security_files list, semgrep_ran
  .santa.json         — fired flag
  .telemetry/{cid}.agent-dispatches.jsonl — subagent dispatches (santa-method-writer)

Own state file:
  .completion-gate.json — {"turn_key": ..., "blocked_this_turn": bool, "failed_gates": [...]}
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or HOOK_DIR / ".state")
TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or HOOK_DIR / ".telemetry")

if str(HOOK_DIR) not in sys.path:
    sys.path.insert(0, str(HOOK_DIR))
try:
    from lib.code_files import git_root as _lib_git_root, is_home as _is_home  # noqa: E402
except Exception:  # pragma: no cover - fail-open
    _lib_git_root = None
    _is_home = None
try:
    from lib import turns as _turns  # noqa: E402
except Exception:  # pragma: no cover - fail-open
    _turns = None
try:
    from lib import memory_gate as _memgate  # noqa: E402
except Exception:  # pragma: no cover - fail-open
    _memgate = None

MIN_FILES_SANTA = 3   # unique code files that require a Santa review
MIN_FILES_DEAD = 3    # unique code files that require a dead-code audit

# The user said stop — honour it. The WHOLE message must be consent clauses
# ("stop", "Stop. Don't do anything else", "that's all"); "stop the server and fix X"
# is a task, not consent (Santa P7).
# Kept in step with mods/mercy/hooks/lib/consent.ts (test_lead_wp8 parity cases).
_CONSENT_CLAUSE = (r"(?:(?:ok(?:ay)?|please|just)[,\s]+)?"
                   r"(?:stop(?:\s+(?:now|here|there))?|don['’]?t do anything(?:\s+else)?"
                   r"|do nothing(?:\s+else)?|leave it(?:\s+there)?|no more changes"
                   r"|that['’]?s (?:all|it|enough)|skip (?:the )?verif(?:y|ication))")
CONSENT_RE = re.compile(
    rf"^\s*{_CONSENT_CLAUSE}(?:\s*[.,;!]+\s*{_CONSENT_CLAUSE})*\s*[.!]*\s*$", re.I)

# Agents whose dispatch counts as the security scan having happened.
SECURITY_AGENTS = {"security-sentinel"}

# ~/.claude config/hook paths — Santa adversarial review not required there, and
# jcodemunch never indexes ~/.claude (index-lifecycle NEVER_INDEX), so Gate 5's
# dead-code tools cannot run on them either.
_INFRA_PATH_MARKERS = (
    ".claude/hooks/",
    ".claude/rules/",
    ".claude/scripts/",
    ".claude/docs/",
    ".claude/mcp.profiles/",
    ".claude/installer/",
    ".claude/tests/",
    ".claude/mods/",
    ".claude/workflows/",
    ".claude/plans/",
    ".claude/agents/",
    ".claude/skills/",
)


def _normalize_path(p: str) -> str:
    return p.replace("\\", "/").lower()


def _is_infra_path(path: str) -> bool:
    n = _normalize_path(path)
    return any(marker in n for marker in _INFRA_PATH_MARKERS)


def _is_infra_only_session(cid: str) -> bool:
    """True when every tracked code write is under ~/.claude config (hooks, rules, etc.)."""
    safe = _safe_cid(cid)
    doc_files = _load_json(STATE_DIR / f"{safe}.doc-enforcer.json").get("code_files", [])
    if doc_files:
        return all(_is_infra_path(str(f)) for f in doc_files)
    paths = _code_files(cid)
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
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _gate_state_path(cid: str) -> Path:
    return STATE_DIR / f"{_safe_cid(cid)}.completion-gate.json"


def _load_gate_state(cid: str) -> dict:
    data = _load_json(_gate_state_path(cid))
    return {
        "turn_key": data.get("turn_key"),
        "blocked_this_turn": bool(data.get("blocked_this_turn")),
        "failed_gates": data.get("failed_gates", []),
        "pass_advisories_sent": bool(data.get("pass_advisories_sent")),
    }


def _save_gate_state(cid: str, state: dict) -> None:
    _save_json(_gate_state_path(cid), state)


def _to_model(cid: str, text: str) -> None:
    """CLAUDE.md §11: a note only the model can act on goes to the advisory queue the next
    prompt delivers, never to the user's screen (a Stop systemMessage shows only to the user)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import dispatch_support as _sup  # noqa: PLC0415
        _sup.enqueue(cid, "hard-completion-gate", text)
    except Exception:  # noqa: BLE001
        pass


def _code_files(cid: str) -> list:
    """Unique code files written this session (desloppify state)."""
    st = _load_json(STATE_DIR / f"{_safe_cid(cid)}.desloppify.json")
    raw = st.get("code_files") or st.get("code_paths") or []
    seen, out = set(), []
    for p in raw:
        n = str(p).replace("\\", "/")
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _git_root_of(path: str) -> "Path | None":
    """HOME-guarded git root of an absolute path (lib.code_files)."""
    try:
        if not Path(path).is_absolute() or _lib_git_root is None:
            return None
        root = _lib_git_root(path)
        if root is None or (_is_home and _is_home(root)):
            return None
        return root
    except Exception:
        return None


def _session_dox_repos(cid: str) -> list:
    """Repos touched this session (via tracked code dirs) that carry a root CLAUDE.md."""
    safe = _safe_cid(cid)
    st = _load_json(STATE_DIR / f"{safe}.doc-enforcer.json")
    roots = set()
    for d in (st.get("code_dirs") or []):
        r = _git_root_of(str(d))
        if r is not None and (r / "CLAUDE.md").is_file():
            roots.add(str(r))
    return sorted(roots)


def _agents_dispatched(cid: str, since: "datetime | None" = None) -> set:
    """subagent_types dispatched this session (optionally only since `since`)."""
    p = TELEMETRY_DIR / f"{_safe_cid(cid)}.agent-dispatches.jsonl"
    out: set = set()
    if not p.is_file():
        return out
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if since is not None and _turns is not None:
                ts = _turns.to_aware(r.get("ts"))
                if ts is not None and ts < since:
                    continue
            a = (r.get("agent") or "").strip()
            if a:
                out.add(a)
    except Exception:
        pass
    return out


def _report_newer_than(roots: list, pattern: str, since: "datetime | None") -> bool:
    """True when a `pattern` file under a root or its `.claude/runs/*/` is newer than
    `since` (any age when `since` is unknown)."""
    for root in roots:
        if not isinstance(root, str) or not root.strip():
            continue
        try:
            candidates = glob.glob(os.path.join(root, pattern))
            candidates += glob.glob(os.path.join(root, ".claude", "runs", "*", pattern))
            for f in candidates:
                if not os.path.isfile(f):
                    continue
                if since is None or os.path.getmtime(f) >= since.timestamp():
                    return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Individual Gates
# ---------------------------------------------------------------------------

def gate1_tests(cid: str, n_files: int) -> tuple:
    """Gate 1: Tests — always PASS, advisory reminder only."""
    if n_files >= 3:
        return True, "Gate 1 (tests)", f"Reminder: {n_files} code files written — verify tests ran."
    return True, "Gate 1 (tests)", ""


def _repo_doc_expectations(workspace_roots: list) -> tuple:
    """Whether this session's workspace(s) define BE docs, FE docs, or linkages trees."""
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


def gate2_docs(cid: str, workspace_roots: "list | None" = None) -> tuple:
    """Gate 2: Documentation — HARD when repo has doc trees; skip when absent."""
    st = _load_json(STATE_DIR / f"{_safe_cid(cid)}.doc-enforcer.json")
    code_files = st.get("code_files", [])
    if not code_files:
        return True, "Gate 2 (docs)", ""
    if _is_infra_only_session(cid):
        return True, "Gate 2 (docs)", ""

    roots = workspace_roots if isinstance(workspace_roots, list) else []
    expect_be, expect_fe, expect_link = _repo_doc_expectations(roots)

    be_touched = st.get("be_touched", False)
    fe_touched = st.get("fe_touched", False)

    missing: list = []
    if be_touched and expect_be and not st.get("be_docs_written", False):
        missing.append("server_docs/")
    if fe_touched and expect_fe and not st.get("fe_docs_written", False):
        missing.append("frontend_docs/")
    if (be_touched or fe_touched) and expect_link and not st.get("linkages_written", False):
        missing.append("PROJECT_LINKAGES.md")

    # dox CLAUDE.md-tree requirement (Phase 7): code edited in a GIT repo that carries
    # a root CLAUDE.md → at least one CLAUDE.md must be updated this session. HOME
    # (which has a CLAUDE.md but is not a repo) never counts.
    ws_has_dox = any(
        isinstance(r, str) and r.strip() and _git_root_of(r) is not None
        and (Path(r) / "CLAUDE.md").is_file()
        for r in roots
    )
    if (ws_has_dox or _session_dox_repos(cid)) and not st.get("claude_md_written"):
        missing.append("dox CLAUDE.md (Phase 7 — update the CLAUDE.md for the dir(s) you changed)")

    if not missing:
        return True, "Gate 2 (docs)", ""
    detail = (
        f"{len(code_files)} code file(s) written but docs not updated. "
        f"Missing: {', '.join(missing)}. "
        f"Fix: dispatch the docs-sync-agent now (Agent tool, subagent_type "
        f"\"docs-sync-agent\")."
    )
    return False, "Gate 2 (docs)", detail


def gate3_security(cid: str, roots: list, turn_ts: "datetime | None") -> tuple:
    """Gate 3: Security — semi-hard when security-sensitive files changed and no
    scan evidence exists: semgrep (CLI or MCP) ran, security-sentinel was
    dispatched, or a SECURITY-REPORT.md newer than the turn exists."""
    if _is_infra_only_session(cid):
        return True, "Gate 3 (security)", ""
    st = _load_json(STATE_DIR / f"{_safe_cid(cid)}.security-scan.json")
    files = st.get("security_files", [])
    if not files:
        return True, "Gate 3 (security)", ""

    if st.get("semgrep_ran", False):
        findings = st.get("semgrep_findings", 0)
        if findings:
            return True, "Gate 3 (security)", (
                f"Semgrep reported {findings} finding(s) on security-sensitive files. "
                "Resolve HIGH/CRITICAL before shipping.")
        return True, "Gate 3 (security)", ""
    if _agents_dispatched(cid) & SECURITY_AGENTS:
        return True, "Gate 3 (security)", ""
    if _report_newer_than(roots, "SECURITY-REPORT*.md", turn_ts):
        return True, "Gate 3 (security)", ""

    detail = (
        f"{len(files)} security-sensitive file(s) modified but no scan recorded. "
        "Fix: dispatch the security-sentinel agent now (Agent tool, subagent_type "
        "\"security-sentinel\") — or run semgrep "
        "(`semgrep scan --config auto` or mcp__semgrep__semgrep_scan) on the changed "
        "auth/API files yourself, then retry."
    )
    return False, "Gate 3 (security)", detail


def gate4_santa(cid: str, n_files: int) -> tuple:
    """Gate 4: Santa Method — SEMI-HARD when >= MIN_FILES_SANTA unique code files
    were written and no review was dispatched."""
    if _is_infra_only_session(cid) or n_files < MIN_FILES_SANTA:
        return True, "Gate 4 (santa)", ""
    if _load_json(STATE_DIR / f"{_safe_cid(cid)}.santa.json").get("fired", False):
        return True, "Gate 4 (santa)", ""
    detail = (
        f"{n_files} code file(s) written. Santa Method adversarial review not dispatched. "
        "Fix: dispatch the santa-reviewer agent now (Agent tool, "
        "subagent_type \"santa-reviewer\") to run the BREAKER + SIMPLIFIER + VERIFIER "
        "passes on the diff and confirm real bugs before completing."
    )
    return False, "Gate 4 (santa)", detail


def _deadcode_done(cid: str) -> bool:
    return bool(_load_json(STATE_DIR / f"{_safe_cid(cid)}.deadcode.json").get("fired", False))


def gate5_dead_code(cid: str, n_files: int) -> tuple:
    """Gate 5: Dead-code audit — SEMI-HARD when >= MIN_FILES_DEAD unique code files
    were written and no audit was recorded."""
    if n_files < MIN_FILES_DEAD or _is_infra_only_session(cid) or _deadcode_done(cid):
        return True, "Gate 5 (dead code)", ""
    detail = (
        f"{n_files} code file(s) written but no dead-code audit recorded. "
        "Fix: dispatch the deadcode-reaper agent now (Agent tool, subagent_type "
        "\"deadcode-reaper\") — or run "
        "mcp__jcodemunch__find_dead_code / get_dead_code_v2 on your changes yourself."
    )
    return False, "Gate 5 (dead code)", detail


def gate6_decision_capture(cid: str, n_files: int) -> tuple:
    """Gate 6: Decision capture — advisory only, always PASS."""
    if n_files < 3 or _is_infra_only_session(cid):
        return True, "Gate 6 (decision capture)", ""
    safe = _safe_cid(cid)
    code_files = _load_json(STATE_DIR / f"{safe}.doc-enforcer.json").get("code_files", [])
    _ADR_PATTERNS = ("docs/adr/", "adr/", "ADR-", "ARCHITECTURE.md", "CODEX.md",
                     "decisions.md", "DECISIONS.md")
    if any(any(p.lower() in str(f).lower() for p in _ADR_PATTERNS) for f in code_files):
        return True, "Gate 6 (decision capture)", ""
    if _load_json(STATE_DIR / f"{safe}.memory-write.json").get("fired", False):
        return True, "Gate 6 (decision capture)", ""
    return True, "Gate 6 (decision capture)", (
        f"{n_files} file(s) changed but no decision record written. "
        "Consider: update CODEX.md with any new patterns or decisions, "
        "or call `mcp__memory__add_observations` to persist key facts.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _roots(payload: dict) -> list:
    roots = [r for r in (payload.get("workspace_roots") or []) if isinstance(r, str) and r.strip()]
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip() and cwd not in roots:
        roots.append(cwd)
    return roots


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.stdout.write("{}")
        return 0

    # Already re-running after our own block → never chain-block.
    if payload.get("stop_hook_active"):
        sys.stdout.write("{}")
        return 0

    _status = payload.get("status")
    if _status not in (None, "", "completed", "stopped", "interrupted"):
        sys.stdout.write("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        sys.stdout.write("{}")
        return 0

    try:
        transcript = payload.get("transcript_path") or payload.get("transcript") or ""
        turn_ts, last_prompt = (None, None)
        if _turns is not None:
            turn_ts, last_prompt = _turns.last_user_turn(transcript)
        if last_prompt and CONSENT_RE.search(last_prompt):
            sys.stdout.write("{}")  # the user said stop — the gate yields
            return 0
        turn_key = turn_ts.isoformat() if turn_ts else "?"

        # thresholds count project files only: infra never needs Santa/dead-code (B2-05)
        n_files = len([f for f in _code_files(cid) if not _is_infra_path(f)])
        roots = _roots(payload)
        gate_state = _load_gate_state(cid)

        results = [
            gate1_tests(cid, n_files),
            gate2_docs(cid, roots),
            gate3_security(cid, roots, turn_ts),
            gate4_santa(cid, n_files),
            gate5_dead_code(cid, n_files),
            gate6_decision_capture(cid, n_files),
        ]
        if _memgate is not None:  # a "remember this" prompt must end with a saved memory
            results.append(_memgate.gate7_memory(transcript, last_prompt))
        hard_failures = [(label, detail) for ok, label, detail in results if not ok]
        advisories = [detail for ok, label, detail in results if ok and detail]

        if not hard_failures:
            out: dict = {}
            if advisories and not gate_state.get("pass_advisories_sent"):
                _to_model(cid, "Completion gate: all checks passed.\n" + "\n".join(f"- {a}" for a in advisories))
                gate_state["pass_advisories_sent"] = True
            gate_state.update({"turn_key": turn_key, "blocked_this_turn": False,
                               "failed_gates": []})
            _save_gate_state(cid, gate_state)
            sys.stdout.write(json.dumps(out))
            return 0

        failed_labels = [label for label, _ in hard_failures]

        # Second Stop in the SAME turn → allow, say what was forced past. An unknown
        # turn ("?") never matches: it would carry the override into the next turn
        # (santa-diff P5); stop_hook_active above still bounds it to one block.
        if (turn_key != "?" and gate_state.get("turn_key") == turn_key
                and gate_state.get("blocked_this_turn")):
            gate_state["failed_gates"] = failed_labels
            gate_state["override_ts"] = datetime.now(timezone.utc).isoformat()
            _save_gate_state(cid, gate_state)
            _to_model(cid, "Completion gate override: " + ", ".join(failed_labels)
                      + " were left open last turn; close them now unless the user said to skip them.")
            sys.stdout.write("{}")
            return 0

        # First Stop this turn with failures → block once.
        lines = ["[COMPLETION GATE: BLOCKED]", "", "Failed gates:"]
        lines += [f"- {label}: {detail}" for label, detail in hard_failures]
        if advisories:
            lines += ["", "Advisory reminders:"] + [f"- {a}" for a in advisories]
        lines += ["", "Fix the issues listed above, then try completing again. "
                  "This gate blocks at most once per turn; the next attempt is allowed "
                  "with a note of what was skipped."]
        gate_state.update({"turn_key": turn_key, "blocked_this_turn": True,
                           "failed_gates": failed_labels,
                           "last_deny_time": datetime.now(timezone.utc).isoformat()})
        _save_gate_state(cid, gate_state)
        sys.stdout.write(json.dumps({"decision": "block", "reason": "\n".join(lines)}))
        return 0

    except Exception:
        sys.stdout.write("{}")  # fail open — never block on an exception
        return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Stop hook: verify every Skill-TOOL skill pushed into the turn actually loaded.

Deterministic + source-agnostic. Skill-injecting hooks that demand Skill-tool
invocations append their exact slug list to a per-conversation sidecar via
suite_push.push() (enforce="hard"):
  - invoke-suite-manifest.py   -> /invoke-* suite commands
  - autonomous-skill-router.py -> keyword auto-routing
This gate, at stop, unions the hard pushes for the CURRENT turn and diffs them
against the skill-invocation telemetry (skill-invocation-tracker.py). Any pushed
skill never invoked via the Skill tool => BLOCK and name it, up to MAX_NAGS times,
then FAIL OPEN with a loud warning (a renamed/bad slug can never trap the session).

v2 (P4, INVOKE-REDESIGN): agent-backed suites verify WORK, not reading. When a
pushed record carries category metadata (invoke-suite-manifest) and the category
has an `agent` in autonomous-skill-router.config.json, that category is satisfied
when EITHER its `artifact` file exists newer than the invoke timestamp OR the
agent was dispatched this session (.telemetry/{cid}.agent-dispatches.jsonl,
written by santa-method-writer.py on every Agent/Task call). Satisfied categories
drop their skill roster from the missing set — skill-load checking remains the
fallback for agent-less categories (and for the legacy inline path, where the
skills really do get loaded).

NOTE: only covers Skill-TOOL pushes. Hooks that say "read this SKILL.md path"
(fullstack-skills-reminder, ui-ux-stack-orchestrator) load by reading, not the Skill
tool, so they never appear in the invocation telemetry and are intentionally NOT gated.

Env: INVOKE_SUITE_GATE_MAX_NAGS (default 5), INVOKE_SUITE_GATE_OFF=1 to disable.

stdin:  Stop payload {conversation_id, transcript_path, stop_hook_active}
stdout: {} to allow | {"decision":"block","reason":...} to re-nag
exit:   0 (fail open on any error)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOK_DIR = Path(__file__).resolve().parent
TELEMETRY_DIR = HOOK_DIR / ".telemetry"
CONFIG_PATH = HOOK_DIR / "autonomous-skill-router.config.json"
MAX_NAGS = int(os.environ.get("INVOKE_SUITE_GATE_MAX_NAGS", "5") or "5")
GRACE = timedelta(seconds=90)  # absorb push-vs-prompt ordering jitter


def _safe_cid(cid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)


def _canon(name: str) -> str:
    return name.split(":", 1)[-1].strip().lower()


def _dt(s):
    try:
        return datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except Exception:
        return None


def _turn_dt(transcript: str):
    """Timestamp of the last real user prompt (turn boundary)."""
    try:
        last = None
        for line in open(transcript, encoding="utf-8"):
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("type") == "user":
                c = e.get("message", {}).get("content")
                if isinstance(c, str) and c.strip():
                    last = e.get("timestamp") or e.get("ts")
        return _dt(last) if last else None
    except Exception:
        return None


def _pushed(cid: str):
    """All hard push records as (dt, skills, categories). Newest-relevant filtered by caller."""
    p = TELEMETRY_DIR / f"{_safe_cid(cid)}.pushed-skills.jsonl"
    out = []
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("enforce", "hard") != "hard":
            continue
        # /invoke-* commands AND router MUST-READ pushes hard-gate the turn
        # (2026-07-18 enforcement bridge); other sources stay advisory.
        if r.get("source") not in ("invoke-cmd", "router"):
            continue
        cats = r.get("categories") or []
        out.append((_dt(r.get("ts")), r.get("skills") or [], cats if isinstance(cats, list) else []))
    return out


# ---------------------------------------------------------------------------
# v2: agent-backed category satisfaction (artifact-or-dispatch)
# ---------------------------------------------------------------------------

def _load_categories() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("categories", {}) or {}
    except Exception:
        return {}


def _artifact_glob(template: str) -> str:
    for ph in ("{date}-{slug}", "{date}", "{slug}"):
        template = template.replace(ph, "*")
    while "**" in template:
        template = template.replace("**", "*")
    while "*-*" in template:
        template = template.replace("*-*", "*")
    return template


def _artifact_roots(payload: dict) -> list:
    roots = []
    for r in (payload.get("workspace_roots") or []):
        if isinstance(r, str) and r.strip():
            roots.append(r)
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        roots.append(cwd)
    try:
        roots.append(str(Path.cwd()))
    except Exception:
        pass
    seen, out = set(), []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _artifact_exists_newer(roots: list, pattern: str, since) -> bool:
    """True when any file matching pattern in a root (or its docs/superpowers/plans/)
    is newer than the invoke window."""
    if not pattern:
        return False
    for root in roots:
        try:
            rp = Path(root)
            if not rp.is_dir():
                continue
            candidates = list(rp.glob(pattern))
            sub = rp / "docs" / "superpowers" / "plans"
            if sub.is_dir():
                candidates += list(sub.glob(pattern))
            for f in candidates:
                if not f.is_file():
                    continue
                if since is None or f.stat().st_mtime >= since.timestamp():
                    return True
        except Exception:
            continue
    return False


def _agents_dispatched(cid: str) -> set:
    """Every subagent_type dispatched this session (santa-method-writer telemetry)."""
    p = TELEMETRY_DIR / f"{_safe_cid(cid)}.agent-dispatches.jsonl"
    out = set()
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        a = (r.get("agent") or "").strip()
        if a:
            out.add(a)
    return out


def _category_skill_canon(cat_cfg: dict) -> set:
    out = set()
    for s in (cat_cfg.get("local_skills") or []):
        out.add(_canon(s))
    for s in (cat_cfg.get("superpowers_skills") or []):
        out.add(_canon(s))
    for group in (cat_cfg.get("stack_groups") or {}).values():
        if isinstance(group, list):
            for s in group:
                out.add(_canon(s))
    return out


def _invoked_since(cid: str, since) -> set:
    p = TELEMETRY_DIR / f"{_safe_cid(cid)}.skill-invocations.jsonl"
    if not p.is_file():
        return set()
    out = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if since is not None:
            rt = _dt(r.get("ts"))
            if rt is not None and rt < since:
                continue
        sk = (r.get("skill") or "").strip()
        if sk:
            out.add(_canon(sk))
    return out


def main() -> int:
    if os.environ.get("INVOKE_SUITE_GATE_OFF") == "1":
        sys.stdout.write("{}\n"); return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        sys.stdout.write("{}\n"); return 0

    cid = (payload.get("conversation_id") or payload.get("session_id") or "").strip()
    if not cid:
        sys.stdout.write("{}\n"); return 0

    pushes = _pushed(cid)
    if not pushes:
        sys.stdout.write("{}\n"); return 0

    # Current-turn window: prefer the transcript's last user-prompt ts; else anchor on
    # the most recent push (current-turn pushes cluster at turn start).
    transcript = payload.get("transcript_path") or payload.get("transcript") or ""
    turn_dt = _turn_dt(transcript) if transcript and Path(transcript).is_file() else None
    if turn_dt is None:
        anchors = [d for d, _, _ in pushes if d is not None]
        turn_dt = max(anchors) if anchors else None
    window = (turn_dt - GRACE) if turn_dt else None

    expected: list[str] = []
    seen = set()
    turn_cats: list[str] = []
    for d, skills, pcats in pushes:
        if window is not None and d is not None and d < window:
            continue
        for s in skills:
            if _canon(s) not in seen:
                seen.add(_canon(s))
                expected.append(s)
        for c in pcats:
            if c not in turn_cats:
                turn_cats.append(c)
    if not expected:
        sys.stdout.write("{}\n"); return 0

    invoked = _invoked_since(cid, window)
    missing = sorted(e for e in expected if _canon(e) not in invoked)

    # v2: agent-backed categories are satisfied by WORK (artifact newer than the
    # invoke, or the agent dispatched this session) — drop their skill roster
    # from the missing set. Agent-less categories keep pure skill-load checking.
    if missing and turn_cats:
        cats_cfg = _load_categories()
        dispatched = None  # lazy
        roots = None
        satisfied: set = set()
        for c in turn_cats:
            cc = cats_cfg.get(c) or {}
            agent = (cc.get("agent") or "").strip()
            if not agent:
                continue
            if dispatched is None:
                dispatched = _agents_dispatched(cid)
                roots = _artifact_roots(payload)
            ok = agent in dispatched
            if not ok:
                ok = _artifact_exists_newer(roots, _artifact_glob(cc.get("artifact") or ""), window)
            if ok:
                satisfied |= _category_skill_canon(cc)
        if satisfied:
            missing = [m for m in missing if _canon(m) not in satisfied]

    state_p = TELEMETRY_DIR / f"{_safe_cid(cid)}.suite-gate.json"
    turn_key = turn_dt.isoformat() if turn_dt else "?"
    try:
        st = json.loads(state_p.read_text(encoding="utf-8"))
    except Exception:
        st = {}
    if st.get("turn") != turn_key:
        st = {"turn": turn_key, "nags": 0}

    if not missing:
        try: state_p.unlink()
        except Exception: pass
        sys.stdout.write("{}\n"); return 0

    nags = int(st.get("nags", 0)) + 1
    if nags > MAX_NAGS:
        sys.stderr.write(
            f"⚠️ SUITE GATE failed open after {MAX_NAGS} nags — pushed skills never "
            f"invoked this turn: {', '.join(missing)}. Allowing stop.\n"
        )
        try: state_p.unlink()
        except Exception: pass
        sys.stdout.write("{}\n"); return 0

    st["nags"] = nags
    try:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        state_p.write_text(json.dumps(st), encoding="utf-8")
    except Exception:
        pass

    reason = (
        f"SUITE GATE ({nags}/{MAX_NAGS}): {len(expected) - len(missing)}/{len(expected)} "
        f"pushed skills loaded. You did NOT invoke these via the Skill tool this turn:\n  - "
        + "\n  - ".join(missing)
        + "\nInvoke each missing skill via the Skill tool now, then finish. Do not skip any."
        + "\n(Agent-backed suites pass automatically instead: dispatch the category's "
          "specialist agent and/or produce its artifact — see the command's ACT B.)"
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("{}\n")
        sys.exit(0)

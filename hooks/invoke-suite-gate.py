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
    """All hard push records as (dt, skills). Newest-relevant filtered by caller."""
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
        # ponytail: only EXPLICIT /invoke-* commands hard-gate the turn. Keyword
        # auto-router pushes are advisory regardless of any stale enforce=hard flag.
        if r.get("source") != "invoke-cmd":
            continue
        out.append((_dt(r.get("ts")), r.get("skills") or []))
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
        anchors = [d for d, _ in pushes if d is not None]
        turn_dt = max(anchors) if anchors else None
    window = (turn_dt - GRACE) if turn_dt else None

    expected: list[str] = []
    seen = set()
    for d, skills in pushes:
        if window is not None and d is not None and d < window:
            continue
        for s in skills:
            if _canon(s) not in seen:
                seen.add(_canon(s))
                expected.append(s)
    if not expected:
        sys.stdout.write("{}\n"); return 0

    invoked = _invoked_since(cid, window)
    missing = sorted(e for e in expected if _canon(e) not in invoked)

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
    )
    sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("{}\n")
        sys.exit(0)

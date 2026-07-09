#!/usr/bin/env python3
"""Stop hook: weekly retro trigger.

Emits a followup_message prompting the user to run /retro when:
  1. Today is Friday (weekly cadence), OR
  2. More than SESSION_THRESHOLD sessions have passed since the last /retro.

State persisted in: ~/.claude/hooks/.state/retro-tracker.json
  {
    "last_retro_ts": "2026-05-23T10:00:00Z",  // ISO8601 when /retro was last run
    "sessions_since_retro": 3,                 // incremented each Stop
    "total_sessions": 47                       // lifetime session count
  }

argv[1]: "stop" (only mode supported)
stdin:   Claude Code Stop hook JSON payload
stdout:  JSON with followup_message or {} (never deny)
exit:    always 0 (fail open)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, date
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / ".state"
TRACKER_FILE = STATE_DIR / "retro-tracker.json"

SESSION_THRESHOLD = 10   # sessions since last retro before triggering
FRIDAY_WEEKDAY = 4       # Python: Monday=0, Friday=4


def _load_tracker() -> dict:
    """Load retro tracker state; return defaults if missing or corrupt."""
    if not TRACKER_FILE.is_file():
        return {
            "last_retro_ts": None,
            "sessions_since_retro": 0,
            "total_sessions": 0,
        }
    try:
        data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
        return {
            "last_retro_ts": data.get("last_retro_ts"),
            "sessions_since_retro": int(data.get("sessions_since_retro", 0)),
            "total_sessions": int(data.get("total_sessions", 0)),
        }
    except (json.JSONDecodeError, OSError, ValueError):
        return {
            "last_retro_ts": None,
            "sessions_since_retro": 0,
            "total_sessions": 0,
        }


def _save_tracker(state: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        TRACKER_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def _is_retro_session(payload: dict) -> bool:
    """Detect if this session ran the /retro skill.

    Heuristic: check if the Stop payload's message or transcript hint contains
    'retro' keyword. The Stop hook receives limited context — we use a best-effort
    check on conversation_id matching a known retro session marker.

    More reliable: check if ~/.gstack/retro/ has a file written today.
    """
    # Check if gstack retro output was written today
    today_str = date.today().isoformat()
    retro_dirs = [
        Path.home() / ".gstack" / "retro",
        Path.home() / ".claude" / "telemetry",
    ]
    for d in retro_dirs:
        if d.is_dir():
            for f in d.iterdir():
                if today_str in f.name and "retro" in f.name.lower():
                    return True

    # Fallback: check conversation payload for retro hints
    transcript = payload.get("transcript", [])
    for turn in transcript[-5:] if isinstance(transcript, list) else []:
        content = str(turn.get("content", "")).lower()
        if "/retro" in content or "weekly retro" in content:
            return True

    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.stdout.write("{}")
        return 0

    tracker = _load_tracker()

    # Always increment session count
    tracker["sessions_since_retro"] += 1
    tracker["total_sessions"] += 1

    # Check if this session was a retro run — if so, reset counter
    if _is_retro_session(payload):
        tracker["last_retro_ts"] = datetime.now(timezone.utc).isoformat()
        tracker["sessions_since_retro"] = 0
        _save_tracker(tracker)
        sys.stdout.write("{}")
        return 0

    now = datetime.now(timezone.utc)
    today_weekday = now.weekday()
    sessions_since = tracker["sessions_since_retro"]

    # Determine if retro should be triggered
    is_friday = today_weekday == FRIDAY_WEEKDAY
    over_threshold = sessions_since >= SESSION_THRESHOLD

    should_trigger = is_friday or over_threshold

    _save_tracker(tracker)

    if not should_trigger:
        sys.stdout.write("{}")
        return 0

    # Build the trigger message
    reason_parts = []
    if is_friday:
        reason_parts.append("today is Friday (weekly retro day)")
    if over_threshold:
        reason_parts.append(f"{sessions_since} sessions since last retro (threshold: {SESSION_THRESHOLD})")

    reason = " and ".join(reason_parts)

    last_retro_str = tracker.get("last_retro_ts")
    if last_retro_str:
        try:
            last_retro = datetime.fromisoformat(last_retro_str.replace("Z", "+00:00"))
            days_ago = (now - last_retro).days
            last_retro_info = f"Last retro: {days_ago} days ago ({last_retro.strftime('%Y-%m-%d')})."
        except (ValueError, TypeError):
            last_retro_info = "Last retro: unknown."
    else:
        last_retro_info = "No retro on record."

    msg = (
        f"Weekly retro due — {reason}. "
        f"{last_retro_info} "
        f"Run `/retro` to review skill usage patterns, gate outcomes, and improvements. "
        f"Total sessions logged: {tracker['total_sessions']}."
    )

    out = {"followup_message": msg}
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stdout.write("{}")
        sys.exit(0)

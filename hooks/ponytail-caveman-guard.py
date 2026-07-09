#!/usr/bin/env python3
"""Force ponytail + caveman to be always-on, top-priority skills.

Three modes (argv[1]):
  session-start : ensure state dir + touch both flag files, inject directive
  pre-tool-use  : deny any tool while either flag is missing (Skill always allowed)
  post-skill    : when ponytail/caveman is invoked, (re)write its flag -> unblock path

Fails OPEN on any error so it can never brick a session.
"""
import json
import os
import sys

STATE_DIR = os.path.expanduser("~/.claude/state")
FLAGS = {
    "ponytail": os.path.join(STATE_DIR, "ponytail-active"),
    "caveman": os.path.join(STATE_DIR, "caveman-active"),
}


def _touch(path):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(path, "w") as f:
        f.write("on\n")


def _missing():
    return [name for name, path in FLAGS.items() if not os.path.exists(path)]


def session_start():
    for path in FLAGS.values():
        _touch(path)
    ctx = (
        "ENFORCED TOP-PRIORITY, ALWAYS-ON (outrank other style guidance): "
        "ponytail (laziest working solution: YAGNI, stdlib/native first, shortest diff) "
        "+ caveman (ultra-compressed prose, ~75% fewer tokens, full technical accuracy). "
        "Both are mandatory in EVERY response. Flags set in ~/.claude/state/. "
        "The pre-tool-use gate denies ALL tools if either is turned off — re-enable by invoking the skills."
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": ctx,
        }
    }))


def pre_tool_use():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # fail open
    tool = data.get("tool_name", "")
    if tool == "Skill":  # always allow re-enabling
        return
    missing = _missing()
    if not missing:
        return  # both on -> allow
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "Please use ponytail and caveman. Both must be ACTIVE (top-priority, always-on). "
                "Currently off: " + ", ".join(missing) + ". "
                "Invoke the ponytail and caveman skills to re-enable, then retry."
            ),
        }
    }))


def post_skill():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    name = (data.get("tool_input", {}) or {}).get("skill", "") or ""
    name = name.lower()
    for key, path in FLAGS.items():
        if key in name:
            _touch(path)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "session-start":
            session_start()
        elif mode == "pre-tool-use":
            pre_tool_use()
        elif mode == "post-skill":
            post_skill()
    except Exception:
        pass  # fail open — never block on error


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ponytail-caveman-guard.py — SessionStart advisory: the ponytail + caveman directive.

Emits the always-on style directive once per session start. No flag files and no
gates any more (the former deny-all pre-tool-use mode and the post-skill flag
re-touch were removed 2026-09-27). Fails OPEN on any error.

argv[1]: "session-start"      stdout: hookSpecificOutput.additionalContext or {}
"""
import json
import sys

_DIRECTIVE = (
    "ALWAYS-ON STYLE (outranks other style guidance): ponytail (laziest working "
    "solution: YAGNI, stdlib/native first, shortest diff) + caveman (ultra-compressed "
    "prose to the user, full technical accuracy). Both apply to every response."
)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "session-start"
    try:
        sys.stdin.read()
    except Exception:  # noqa: BLE001
        pass
    if mode == "session-start":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": _DIRECTIVE,
        }}))
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001
        print("{}")

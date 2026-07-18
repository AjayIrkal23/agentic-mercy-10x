#!/usr/bin/env python3
"""opus-guard: the agent `name` must carry the resolved model as a trailing segment.

Run: python3 ~/.claude/hooks/tests/test_opus_guard_name.py
Covers all three models, not just opus. Session flags in ~/.claude/state/ are moved
aside for the smart-routing cases and restored on exit.
"""
import json
import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parent.parent / "opus-guard.py"
STATE = Path.home() / ".claude" / "state"
FLAGS = ["sonnet-only-mode", "opus-only-mode", "fable-only-mode"]


def guard(tool_input: dict) -> dict:
    out = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"tool_name": "Agent", "tool_input": tool_input}),
        capture_output=True, text=True,
    ).stdout.strip()
    # allow-unchanged is an empty body or a bare "{}" — the call proceeds as written
    payload = json.loads(out) if out else {}
    hook = payload.get("hookSpecificOutput")
    return hook["updatedInput"] if hook else dict(tool_input)


def check(label, tool_input, want_name):
    got = guard(tool_input).get("name")
    assert got == want_name, f"{label}: expected {want_name!r}, got {got!r}"
    print(f"  ok  {label:26} -> {got}")


def main():
    held = [(STATE / f, (STATE / f).read_bytes()) for f in FLAGS if (STATE / f).is_file()]
    for path, _ in held:
        path.unlink()
    try:
        print("smart routing (no session flag):")
        check("sonnet via pinned agent", {"name": "map-flow", "description": "Map it",
                                          "subagent_type": "Explore"}, "map-flow-sonnet")
        check("fable via pinned agent", {"name": "build-api", "description": "Build it",
                                         "subagent_type": "backend-implementor-specialist"},
              "build-api-fable")
        check("opus via explicit model", {"name": "design-sys", "description": "[opus] Design",
                                          "model": "opus", "subagent_type": "general-purpose"},
              "design-sys-opus")

        print("edge cases:")
        # a stale suffix is replaced, never stacked
        check("re-suffix not stacked", {"name": "map-flow-fable", "description": "Map it",
                                        "subagent_type": "Explore"}, "map-flow-sonnet")
        # already correct -> hook returns allow-unchanged, name survives
        check("idempotent", {"name": "map-flow-sonnet", "description": "[sonnet] Map it",
                             "model": "sonnet", "subagent_type": "Explore"}, "map-flow-sonnet")
        # names are capped at 64 chars by the Agent tool's own regex
        long_name = guard({"name": "a" * 60, "description": "x",
                           "subagent_type": "Explore"})["name"]
        assert len(long_name) <= 64 and long_name.endswith("-sonnet"), long_name
        print(f"  ok  {'64-char cap':26} -> len={len(long_name)}")
        # no name supplied -> the hook must not invent one (it is the SendMessage address)
        assert "name" not in guard({"description": "x", "subagent_type": "Explore"})
        print(f"  ok  {'absent name untouched':26} -> not invented")

        print("session flag forces the tier for every agent:")
        (STATE / "opus-only-mode").touch()
        check("flag overrides pin", {"name": "map-flow", "description": "Map it",
                                     "subagent_type": "Explore"}, "map-flow-opus")
        (STATE / "opus-only-mode").unlink()
    finally:
        for path, data in held:
            path.write_bytes(data)
    print(f"\nPASS — flags restored: {[p.name for p, _ in held] or 'none were set'}")


if __name__ == "__main__":
    main()

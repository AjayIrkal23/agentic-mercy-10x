#!/usr/bin/env python3
"""hookify-gate.py — repo-local hookify rules (`<repo>/.claude/hookify.<name>.local.md`), ECC hookify runtime
ported to one Python link. Three link ids run this script: `hookify-gate` (pre-tool-use GATE on
Bash/PowerShell/Write/Edit/MultiEdit/NotebookEdit), `hookify-prompt` (user-prompt-submit advisory) and
`hookify-stop` (stop gate link, never blocks; honours `stop_hook_active`).

Rules are untrusted repo files with hard caps (lib/hookify_rules.py). Output:
- PreToolUse: a matched `action: block` rule denies (blockers' messages only); `warn` rules add context.
  The deny is not routed through lib/gate_mode: `block` is a policy the user wrote into the repo, and
  the way past it is to edit or disable the rule file, not to retry.
- UserPromptSubmit: always `additionalContext` (dispatch forwards only that from an advisory link).
- Stop: a top-level `systemMessage`, never a block (dispatch forwards a Stop gate's systemMessage; Stop
  accepts no hookSpecificOutput). On both, a `block` rule's line says "(block requested; advisory on this event)".
Every message line starts `[untrusted local rule <name>]`, is clipped to 2,000 chars, and at most 5 rules
are shown. No rules dir, no repo, cwd = $HOME, malformed stdin or any error: `{}`, exit 0.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib import hookify_rules as hr  # noqa: E402

_EVENT_NAMES = {"bash": "PreToolUse", "file": "PreToolUse", "prompt": "UserPromptSubmit", "stop": "Stop"}


def _telemetry(**fields) -> None:
    try:
        from lib import hook_telemetry
        hook_event = fields.pop("event_name", "PreToolUse")
        fields["rule_event"] = fields.pop("event", "")  # `event` is record()'s own positional name
        hook_telemetry.record(hook_event, "hookify-gate", **fields)
    except Exception:  # noqa: BLE001
        pass


def _clip(text: str) -> str:
    return text if len(text) <= hr.MAX_MESSAGE else text[:hr.MAX_MESSAGE] + " …"


def _message(rules: list, advisory_event: bool) -> str:
    lines = []
    for r in rules[:hr.MAX_SHOWN]:
        line = f"[untrusted local rule {r['name']}] {_clip(r.get('message') or '')}"
        if advisory_event and r.get("action") == "block":
            line += " (block requested; advisory on this event)"
        lines.append(line)
    if len(rules) > hr.MAX_SHOWN:
        lines.append(f"(+{len(rules) - hr.MAX_SHOWN} more)")
    return "\n\n".join(lines)


def _repo_root(payload: dict):
    try:
        from lib import repo_context
        repo = repo_context.active_repo(payload)
    except Exception:  # noqa: BLE001
        return None
    if repo is None:
        return None
    try:
        if Path(repo.root).resolve() == Path.home().resolve():  # a container, never a repo
            return None
    except (OSError, RuntimeError):
        return None
    return repo.root


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        print("{}")
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0
    alias = hr.event_alias(payload)
    if not alias or payload.get("stop_hook_active"):
        print("{}")
        return 0
    root = _repo_root(payload)
    if not root or not hr.rules_dir(root).is_dir():
        print("{}")
        return 0
    sid = str(payload.get("session_id") or "")
    event_name = _EVENT_NAMES[alias]
    rules, diags = hr.load_rules(root)
    if diags:
        _telemetry(event_name=event_name, decision="diag", diagnostics=diags[:10], event=alias, session=sid)
    if not rules:
        print("{}")
        return 0
    matched, more = hr.evaluate(rules, alias, payload, deadline=time.monotonic() + hr.MAX_EVAL_S)
    if more:
        late = any(d.startswith("deadline:") for d in more)
        _telemetry(event_name=event_name, decision="deadline" if late else "diag", diagnostics=more[:10],
                   event=alias, session=sid)
    if not matched:
        print("{}")
        return 0
    if event_name == "PreToolUse":
        blockers = [r for r in matched if r.get("action") == "block"]
        if blockers:
            _telemetry(decision="deny", rules=[r["name"] for r in blockers], event=alias, session=sid)
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                     "permissionDecisionReason": _message(blockers, False)}}))
            return 0
        _telemetry(decision="warn", rules=[r["name"] for r in matched], event=alias, session=sid)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "additionalContext": _message(matched, False)}}))
        return 0
    _telemetry(event_name=event_name, decision="warn", rules=[r["name"] for r in matched], event=alias, session=sid)
    if event_name == "Stop":  # Stop takes only a top-level block / systemMessage (REVIEW2 Fix 4)
        print(json.dumps({"systemMessage": _message(matched, True)}))
        return 0
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event_name,
                                             "additionalContext": _message(matched, True)}}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - fail open
        print("{}")
        raise SystemExit(0)

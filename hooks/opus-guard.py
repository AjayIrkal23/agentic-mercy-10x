#!/usr/bin/env python3
"""
opus-guard.py — PreToolUse hook for the Agent tool: the SINGLE source of truth for
subagent model routing.

Goal (per user policy): Sonnet is the default for EVERY subagent. Opus is reserved
for HEAVY/complex work or UI/UX work only. Fable runs ONLY when the user explicitly
asks for it (label [fable] / model:"fable" / fable-only-mode flag) — it is never an
automatic choice. Everything else — small, medium, even "a bit complex" — runs on
Sonnet.

Why this hook must PIN the model explicitly:
  The main session runs on Opus. The Agent tool, when `model` is unset, makes the
  subagent INHERIT the parent model (= Opus). So leaving `model` unset would silently
  send every subagent to Opus. This router therefore ALWAYS writes an explicit
  `model` ("sonnet" or "opus"); it never leaves the choice to inheritance.

Resolution order (first match wins) -> the required model:
  1. sonnet-only-mode flag  -> sonnet   (kill-switch; overrides everything)
  2. opus-only-mode flag     -> opus     (force-opus session)
  3. fable-only-mode flag    -> fable    (force-fable session)
  4. subagent_type is an OPUS-only agent (frontend-uiux-designer) -> opus  (UI/UX)
  5. subagent_type is a SONNET-only agent (Explore, claude-code-guide) -> sonnet
  6. explicit model:"opus"/"sonnet"/"fable" param -> honor it (deliberate choice)
  7. description label [opus]/[sonnet]/[fable]     -> use the label (explicit signal)
  8. nothing specified                              -> sonnet (the cheap default)

Then it pins `model` to the resolved value AND aligns the visible
[sonnet]/[opus]/[fable] label so the label never lies about what runs.

The main model should STILL write the [sonnet]/[opus] prefix on every Agent call
(see the "Agent tool" rule in ~/.claude/CLAUDE.md) so routing stays explicit — this
hook is the safety net + the thing that makes the label real.

Protocol:
  stdin:  {"tool_name":"Agent","tool_input":{"description":"...","model":"...","subagent_type":"..."}}
  stdout: {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",
           "updatedInput":{...},"additionalContext":"..."}}  to normalize + allow,
          or {} to allow unchanged.
  exit:   always 0 (fail-open).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "state"
OPUS_ONLY_FLAG = STATE_DIR / "opus-only-mode"
SONNET_ONLY_FLAG = STATE_DIR / "sonnet-only-mode"
FABLE_ONLY_FLAG = STATE_DIR / "fable-only-mode"

SONNET_ONLY_AGENTS = {"explore", "claude-code-guide"}
OPUS_ONLY_AGENTS = {"frontend-uiux-designer", "implementation-engineer"}

VALID_MODELS = {"sonnet", "opus", "fable"}

PREFIX_RE = re.compile(r"^\[(sonnet|opus|fable)\]\s", re.IGNORECASE)


def _allow_unchanged() -> int:
    print("{}")
    return 0


def _resolve_required(subagent_type: str, model: str, description: str) -> tuple[str, str]:
    """Return (required_model, reason)."""
    if SONNET_ONLY_FLAG.is_file():
        return "sonnet", "sonnet-only-mode active"
    if OPUS_ONLY_FLAG.is_file():
        return "opus", "opus-only-mode active"
    if FABLE_ONLY_FLAG.is_file():
        return "fable", "fable-only-mode active"
    if subagent_type in OPUS_ONLY_AGENTS:
        return "opus", f"'{subagent_type}' is a UI/UX (opus) agent"
    if subagent_type in SONNET_ONLY_AGENTS:
        return "sonnet", f"'{subagent_type}' is a sonnet-only agent"
    if model in VALID_MODELS:
        return model, "explicit model param"
    m = PREFIX_RE.match(description)
    if m:
        return m.group(1).lower(), "description label"
    return "sonnet", "default (no opus/fable signal)"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return _allow_unchanged()

    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return _allow_unchanged()

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return _allow_unchanged()

    description = tool_input.get("description", "") or ""
    model = (tool_input.get("model") or "").lower()
    subagent_type = (tool_input.get("subagent_type") or "").lower()

    required, reason = _resolve_required(subagent_type, model, description)

    # Align the visible label.
    m = PREFIX_RE.match(description)
    current_prefix = m.group(1).lower() if m else None
    body = description[m.end():] if m else description

    updated: dict[str, object] = {}
    if current_prefix != required:
        updated["description"] = f"[{required}] {body}"
    # ALWAYS pin the model explicitly so an unset model never inherits the Opus parent.
    if model != required:
        updated["model"] = required

    if not updated:
        return _allow_unchanged()

    # Emit the FULL tool_input with overrides applied (some harness versions REPLACE
    # tool_input with updatedInput instead of merging — returning only changed keys
    # would drop required params and fail schema validation).
    full_input = dict(tool_input)
    full_input.update(updated)

    note = (
        f"opus-guard: subagent routed to [{required}] — {reason}. "
        "Sonnet is the default; Opus is reserved for heavy/complex or UI/UX subagent "
        "tasks; Fable runs only when YOU explicitly ask ([fable] / model:fable / "
        "fable-only-mode). Write the [sonnet]/[opus]/[fable] prefix yourself to keep "
        "routing explicit."
    )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": full_input,
            "additionalContext": note,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

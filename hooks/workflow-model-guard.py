#!/usr/bin/env python3
"""
workflow-model-guard.py — PreToolUse hook for the **Workflow** tool.

THE PROBLEM IT SOLVES (the real token burn):
  The Workflow tool's `agent(prompt, opts)` calls inherit the main-loop model when
  `opts.model` is omitted. The main session runs on Opus, so EVERY workflow agent
  that forgets a model silently fans out on Opus. These dispatches happen INSIDE the
  workflow runtime and never pass through `opus-guard.py` (which only sees the Agent
  tool). A single workflow can spawn dozens of agents — all on Opus. That is the
  burn the user reported.

THE FIX:
  Rewrite the inline workflow `script` before it runs so that every `agent(...)` call
  routes through a tiny injected wrapper `__wfAgent` that:
    - HONORS an explicit `opts.model` (sonnet/opus/fable) — your deliberate per-task
      override is never touched;
    - auto-promotes the UI/UX agent (agentType 'frontend-uiux-designer') to opus and
      keeps Explore/claude-code-guide on sonnet (mirrors opus-guard's exceptions);
    - otherwise DEFAULTS to sonnet (never inherits the Opus parent);
    - and if a session flag is set, FORCES that model on every agent (kill-switch):
        ~/.claude/state/sonnet-only-mode -> force sonnet (wins over everything)
        ~/.claude/state/opus-only-mode   -> force opus
        ~/.claude/state/fable-only-mode  -> force fable

  The rewrite is a single safe token substitution (`agent(` -> `__wfAgent(`) plus a
  prepended wrapper; it does NOT try to parse each opts object, so it is robust.

  The injected `__wfAgent` wrapper (see `_build_wrapper`) is arg-drop safe:
    - it forwards EVERY argument via `(p, opts, ...rest) => __wfOrigAgent(p, o, ...rest)`
      (a 3rd+ positional arg — callback, abort signal, args payload — is never lost);
    - a 2nd arg that is not a plain object (string / function / number / array) is passed
      through completely untouched (a shape we can't safely rewrite is never corrupted).

SAFETY (fail-open, never corrupt a script):
  - Only inline `script` is rewritten. `scriptPath` / `name` (saved/on-disk workflows)
    are left untouched with an advisory — we never silently mutate a file on disk.
  - If the script is already processed (`__wfAgent` present) -> left unchanged.
  - No `export const meta = {` block -> the wrapper is prepended at position 0 (it only
    references the `agent` runtime global, so it is safe at the top) and pinning still
    happens. Only a meta block whose braces cannot be matched -> left unchanged + advisory.
  - Any exception -> allow unchanged. The hook can never block a workflow.

Protocol:
  stdin:  {"tool_name":"Workflow","tool_input":{"script":"...", ...}}
  stdout: {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",
           "updatedInput":{...},"additionalContext":"..."}}  to rewrite + allow,
          or {} to allow unchanged.
  exit:   always 0 (fail-open).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "state"
SONNET_ONLY_FLAG = STATE_DIR / "sonnet-only-mode"
OPUS_ONLY_FLAG = STATE_DIR / "opus-only-mode"
FABLE_ONLY_FLAG = STATE_DIR / "fable-only-mode"

MARKER = "__wfAgent"
# Match a bare `agent(` call (the workflow global), not `__wfAgent(`, `myagent(`,
# `agentType`, etc. \b prevents matching when preceded by a word char like `_`.
AGENT_CALL_RE = re.compile(r"\bagent\s*\(")
META_RE = re.compile(r"export\s+const\s+meta\s*=\s*\{")


def _allow_unchanged() -> int:
    print("{}")
    return 0


def _advisory(note: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "additionalContext": note,
        }
    }))
    return 0


def _forced_model() -> str | None:
    """Session kill-switch flag -> forced model, or None for smart routing."""
    if SONNET_ONLY_FLAG.is_file():
        return "sonnet"
    if OPUS_ONLY_FLAG.is_file():
        return "opus"
    if FABLE_ONLY_FLAG.is_file():
        return "fable"
    return None


def _meta_end_index(script: str) -> int | None:
    """Return the index just past the meta declaration (after its closing brace and
    an optional trailing semicolon), or None if it can't be safely located.

    Brace-matches from the meta object's opening `{`, skipping braces inside string
    literals (', ", `). meta is a 'pure literal', so this is reliable in practice.
    """
    m = META_RE.search(script)
    if not m:
        return None
    i = m.end() - 1  # position of the opening '{'
    depth = 0
    n = len(script)
    quote: str | None = None
    while i < n:
        c = script[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"', "`"):
            quote = c
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                j = i + 1
                # consume an optional trailing semicolon
                while j < n and script[j] in " \t":
                    j += 1
                if j < n and script[j] == ";":
                    j += 1
                return j
        i += 1
    return None


def _build_wrapper(forced: str | None) -> str:
    forced_js = f"'{forced}'" if forced else "null"
    return (
        "\n/* injected by workflow-model-guard: default subagents to sonnet */\n"
        "const __wfOrigAgent = agent;\n"
        "const __wfForce = " + forced_js + ";\n"
        "const __wfOpusAgents = new Set(['frontend-uiux-designer']);\n"
        "const __wfSonnetAgents = new Set(['explore', 'claude-code-guide']);\n"
        "const __wfAgent = (p, opts, ...rest) => {\n"
        # Defect 2: a 2nd arg we can't safely rewrite (string/function/number/array) is
        # passed through with ALL args untouched — never replaced by {} or mutated.
        "  if (opts !== undefined && (typeof opts !== 'object' || Array.isArray(opts))) {\n"
        "    return __wfOrigAgent(p, opts, ...rest);\n"
        "  }\n"
        "  const o = opts ? { ...opts } : {};\n"
        # Defect 1: forward every trailing argument via ...rest, never truncate to 2.
        "  if (__wfForce) { o.model = __wfForce; return __wfOrigAgent(p, o, ...rest); }\n"
        "  if (!o.model) {\n"
        "    const at = (o.agentType || '').toLowerCase();\n"
        "    if (__wfOpusAgents.has(at)) o.model = 'opus';\n"
        "    else if (__wfSonnetAgents.has(at)) o.model = 'sonnet';\n"
        "    else o.model = 'sonnet';\n"
        "  }\n"
        "  return __wfOrigAgent(p, o, ...rest);\n"
        "};\n"
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return _allow_unchanged()

    if not isinstance(payload, dict) or payload.get("tool_name") != "Workflow":
        return _allow_unchanged()

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return _allow_unchanged()

    script = tool_input.get("script")

    # Non-inline workflows: we never mutate on-disk / saved workflows. Advise instead.
    if not isinstance(script, str) or not script.strip():
        if tool_input.get("scriptPath") or tool_input.get("name"):
            return _advisory(
                "workflow-model-guard: this workflow runs from scriptPath/name, so its "
                "agent() model defaults are NOT auto-pinned. Ensure each agent() passes "
                "an explicit model (default 'sonnet') or its agents will inherit the "
                "Opus parent and burn tokens."
            )
        return _allow_unchanged()

    # Already processed (e.g. resume) -> leave it alone.
    if MARKER in script:
        return _allow_unchanged()

    # No agent() calls -> nothing to do.
    if not AGENT_CALL_RE.search(script):
        return _allow_unchanged()

    try:
        # Defect 3: distinguish "no meta block" (prepend the wrapper at the top and pin)
        # from "meta present but braces unmatched" (truly unparseable -> advise, no mutate).
        if META_RE.search(script) is None:
            end = 0  # no meta -> the whole script is the body; wrapper goes at position 0
        else:
            end = _meta_end_index(script)
            if end is None:
                return _advisory(
                    "workflow-model-guard: the meta block's braces could not be matched, "
                    "so agent() models were NOT auto-pinned. Pass an explicit model to "
                    "every agent() (default 'sonnet') to avoid inheriting the Opus parent."
                )

        forced = _forced_model()
        head = script[:end]
        body = script[end:]
        # Single safe substitution in the body: agent( -> __wfAgent(
        new_body = AGENT_CALL_RE.sub(MARKER + "(", body)
        new_script = head + _build_wrapper(forced) + new_body
    except Exception:
        return _allow_unchanged()

    full_input = dict(tool_input)
    full_input["script"] = new_script

    if forced:
        note = (
            f"workflow-model-guard: {forced}-only-mode active — every workflow agent() "
            f"FORCED to {forced}."
        )
    else:
        note = (
            "workflow-model-guard: workflow agent() calls without an explicit model now "
            "default to SONNET (UI/UX agentType -> opus). Pass {model:'opus'} or "
            "{model:'fable'} per agent to override; this stops workflow agents from "
            "inheriting the Opus parent and burning tokens."
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

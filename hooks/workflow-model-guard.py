#!/usr/bin/env python3
"""
workflow-model-guard.py — PreToolUse hook for the **Workflow** tool.

THE PROBLEM IT SOLVES (the real token burn):
  A Workflow `agent(prompt, opts)` call inherits the main-loop model when `opts.model`
  is omitted. The main session runs on Opus, so every workflow agent that forgets a
  model silently fans out on Opus. These dispatches happen INSIDE the workflow runtime
  and never pass through `opus-guard.py` (which only sees the Agent tool).

THE FIX:
  Rewrite the inline workflow `script` before it runs so every `agent(...)` call goes
  through an injected wrapper `__wfAgent` (lib/workflow_script.build_wrapper) that:
    - HONORS an explicit `opts.model` (sonnet/opus/fable);
    - pins the model-policy agent_pins: the opus judges (santa, uiux, plan, spec,
      debug) to opus, Explore/claude-code-guide to sonnet; opus-guard's per-prompt
      escalation is not applied here;
    - otherwise DEFAULTS to sonnet (never inherits the Opus parent);
    - FORCES one model on every agent when a session flag
      (~/.claude/state/{sonnet,opus,fable}-only-mode, sonnet wins) or the per-project
      mode (lib/model_mode) is set.
  The rewrite is one safe token substitution (`agent(` -> `__wfAgent(`) plus the
  prepended wrapper, which forwards every argument and passes a non-object 2nd arg
  through untouched.

SAFETY (fail-open, never corrupt a script):
  - Only inline `script` is rewritten. `scriptPath` / `name` (saved/on-disk workflows)
    are left untouched with an advisory — a file on disk is never mutated.
  - Already processed (`__wfAgent` present) -> unchanged.
  - No `export const meta = {` block -> the wrapper goes at position 0 and pinning still
    happens; a meta block whose braces cannot be matched -> unchanged + advisory.
  - Any exception -> allow unchanged. The hook can never block a workflow.

Protocol: stdin {"tool_name":"Workflow","tool_input":{"script":"...", ...}}; stdout a
PreToolUse `updatedInput` + `additionalContext`, or {} to allow unchanged; exit 0.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import model_mode as _mm
except Exception:  # noqa: BLE001 - never let the per-project layer brick the guard
    _mm = None  # type: ignore
try:
    from lib import workflow_script as _ws
except Exception:  # noqa: BLE001 - no wrapper builder -> allow unchanged
    _ws = None  # type: ignore

MARKER = "__wfAgent"
# Match a bare `agent(` call (the workflow global) — not `__wfAgent(`, `myagent(`,
# `agentType`, and not a METHOD call `obj.agent(` (the `.` lookbehind, 2026-09-27).
AGENT_CALL_RE = re.compile(r"(?<![\w.])agent\s*\(")
META_RE = re.compile(r"export\s+const\s+meta\s*=\s*\{")

# --- model-policy.json: the single model truth (P2). ---------------------------
# Session-flag dir/names/precedence and the agent pins injected into the wrapper.
# Fail-open to these literals if the file is missing/corrupt. Execution agents run on
# the sonnet default; pass opts.model 'opus' in a script to escalate one.
POLICY_PATH = Path(__file__).resolve().parent / "model-policy.json"

_DEFAULT_FLAG_DIR = "state"
_DEFAULT_FLAG_NAMES = {"sonnet": "sonnet-only-mode", "opus": "opus-only-mode", "fable": "fable-only-mode"}
_DEFAULT_FLAG_PRECEDENCE = ["sonnet", "opus", "fable"]
_DEFAULT_OPUS_AGENTS = ["frontend-uiux-designer", "santa-reviewer"]
_DEFAULT_SONNET_AGENTS = ["explore", "claude-code-guide"]

_POLICY_CACHE: dict | None = None


def _load_policy() -> dict:
    """Read model-policy.json once (cached). Fail-open to {} on any error."""
    global _POLICY_CACHE
    if _POLICY_CACHE is None:
        try:
            with open(POLICY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _POLICY_CACHE = data if isinstance(data, dict) else {}
        except Exception:
            _POLICY_CACHE = {}
    return _POLICY_CACHE


def _claude_dir() -> Path:
    try:
        from lib import platform as _plat

        return _plat.claude_dir()
    except Exception:  # noqa: BLE001
        return Path.home() / ".claude"


def _flag_paths() -> dict[str, Path]:
    sf = _load_policy().get("session_flags")
    sf = sf if isinstance(sf, dict) else {}
    fdir = sf.get("dir") if isinstance(sf.get("dir"), str) and sf.get("dir") else _DEFAULT_FLAG_DIR
    base = _claude_dir() / fdir
    out: dict[str, Path] = {}
    for key, default_name in _DEFAULT_FLAG_NAMES.items():
        name = sf.get(key)
        out[key] = base / (name if isinstance(name, str) and name else default_name)
    return out


def _flag_precedence() -> list[str]:
    sf = _load_policy().get("session_flags")
    prec = sf.get("precedence") if isinstance(sf, dict) else None
    if isinstance(prec, list) and prec and all(p in _DEFAULT_FLAG_NAMES for p in prec):
        return prec
    return list(_DEFAULT_FLAG_PRECEDENCE)


def _agent_sets() -> tuple[list[str], list[str], list[str]]:
    """(sonnet, opus, fable) agent lists as lowercased JS-set members, fail-open to
    literals. 2026-07-18: an EMPTY opus list in policy is respected (fable directive)."""
    pins = _load_policy().get("agent_pins")
    pins = pins if isinstance(pins, dict) else {}
    opus = pins.get("opus")
    sonnet = pins.get("sonnet")
    fable = pins.get("fable")
    opus_list = [str(a).lower() for a in opus] if isinstance(opus, list) else list(_DEFAULT_OPUS_AGENTS)
    sonnet_list = [str(a).lower() for a in sonnet] if isinstance(sonnet, list) else list(_DEFAULT_SONNET_AGENTS)
    fable_list = [str(a).lower() for a in fable] if isinstance(fable, list) else []
    return sonnet_list, opus_list, fable_list


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


def _forced_model(cwd: str | None = None) -> str | None:
    """Global kill-switch flag, else the per-project mode (lib/model_mode, D4),
    else None for smart routing. Flag dir/names/precedence come from
    model-policy.json (fail-open to literals).
    """
    flag_paths = _flag_paths()
    for mdl in _flag_precedence():
        fp = flag_paths.get(mdl)
        if fp is not None and fp.is_file():
            return mdl
    if _mm is not None and cwd:
        try:
            return _mm.forced_mode(cwd)
        except Exception:  # noqa: BLE001
            return None
    return None


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

    # Already processed (e.g. resume) or no agent() calls -> leave it alone.
    if MARKER in script or not AGENT_CALL_RE.search(script) or _ws is None:
        return _allow_unchanged()

    try:
        # "no meta block" -> wrapper at position 0 and pin; "meta present but braces
        # unmatched" -> truly unparseable -> advise, no mutation.
        if META_RE.search(script) is None:
            end = 0
        else:
            end = _ws.meta_end_index(script)
            if end is None:
                return _advisory(
                    "workflow-model-guard: the meta block's braces could not be matched, "
                    "so agent() models were NOT auto-pinned. Pass an explicit model to "
                    "every agent() (default 'sonnet') to avoid inheriting the Opus parent."
                )

        cwd = payload.get("cwd")
        forced = _forced_model(cwd if isinstance(cwd, str) else None)
        head = script[:end]
        body = script[end:]
        # Single safe substitution in the body: agent( -> __wfAgent(
        new_body = AGENT_CALL_RE.sub(MARKER + "(", body)
        new_script = head + _ws.build_wrapper(forced, *_agent_sets()) + new_body
    except Exception:
        return _allow_unchanged()

    full_input = dict(tool_input)
    full_input["script"] = new_script

    if forced:
        note = (
            f"workflow-model-guard: model forced to {forced} (session flag or per-project "
            f"model mode) — every workflow agent() runs on {forced}."
        )
    else:
        note = (
            "workflow-model-guard: workflow agent() calls without an explicit model now "
            "default to SONNET; the model-policy agent pins apply (the opus judges: "
            "santa, uiux, plan, spec, debug). Pass {model:'opus'} or {model:'fable'} per "
            "agent to override; this stops workflow agents from inheriting the Opus parent."
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

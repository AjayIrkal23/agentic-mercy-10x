#!/usr/bin/env python3
"""
workflow-model-guard.py — PreToolUse hook for the **Workflow** tool (plan tiers, R3.3).

THE PROBLEM IT SOLVES:
  A Workflow `agent(prompt, opts)` call inherits the main-loop model when `opts.model` is omitted,
  and these dispatches never pass through `opus-guard.py` (which only sees the Agent tool).

THE FIX (inline `script`):
  Rewrite the script so every `agent(...)` call goes through an injected wrapper `__wfAgent`
  (lib/workflow_script.build_wrapper) holding tables this hook precomputes from model-policy.json:
    - role lookup by `agentType`, else by an `opts.label` word token (equal to or starting with a
      roles.labels key), else `default`;
    - the plan tier's model for that role (state/plan-tier.json; max20 when missing), with the
      usage-guard step-down applied and capped to the tier ceiling;
    - I-5 escalation (lib/model_mode.escalation_signal): a retry marker in `args.task`/`args.brief`
      lifts every call; a retry marker in one call's prompt lifts that call (tested at run time, so a
      fix-loop template in the script does not lift its first call); the size/risk rule reads the
      script text plus task/brief once. Executor roles take their `escalate` model, judges never;
    - an explicit `opts.model` is honoured within the tier ceiling, except a tier's ask-only model
      (model-policy `ask_only`: Opus on max5/api, Fable on max20), which needs the user's phrase this
      turn (otherwise the call takes its role route); fable always needs the phrase and pauses under
      the usage guard, which also steps any other bare literal down;
    - a session flag (state/<m>-only-mode, haiku first) or the per-project mode FORCES one model
      on every agent, capped to the tier ceiling; the usage guard steps a per-project pin down (a
      flag is the user's words and stays).

SAVED scripts (`scriptPath` / `name`): the file is never mutated. When `args.task`/`args.brief`
  carries an escalation signal, `args.tier_hint = "escalate"` is added (the generated scripts pick
  their `:up` literals). An advisory fires only when workflows/.rendered.json is missing (not from
  the generated library) or disagrees with the current tier / usage state (then the library is
  regenerated in the background). The common case is silent.

SAFETY (fail-open, never corrupt a script): already processed (`__wfAgent` present) -> unchanged;
  no `export const meta = {` -> wrapper at position 0; meta braces unmatched -> unchanged +
  advisory; any exception -> allow unchanged. Each decision is logged to the same routing
  telemetry as opus-guard (.telemetry/<sid>.model-routing.jsonl, agent `workflow:<name>`).

Protocol: stdin {"tool_name":"Workflow","tool_input":{...}}; stdout a PreToolUse `updatedInput`
and/or `additionalContext`, or {} to allow unchanged; exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import model_mode as _mm
except Exception:  # noqa: BLE001 - never let the routing lib brick the guard
    _mm = None  # type: ignore
try:
    from lib import workflow_script as _ws
except Exception:  # noqa: BLE001 - no wrapper builder -> allow unchanged
    _ws = None  # type: ignore
try:
    from lib import plan_tier as _pt
except Exception:  # noqa: BLE001
    _pt = None  # type: ignore
try:
    from lib import usage_guard as _ug
except Exception:  # noqa: BLE001
    _ug = None  # type: ignore

MARKER = "__wfAgent"
# Match a bare `agent(` call (the workflow global) — not `__wfAgent(`, `myagent(`,
# `agentType`, and not a METHOD call `obj.agent(` (the `.` lookbehind, 2026-09-27).
AGENT_CALL_RE = re.compile(r"(?<![\w.])agent\s*\(")
META_RE = re.compile(r"export\s+const\s+meta\s*=\s*\{")

POLICY_PATH = _HOOKS / "model-policy.json"
_TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or _HOOKS / ".telemetry")
_ORDER = ["haiku", "sonnet", "opus", "fable"]

_POLICY_CACHE: dict | None = None


def _load_policy() -> dict:
    """Read model-policy.json once (cached). Fail-open to {} on any error."""
    global _POLICY_CACHE
    if _POLICY_CACHE is None:
        try:
            with open(POLICY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _POLICY_CACHE = data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            _POLICY_CACHE = {}
    return _POLICY_CACHE


def _claude_dir() -> Path:
    try:
        from lib import platform as _plat

        return _plat.claude_dir()
    except Exception:  # noqa: BLE001
        return Path.home() / ".claude"


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _allow_unchanged() -> int:
    print("{}")
    return 0


def _emit(updated: dict | None, note: str | None) -> int:
    if updated is None and not note:
        return _allow_unchanged()
    hso: dict = {"hookEventName": "PreToolUse", "permissionDecision": "allow"}
    if updated is not None:
        hso["updatedInput"] = updated
    if note:
        hso["additionalContext"] = note
    print(json.dumps({"hookSpecificOutput": hso}))
    return 0


def _advisory(note: str) -> int:
    return _emit(None, note)


def _tier() -> str:
    try:
        return _pt.read().get("tier", "max20") if _pt is not None else "max20"
    except Exception:  # noqa: BLE001
        return "max20"


def _usage_active() -> bool:
    try:
        return bool(_ug.state().get("active")) if _ug is not None else False
    except Exception:  # noqa: BLE001
        return False


def _cap(model: str, tier: str) -> str:
    return _pt.cap(model, tier) if _pt is not None else model


def _regenerate() -> None:
    """Detached scripts/build_workflows.py when present (usage_guard owns the safe lookup)."""
    try:
        if _ug is not None:
            _ug._regenerate()  # noqa: SLF001 - same package, one implementation
    except Exception:  # noqa: BLE001
        pass


def _log_route(sid: str, agent: str, model: str, reason: str, *, tier: str, usage: bool,
               escalated: bool = False, drift: bool = False) -> None:
    if not sid or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return
    try:
        _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "agent": agent, "model": model, "reason": reason,
               "tier": tier, "usage_guard": bool(usage), "escalated": bool(escalated), "drift": bool(drift)}
        with (_TELEMETRY_DIR / f"{safe}.model-routing.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 - telemetry is best-effort
        pass


def _forced_model(cwd: str | None, policy: dict, tier: str, usage: bool) -> str | None:
    """First global flag, else the per-project mode, capped to the tier; fable paused by the guard.
    Like model_mode.resolve: a global flag is the user's words (kept), the per-project pin is not
    (the usage guard steps it down)."""
    forced, from_pin = None, False
    if _mm is not None:
        try:
            flags = _mm.global_flags(policy)
            if flags:
                forced = flags[0]
            elif cwd:
                forced, from_pin = _mm.forced_mode(cwd), True
        except Exception:  # noqa: BLE001
            forced = None
    if not forced:
        return None
    if usage and forced == "fable":
        forced = "sonnet"
    if usage and from_pin and _ug is not None:
        try:
            forced = _ug.step_down(forced, "default", tier, policy)
        except Exception:  # noqa: BLE001
            pass
    return _cap(forced, tier)


def _wrapper_cfg(policy: dict, tier: str, usage: bool, forced: str | None, escalated: bool,
                 phrase_for) -> dict:
    roles_cfg = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    blk = _mm.tier_block(policy, tier) if _mm is not None else {"roles": {"default": "sonnet"}, "escalate": {}}
    roles_map = roles_cfg.get("agents") if isinstance(roles_cfg.get("agents"), dict) else \
        (getattr(_mm, "_LIT_ROLES", {}) if _mm is not None else {})

    def finish(model: str, role: str) -> str:
        if usage and _ug is not None:
            model = _ug.step_down(model, role, tier, policy)
        return _cap(model, tier)

    roles = blk.get("roles") or {}
    models = {r: finish(roles.get(r) or roles.get("default") or "sonnet", r) for r in set(roles) | {"default"}}
    models_up = {r: finish(m, r) for r, m in (blk.get("escalate") or {}).items()}
    explicit = {}
    ask_only = {str(m) for m in (blk.get("ask_only") or [])}
    for m in policy.get("model_order") or _ORDER:
        target = m
        if m == "fable" and (usage or not phrase_for("fable")):
            if tier == "pro":  # D6: on Pro no fable floor lifts the role route (model_mode does the same)
                explicit[m] = None
                continue
            target = "sonnet"  # fable needs the user's own words this turn and pauses under the guard
        elif m in ask_only and not phrase_for(m):
            explicit[m] = None  # the wrapper falls back to the call's role route (the literal is advice)
            continue
        elif usage and _ug is not None and not phrase_for(m):
            target = _ug.step_down(m, "default", tier, policy)  # a bare literal is not the user's words
        explicit[m] = _cap(target, tier)
    esc = policy.get("escalation") if isinstance(policy.get("escalation"), dict) else {}
    retry = (esc.get("retry_markers") or []) if esc.get("enabled") else []
    return {"forced": forced, "roles": {str(k).lower(): v for k, v in roles_map.items()},
            "labels": roles_cfg.get("labels") or {}, "default_role": roles_cfg.get("default") or "default",
            "models": models, "models_up": models_up, "escalated": escalated, "retry_markers": retry,
            "explicit": explicit, "tier": tier, "usage": usage}


def _signal(policy: dict, text: str, cwd: str | None) -> str | None:
    if _mm is None or not text.strip():
        return None
    try:
        return _mm.escalation_signal(policy, text, cwd)
    except Exception:  # noqa: BLE001
        return None


def _saved(tool_input: dict, policy: dict, cwd: str | None, sid: str) -> int:
    """scriptPath / name: tier_hint on escalation, advisory only on drift or a non-generated script."""
    tier, usage = _tier(), _usage_active()
    args = tool_input.get("args") if isinstance(tool_input.get("args"), dict) else {}
    sig = _signal(policy, "\n".join(str(args.get(k) or "") for k in ("task", "brief")), cwd)
    rendered = _load_json(_claude_dir() / "workflows" / ".rendered.json")
    notes, drift = [], False
    if rendered is None:
        notes.append("workflow-model-guard: this saved workflow is not from the generated library "
                      "(no workflows/.rendered.json); make sure every agent() passes an explicit model "
                      "(default 'sonnet').")
    elif rendered.get("tier") != tier or bool(rendered.get("usage_guard")) != usage:
        drift = True
        notes.append(f"workflow-model-guard: saved workflows were rendered for tier {rendered.get('tier')} "
                     f"(usage-guard {bool(rendered.get('usage_guard'))}) but this session is {tier} "
                     f"(usage-guard {usage}); regenerating now, this run may still carry the old model literals.")
        _regenerate()
    updated = None
    if sig and args.get("tier_hint") != "escalate":
        updated = dict(tool_input)
        updated["args"] = {**args, "tier_hint": "escalate"}
        notes.append(f"workflow-model-guard: args.tier_hint='escalate' ({sig}); "
                     "the saved script picks its :up literals.")
    name = tool_input.get("name") or tool_input.get("scriptPath") or "saved"
    _log_route(sid, f"workflow:{name}", "rendered", f"saved script; escalated: {sig}" if sig else "saved script",
               tier=tier, usage=usage, escalated=bool(sig), drift=drift)
    return _emit(updated, " ".join(notes) or None)


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
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else None
    sid = str(payload.get("session_id") or "")
    transcript = payload.get("transcript_path") if isinstance(payload.get("transcript_path"), str) else None
    script = tool_input.get("script")

    try:
        policy = _load_policy()
        if not isinstance(script, str) or not script.strip():
            if tool_input.get("scriptPath") or tool_input.get("name"):
                return _saved(tool_input, policy, cwd, sid)
            return _allow_unchanged()

        # Already processed (e.g. resume) or no agent() calls -> leave it alone.
        if MARKER in script or not AGENT_CALL_RE.search(script) or _ws is None:
            return _allow_unchanged()

        # "no meta block" -> wrapper at position 0; "meta present but braces unmatched" -> advise.
        if META_RE.search(script) is None:
            end = 0
        else:
            end = _ws.meta_end_index(script)
            if end is None:
                return _advisory(
                    "workflow-model-guard: the meta block's braces could not be matched, "
                    "so agent() models were NOT auto-pinned. Pass an explicit model to "
                    "every agent() (default 'sonnet') to avoid inheriting the Opus parent.")

        tier, usage = _tier(), _usage_active()
        forced = _forced_model(cwd, policy, tier, usage)
        args = tool_input.get("args") if isinstance(tool_input.get("args"), dict) else {}
        task_text = "\n".join(str(args.get(k) or "") for k in ("task", "brief"))
        sig = _signal(policy, task_text, cwd)
        if sig != "previous attempt failed":
            # Retry wording in the script body (a fix-loop prompt template) is tested per call against
            # the real prompt inside __wfAgent; statically only the size/risk rule reads the script.
            esc = policy.get("escalation") if isinstance(policy.get("escalation"), dict) else {}
            sig = _signal({**policy, "escalation": {**esc, "retry_markers": []}},
                          "\n".join([script, task_text]), cwd)
        phrases = policy.get("override_phrases")

        def phrase_for(m: str) -> str | None:
            return _mm.user_phrase(m, transcript, phrases) if _mm is not None else None

        cfg = _wrapper_cfg(policy, tier, usage, forced, bool(sig), phrase_for)
        try:
            retry_in_script = not sig and any(re.search(r, script, re.IGNORECASE) for r in cfg["retry_markers"])
        except re.error:
            retry_in_script = False
        new_script = script[:end] + _ws.build_wrapper(cfg) + AGENT_CALL_RE.sub(MARKER + "(", script[end:])
    except Exception:  # noqa: BLE001
        return _allow_unchanged()

    full_input = dict(tool_input)
    full_input["script"] = new_script
    if forced:
        note = (f"workflow-model-guard: model forced to {forced} (session flag or per-project mode, "
                f"capped to tier {tier}).")
        reason = "forced"
    else:
        listing = ", ".join(f"{r}={m}" for r, m in sorted(cfg["models"].items()) if r != "default")
        note = (f"workflow-model-guard: agent() models follow plan tier {tier}"
                + (" with the usage-guard step-down" if usage else "")
                + (f"; escalated ({sig}) for executor roles" if sig else "")
                + ("; executor calls whose prompt reports a failed previous attempt are escalated per call"
                   if retry_in_script else "")
                + f": {listing}. An explicit opts.model is honoured within the tier ceiling; "
                "fable needs your own phrase this turn.")
        reason = f"tier {tier}" + (f"; escalated: {sig}" if sig else "") + ("; usage-guard" if usage else "")
    _log_route(sid, "workflow:inline", forced or "per-role", reason, tier=tier, usage=usage, escalated=bool(sig))
    return _emit(full_input, note)


if __name__ == "__main__":
    raise SystemExit(main())

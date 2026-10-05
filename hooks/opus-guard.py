#!/usr/bin/env python3
"""opus-guard.py — PreToolUse mutator for the Agent tool: sets `model` and the [label]
in `description` to the model that will actually run (D2). Sonnet executes, Opus judges
(pins in model-policy.json), executors escalate, Fable only on the user's word.

Order (first hit wins): 1 session flags state/<m>-only-mode · 2 per-project mode
(lib/model_mode) · 3 explicit `model` / [label] — outright only for an unguarded agent;
a pinned agent, an escalation executor or fable needs the user's own override phrase
this turn (E-04) · 4 agent_pins · 5 escalation (retry marker, or no plan marker and
classify() size/risk >= heavy_qualifiers) · 6 default sonnet.

Each decision goes to .telemetry/<session>.model-routing.jsonl {ts, agent, model,
reason}; an ignored request is named in the reason. Emits the FULL tool_input echo
with only `model` / `description` changed, and only when something changes; never
touches `prompt` or `name`. stdout `{}` or a PreToolUse `updatedInput`; exit always 0.
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
except Exception:  # noqa: BLE001 - never let the per-project layer brick the guard
    _mm = None  # type: ignore

PREFIX_RE = re.compile(r"^\[(sonnet|opus|fable)\]\s", re.IGNORECASE)

# --- model-policy.json: the single model truth. Fail-open to these literals. -----
POLICY_PATH = _HOOKS / "model-policy.json"
_TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or _HOOKS / ".telemetry")

_DEFAULT_FLAG_DIR = "state"
_DEFAULT_FLAG_NAMES = {"sonnet": "sonnet-only-mode", "opus": "opus-only-mode", "fable": "fable-only-mode"}
_DEFAULT_FLAG_PRECEDENCE = ["sonnet", "opus", "fable"]
_DEFAULT_SONNET_ONLY_AGENTS = {"explore", "claude-code-guide"}
_DEFAULT_OPUS_ONLY_AGENTS = {"frontend-uiux-designer", "santa-reviewer"}
_DEFAULT_VALID_MODELS = {"sonnet", "opus", "fable"}
_DEFAULT_MODEL = "sonnet"

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


def _agent_sets() -> tuple[set[str], set[str], set[str]]:
    """(sonnet_only, opus_only, fable_only) agent sets from policy, fail-open to
    literals. An empty list in the policy is RESPECTED; only a missing/invalid list
    falls back. Fable is opt-in only, so agent_pins.fable is expected to be empty."""
    pins = _load_policy().get("agent_pins")
    pins = pins if isinstance(pins, dict) else {}
    opus = pins.get("opus")
    sonnet = pins.get("sonnet")
    fable = pins.get("fable")
    opus_set = {str(a).lower() for a in opus} if isinstance(opus, list) else set(_DEFAULT_OPUS_ONLY_AGENTS)
    sonnet_set = {str(a).lower() for a in sonnet} if isinstance(sonnet, list) else set(_DEFAULT_SONNET_ONLY_AGENTS)
    fable_set = {str(a).lower() for a in fable} if isinstance(fable, list) else set()
    return sonnet_set, opus_set, fable_set


def _flag_paths() -> dict[str, Path]:
    """{model: flag_path} under <claude_dir>/<dir>/, from policy, fail-open to literals."""
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
    prec = _load_policy().get("session_flags")
    prec = prec.get("precedence") if isinstance(prec, dict) else None
    if isinstance(prec, list) and prec and all(p in _DEFAULT_FLAG_NAMES for p in prec):
        return prec
    return list(_DEFAULT_FLAG_PRECEDENCE)


def _valid_models() -> set[str]:
    ids = _load_policy().get("model_ids")
    return set(ids) if isinstance(ids, dict) and ids else set(_DEFAULT_VALID_MODELS)


def _default_model() -> str:
    d = _load_policy().get("default")
    return d if isinstance(d, str) and d else _DEFAULT_MODEL


def _allow_unchanged() -> int:
    print("{}")
    return 0


def _log_route(sid: str, agent: str, model: str, reason: str) -> None:
    """Append one routing decision to .telemetry/<sid>.model-routing.jsonl."""
    if not sid or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return
    try:
        _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "agent": agent,
               "model": model, "reason": reason}
        with (_TELEMETRY_DIR / f"{safe}.model-routing.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 - telemetry is best-effort
        pass


def _routed(subagent_type: str, text: str, cwd: str | None) -> tuple[str, str]:
    """Pin -> escalation -> default, ignoring any explicit request."""
    sonnet_agents, opus_agents, fable_agents = _agent_sets()
    for mdl, agents in (("fable", fable_agents), ("opus", opus_agents), ("sonnet", sonnet_agents)):
        if subagent_type in agents:
            return mdl, f"'{subagent_type}' is a pinned {mdl} agent"
    policy = _load_policy()
    why = _mm.escalation_reason(policy, subagent_type, text, cwd) if _mm is not None else None
    target = (policy.get("escalation") or {}).get("to", "opus")
    if why and target in _valid_models():
        return target, f"escalated: {why}"
    return _default_model(), "default (no opus/fable signal)"


def _guarded(subagent_type: str) -> bool:
    """Pinned agents and escalation executors: a request alone may not move them."""
    esc = _load_policy().get("escalation")
    esc_agents = {str(a).lower() for a in (esc.get("agents") or [])} if isinstance(esc, dict) else set()
    return subagent_type in set().union(*_agent_sets(), esc_agents)


def _resolve_required(subagent_type: str, model: str, description: str,
                      cwd: str | None = None, prompt: str = "",
                      transcript: str | None = None) -> tuple[str, str]:
    """Return (required_model, reason). Order: session flags -> per-project mode ->
    explicit model / [label] (guarded agents and fable need the user's phrase) ->
    agent pins -> escalation -> default."""
    flag_paths = _flag_paths()
    for mdl in _flag_precedence():
        fp = flag_paths.get(mdl)
        if fp is not None and fp.is_file():
            return mdl, f"{mdl}-only-mode active"
    if _mm is not None and cwd:
        try:
            pm = _mm.forced_mode(cwd)
        except Exception:  # noqa: BLE001
            pm = None
        if pm:
            return pm, "per-project model mode"
    label = PREFIX_RE.match(description)
    if model in _valid_models():
        asked, src = model, "explicit model param"
    else:
        asked, src = (label.group(1).lower(), "description label") if label else (None, "")
    if asked and asked != "fable" and not _guarded(subagent_type):
        return asked, src
    if asked and _mm is not None:
        phrase = _mm.user_phrase(asked, transcript, _load_policy().get("override_phrases"))
        if phrase:
            return asked, f"{src} (user said '{phrase}')"
    required, reason = _routed(subagent_type, f"{description}\n{prompt}", cwd)
    if asked and asked != required:
        reason += f"; {src} '{asked}' ignored (no '{asked}' override phrase in the user's turn)"
    elif model and model not in _valid_models():
        reason += f"; explicit model '{model}' is not a policy model"
    return required, reason


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return _allow_unchanged()

    if not isinstance(payload, dict) or payload.get("tool_name") not in ("Agent", "Task"):
        return _allow_unchanged()

    tool_input = payload.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return _allow_unchanged()

    description = tool_input.get("description", "") or ""
    model = (tool_input.get("model") or "").lower()
    subagent_type = (tool_input.get("subagent_type") or "").lower()
    cwd = payload.get("cwd")

    prompt, transcript = tool_input.get("prompt"), payload.get("transcript_path")
    required, reason = _resolve_required(
        subagent_type, model, description, cwd if isinstance(cwd, str) else None,
        prompt if isinstance(prompt, str) else "", transcript if isinstance(transcript, str) else None)
    _log_route(str(payload.get("session_id") or ""), subagent_type or "general-purpose",
               required, reason)

    m = PREFIX_RE.match(description)
    current_prefix = m.group(1).lower() if m else None
    body = description[m.end():] if m else description

    updated: dict[str, object] = {}
    if current_prefix != required:
        updated["description"] = f"[{required}] {body}"
    # Pin the model explicitly so an unset model never silently inherits the parent.
    if model != required:
        updated["model"] = required
    if not updated:
        return _allow_unchanged()

    # FULL tool_input echo: some harness versions REPLACE tool_input with updatedInput
    # instead of merging, so returning only the changed keys would drop required params.
    full_input = dict(tool_input)
    full_input.update(updated)

    note = (f"opus-guard: subagent runs on [{required}] ({reason}). Omit `model` on Agent "
            "calls: pins and escalation decide; a pinned judge, an executor or fable moves "
            "only on the user's own phrase this turn ('use opus' / 'use sonnet' / 'use fable').")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": full_input, "additionalContext": note}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

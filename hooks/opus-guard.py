#!/usr/bin/env python3
"""
opus-guard.py — PreToolUse mutator for the Agent tool: aligns the [label] in
`description` with the `model` that will actually run (D2).

Sonnet 5.5 executes (default); Opus judges — the pinned review / UI / plan / spec /
debug agents (model-policy.json) or an explicit [opus] label. Execution agents are
escalated to Opus on a failed previous attempt or large unplanned work. Fable runs
ONLY when explicitly asked — never automatically.

Resolution order (first hit wins):
  1. session kill-switch flags   state/{sonnet,opus,fable}-only-mode
  2. per-project mode            state/model-modes/<repo_key>   (lib/model_mode, D4)
  3. explicit `model` param      the user's explicit word wins over a pin
  4. agent_pins                  model-policy.json
  5. escalation                  execution agents: retry marker, or no plan marker and
                                 classify() size/risk >= heavy_qualifiers (fail-open)
  6. [label] prefix in description
  7. default                     sonnet

Every decision is appended to .telemetry/<session>.model-routing.jsonl
({ts, agent, model, reason}) so routing can be audited.

Emits `updatedInput` (FULL tool_input echo — only `model` / `description` changed)
only when something actually changes. It never touches `prompt` (the write protocol
is delivered by the SubagentStart hook, D3) or `name` (names are a teams decision,
not a labeling convention, D1).

Protocol:
  stdin:  {"tool_name":"Agent","tool_input":{...},"cwd":"..."}
  stdout: {} to allow unchanged, or
          {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",
           "updatedInput":{...},"additionalContext":"..."}}
  exit:   always 0 (fail-open).
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
_TELEMETRY_DIR = _HOOKS / ".telemetry"

_DEFAULT_FLAG_DIR = "state"
_DEFAULT_FLAG_NAMES = {
    "sonnet": "sonnet-only-mode",
    "opus": "opus-only-mode",
    "fable": "fable-only-mode",
}
_DEFAULT_FLAG_PRECEDENCE = ["sonnet", "opus", "fable"]
_DEFAULT_SONNET_ONLY_AGENTS = {"explore", "claude-code-guide"}
_DEFAULT_OPUS_ONLY_AGENTS = {"frontend-uiux-designer", "santa-reviewer"}
_SIZE_RANK = {"S": 1, "M": 2, "L": 3}
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


def _escalation(subagent_type: str, text: str, cwd: str | None) -> str | None:
    """Reason to lift an execution agent to escalation.to, or None. Fail-open."""
    policy = _load_policy()
    esc = policy.get("escalation")
    if not isinstance(esc, dict) or not esc.get("enabled"):
        return None
    if subagent_type not in {str(a).lower() for a in esc.get("agents") or []}:
        return None
    try:
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("retry_markers") or []):
            return "previous attempt failed"
        if any(re.search(p, text, re.IGNORECASE) for p in esc.get("plan_markers") or []):
            return None  # a plan/spec/contract drives the work: Sonnet executes it
        from prompt_router.classify import classify  # noqa: PLC0415 - only on this path

        prof = classify({"prompt": text, "cwd": cwd or ""})
        hq = policy.get("heavy_qualifiers") or {}
        if (_SIZE_RANK.get(prof.size, 0) >= _SIZE_RANK.get(hq.get("min_size", "L"), 3)
                and prof.risk >= int(hq.get("min_risk", 2))):
            return f"large task with no plan (size {prof.size}, risk {prof.risk})"
    except Exception:  # noqa: BLE001 - escalation must never break routing
        return None
    return None


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


def _resolve_required(subagent_type: str, model: str, description: str,
                      cwd: str | None = None, prompt: str = "") -> tuple[str, str]:
    """Return (required_model, reason). Order:
    session flags -> per-project mode -> explicit model param -> agent pins ->
    escalation -> [label] -> default."""
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
    if model in _valid_models():
        return model, "explicit model param"
    sonnet_agents, opus_agents, fable_agents = _agent_sets()
    if subagent_type in fable_agents:
        return "fable", f"'{subagent_type}' is a pinned fable agent"
    if subagent_type in opus_agents:
        return "opus", f"'{subagent_type}' is a pinned opus agent"
    if subagent_type in sonnet_agents:
        return "sonnet", f"'{subagent_type}' is a pinned sonnet agent"
    why = _escalation(subagent_type, f"{description}\n{prompt}", cwd)
    target = (_load_policy().get("escalation") or {}).get("to", "opus")
    if why and target in _valid_models():
        return target, f"escalated: {why}"
    m = PREFIX_RE.match(description)
    if m:
        return m.group(1).lower(), "description label"
    return _default_model(), "default (no opus/fable signal)"


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

    prompt = tool_input.get("prompt") or ""
    required, reason = _resolve_required(
        subagent_type, model, description, cwd if isinstance(cwd, str) else None,
        prompt if isinstance(prompt, str) else "")
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

    note = (f"opus-guard: subagent runs on [{required}] ({reason}); sonnet executes by "
            "default, opus for pinned judge agents (review/UI/plan/spec/debug), escalated "
            "execution agents or an explicit [opus] label, fable only on explicit request.")
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

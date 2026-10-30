#!/usr/bin/env python3
"""opus-guard.py — PreToolUse mutator for the Agent tool: sets `model` and the [label] in
`description` to the model that will actually run (D2, plan tiers R3.3).

The model comes from lib/model_mode.resolve(), the one resolver both guards share:
1 session flags state/<m>-only-mode (haiku > sonnet > opus > fable) · 2 per-project mode
(lib/model_mode) · 3 explicit `model` / [label] — outright only for an unguarded role; a judge,
an executor or fable needs the user's own override phrase this turn (E-04) · 4 role x plan tier
(model-policy.json `roles` + `tiers`; tier from state/plan-tier.json, max20 when missing) ·
5 escalation one model up for executors (retry marker, or no plan marker and classify()
size/risk >= heavy_qualifiers) · 6 usage-guard step-down while the 5-hour window is >= 80 %
(lib/usage_guard) · 7 the tier ceiling, always last.

Each decision goes to .telemetry/<session>.model-routing.jsonl {ts, agent, model, reason, tier,
usage_guard, fallback}. Emits the FULL tool_input echo with only `model` / `description` changed,
and only when something changes; never touches `prompt` or `name`. stdout `{}` or a PreToolUse
`updatedInput`; exit always 0.
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
    from lib import plan_tier as _pt
except Exception:  # noqa: BLE001
    _pt = None  # type: ignore
try:
    from lib import usage_guard as _ug
except Exception:  # noqa: BLE001
    _ug = None  # type: ignore

PREFIX_RE = re.compile(r"^\[(haiku|sonnet|opus|fable)\]\s", re.IGNORECASE)

# --- model-policy.json: the single model truth. Fail-open to these literals. -----
POLICY_PATH = _HOOKS / "model-policy.json"
_TELEMETRY_DIR = Path(os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR") or _HOOKS / ".telemetry")

_DEFAULT_FLAG_DIR = "state"
_DEFAULT_FLAG_NAMES = {"haiku": "haiku-only-mode", "sonnet": "sonnet-only-mode", "opus": "opus-only-mode",
                       "fable": "fable-only-mode"}
_DEFAULT_FLAG_PRECEDENCE = ["haiku", "sonnet", "opus", "fable"]
_DEFAULT_VALID_MODELS = {"haiku", "sonnet", "opus", "fable"}
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


def _fallback_chain(tier: str) -> list:
    try:
        return _pt.render_overrides(tier)["fallbackModel"] if _pt is not None else []
    except Exception:  # noqa: BLE001
        return []


def _log_route(sid: str, agent: str, model: str, reason: str, *, tier: str = "?", usage: bool = False,
               fallback: list | None = None) -> None:
    """Append one routing decision to .telemetry/<sid>.model-routing.jsonl."""
    if not sid or os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return
    try:
        _TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "agent": agent, "model": model, "reason": reason,
               "tier": tier, "usage_guard": bool(usage), "fallback": list(fallback or [])}
        with (_TELEMETRY_DIR / f"{safe}.model-routing.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:  # noqa: BLE001 - telemetry is best-effort
        pass


def _resolve_required(subagent_type: str, model: str, description: str,
                      cwd: str | None = None, prompt: str = "",
                      transcript: str | None = None) -> tuple[str, str, str, bool]:
    """-> (required_model, reason, tier, usage_active). See the module docstring for the order."""
    policy = _load_policy()
    try:
        tier = _pt.read().get("tier", "max20") if _pt is not None else "max20"
    except Exception:  # noqa: BLE001
        tier = "max20"
    try:
        usage = bool(_ug.state().get("active")) if _ug is not None else False
    except Exception:  # noqa: BLE001
        usage = False
    fps = _flag_paths()
    flags = [m for m in _flag_precedence() if (fp := fps.get(m)) is not None and fp.is_file()]
    pin = None
    if _mm is not None and cwd:
        try:
            pin = _mm.forced_mode(cwd, cap=False)  # the resolver caps it and names `tier-cap`
        except Exception:  # noqa: BLE001
            pin = None
    label = PREFIX_RE.match(description)
    if model in _valid_models():
        asked, src = model, "param"
    elif label:
        asked, src = label.group(1).lower(), "label"
    else:
        asked, src = None, "param"
    if _mm is None:  # the lib failed to import: the literal default, capped when plan_tier works
        req = flags[0] if flags else (asked if asked and asked != "fable" else _default_model())
        return (_pt.cap(req, tier) if _pt is not None else req), "model_mode unavailable", tier, usage
    phrases = policy.get("override_phrases")

    def phrase_for(m: str) -> str | None:
        return _mm.user_phrase(m, transcript, phrases)

    required, reason = _mm.resolve(policy, subagent_type, asked=asked, asked_src=src, phrase_for=phrase_for,
                                   text=f"{description}\n{prompt}", cwd=cwd, tier=tier,
                                   usage_active=usage, flags=flags, pin=pin)
    if model and model not in _valid_models():
        reason += f"; explicit model '{model}' is not a policy model"
    return required, reason, tier, usage


def main_with_payload(payload: dict) -> int:
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
    required, reason, tier, usage = _resolve_required(
        subagent_type, model, description, cwd if isinstance(cwd, str) else None,
        prompt if isinstance(prompt, str) else "", transcript if isinstance(transcript, str) else None)
    _log_route(str(payload.get("session_id") or ""), subagent_type or "general-purpose", required, reason,
               tier=tier, usage=usage, fallback=_fallback_chain(tier))

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

    note = (f"opus-guard: {subagent_type or 'general-purpose'} -> [{required}] ({reason}"
            + ("; usage-guard active" if usage and "usage-guard" not in reason else "")
            + "). Omit `model`; judges, executors and fable move only on the user's phrase this turn.")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": full_input, "additionalContext": note}}))
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        return _allow_unchanged()
    try:
        return main_with_payload(payload)
    except Exception:  # noqa: BLE001 - the guard must never block an Agent call
        return _allow_unchanged()


if __name__ == "__main__":
    raise SystemExit(main())

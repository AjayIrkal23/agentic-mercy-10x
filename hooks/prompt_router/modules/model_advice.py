"""model_advice.py — S3 delegate: main-session heavy-task advice (P2-T4; plan tiers R3.3).

Fires ONLY when the TaskProfile hits a row of the plan tier's ``task_matrix`` column AND
``heavy_qualifiers`` pass (size L AND risk >= min_risk). Otherwise SILENT. The line is for
the model, never the user (autonomy §11): it says to dispatch the judge agent named in
``main_session_advice.agents`` for the heavy part. Per tier (state/plan-tier.json, max20 when
missing): max20 names Opus (wording unchanged); pro names sonnet and never Opus; max5/api name
sonnet and say how to lift the judge ("say 'use opus'"); while the usage guard is active the
model is the tier's guarded judge model and the line says so. Fail-open to no advice when the
policy is missing/corrupt.

This module is import-safe and pure — it does NOT wrap a stdin hook, so it is
exempt from the delegate enable-gate concern (no legacy state to double-fire);
``collect`` still respects the gate for consistency.
"""
from __future__ import annotations

import json
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]
_POLICY = _HOOKS / "model-policy.json"


def _policy() -> dict:
    try:
        return json.loads(_POLICY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


_SIZE_RANK = {"S": 1, "M": 2, "L": 3}


def _task_matrix_hit(profile, matrix: dict) -> tuple[str, str] | None:
    """(task_matrix key, model) of the row the profile hits in this tier's column, else None."""
    intents = set(profile.intents)
    if "DESIGN" in intents and matrix.get("DESIGN"):
        return "DESIGN", matrix["DESIGN"]
    # HEAVY_ARCHITECTURE — architecture/plan/spec shaped at scale
    if matrix.get("HEAVY_ARCHITECTURE") and (
        (profile.is_arch or bool({"PLAN", "SPEC"} & intents)) and profile.size == "L"
    ):
        return "HEAVY_ARCHITECTURE", matrix["HEAVY_ARCHITECTURE"]
    # DEEP_DEBUG — debugging at scale
    if matrix.get("DEEP_DEBUG") and "DEBUG" in intents and profile.size == "L":
        return "DEEP_DEBUG", matrix["DEEP_DEBUG"]
    # IMPLEMENT_SUITE — implementation at scale
    if matrix.get("IMPLEMENT_SUITE") and "IMPLEMENT" in intents and profile.size == "L":
        return "IMPLEMENT_SUITE", matrix["IMPLEMENT_SUITE"]
    return None


def _override_suppresses(profile, policy: dict) -> bool:
    """A user 'use sonnet' / 'use haiku' / 'use fable' phrase suppresses the nudge."""
    text = profile.text
    ov = policy.get("override_phrases", {})
    for phrase in ov.get("sonnet", []) + ov.get("haiku", []) + ov.get("fable", []):
        if phrase and phrase.lower() in text:
            return True
    return False


def _tier_and_usage() -> tuple[str, bool]:
    """(plan tier, usage guard active); ("max20", False) when the libs or state are unavailable."""
    try:
        from lib import plan_tier  # noqa: PLC0415

        tier = plan_tier.read().get("tier", "max20")
    except Exception:  # noqa: BLE001
        tier = "max20"
    try:
        from lib import usage_guard  # noqa: PLC0415

        usage = bool(usage_guard.state().get("active"))
    except Exception:  # noqa: BLE001
        usage = False
    return tier, usage


def _column(policy: dict, tier: str) -> dict:
    """This tier's task_matrix column (api uses max5); a flat v1 matrix is the max20 column."""
    tm = policy.get("task_matrix") or {}
    col = tm.get("max5" if tier == "api" else tier)
    if isinstance(col, dict):
        return col
    return tm if any(isinstance(v, str) and k.isupper() for k, v in tm.items()) else {}


def advise(profile) -> str | None:
    """Return the heavy-task dispatch advice string, or None (silent)."""
    policy = _policy()
    if not policy:
        return None
    if not policy.get("main_session_advice", {}).get("enabled", False):
        return None
    tier, usage = _tier_and_usage()
    found = _task_matrix_hit(profile, _column(policy, tier))
    if not found:
        return None
    hit, model = found
    # heavy_qualifiers gate — size L AND risk >= min_risk
    hq = policy.get("heavy_qualifiers", {})
    min_size = _SIZE_RANK.get(hq.get("min_size", "L"), 3)
    min_risk = int(hq.get("min_risk", 2))
    if _SIZE_RANK.get(profile.size, 0) < min_size or profile.risk < min_risk:
        return None
    if _override_suppresses(profile, policy):
        return None
    agents = policy.get("main_session_advice", {}).get("agents", {})
    key = hit
    if hit == "HEAVY_ARCHITECTURE" and "SPEC" in profile.intents and "PLAN" not in profile.intents:
        key = "HEAVY_ARCHITECTURE_SPEC"
    agent = agents.get(key) or agents.get(hit)
    if not agent:
        return None
    if usage:
        try:
            from lib import usage_guard  # noqa: PLC0415

            model = usage_guard.step_down(model, "judge", tier, policy)  # the tier's judge model under the guard
        except Exception:  # noqa: BLE001
            pass
    shown = "Opus" if model == "opus" else model
    tail = f"({shown}, via the Agent tool) for the heavy part now"
    if usage:
        tail += " (usage-guard active)"
    if tier in ("max5", "api") and model != "opus":
        tail += "; say 'use opus' to lift this judge to Opus for the turn"
    return f"Heavy task ({hit}, size {profile.size}, risk {profile.risk}): dispatch the {agent} agent {tail}."


def items(payload: dict, ctx: dict) -> list[dict]:
    profile = ctx.get("profile")
    if profile is None:
        return []
    text = advise(profile)
    if text:
        return [{"id": "model:advice", "tier": 3, "section": "MODEL", "text": text}]
    return []


__all__ = ["advise", "items"]

"""model_advice.py — S3 delegate: main-session /model advice (P2-T4, filled here).

Re-homes the model-router's per-prompt /model advice, INVERTED from the old
Opus bias (Spec A §3.2 / plan P2-T4): advise ``/model <opus_id>`` ONLY when the
TaskProfile hits an opus row of ``task_matrix`` AND ``heavy_qualifiers`` pass
(size L AND risk >= min_risk). Otherwise SILENT — no per-prompt model nag. All
ids come from ``hooks/model-policy.json`` (the single model truth); fail-open to
no advice when the policy is missing/corrupt.

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


def _task_matrix_hit(profile, matrix: dict) -> str | None:
    """Return the task_matrix key the profile hits (opus rows), else None."""
    intents = set(profile.intents)
    # DESIGN
    if "DESIGN" in intents and matrix.get("DESIGN") == "opus":
        return "DESIGN"
    # HEAVY_ARCHITECTURE — architecture/plan/spec shaped at scale
    if matrix.get("HEAVY_ARCHITECTURE") == "opus" and (
        (profile.is_arch or bool({"PLAN", "SPEC"} & intents)) and profile.size == "L"
    ):
        return "HEAVY_ARCHITECTURE"
    # DEEP_DEBUG — debugging at scale
    if matrix.get("DEEP_DEBUG") == "opus" and "DEBUG" in intents and profile.size == "L":
        return "DEEP_DEBUG"
    # IMPLEMENT_SUITE — implementation at scale
    if matrix.get("IMPLEMENT_SUITE") == "opus" and "IMPLEMENT" in intents and profile.size == "L":
        return "IMPLEMENT_SUITE"
    return None


def _override_suppresses(profile, policy: dict) -> bool:
    """A user 'use sonnet'/'use fable' phrase suppresses an opus nudge."""
    text = profile.text
    ov = policy.get("override_phrases", {})
    for phrase in ov.get("sonnet", []) + ov.get("fable", []):
        if phrase and phrase.lower() in text:
            return True
    return False


def advise(profile) -> str | None:
    """Return the /model advice string, or None (silent)."""
    policy = _policy()
    if not policy:
        return None
    if not policy.get("main_session_advice", {}).get("enabled", False):
        return None
    matrix = policy.get("task_matrix", {})
    hit = _task_matrix_hit(profile, matrix)
    if not hit:
        return None
    # heavy_qualifiers gate — size L AND risk >= min_risk
    hq = policy.get("heavy_qualifiers", {})
    min_size = _SIZE_RANK.get(hq.get("min_size", "L"), 3)
    min_risk = int(hq.get("min_risk", 2))
    if _SIZE_RANK.get(profile.size, 0) < min_size or profile.risk < min_risk:
        return None
    if _override_suppresses(profile, policy):
        return None
    opus_id = policy.get("model_ids", {}).get("opus", "claude-opus-4-8")
    return (f"Heavy task ({hit}, size {profile.size}, risk {profile.risk}): "
            f"consider /model {opus_id} for this work.")


def items(payload: dict, ctx: dict) -> list[dict]:
    profile = ctx.get("profile")
    if profile is None:
        return []
    text = advise(profile)
    if text:
        return [{"id": "model:advice", "tier": 3, "section": "MODEL", "text": text}]
    return []


__all__ = ["advise", "items"]

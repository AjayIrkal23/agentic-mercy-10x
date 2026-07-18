"""select.py — S2: ranked skill selection + suggest/dispatch tiering.

Ranks skills for the current TaskProfile from ``skills-index.json`` when it
exists (built by P1-T5 / enriched by P5), and DEGRADES GRACEFULLY to the
trigger floor's path-route rules + cross-cutting groups when the index is
absent — so the router ranks sanely from day 1, before the front-matter corpus
pass (Charter §4a: all skills stay rankable; the index only re-orders).

Also implements the auto-dispatch tiering (P1-T6, router side): an intent whose
score >= ``auto_dispatch_threshold`` (default 3) is surfaced as an AGENT
dispatch suggestion; a weaker hit (1..2) is surfaced as a lightweight COMMAND
suggestion. No keyword is ever pruned — only the *consequence* is tiered.

Pure stdlib; never raises.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as _classify  # noqa: E402

_SKILLS_INDEX = _HOOKS / "skills-index.json"
_WEIGHTS = _HOOKS / "skill_router_weights.json"

DEFAULT_AUTO_DISPATCH_THRESHOLD = 3

# intent category -> specialist agent (for dispatch tiering)
_AGENT_FOR = {
    "DEBUG": "debug-detective", "DESIGN": "frontend-uiux-designer",
    "AUDIT": "audit-specialist", "SPEC": "spec-architect",
    "PLAN": "planning-director", "IMPLEMENT": "implementation-engineer",
    "CLEANUP": "deadcode-reaper", "SECURITY": "security-sentinel",
    "REVIEW": "santa-reviewer", "TEST": "test-author",
    "REFACTOR": "refactor-specialist",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _weights() -> dict:
    return _load_json(_WEIGHTS).get("weights", {}) if _WEIGHTS.exists() else {}


def _norm(s: str) -> str:
    return s.replace("\\", "/").lower()


def _path_route_skills(profile) -> dict[str, float]:
    """Fallback ranking source: floor path-route rules matched against paths."""
    idx = _classify._floor_index()
    scores: dict[str, float] = {}
    paths = profile.paths or []
    for rule in idx.get("path_route", []):
        if not isinstance(rule, dict):
            continue
        match = rule.get("match", {})
        hit = False
        for pth in paths:
            fp = _norm(pth)
            name = fp.rsplit("/", 1)[-1]
            ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            if any(_norm(x) in fp for x in match.get("exclude_paths", [])):
                continue
            if match.get("catch_all"):
                hit = True
            if any(_norm(x) in fp for x in match.get("path_contains_any", [])):
                hit = True
            if any(_norm(x) in name for x in match.get("filename_contains_any", [])):
                hit = True
            if ext and ext in [e.lower() for e in match.get("extensions", [])]:
                hit = True
            if hit:
                break
        if hit:
            for i, sk in enumerate(rule.get("skills", [])):
                scores[sk] = scores.get(sk, 0.0) + (2.0 - i * 0.3)
    return scores


def _cross_cutting_skills(profile) -> dict[str, float]:
    idx = _classify._floor_index()
    # cross_cutting captured in floor under kind path_route? No — separate; reload from floor
    scores: dict[str, float] = {}
    try:
        floor = json.loads((_HOOKS / "trigger-floor.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return scores
    groups: dict[str, list] = {}
    for e in floor.get("entries", []):
        if e.get("kind") == "cross_cutting":
            v = e.get("value", {})
            groups[v.get("group", "")] = v.get("skills", [])
    for sk in groups.get("always", []):
        scores[sk] = scores.get(sk, 0.0) + 2.5
    if profile.first_write_candidate:
        for sk in groups.get("first_write_only", []):
            scores[sk] = scores.get(sk, 0.0) + 1.8
    if "DEBUG" in profile.intents:
        for sk in groups.get("debug", []):
            scores[sk] = scores.get(sk, 0.0) + 1.5
    if {"IMPLEMENT", "SPEC", "PLAN"} & set(profile.intents):
        for sk in groups.get("implementation", []):
            scores[sk] = scores.get(sk, 0.0) + 1.3
    if {"REVIEW", "TEST", "QA"} & set(profile.intents):
        for sk in groups.get("verification", []):
            scores[sk] = scores.get(sk, 0.0) + 1.2
    return scores


def _index_skills(profile, index: dict) -> dict[str, float]:
    """Rank from skills-index.json when present."""
    scores: dict[str, float] = {}
    text = profile.text
    intents = set(profile.intents)
    surfaces = set(profile.surfaces)
    for name, meta in (index.get("skills") or {}).items():
        if not isinstance(meta, dict):
            continue
        s = 0.0
        for kw in meta.get("keywords", []) or []:
            if kw and str(kw).lower() in text:
                s += 1.0
        if intents & set(meta.get("intents", []) or []):
            s += 1.5
        if surfaces & set(meta.get("surfaces", []) or []):
            s += 1.0
        # path rules
        for rule in meta.get("path_rules", []) or []:
            for pth in profile.paths:
                if any(_norm(x) in _norm(pth) for x in (rule.get("path_contains_any", []) or [])):
                    s += 1.2
        if s > 0:
            scores[name] = scores.get(name, 0.0) + s
    return scores


_AUTON_CONFIG = _HOOKS / "autonomous-skill-router.config.json"


def _category_skills(profile) -> dict[str, float]:
    """Curated category -> local_skills mapping from the autonomous router config.
    The legacy autonomous router pushed these directly; the live router only kept
    the category *keywords* (as floor act_keyword intents), silently orphaning the
    curated skill lists (e.g. PLAN->idea-refine, DEBUG->diagnose). Restored
    2026-07-18: each intent hit boosts that category's local_skills so curated
    skills outrank tokenized-description noise."""
    scores: dict[str, float] = {}
    cats = (_load_json(_AUTON_CONFIG).get("categories") or {})
    for cat, hit_score in (profile.intents or {}).items():
        meta = cats.get(cat)
        if not isinstance(meta, dict):
            continue
        boost = 1.4 + 0.2 * min(int(hit_score), 3)
        for sk in meta.get("local_skills") or []:
            scores[sk] = max(scores.get(sk, 0.0), boost)
    return scores


def index_meta() -> dict:
    """skills-index metadata (name -> {description, keywords, ...}); {} on error."""
    return (_load_json(_SKILLS_INDEX).get("skills") or {})


def rank_skills(profile, *, top_n: int = 10) -> list[tuple[str, float]]:
    """Return [(skill_name, score)] descending. Index-driven when available,
    else floor-driven. Weights (P4-T9 loop) multiply when present."""
    index = _load_json(_SKILLS_INDEX)
    if index.get("skills"):
        scores = _index_skills(profile, index)
        # blend in cross-cutting so mandatory baselines never fall out
        for sk, v in _cross_cutting_skills(profile).items():
            scores[sk] = scores.get(sk, 0.0) + v
    else:
        scores = _path_route_skills(profile)
        for sk, v in _cross_cutting_skills(profile).items():
            scores[sk] = scores.get(sk, 0.0) + v
    # curated category->skill lists always blend in (both branches)
    for sk, v in _category_skills(profile).items():
        scores[sk] = scores.get(sk, 0.0) + v

    weights = _weights()
    for sk in list(scores):
        scores[sk] *= float(weights.get(sk, 1.0))

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top_n]


def dispatch_tiers(profile, *, threshold: int = DEFAULT_AUTO_DISPATCH_THRESHOLD) -> list[dict]:
    """Suggest/dispatch tiering per act intent (P1-T6). Returns items:
    {act, category, score, kind:'agent'|'suggest', agent}."""
    out: list[dict] = []
    for cat, act in _classify.ACT_MAP.items():
        score = profile.intent_score(cat)
        if score < 1:
            continue
        kind = "agent" if score >= threshold else "suggest"
        out.append({
            "act": act, "category": cat, "score": score, "kind": kind,
            "agent": _AGENT_FOR.get(cat, ""),
        })
    # stable order: strongest first
    out.sort(key=lambda d: -d["score"])
    return out


__all__ = ["rank_skills", "dispatch_tiers", "DEFAULT_AUTO_DISPATCH_THRESHOLD"]

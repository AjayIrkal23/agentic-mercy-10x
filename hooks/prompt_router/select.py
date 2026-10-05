"""select.py — S2: ranked skill selection + suggest/dispatch tiering (v3).

Ranks skills for the current TaskProfile. Scorers (each canonicalizes aliases
with a max-merge inside itself, then the scorers SUM):

  index         skills-index.json: keyword hits (word-boundary; description-token
                fallbacks count half), intent overlap, surface overlap, path rules
  cross_cut     floor cross_cutting groups (first_write / debug / implementation /
                verification — the "always" group is carried by core-skill-set)
  category      autonomous-skill-router.config.json categories[intent].local_skills
  surface       router.config.json additions.surface_skills — FE/BE/API/go/sql/…
                baselines per detected surface; stack-only inferences half-weight
  rules         router.config.json additions.skill_rules — regex -> boost

Then: weights multiply, candidates that do not exist on disk (local skill dir or
installed plugin ``plugin:skill``) or that core-skill-set already injects are
dropped, and the result is the top-N (default 5) above ``min_skill_score``.

Dispatch tiering: an intent at/above ``auto_dispatch_threshold`` is surfaced as
an AGENT dispatch (agent from the autonomous config, IMPLEMENT surface-routed via
``surface_routing``), weaker hits as a lightweight ``/invoke <act>`` suggestion.

Pure stdlib; never raises.
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import classify as _classify  # noqa: E402

_SKILLS_INDEX = _HOOKS / "skills-index.json"
_WEIGHTS = _HOOKS / "skill_router_weights.json"
_ALIASES = _HOOKS / "skill-aliases.json"
_CORE = _HOOKS / "core-skill-set.json"
_AUTON_CONFIG = _HOOKS / "autonomous-skill-router.config.json"
_ROUTER_CONFIG = _HOOKS / "prompt_router" / "router.config.json"
_CLAUDE = _HOOKS.parent

DEFAULT_AUTO_DISPATCH_THRESHOLD = 3
DEFAULT_TOP_N = 5
DEFAULT_MIN_SCORE = 3.0

# intent category -> specialist agent (fallback when the autonomous config lacks `.agent`)
_AGENT_FOR = {
    "DEBUG": "debug-detective", "DESIGN": "frontend-uiux-designer",
    "AUDIT": "audit-specialist", "SPEC": "spec-architect",
    "PLAN": "planning-director", "IMPLEMENT": "implementation-engineer",
    "CLEANUP": "deadcode-reaper", "SECURITY": "security-sentinel",
    "REVIEW": "santa-reviewer", "TEST": "test-author",
    "REFACTOR": "refactor-specialist", "DOCS": "docs-sync-agent", "VERIFY": "qa-verifier",
}
_SURFACE_ROUTING_FALLBACK = {
    "frontend": "frontend-implementor-specialist",
    "backend": "backend-implementor-specialist",
    "mixed": ["backend-implementor-specialist", "frontend-implementor-specialist", "integrator-specialist"],
    "general": "implementation-engineer",
}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def _router_cfg() -> dict:
    return _load_json(_ROUTER_CONFIG)


@lru_cache(maxsize=1)
def _auton() -> dict:
    return _load_json(_AUTON_CONFIG).get("categories") or {}


# --------------------------------------------------------------------------- #
# aliases / existence / core set
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    return {k: v for k, v in _load_json(_ALIASES).items()
            if not k.startswith("_") and isinstance(v, str)}


def canonical(name: str) -> str:
    """Alias -> canonical skill name. Prefers lib.skill_aliases (WP-3) when present."""
    try:
        from lib import skill_aliases as _sa  # noqa: PLC0415
        return _sa.canonical(name)
    except Exception:  # noqa: BLE001
        return _alias_map().get(name, name)


@lru_cache(maxsize=1)
def _skill_paths() -> dict[str, Path]:
    """Every skill that exists on disk: local ``skills/<name>`` and installed
    plugin skills as ``plugin:skill``."""
    out: dict[str, Path] = {}
    try:
        for p in (_CLAUDE / "skills").iterdir():
            if (p / "SKILL.md").is_file():
                out[p.name] = p / "SKILL.md"
    except OSError:
        pass
    inst = _load_json(_CLAUDE / "plugins" / "installed_plugins.json").get("plugins") or {}
    for key, entries in inst.items():
        plugin = str(key).split("@", 1)[0]
        for e in (entries if isinstance(entries, list) else []):
            ip = e.get("installPath") if isinstance(e, dict) else None
            if not ip:
                continue
            try:
                for sk in (Path(ip) / "skills").iterdir():
                    f = sk / "SKILL.md"
                    if f.is_file():
                        out.setdefault(f"{plugin}:{sk.name}", f)
            except OSError:
                continue
    return out


def skill_exists(name: str) -> bool:
    if name in _skill_paths():
        return True
    return name in index_meta()


def skill_path(name: str) -> Path | None:
    return _skill_paths().get(name)


@lru_cache(maxsize=1)
def core_skills() -> frozenset[str]:
    """Skills core-skill-set.json already injects at SessionStart (never re-pushed)."""
    names = set()
    for e in _load_json(_CORE).get("always") or []:
        if isinstance(e, dict) and e.get("skill"):
            names.add(canonical(str(e["skill"])))
    return frozenset(names)


def _weights() -> dict:
    """Shared loader with skill_router.py: clamp [0.1, 1.0], dead keys dropped (C-16)."""
    from prompt_router import weights as _w  # noqa: PLC0415
    return _w.load(_WEIGHTS, set(index_meta()))


def _norm(s: str) -> str:
    return s.replace("\\", "/").lower()


def _merge_canonical(raw: dict[str, float]) -> dict[str, float]:
    """Alias + canonical scored by the same scorer collapse to max(canonical)."""
    out: dict[str, float] = {}
    for name, v in raw.items():
        c = canonical(name)
        out[c] = max(out.get(c, 0.0), float(v))
    return out


# --------------------------------------------------------------------------- #
# scorers
# --------------------------------------------------------------------------- #
def _index_skills(profile, index: dict, grams: set) -> dict[str, float]:
    scores: dict[str, float] = {}
    intents = set(profile.intents)
    surfaces = set(profile.surfaces)
    weak = set(getattr(profile, "weak_surfaces", set()) or set())
    weak_factor = float(_router_cfg().get("weak_surface_factor", 0.5))
    for name, meta in (index.get("skills") or {}).items():
        if not isinstance(meta, dict):
            continue
        # description-token keywords (index source `description`; `floor-fallback`
        # on the no-index path) count half and saturate at 2.0 — a long description
        # must not outscore a real signal; curated keywords count 1.0, cap 4.0
        fallback = meta.get("source") in ("description", "floor-fallback")
        kw_w, kw_cap = (0.5, 2.0) if fallback else (1.0, 4.0)
        s = 0.0
        for kw in meta.get("keywords", []) or []:
            k = str(kw).lower()
            if _classify.keyword_ok(k) and _classify.words(k) in grams:
                s += kw_w
        s = min(s, kw_cap)
        if intents & set(meta.get("intents", []) or []):
            s += 1.5
        hit = surfaces & set(meta.get("surfaces", []) or [])
        if hit:  # stack-only (weak) surfaces earn partial credit, like _surface_skills
            s += 1.0 if hit - weak else weak_factor
        for rule in meta.get("path_rules", []) or []:
            if not isinstance(rule, dict):
                continue
            for pth in profile.paths:
                if any(_norm(x) in _norm(pth) for x in (rule.get("path_contains_any", []) or [])):
                    s += 1.2
                ext = "." + pth.rsplit(".", 1)[-1] if "." in pth.rsplit("/", 1)[-1] else ""
                if ext and ext in [str(e).lower() for e in (rule.get("extensions") or [])]:
                    s += 1.2
        if s > 0:
            scores[name] = s
    return scores


def _path_route_skills(profile) -> dict[str, float]:
    """Floor path-route rules matched against paths (index-less fallback)."""
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
    groups = _classify._floor_index().get("cross_cutting") or {}
    scores: dict[str, float] = {}
    if profile.first_write_candidate:
        for sk in groups.get("first_write_only", []):
            scores[sk] = scores.get(sk, 0.0) + 1.8
    if "DEBUG" in profile.intents:
        for sk in groups.get("debug", []):
            scores[sk] = scores.get(sk, 0.0) + 1.5
    if {"IMPLEMENT", "SPEC", "PLAN"} & set(profile.intents):
        for sk in groups.get("implementation", []):
            scores[sk] = scores.get(sk, 0.0) + 1.3
    if {"REVIEW", "TEST", "QA", "VERIFY"} & set(profile.intents):
        for sk in groups.get("verification", []):
            scores[sk] = scores.get(sk, 0.0) + 1.2
    return scores


def _category_skills(profile) -> dict[str, float]:
    """Curated category -> local_skills from the autonomous router config.

    IMPLEMENT is surface-aware: its 40-skill ``local_skills`` list is replaced by
    ``stack_groups[<surface>]`` for each surface the PROMPT/cwd established
    (stack-only inferences do not count) plus ``stack_groups.cross_cutting`` at
    half boost — so a build prompt never drags the other surface's baseline in.
    """
    scores: dict[str, float] = {}
    cats = _auton()
    strong = set(profile.surfaces) - set(getattr(profile, "weak_surfaces", set()) or set())
    for cat, hit_score in (profile.intents or {}).items():
        meta = cats.get(cat)
        if not isinstance(meta, dict):
            continue
        boost = 1.4 + 0.2 * min(int(hit_score), 3)
        groups = meta.get("stack_groups")
        if cat == "IMPLEMENT" and isinstance(groups, dict):
            for surf in ("frontend", "backend"):
                if surf in strong:
                    for sk in groups.get(surf) or []:
                        scores[sk] = max(scores.get(sk, 0.0), boost)
            for sk in groups.get("cross_cutting") or []:
                scores[sk] = max(scores.get(sk, 0.0), boost * 0.5)
            continue
        for sk in meta.get("local_skills") or []:
            scores[sk] = max(scores.get(sk, 0.0), boost)
    return scores


def _surface_skills(profile) -> dict[str, float]:
    cfg = _router_cfg()
    table = (cfg.get("additions") or {}).get("surface_skills") or {}
    weak_factor = float(cfg.get("weak_surface_factor", 0.5))
    weak = set(getattr(profile, "weak_surfaces", set()) or set())
    scores: dict[str, float] = {}
    for surf in profile.surfaces:
        f = weak_factor if surf in weak else 1.0
        for sk, boost in (table.get(surf) or {}).items():
            scores[sk] = max(scores.get(sk, 0.0), float(boost) * f)
    return scores


def _rule_skills(profile) -> dict[str, float]:
    rules = (_router_cfg().get("additions") or {}).get("skill_rules") or []
    scores: dict[str, float] = {}
    for r in rules:
        if not isinstance(r, dict) or not r.get("skill") or not r.get("regex"):
            continue
        need = set(r.get("surfaces") or [])
        if need and not (need & profile.surfaces):
            continue
        try:
            if re.search(str(r["regex"]), profile.text, re.IGNORECASE):
                scores[r["skill"]] = max(scores.get(r["skill"], 0.0), float(r.get("boost", 1.0)))
        except re.error:
            continue
    return scores


def index_meta() -> dict:
    """skills-index metadata (name -> {description, keywords, ...}); {} on error."""
    return (_load_json(_SKILLS_INDEX).get("skills") or {})


def rank_all(profile) -> list[tuple[str, float]]:
    """Every scored, existing, non-core skill — descending (no cap, no floor)."""
    index = _load_json(_SKILLS_INDEX)
    grams = _classify.ngrams(profile.text)
    scorers = [
        _index_skills(profile, index, grams) if index.get("skills") else _path_route_skills(profile),
        _cross_cutting_skills(profile),
        _category_skills(profile),
        _surface_skills(profile),
        _rule_skills(profile),
    ]
    total: dict[str, float] = {}
    for raw in scorers:
        for name, v in _merge_canonical(raw).items():
            total[name] = total.get(name, 0.0) + v
    weights = _weights()
    demote = (_router_cfg().get("additions") or {}).get("demote") or {}
    core = core_skills()
    hidden = {n for n, m in (index.get("skills") or {}).items()
              if isinstance(m, dict) and m.get("hidden")}
    out = []
    for name, v in total.items():
        if name in core or name in hidden or not skill_exists(name):
            continue
        # learned weights may demote, never boost: their input is test-polluted and
        # frozen since 2026-09-27 (audit C-01)
        v *= min(float(weights.get(name, 1.0)), 1.0) * float(demote.get(name, 1.0))
        out.append((name, v))
    out.sort(key=lambda kv: (-kv[1], kv[0]))
    return out


def rank_skills(profile, *, top_n: int = DEFAULT_TOP_N,
                min_score: float = DEFAULT_MIN_SCORE) -> list[tuple[str, float]]:
    """Return [(skill_name, score)] descending — at most ``top_n``, all >= ``min_score``."""
    return [(n, s) for n, s in rank_all(profile) if s >= min_score][:top_n]


# --------------------------------------------------------------------------- #
# dispatch tiering
# --------------------------------------------------------------------------- #
def implement_agent(profile) -> str:
    """IMPLEMENT specialist by surface (categories.IMPLEMENT.surface_routing)."""
    routing = (_auton().get("IMPLEMENT") or {}).get("surface_routing")
    if not isinstance(routing, dict):
        routing = _SURFACE_ROUTING_FALLBACK
    s = profile.surfaces
    if "fullstack" in s or {"frontend", "backend"} <= s:
        mixed = routing.get("mixed") or _SURFACE_ROUTING_FALLBACK["mixed"]
        if isinstance(mixed, list):
            return " then ".join(str(x) for x in mixed)
        return str(mixed)
    if "frontend" in s:
        return str(routing.get("frontend") or _SURFACE_ROUTING_FALLBACK["frontend"])
    if "backend" in s:
        return str(routing.get("backend") or _SURFACE_ROUTING_FALLBACK["backend"])
    return str(routing.get("general") or _SURFACE_ROUTING_FALLBACK["general"])


def agent_for(category: str, profile=None) -> str:
    if category == "IMPLEMENT" and profile is not None:
        return implement_agent(profile)
    meta = _auton().get(category)
    if isinstance(meta, dict) and isinstance(meta.get("agent"), str) and meta["agent"]:
        return meta["agent"]
    return _AGENT_FOR.get(category, "")


def dispatch_tiers(profile, *, threshold: int = DEFAULT_AUTO_DISPATCH_THRESHOLD) -> list[dict]:
    """Suggest/dispatch tiering per act intent. Returns items
    {act, category, score, kind:'agent'|'suggest', agent} strongest first."""
    out: list[dict] = []
    for cat, act in _classify.ACT_MAP.items():
        score = profile.intent_score(cat)
        if score < 1:
            continue
        kind = "agent" if score >= threshold else "suggest"
        out.append({"act": act, "category": cat, "score": score, "kind": kind,
                    "agent": agent_for(cat, profile)})
    out.sort(key=lambda d: -d["score"])
    return out


__all__ = ["rank_skills", "rank_all", "dispatch_tiers", "canonical", "skill_exists",
           "skill_path", "core_skills", "index_meta", "implement_agent", "agent_for",
           "DEFAULT_AUTO_DISPATCH_THRESHOLD", "DEFAULT_TOP_N", "DEFAULT_MIN_SCORE"]

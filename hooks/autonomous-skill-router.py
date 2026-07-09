#!/usr/bin/env python3
"""
autonomous-skill-router.py — UserPromptSubmit hook.

Classifies user prompt intent via multi-signal weighted keyword matching and
auto-injects skill routing context so Claude invokes the right skill immediately.

Protocol:
  stdin:  {"prompt": "...", "conversation_id": "...", "attachments": [...]}
  stdout: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}
  exit:   always 0 (fail-open)

State file: ~/.claude/hooks/.state/{conversation_id}.skill-router.json
  {"last_classification": "DEBUG", "classifications_count": 1}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "autonomous-skill-router.config.json"
STATE_DIR = SCRIPT_DIR / ".state"
SKILL_ROOT = Path.home() / ".claude" / "skills"
PLUGINS_ROOT = Path.home() / ".claude" / "plugins"

# ---------------------------------------------------------------------------
# Default config (written when config file is absent)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict[str, Any] = {
    "superpowers_skills_root": "",
    "categories": {},
    "phase_change_pairs": [],
    "category_priority": [
        "DEBUG", "SECURITY", "SHIP", "PLAN", "LARGE", "REVIEW",
        "QA", "TEST", "DESIGN", "RESUME", "MEDIUM", "SMALL",
    ],
}

# Minimum score threshold to emit any routing. MIN_SCORE=1 means a SINGLE
# keyword match is enough to fire a category (e.g. "audit" -> AUDIT). This is
# intentional: the user wants single keywords to trigger, not be dropped.
# Override per-config with top-level "min_score".
MIN_SCORE = 1

# Generic "size" buckets. They only emit when NO specialized intent
# (DEBUG/SPEC/PLAN/AUDIT/REVIEW/…) fired, so "plan the auth system" routes
# PLAN — not LARGE noise alongside it.
SIZE_CATS = {"SMALL", "MEDIUM", "LARGE"}

# Max number of categories that may stack in one routing emission.
# 6 so all specialized intents (SPEC/PLAN/AUDIT/IMPLEMENT/DESIGN/CLEANUP) can
# fire together without any being dropped. Override with top-level "max_stack".
MAX_STACK = 6


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {**_DEFAULT_CONFIG, **raw}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT_CONFIG)


# ---------------------------------------------------------------------------
# Superpowers skill discovery
# ---------------------------------------------------------------------------

def _discover_superpowers_dir(cfg: dict) -> Path | None:
    env = (os.environ.get("SUPERPOWERS_SKILLS_ROOT") or "").strip()
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
    cfg_val = (cfg.get("superpowers_skills_root") or "").strip()
    if cfg_val:
        p = Path(cfg_val).expanduser()
        if p.is_dir():
            return p
    # Glob for versioned directory
    try:
        for candidate in PLUGINS_ROOT.glob("**/superpowers"):
            if not candidate.is_dir():
                continue
            for child in candidate.iterdir():
                skills_dir = child / "skills"
                if child.is_dir() and skills_dir.is_dir():
                    return skills_dir
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Prompt flattening
# ---------------------------------------------------------------------------

def _flatten_prompt(payload: dict) -> str:
    parts: list[str] = []
    p = payload.get("prompt")
    if isinstance(p, str):
        parts.append(p)
    attachments = payload.get("attachments")
    if isinstance(attachments, list):
        for a in attachments:
            if isinstance(a, dict) and isinstance(a.get("file_path"), str):
                parts.append(a["file_path"])
    return "\n".join(parts).lower()


# ---------------------------------------------------------------------------
# Keyword matching
# ---------------------------------------------------------------------------

def _kw_match(text: str, keyword: str) -> bool:
    """Word-boundary match for short keywords (<=4 chars), substring for longer."""
    kw = keyword.strip().lower()
    if not kw:
        return False
    if len(kw) <= 4:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text))
    return kw in text


def _score_category(text: str, keywords: list[str]) -> int:
    """Count how many keywords match; heavier weight for multi-word phrases."""
    score = 0
    for kw in keywords:
        if _kw_match(text, kw):
            score += 2 if " " in kw else 1
    return score


# ---------------------------------------------------------------------------
# File-extension complexity hint
# ---------------------------------------------------------------------------

_CODE_EXTS = {".go", ".ts", ".tsx", ".py", ".js", ".jsx", ".sql", ".yaml", ".yml"}

def _count_code_file_refs(text: str) -> int:
    """Count how many distinct code file references appear in the prompt."""
    pattern = r"\b\w[\w\-/]*\.(?:go|tsx?|jsx?|py|sql|yaml|yml)\b"
    matches = set(re.findall(pattern, text))
    return len(matches)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify(text: str, cfg: dict) -> str | None:
    """
    Return the winning category name, or None if no signal is strong enough.

    Priority order: category_priority list in config.
    A category must score >= 1 to be considered (except TRIVIAL which uses
    its own heuristic check first).
    """
    categories: dict[str, Any] = cfg.get("categories", {})
    priority_order: list[str] = cfg.get("category_priority", [])

    # Score every non-TRIVIAL category first
    scores: dict[str, int] = {}
    for cat_name, cat_cfg in categories.items():
        if cat_name == "TRIVIAL":
            continue
        kws: list[str] = cat_cfg.get("keywords", [])
        s = _score_category(text, kws)
        if s > 0:
            scores[cat_name] = s

    # TRIVIAL check: only wins if trivial keyword present AND no other
    # category scored > 1. This prevents "fix the hero section typo"
    # from suppressing the DESIGN routing.
    trivial_cfg = categories.get("TRIVIAL", {})
    trivial_kws: list[str] = trivial_cfg.get("keywords", [])
    file_refs = _count_code_file_refs(text)
    trivial_kw_hit = any(_kw_match(text, kw) for kw in trivial_kws)
    max_other_score = max(scores.values()) if scores else 0
    if trivial_kw_hit and file_refs <= 1 and max_other_score == 0:
        return "TRIVIAL"

    if not scores:
        return None

    # Pick winner by priority order; ties broken by score then priority index
    best_cat: str | None = None
    best_score = 0
    for cat in priority_order:
        if cat in scores:
            if scores[cat] > best_score:
                best_score = scores[cat]
                best_cat = cat
            elif scores[cat] == best_score and best_cat is None:
                best_cat = cat
            # Respect explicit priority: first hit in priority list wins ties
            if best_cat is None:
                best_cat = cat

    # Fall back to highest raw score if priority list incomplete
    if best_cat is None and scores:
        best_cat = max(scores, key=lambda c: scores[c])

    return best_cat


def _classify_multi(text: str, cfg: dict) -> list[str]:
    """
    Return ALL qualifying categories (intent stacking), priority-ordered,
    capped at MAX_STACK. This lets overlapping intents fire together —
    e.g. "spec and plan the auth system" → ["SPEC", "PLAN"].

    Rules:
      - A category qualifies at score >= MIN_SCORE (filters single weak hits).
      - Specialized intents suppress the generic SIZE_CATS buckets: size
        buckets only survive when no specialized category qualified.
      - TRIVIAL wins alone only when a trivial keyword hit, <=1 file ref,
        and nothing else scored (same guard as _classify).
      - Ordering: category_priority index, then score desc. Top MAX_STACK kept.
    """
    categories: dict[str, Any] = cfg.get("categories", {})
    priority_order: list[str] = cfg.get("category_priority", [])
    min_score = int(cfg.get("min_score", MIN_SCORE))
    max_stack = int(cfg.get("max_stack", MAX_STACK))

    scores: dict[str, int] = {}
    for cat_name, cat_cfg in categories.items():
        if cat_name == "TRIVIAL":
            continue
        s = _score_category(text, cat_cfg.get("keywords", []))
        if s > 0:
            scores[cat_name] = s

    # TRIVIAL guard (mirrors _classify)
    trivial_cfg = categories.get("TRIVIAL", {})
    trivial_kws: list[str] = trivial_cfg.get("keywords", [])
    file_refs = _count_code_file_refs(text)
    trivial_kw_hit = any(_kw_match(text, kw) for kw in trivial_kws)
    max_other_score = max(scores.values()) if scores else 0
    if trivial_kw_hit and file_refs <= 1 and max_other_score == 0:
        return ["TRIVIAL"]

    qualified = {c: s for c, s in scores.items() if s >= min_score}
    if not qualified:
        return []

    specialized = {c: s for c, s in qualified.items() if c not in SIZE_CATS}
    pool = specialized if specialized else qualified

    def _sort_key(c: str) -> tuple[int, int]:
        pi = priority_order.index(c) if c in priority_order else len(priority_order)
        return (pi, -pool[c])

    return sorted(pool.keys(), key=_sort_key)[:max_stack]


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _state_path(conversation_id: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", conversation_id)[:64]
    return STATE_DIR / f"{safe_id}.skill-router.json"


def _load_state(conversation_id: str) -> dict:
    p = _state_path(conversation_id)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_classification": None, "classifications_count": 0, "turns_since_last_emit": 0}


def _save_state(conversation_id: str, state: dict) -> None:
    try:
        _state_path(conversation_id).write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


def _is_phase_change(prev: str | None, current: str, state: dict) -> bool:
    """True when routing should re-emit.

    Re-emits when:
      - First classification in this conversation (prev is None), OR
      - More than STALENESS_TURNS have passed since last emit (staleness timer).
        This applies regardless of whether the category changed — it handles
        both "conversation drift to a new category" and "sustained work in the
        same category that needs a periodic reminder".
      - The category has changed since the last emit (immediate re-emit on
        intent switch, e.g. PLAN → DEBUG on turn 2 before staleness expires).

    STALENESS_TURNS=3 means: after 3 un-emitted turns, re-emit the routing.
    Category-change detection replaces the hard-coded phase_change_pairs list
    and handles all 132+ possible category transitions immediately.
    """
    STALENESS_TURNS = 3
    if prev is None:
        return True
    turns_since_last = state.get("turns_since_last_emit", 0)
    return turns_since_last >= STALENESS_TURNS or (prev is not None and prev != current)


# ---------------------------------------------------------------------------
# Output builders
# ---------------------------------------------------------------------------

def _skill_path(name: str) -> str:
    if ":" in name:  # plugin-namespaced skill — no local path; the invoke name IS the hint
        return name
    return str((SKILL_ROOT / name / "SKILL.md").resolve())


def _sp_skill_path(sp_dir: Path, name: str) -> str | None:
    p = sp_dir / name / "SKILL.md"
    return str(p.resolve()) if p.is_file() else None


def _skill_exists(name: str) -> bool:
    if ":" in name:  # plugin-namespaced skill (plugin:skill) — plugin mgr owns it, trust it
        return True
    return (SKILL_ROOT / name / "SKILL.md").is_file()


_CEREMONY_LABELS = {
    "trivial": "trivial",
    "light": "light",
    "standard": "standard",
    "full": "full",
}


def _build_context(category: str, cat_cfg: dict, sp_dir: Path | None) -> str:
    local_skills: list[str] = [s for s in cat_cfg.get("local_skills", []) if _skill_exists(s)]
    sp_skills_names: list[str] = cat_cfg.get("superpowers_skills", [])
    ceremony = _CEREMONY_LABELS.get(cat_cfg.get("ceremony", "standard"), "standard")

    # Resolve superpowers paths
    sp_lines: list[str] = []
    if sp_dir:
        for name in sp_skills_names:
            p = _sp_skill_path(sp_dir, name)
            if p:
                sp_lines.append(f"  - {name}: `{p}`")

    # Primary local skill (first one = auto-invoke)
    primary = local_skills[0] if local_skills else None
    secondary = local_skills[1:] if len(local_skills) > 1 else []

    lines: list[str] = [
        f"AUTONOMOUS ROUTING: Detected intent=[{category}]. Ceremony level: {ceremony}.",
    ]

    if primary:
        lines.append(f"Auto-invoking skill: {primary}.")
        lines.append("You MUST invoke this skill via the Skill tool BEFORE any other action.")
        lines.append("Do NOT ask the user for confirmation — this is autonomous routing.")
        lines.append(f"  Primary: `{_skill_path(primary)}`")
    elif sp_lines:
        # No local skill but superpowers available
        first_sp_name = sp_skills_names[0] if sp_skills_names else None
        if first_sp_name:
            lines.append(f"Auto-invoking skill: {first_sp_name}.")
            lines.append("You MUST invoke this skill via the Skill tool BEFORE any other action.")
            lines.append("Do NOT ask the user for confirmation — this is autonomous routing.")

    if secondary:
        also_paths = " | ".join(f"`{_skill_path(s)}`" for s in secondary)
        lines.append(f"  Also read: {also_paths}")

    if sp_lines:
        lines.append("  Superpowers skills (in order):")
        lines.extend(sp_lines)

    return "\n".join(lines)


def _build_multi_context(cats: list[str], cfg: dict, sp_dir: Path | None) -> str:
    """
    Build forceful routing context for one or more stacked intents.

    Unlike _build_context (first-skill-only auto-invoke), this lists EVERY
    skill in each routed bucket and instructs Claude to invoke all that apply,
    category-by-category. Skills shared across buckets are listed once.
    """
    categories: dict[str, Any] = cfg.get("categories", {})
    intents = ", ".join(cats)

    lines: list[str] = [
        f"AUTONOMOUS ROUTING: Detected intent(s)=[{intents}].",
        "You MUST invoke the skills below via the Skill tool BEFORE any other "
        "action (before planning, reading files, editing, or answering).",
        "Invoke ALL listed skills, no exceptions — do NOT cherry-pick just one, and "
        "do NOT ask the user for confirmation. This is autonomous routing. "
        "(A Stop gate re-nags until every listed skill has loaded.)",
        "Work category-by-category, top to bottom.",
    ]

    seen: set[str] = set()
    for cat in cats:
        cat_cfg = categories.get(cat, {})
        local_skills = [
            s for s in cat_cfg.get("local_skills", [])
            if _skill_exists(s) and s not in seen
        ]
        sp_names = cat_cfg.get("superpowers_skills", [])
        ceremony = _CEREMONY_LABELS.get(cat_cfg.get("ceremony", "standard"), "standard")

        sp_lines: list[str] = []
        if sp_dir:
            for name in sp_names:
                if name in seen:
                    continue
                p = _sp_skill_path(sp_dir, name)
                if p:
                    sp_lines.append(f"  - {name} (superpowers): `{p}`")
                    seen.add(name)

        if not local_skills and not sp_lines:
            continue

        lines.append("")
        lines.append(f"[{cat}] (ceremony: {ceremony}) — invoke these skills:")
        for s in local_skills:
            seen.add(s)
            lines.append(f"  - {s}: `{_skill_path(s)}`")
        lines.extend(sp_lines)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError, ValueError):
        print("{}")
        return 0
    if not isinstance(payload, dict):
        print("{}")
        return 0

    conversation_id: str = payload.get("conversation_id") or payload.get("session_id") or "unknown"
    cfg = _load_config()
    text = _flatten_prompt(payload)

    # Multi-intent classification: one or more stacked categories.
    # _classify_multi already applies the MIN_SCORE gate per category.
    cats = _classify_multi(text, cfg)

    # TRIVIAL (alone) or no signal → emit nothing
    if not cats or cats == ["TRIVIAL"]:
        print("{}")
        return 0

    # Stable key for state comparison (order-independent set of intents)
    current_key = "+".join(sorted(cats))

    # State check: only route on first prompt or genuine phase changes
    state = _load_state(conversation_id)
    prev_key: str | None = state.get("last_classification")
    count: int = state.get("classifications_count", 0)
    turns_since_last: int = state.get("turns_since_last_emit", 0)

    should_emit = (count == 0) or _is_phase_change(prev_key, current_key, state)

    # Update state — only update last_classification when emitting so that
    # _is_phase_change compares against the last *emitted* intent set, not the
    # last *classified* one. This keeps the staleness timer correct when the
    # same intent set persists for STALENESS_TURNS without a re-emit.
    state["classifications_count"] = count + 1
    if should_emit:
        state["last_classification"] = current_key
        state["turns_since_last_emit"] = 0
    else:
        state["turns_since_last_emit"] = turns_since_last + 1
    _save_state(conversation_id, state)

    if not should_emit:
        print("{}")
        return 0

    sp_dir = _discover_superpowers_dir(cfg)
    ctx = _build_multi_context(cats, cfg, sp_dir)
    if not ctx.strip():
        print("{}")
        return 0

    # Record the Skill-tool slugs this routing pushed, so invoke-suite-gate.py (Stop)
    # can verify they all loaded. Mirror exactly what _build_multi_context surfaced:
    # local skills that exist, plus superpowers only when the superpowers dir resolved.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import suite_push  # noqa: E402
        cats_cfg = cfg.get("categories", {})
        pushed: list[str] = []
        for c in cats:
            cc = cats_cfg.get(c, {})
            pushed += [s for s in cc.get("local_skills", []) if _skill_exists(s)]
            if sp_dir:
                pushed += [f"superpowers:{n}" for n in cc.get("superpowers_skills", [])]
        # ponytail: keyword guesses SURFACE skills, they don't trap the turn. Soft push =
        # reminded but not Stop-gated. Only explicit /invoke-* (invoke-suite-manifest.py)
        # stays enforce="hard". Kills the "matched N categories -> must invoke 76 skills" loop.
        suite_push.push(conversation_id, pushed, source="auto-router", enforce="soft")
    except Exception:
        pass

    out = {
        "additionalContext": ctx,
    }
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

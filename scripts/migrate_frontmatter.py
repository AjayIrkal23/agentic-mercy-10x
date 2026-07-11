#!/usr/bin/env python3
"""
migrate_frontmatter.py — P5-T2 schema-v1 enrichment.

- 90 user-authored skills: enrich SKILL.md front-matter in place (idempotent):
  schema:1, triggers{keywords,paths,intents}, category, surfaces, platforms,
  token-cost. Native keys preserved. The 10 garbled descriptions are rewritten
  to sharp single sentences; the token-diff gate folds any dropped trigger word
  into triggers.keywords (garble removal != keyword removal).
- 128 upstream-locked skills: ZERO file writes; the same metadata is written to
  hooks/skills-index-overrides.json 'skills' (native name/description only read).

Emits hooks/skills-index.json (all 218). Re-running is a no-op.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import skills_lib as sl

OVERRIDES = sl.HOOKS_DIR / "skills-index-overrides.json"
FLOOR = sl.HOOKS_DIR / "trigger-floor.json"

# The 10 garbled doubled descriptions -> sharp single sentences (audit §5).
# First clean sentence retained (carries the trigger words); doubled tail dropped.
DESC_REWRITE = {
    "agent-development":
        "Use when creating or revising reusable agent definitions, trigger text, or "
        "system prompts for autonomous helpers.",
    "api-contract-standards":
        "Use when backend response envelopes, list metadata, error shapes, versioning, "
        "or the separation between table, card, and summary contracts are being defined "
        "or reviewed.",
    "architect-system-design":
        "Use when the main task is design, decomposition, interface planning, or "
        "implementation planning before code changes begin.",
    "backend-api-standards":
        "Use when a backend task needs strict list or search endpoint rules for "
        "filtering, sorting, pagination, stable response shapes, or query validation.",
    "backend-error-handling":
        "Use when defining backend error taxonomy, centralized handler behavior, safe "
        "logging, redaction, or client-safe error mapping.",
    "backend-performance-standards":
        "Use when reviewing backend query efficiency, file-size pressure, repeated DB "
        "work, scaling risk, or safe optimization boundaries.",
    "react-hooks-patterns":
        "Use when implementing or reviewing React component state, effects, refs, "
        "reducers, memoization, or custom hook extraction.",
    "scaffold-standards":
        "Use when scaffolding a new backend or full-stack domain, a "
        "route/controller/service/schema skeleton, or a standard list and CRUD "
        "feature structure.",
    "service-layer-standards":
        "Use when any backend API, route, controller, schema, service, contract, "
        "persistence, auth, validation, worker, queue, integration, or server behavior "
        "task is requested.",
    "tailwind-design-system":
        "Use when implementing or revising Tailwind CSS v4 tokens, themes, utility "
        "conventions, or component primitives in a Tailwind-based frontend.",
}

_LOCKED_PLATFORMS = {"gstack-clone": ["linux", "darwin"]}


def _floor_paths_by_skill() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if not FLOOR.exists():
        return out
    try:
        floor = json.loads(FLOOR.read_text())
    except json.JSONDecodeError:
        return out
    for ent in floor.get("entries", []):
        if not isinstance(ent, dict):
            continue
        val = ent.get("value")
        if isinstance(val, dict) and val.get("skills"):
            match = val.get("match", {})
            paths = []
            for key in ("path_contains_any", "path_suffix_any", "path_any"):
                paths += match.get(key, []) or []
            for s in val["skills"]:
                if paths:
                    out.setdefault(s, set()).update(paths)
    return out


def _seed_keywords(name: str, old_desc: str, new_desc: str) -> list[str]:
    kws = sl.trigger_words(new_desc) | sl.trigger_words(name.replace("-", " "))
    missing = sl.token_diff(old_desc, new_desc, kws)
    kws |= missing  # trigger-law: no distinctive old word is lost
    return sorted(kws)


def migrate_user(dry: bool = False) -> tuple[int, list[str]]:
    floor_paths = _floor_paths_by_skill()
    edited = 0
    diff_fail: list[str] = []
    for name in sl.user_authored_skills():
        d = sl.SKILLS_DIR / name
        fm, body, ok = sl.read_frontmatter(d / "SKILL.md")
        if not ok:
            diff_fail.append(f"{name}: unreadable")
            continue
        old_desc = str(fm.get("description", ""))
        new_desc = DESC_REWRITE.get(name, old_desc)
        keywords = _seed_keywords(name, old_desc, new_desc)
        # trigger-law proof
        if sl.token_diff(old_desc, new_desc, keywords):
            diff_fail.append(f"{name}: {sorted(sl.token_diff(old_desc, new_desc, keywords))}")
        category = sl.infer_category(name, body)
        surfaces = sl.infer_surfaces(category)
        platforms = sl.infer_platforms(body)
        paths = sorted(floor_paths.get(name, set()))
        intents = sorted({category})
        triggers = {"keywords": keywords, "paths": paths, "intents": intents}

        new_fm = dict(fm)
        new_fm["description"] = new_desc
        new_fm["schema"] = 1
        new_fm["category"] = category
        new_fm["surfaces"] = surfaces
        new_fm["platforms"] = platforms
        new_fm["token-cost"] = sl.estimate_token_cost(d)
        new_fm["triggers"] = triggers

        # idempotence: compare serialized bytes (bulletproof — a re-run that would
        # produce the identical file is a no-op).
        new_content = sl.dump_frontmatter(new_fm, body)
        current = (d / "SKILL.md").read_text(encoding="utf-8")
        if new_content == current:
            continue
        if not dry:
            (d / "SKILL.md").write_text(new_content, encoding="utf-8")
        edited += 1
    return edited, diff_fail


def migrate_locked_sidecar() -> int:
    families = sl.derive_families()
    ov = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {"skills": {}}
    ov.setdefault("skills", {})
    for name, family in families.items():
        desc = sl.skill_description(name)  # native description only
        keywords = sorted(sl.trigger_words(desc) | sl.trigger_words(name.replace("-", " ")))
        category = sl.infer_category(name, "")
        entry = ov["skills"].get(name, {})
        entry.update({
            "triggers": {"keywords": keywords, "paths": entry.get("triggers", {}).get("paths", []),
                         "intents": [category]},
            "category": category,
            "surfaces": sl.infer_surfaces(category),
            "platforms": _LOCKED_PLATFORMS.get(family, ["linux", "darwin", "windows"]),
            "family": family,
        })
        # preserve any cluster links / exec-note set by T5
        ov["skills"][name] = entry
    OVERRIDES.write_text(json.dumps(ov, indent=2) + "\n", encoding="utf-8")
    return len(families)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    edited, diff_fail = migrate_user(dry=args.dry_run)
    locked = migrate_locked_sidecar()
    print(f"user-authored edited: {edited}/90 (dry={args.dry_run})")
    print(f"locked sidecar entries: {locked}/128")
    if diff_fail:
        print(f"TOKEN-DIFF FAIL ({len(diff_fail)}):")
        for f in diff_fail:
            print("  ", f)
        return 1
    print("token-diff: PASS (every distinctive old trigger word survives)")
    # refresh index
    import build_skills_index
    payload = build_skills_index.build()
    (sl.HOOKS_DIR / "skills-index.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"skills-index.json: {payload['_meta']['count']} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())

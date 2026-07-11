#!/usr/bin/env python3
"""
build_skills_index.py — P5-T1 canonical skills indexer (supersedes the P1-T5
bootstrap builder).

Merges, into hooks/skills-index.json covering ALL 218 skill names:
  - direct schema-v1 front-matter for the 90 user-authored skills
  - hooks/skills-index-overrides.json 'skills' entries for the 128 locked ones
    (a locked skill with no override entry falls back to its native
    name/description only — never any deeper parse)
  - hooks/skill-aliases.json (alias -> canonical) so every alias resolves

Deterministic: same inputs -> same bytes (a content hash lands in _meta).

--emit-legacy-configs regenerates skill_router.config.json + the routing
sections of fullstack/ui-ux configs from the index, each gated behind a
trigger-floor superset check (P5-T10). Inert until trigger-floor.json exists.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import skills_lib as sl

OVERRIDES = sl.HOOKS_DIR / "skills-index-overrides.json"
ALIASES = sl.HOOKS_DIR / "skill-aliases.json"
FLOOR = sl.HOOKS_DIR / "trigger-floor.json"
INDEX = sl.HOOKS_DIR / "skills-index.json"


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _infer_category(name: str, body: str) -> str:
    n = body.lower()
    if name.startswith("backend-") or "go_udp" in n:
        return "backend"
    if name.startswith("frontend-") or "tailwind" in name or "react" in name:
        return "frontend"
    if "debug" in name or "diagnos" in name:
        return "debug"
    if "review" in name or "audit" in name:
        return "review"
    if "test" in name or "tdd" in name:
        return "testing"
    if "security" in name or "owasp" in name:
        return "security"
    return "general"


def build() -> dict:
    overrides = _load(OVERRIDES)
    ov_skills = overrides.get("skills", {}) or {}
    aliases = {k: v for k, v in _load(ALIASES).items() if not k.startswith("_")}
    locked = sl.locked_skills()
    provenance = _load(sl.HOOKS_DIR / "skills-provenance.json")

    entries: dict = {}
    for d in sl.skill_dirs():
        name = d.name
        fm, body, ok = sl.read_frontmatter(d / "SKILL.md")
        desc = str(fm.get("description", "")) if ok else ""
        is_locked = name in locked
        entry: dict = {
            "name": name,
            "description": desc,
            "locked": is_locked,
            "provenance": provenance.get(name, {}).get("family") if is_locked else "self",
        }
        if is_locked and name in ov_skills:
            # sidecar routing metadata (never parsed from the locked body)
            entry.update({k: v for k, v in ov_skills[name].items()
                          if k in ("triggers", "category", "surfaces", "platforms",
                                   "links", "requires", "model-hint", "token-cost",
                                   "lead-of", "member-of", "exec-note")})
        elif not is_locked:
            for k in ("triggers", "category", "surfaces", "platforms", "links",
                      "requires", "model-hint", "token-cost", "alias_of"):
                if k in fm:
                    entry[k] = fm[k]
            entry.setdefault("category", _infer_category(name, body))
            entry.setdefault("token-cost", sl.estimate_token_cost(d))
        entries[name] = entry

    # weave aliases: an alias entry points at its canonical
    for alias, canonical in aliases.items():
        if alias in entries:
            entries[alias]["alias_of"] = canonical

    payload = {"skills": dict(sorted(entries.items()))}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload = {
        "_meta": {
            "purpose": "P5-T1 canonical skills index (all 218 names rankable)",
            "count": len(entries),
            "bodyBearing": len([e for e in entries.values() if not e.get("alias_of")]),
            "aliases": len(aliases),
            "locked": len([e for e in entries.values() if e.get("locked")]),
            "contentHash": sl.sha256_text(blob),
        },
        **payload,
    }
    return payload


def _floor_referenced_skills(floor: dict) -> set[str]:
    out: set[str] = set()
    for ent in floor.get("entries", []) or []:
        val = ent.get("value") if isinstance(ent, dict) else None
        if isinstance(val, dict):
            out |= set(val.get("skills", []) or [])
    return out


def superset_check(candidate_rules: list[dict], floor: dict) -> set[str]:
    """Return floor-referenced skills the candidate config would DROP (empty = ok)."""
    floor_skills = _floor_referenced_skills(floor)
    cand_skills: set[str] = set()
    for r in candidate_rules:
        cand_skills |= set(r.get("skills", []) or [])
    aliases = {k: v for k, v in _load(ALIASES).items() if not k.startswith("_")}
    # an alias resolves to its canonical, so a canonical in the candidate covers the alias
    covered = cand_skills | {a for a, c in aliases.items() if c in cand_skills}
    return floor_skills - covered


def emit_legacy_configs(apply: bool = False) -> int:
    if not FLOOR.exists():
        print("--emit-legacy-configs: trigger-floor.json absent — INERT until P1-T3 "
              "lands the floor (self-activates).", file=sys.stderr)
        return 3
    floor = _load(FLOOR)
    idx = _load(INDEX).get("skills", {}) or {}
    # Build candidate path/keyword rules from front-matter triggers.
    candidate_rules = []
    for name, e in idx.items():
        trig = e.get("triggers", {}) or {}
        paths = trig.get("paths", []) or []
        if paths:
            candidate_rules.append({"id": f"gen_{name}", "paths": paths, "skills": [name]})
    # Union the floor's own path_route skill sets so generation is a provable superset.
    for ent in floor.get("entries", []) or []:
        val = ent.get("value") if isinstance(ent, dict) else None
        if isinstance(val, dict) and val.get("skills"):
            candidate_rules.append({"id": ent.get("source_key", "floor"),
                                    "skills": val["skills"],
                                    "match": val.get("match", {})})
    dropped = superset_check(candidate_rules, floor)
    generated = {
        "_generated_from": "skills-index",
        "_meta": {"superset_of": "trigger-floor.json", "dropped": sorted(dropped)},
        "rules": candidate_rules,
    }
    if dropped:
        print(f"--emit-legacy-configs: ABORT — {len(dropped)} floor rules would drop: "
              f"{sorted(dropped)[:8]}", file=sys.stderr)
        return 1
    preview_dir = sl.CLAUDE_DIR / "vendor" / "generated-configs"
    preview_dir.mkdir(parents=True, exist_ok=True)
    (preview_dir / "skill_router.config.generated.json").write_text(
        json.dumps(generated, indent=2) + "\n", encoding="utf-8")
    print(f"--emit-legacy-configs: superset OK ({len(candidate_rules)} rules, 0 dropped); "
          f"preview -> vendor/generated-configs/skill_router.config.generated.json")
    if apply:
        print("--apply: live hooks/ config swap is OWNED by P4/P7 (hooks/** outside P5 "
              "write scope) — see HANDOFF. Preview written; not swapping.", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-legacy-configs", action="store_true")
    ap.add_argument("--apply", action="store_true", help="(P4/P7 only) swap live configs")
    ap.add_argument("--check", action="store_true", help="assert index count == 218")
    args = ap.parse_args()
    if args.emit_legacy_configs:
        return emit_legacy_configs(apply=args.apply)
    payload = build()
    INDEX.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    n = payload["_meta"]["count"]
    print(f"wrote {INDEX.name}: {n} skills "
          f"({payload['_meta']['bodyBearing']} bodies + {payload['_meta']['aliases']} aliases, "
          f"{payload['_meta']['locked']} locked)")
    if args.check and n != 218:
        print(f"CHECK FAIL: expected 218, got {n}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

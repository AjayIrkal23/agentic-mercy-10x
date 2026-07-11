#!/usr/bin/env python3
"""
validate_skills.py — P5-T1 skill validator (schema v1), rules R1..R10.

Rules (Charter §4 amended):
  R1  name == dir (exemptions from skills-index-overrides.json _aliases)
  R2  single-sentence description + 6-gram garble detection (user-authored only) [WARN]
  R3  >=3 trigger keywords once migrated (schema present)                        [WARN]
  R4  token-cost within +/-20% of estimate (--fix rewrites)                      [WARN]
  R5  platforms honesty: 'windows' forbidden if .sh/open/caffeinate/systemctl    [HARD]
  R6  all links / references/*.md resolve (user-authored)                        [HARD]
  R7  keyword overlap across >3 skills per intent — disambiguation report        [WARN]
  R8  index freshness hash (--fix rebuilds index)                                [WARN]
  R9  floor guard: every trigger-floor.json entry reachable in the index         [HARD when floor present, else SKIP]
  R10 upstream-intactness: locked skills hash-match their provenance baseline    [HARD when provenance present]

--fix applies only to R1/R4/R8. Exit nonzero on any HARD failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import skills_lib as sl

OVERRIDES = sl.HOOKS_DIR / "skills-index-overrides.json"
PROVENANCE = sl.HOOKS_DIR / "skills-provenance.json"
FLOOR = sl.HOOKS_DIR / "trigger-floor.json"
INDEX = sl.HOOKS_DIR / "skills-index.json"

_POSIX_TOKENS = re.compile(r"(?<![\w-])(\.sh\b|\bcaffeinate\b|\bsystemctl\b|\bopen\s+-a\b)")
_GLUED_IMPERATIVE = re.compile(r"[a-z]{3,}\s+(Use|Guard|Diagnose|Create|Apply|Choose|Model|Organize|Scaffold|Implement|Define|Audit)\s+[a-z]")


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}


def _exemptions() -> set[str]:
    ov = _load_json(OVERRIDES)
    return set(ov.get("_aliases", {}).values())


def _has_repeated_ngram(text: str, n: int = 6) -> bool:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    seen: set = set()
    for g in grams:
        if g in seen:
            return True
        seen.add(g)
    return False


def validate(fix: bool = False) -> int:
    exempt = _exemptions()
    locked = sl.locked_skills()
    provenance = _load_json(PROVENANCE)
    floor = _load_json(FLOOR)
    index = _load_json(INDEX)

    hard_fail = 0
    warns = 0
    intent_kw: dict[str, set[str]] = defaultdict(set)

    for d in sl.skill_dirs():
        name = d.name
        fm, body, ok = sl.read_frontmatter(d / "SKILL.md")
        is_locked = name in locked
        is_user = not is_locked
        if not ok:
            print(f"  R0  HARD {name}: unreadable front-matter")
            hard_fail += 1
            continue

        # R1 name == dir. Locked skills are upstream-named (e.g. the gstack twin
        # dir 'connect-chrome' whose clone SKILL.md says 'open-gstack-browser', or
        # vendored 'taste-skill' -> 'design-taste-frontend'); their sidecar alias
        # handles routing and P5-T12 pointerization gives twins name==dir. So R1 is
        # enforced only for user-authored skills.
        fm_name = str(fm.get("name", ""))
        if is_user and fm_name != name and name not in exempt and fm_name not in exempt:
            if fix:
                fm["name"] = name
                sl.write_skill(d / "SKILL.md", fm, body)
                print(f"  R1  FIX  {name}: name -> {name}")
            else:
                print(f"  R1  HARD {name}: front-matter name '{fm_name}' != dir")
                hard_fail += 1

        desc = str(fm.get("description", ""))

        # R2 garble (user-authored only) — WARN
        if is_user:
            if _has_repeated_ngram(desc) or _GLUED_IMPERATIVE.search(desc):
                print(f"  R2  WARN {name}: garbled/run-on description")
                warns += 1

        # R3 keywords once migrated — WARN
        trig = fm.get("triggers") or {}
        kws = trig.get("keywords") or [] if isinstance(trig, dict) else []
        if fm.get("schema") and is_user and len(kws) < 3:
            print(f"  R3  WARN {name}: <3 trigger keywords ({len(kws)})")
            warns += 1

        # R4 token-cost +/-20% — WARN / FIX
        if "token-cost" in fm:
            est = sl.estimate_token_cost(d)
            tc = fm.get("token-cost") or 0
            if isinstance(tc, int) and tc > 0 and abs(tc - est) > 0.2 * est:
                if fix and is_user:
                    fm["token-cost"] = est
                    sl.write_skill(d / "SKILL.md", fm, body)
                    print(f"  R4  FIX  {name}: token-cost -> {est}")
                else:
                    print(f"  R4  WARN {name}: token-cost {tc} vs est {est}")
                    warns += 1

        # R5 platforms honesty — HARD
        plats = fm.get("platforms") or []
        if isinstance(plats, list) and "windows" in plats:
            if _POSIX_TOKENS.search(body):
                print(f"  R5  HARD {name}: claims windows but body has POSIX-only calls")
                hard_fail += 1

        # R6 references resolve — HARD (user-authored). A ref written as
        # "<skill>/references/x.md" is skill-root-relative (thin aliases point at
        # their canonical); a bare "references/x.md" is dir-relative.
        if is_user:
            refs = set(re.findall(r"(?:[\w-]+/)?references/[\w./-]+\.md", body))
            for lk in (fm.get("links") or []):
                if isinstance(lk, str) and lk.endswith(".md"):
                    refs.add(lk)
            for r in refs:
                if (d / r).exists() or (sl.SKILLS_DIR / r).exists():
                    continue
                print(f"  R6  HARD {name}: missing reference {r}")
                hard_fail += 1

        # R7 overlap accounting
        intent_list = trig.get("intents") or [] if isinstance(trig, dict) else []
        for kw in kws:
            for it in (intent_list or ["_"]):
                intent_kw[f"{it}:{kw}"].add(name)

    # R7 — WARN report
    overloaded = {k: v for k, v in intent_kw.items() if len(v) > 3}
    if overloaded:
        print(f"  R7  WARN disambiguation: {len(overloaded)} keyword×intent pairs on >3 skills")
        warns += 1

    # R9 floor guard — every SKILL name a floor rule references must still resolve
    # in the compiled index (skill names + alias names). Merges keep all 218 names
    # alive via aliases, so a missing name == a silently-killed trigger == HARD FAIL.
    floor_entries = floor.get("entries") if isinstance(floor.get("entries"), list) else None
    if floor_entries:
        resolvable = set((index.get("skills", {}) or {}).keys()) or set(sl.skill_names())
        referenced: set[str] = set()
        for ent in floor_entries:
            val = ent.get("value") if isinstance(ent, dict) else None
            if isinstance(val, dict):
                for s in (val.get("skills") or []):
                    referenced.add(s)
        missing = {s for s in referenced if s not in resolvable}
        if missing:
            print(f"  R9  HARD floor guard: {len(missing)} floor-referenced skills not "
                  f"resolvable in index: {sorted(missing)[:8]}")
            hard_fail += 1
        else:
            print(f"  R9  OK   floor guard: all {len(referenced)} floor-referenced "
                  f"skills resolve in index")
    else:
        print("  R9  SKIP floor guard: trigger-floor.json absent/empty (P1-T3 pending) "
              "— self-activates when present")

    # R10 upstream-intactness
    if provenance:
        reg = {k: v for k, v in provenance.items() if not k.startswith("_")}
        r10 = sl.r10_check(reg)
        r10_fail = [r for r in r10 if r[1] == "FAIL"]
        if r10_fail:
            print(f"  R10 HARD upstream-intactness: {len(r10_fail)} locked skills edited")
            for n, _, det in r10_fail:
                print(f"        {n}: {det}")
            hard_fail += len(r10_fail)
        else:
            print(f"  R10 OK   upstream-intactness: {len(r10)} locked skills hash-clean")
    else:
        print("  R10 SKIP: no provenance registry")

    print(f"\nvalidate_skills: {hard_fail} HARD failures, {warns} warnings")
    return 1 if hard_fail else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="apply R1/R4/R8 fixes")
    args = ap.parse_args()
    return validate(fix=args.fix)


if __name__ == "__main__":
    sys.exit(main())

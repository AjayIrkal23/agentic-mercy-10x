#!/usr/bin/env python3
"""
validate_skills.py — skill validator, rules R1..R12.

  R1  name == dir (user-authored; vendored skills may keep upstream names)     [HARD]
  R2  single-sentence description + 6-gram garble detection (user-authored)   [WARN]
  R3  >=3 trigger keywords once metadata present (user-authored)              [WARN]
  R4  token-cost within +/-20% of estimate (--fix rewrites)                   [WARN]
  R5  platforms honesty: 'windows' forbidden if .sh/open/caffeinate/systemctl [HARD]
  R6  all links / references/*.{md,mdc} resolve (user-authored)               [HARD]
  R7  keyword overlap across >3 skills per intent — disambiguation report     [WARN]
  R9  floor guard: every trigger-floor.json skill resolves (index ∪ aliases)  [HARD when floor present]
  R10 upstream-intactness: locked skills hash-match their provenance baseline [HARD when provenance present]
  R11 custom keys live under ``metadata:`` (HARD user-authored, WARN locked)
  R12 ``paths:`` entries are plain glob strings without ``~``                 [HARD]

Routing metadata is read through build_skills_index.skill_meta (metadata: first,
legacy top-level keys as fallback). --fix applies only to R1/R4. Exit nonzero on
any HARD failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import skills_lib as sl
from build_skills_index import LEGACY_META_KEYS, skill_meta

PROVENANCE = sl.HOOKS_DIR / "skills-provenance.json"
SOURCES = sl.HOOKS_DIR / "skills-sources.json"
FLOOR = sl.HOOKS_DIR / "trigger-floor.json"
INDEX = sl.HOOKS_DIR / "skills-index.json"
ALIASES = sl.HOOKS_DIR / "skill-aliases.json"

# Claude Code skill frontmatter keys (skills.md "Frontmatter reference", v2.1.283).
NATIVE_KEYS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
}

_POSIX_TOKENS = re.compile(r"(?<![\w-])(\.sh\b|\bcaffeinate\b|\bsystemctl\b|\bopen\s+-a\b)")
_GLUED_IMPERATIVE = re.compile(r"[a-z]{3,}\s+(Use|Guard|Diagnose|Create|Apply|Choose|Model|Organize|Scaffold|Implement|Define|Audit)\s+[a-z]")


def _load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _has_repeated_ngram(text: str, n: int = 6) -> bool:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    grams = [tuple(toks[i:i + n]) for i in range(len(toks) - n + 1)]
    seen: set = set()
    for g in grams:
        if g in seen:
            return True
        seen.add(g)
    return False


def _locked_names() -> set[str]:
    """Locked = declared in hooks/skills-sources.json when present, else provenance families."""
    src = _load_json(SOURCES)
    if src:
        return {k for k in src if not k.startswith("_")}
    return sl.locked_skills()


def validate(fix: bool = False) -> int:
    locked = _locked_names()
    provenance = _load_json(PROVENANCE)
    floor = _load_json(FLOOR)
    index = _load_json(INDEX)
    aliases = {k for k in _load_json(ALIASES) if not k.startswith("_")}

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

        # R1 name == dir (user-authored only; vendored skills keep upstream names).
        fm_name = str(fm.get("name", ""))
        if is_user and fm_name != name:
            if fix:
                fm["name"] = name
                sl.write_skill(d / "SKILL.md", fm, body)
                print(f"  R1  FIX  {name}: name -> {name}")
            else:
                print(f"  R1  HARD {name}: front-matter name '{fm_name}' != dir")
                hard_fail += 1

        desc = str(fm.get("description", ""))
        meta = skill_meta(fm)
        trig = meta.get("triggers") if isinstance(meta.get("triggers"), dict) else {}
        kws = list(trig.get("keywords") or meta.get("keywords") or [])

        # R2 garble (user-authored only) — WARN
        if is_user and (_has_repeated_ngram(desc) or _GLUED_IMPERATIVE.search(desc)):
            print(f"  R2  WARN {name}: garbled/run-on description")
            warns += 1

        # R3 keywords once metadata is present — WARN
        if is_user and (meta.get("schema") or fm.get("metadata")) and len(kws) < 3:
            print(f"  R3  WARN {name}: <3 trigger keywords ({len(kws)})")
            warns += 1

        # R4 token-cost +/-20% — WARN / FIX
        if "token-cost" in meta:
            est = sl.estimate_token_cost(d)
            tc = meta.get("token-cost") or 0
            if isinstance(tc, int) and tc > 0 and abs(tc - est) > 0.2 * est:
                if fix and is_user and isinstance(fm.get("metadata"), dict):
                    fm["metadata"]["token-cost"] = est
                    sl.write_skill(d / "SKILL.md", fm, body)
                    print(f"  R4  FIX  {name}: token-cost -> {est}")
                else:
                    print(f"  R4  WARN {name}: token-cost {tc} vs est {est}")
                    warns += 1

        # R5 platforms honesty — HARD
        plats = meta.get("platforms") or []
        if isinstance(plats, list) and "windows" in plats and _POSIX_TOKENS.search(body):
            print(f"  R5  HARD {name}: claims windows but body has POSIX-only calls")
            hard_fail += 1

        # R6 references resolve — HARD (user-authored). "<skill>/references/x.md" is
        # skills-root-relative; a bare "references/x.md" is dir-relative.
        if is_user:
            refs = set(re.findall(
                r"(?<![\w./-])(?:~/\.claude/)?(?:[\w-]+/)?references/"
                r"[\w./-]+\.(?:mdc|md)(?![\w.-])",
                body,
            ))
            for lk in (meta.get("links") or []):
                if isinstance(lk, str) and lk.endswith((".md", ".mdc")):
                    refs.add(lk)
            for r in refs:
                if r.startswith("~/.claude/"):
                    if (sl.CLAUDE_DIR / r.removeprefix("~/.claude/")).exists():
                        continue
                if (d / r).exists() or (sl.SKILLS_DIR / r).exists():
                    continue
                print(f"  R6  HARD {name}: missing reference {r}")
                hard_fail += 1

        # R7 overlap accounting
        intent_list = list(trig.get("intents") or meta.get("intents") or [])
        for kw in kws:
            for it in (intent_list or ["_"]):
                intent_kw[f"{it}:{kw}"].add(name)

        # R11 custom keys under metadata: — HARD for user-authored, WARN for locked
        stray = sorted(k for k in fm if k not in NATIVE_KEYS)
        if stray:
            hint = " (legacy routing keys)" if any(k in LEGACY_META_KEYS for k in stray) else ""
            if is_user:
                print(f"  R11 HARD {name}: custom keys outside metadata:{hint} {stray} "
                      f"— run scripts/migrate_frontmatter.py --only {name}")
                hard_fail += 1
            else:
                print(f"  R11 WARN {name}: custom keys outside metadata: {stray}")
                warns += 1

        # R12 paths: plain glob strings, no ~ — HARD
        if "paths" in fm:
            paths = fm["paths"] if isinstance(fm["paths"], list) else [fm["paths"]]
            bad = [p for p in paths if not isinstance(p, str) or not p.strip() or "~" in p]
            if bad:
                print(f"  R12 HARD {name}: paths entries must be non-empty strings without '~': {bad}")
                hard_fail += 1

    # R7 — WARN report
    overloaded = {k: v for k, v in intent_kw.items() if len(v) > 3}
    if overloaded:
        print(f"  R7  WARN disambiguation: {len(overloaded)} keyword×intent pairs on >3 skills")
        warns += 1

    # R9 floor guard — every skill the floor references must resolve: index entry,
    # alias (resolved at runtime by lib/skill_aliases), or on-disk dir.
    floor_entries = floor.get("entries") if isinstance(floor.get("entries"), list) else None
    if floor_entries:
        resolvable = set((index.get("skills", {}) or {}).keys()) | aliases | set(sl.skill_names())
        referenced: set[str] = set()
        for ent in floor_entries:
            val = ent.get("value") if isinstance(ent, dict) else None
            if isinstance(val, dict):
                referenced.update(val.get("skills") or [])
        missing = {s for s in referenced if s not in resolvable}
        if missing:
            print(f"  R9  HARD floor guard: {len(missing)} floor-referenced skills not "
                  f"resolvable (index ∪ aliases): {sorted(missing)[:8]}")
            hard_fail += 1
        else:
            print(f"  R9  OK   floor guard: all {len(referenced)} floor-referenced skills resolve")
    else:
        print("  R9  SKIP floor guard: trigger-floor.json absent/empty")

    # R10 upstream-intactness
    if provenance:
        reg = {k: v for k, v in provenance.items() if not k.startswith("_") and (sl.SKILLS_DIR / k).exists()}
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
    ap.add_argument("--fix", action="store_true", help="apply R1/R4 fixes")
    args = ap.parse_args()
    return validate(fix=args.fix)


if __name__ == "__main__":
    sys.exit(main())

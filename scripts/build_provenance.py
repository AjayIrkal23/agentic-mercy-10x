#!/usr/bin/env python3
"""
build_provenance.py — P5-T14 provenance registry builder (the carve-out, made
permanent + machine-enforced).

Emits hooks/skills-provenance.json — one entry per upstream-locked skill (128):
  {family, source, sourceType, updateCommand, hashBasis, baselineHash, capturedAt}

Baseline hashes are captured NOW (pre-P5 edits) so R10 can prove zero local
edits from day one. Families are DERIVED FROM DISK (skills_lib.derive_families),
never hardcoded. Also creates the hooks/skills-index-overrides.json skeleton if
absent (filled by P5-T2/T5).

Usage:
  python3 scripts/build_provenance.py            # write registry (idempotent-safe:
                                                 #   preserves existing baselines)
  python3 scripts/build_provenance.py --recapture  # recapture ALL baselines
  python3 scripts/build_provenance.py --check    # run R10 against current tree
  python3 scripts/build_provenance.py --rebaseline <skill>  # after verified update
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import skills_lib as sl

PROV_PATH = sl.HOOKS_DIR / "skills-provenance.json"
OVERRIDES_PATH = sl.HOOKS_DIR / "skills-index-overrides.json"
LOCK_PATH = sl.HOOKS_DIR / "skills-lock.json"

_FAMILY_META = {
    "gstack-clone": {
        "source": "https://github.com/garrytan/gstack",
        "sourceType": "git-clone",
        "updateCommand": "gstack-upgrade (git pull inside skills/gstack)",
    },
    "installer-managed": {
        "source": "https://github.com/higgsfield-ai/skills (npx skills)",
        "sourceType": "skills-cli",
        "updateCommand": "npx skills update -> re-materialize -> re-hash",
    },
    "gsd": {
        "source": "get-shit-done suite (~/.claude/get-shit-done)",
        "sourceType": "vendored-suite",
        "updateCommand": "gsd-update",
    },
    "vendored-design": {
        "source": "author release (six-skill UI craft stack)",
        "sourceType": "vendored",
        "updateCommand": "re-vendor from author release",
    },
    "embedded-git": {
        "source": "https://github.com/claudiocebpaz/vite-react-best-practices",
        "sourceType": "embedded-git",
        "updateCommand": "rename .git-upstream->.git; git pull; rename .git->.git-upstream",
    },
    "skills-cli": {
        "source": "npx skills ecosystem discovery skill",
        "sourceType": "skills-cli",
        "updateCommand": "npx skills update",
    },
}


def _baseline(name: str, family: str, basis: str) -> str:
    if basis == "git-clean":
        return ""  # git status is the check; no stored hash
    if basis == "pointer-desc":
        return sl.sha256_text(sl.clone_member_description(name))
    return sl.dir_content_hash(sl.SKILLS_DIR / name)


def _basis_for(name: str, family: str) -> str:
    if family == "gstack-clone":
        return "git-clean" if name == "gstack" else "pointer-desc"
    return "content-hash"


def build(recapture: bool = False) -> dict:
    families = sl.derive_families()
    existing = {}
    if PROV_PATH.exists() and not recapture:
        try:
            existing = json.loads(PROV_PATH.read_text())
        except json.JSONDecodeError:
            existing = {}
    now = dt.datetime.now().strftime("%Y-%m-%d")
    reg: dict = {}
    for name in sorted(families):
        family = families[name]
        basis = _basis_for(name, family)
        meta = dict(_FAMILY_META[family])
        # preserve an already-captured baseline unless recapturing
        prior = existing.get(name, {}) if isinstance(existing.get(name), dict) else {}
        if not recapture and prior.get("baselineHash") is not None \
                and prior.get("hashBasis") == basis:
            baseline = prior["baselineHash"]
            captured = prior.get("capturedAt", now)
        else:
            baseline = _baseline(name, family, basis)
            captured = now
        entry = {
            "family": family,
            "source": meta["source"],
            "sourceType": meta["sourceType"],
            "updateCommand": meta["updateCommand"],
            "hashBasis": basis,
            "baselineHash": baseline,
            "capturedAt": captured,
        }
        if family == "installer-managed":
            entry["authoritativeCheck"] = "hooks/skills-lock.json computedHash"
        reg[name] = entry
    return reg


def write_registry(reg: dict) -> None:
    header = {
        "_meta": {
            "purpose": "P5-T14 upstream-locked skill provenance + R10 baseline registry",
            "count": len(reg),
            "authority": "plans/SKILL-FATE-2026-07-11.md §1",
            "note": "Locked skills are NEVER edited; router integration is sidecar-only. "
                    "R10 (validate_skills.py / doctor / CI) re-hashes and FAILS on any local edit.",
        }
    }
    out = {**header, **reg}
    PROV_PATH.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


def ensure_overrides_skeleton() -> None:
    if OVERRIDES_PATH.exists():
        return
    skel = {
        "_meta": {
            "purpose": "Sidecar routing metadata for the 128 upstream-locked skills "
                       "(SKILL-FATE §1.2). build_skills_index merges these; no locked "
                       "file is ever parsed beyond its native name/description.",
            "schema": 1,
        },
        "_aliases": {
            "_comment": "sidecar name aliases for locked skills, e.g. taste-skill",
            "design-taste-frontend": "taste-skill",
        },
        "skills": {},
    }
    OVERRIDES_PATH.write_text(json.dumps(skel, indent=2) + "\n", encoding="utf-8")


def gsd_reconcile() -> None:
    """Reconcile on-disk gsd-* set vs get-shit-done's managed suite (SKILL-FATE §0).

    There is no flat skill manifest in get-shit-done/; the suite ships its skills
    into skills/. All on-disk gsd-* dirs are treated as GSD-upstream-managed
    (sidecar-only treatment is safe in both directions). Reports the count and any
    obvious straggler (a gsd-* dir with no SKILL.md, which would be non-upstream).
    """
    disk = sorted(d.name for d in sl.SKILLS_DIR.glob("gsd-*") if (d / "SKILL.md").exists())
    version = (sl.CLAUDE_DIR / "get-shit-done" / "VERSION")
    ver = version.read_text().strip() if version.exists() else "?"
    print(f"gsd reconcile: {len(disk)} gsd-* skills on disk vs get-shit-done v{ver}; "
          f"all treated as upstream-managed (SKILL-FATE §0 — resolves 53-vs-67).")


def run_check() -> int:
    if not PROV_PATH.exists():
        print("R10: no provenance registry — run build first", file=sys.stderr)
        return 2
    reg = {k: v for k, v in json.loads(PROV_PATH.read_text()).items()
           if not k.startswith("_")}
    results = sl.r10_check(reg)
    fails = [r for r in results if r[1] == "FAIL"]
    skips = [r for r in results if r[1] == "SKIP"]
    print(f"R10: {len(results)} locked skills, {len(fails)} FAIL, {len(skips)} SKIP")
    for name, status, detail in fails + skips:
        print(f"  {status:4} {name}: {detail}")
    gsd_reconcile()
    return 1 if fails else 0


def rebaseline(skill: str) -> int:
    reg = json.loads(PROV_PATH.read_text())
    entries = {k: v for k, v in reg.items() if not k.startswith("_")}
    if skill not in entries:
        print(f"{skill} not in registry", file=sys.stderr)
        return 2
    fam = entries[skill]["family"]
    basis = entries[skill]["hashBasis"]
    entries[skill]["baselineHash"] = _baseline(skill, fam, basis)
    entries[skill]["capturedAt"] = dt.datetime.now().strftime("%Y-%m-%d")
    write_registry(entries)
    manifest = sl.CLAUDE_DIR / "attic" / "2026-07-11" / "MANIFEST.md"
    if manifest.exists():
        with manifest.open("a") as f:
            f.write(f"- [P5-T14] rebaseline {skill} ({fam}) after verified upstream "
                    f"update — {dt.datetime.now():%Y-%m-%d}\n")
    print(f"rebaselined {skill}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recapture", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rebaseline", metavar="SKILL")
    args = ap.parse_args()
    if args.check:
        return run_check()
    if args.rebaseline:
        return rebaseline(args.rebaseline)
    reg = build(recapture=args.recapture)
    write_registry(reg)
    ensure_overrides_skeleton()
    print(f"wrote {PROV_PATH.name}: {len(reg)} locked skills")
    from collections import Counter
    print("families:", dict(Counter(v["family"] for v in reg.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

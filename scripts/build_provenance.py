#!/usr/bin/env python3
"""
build_provenance.py — R10 provenance registry for vendored third-party skills.

Emits hooks/skills-provenance.json — one entry per skill declared in
hooks/skills-sources.json (family "vendored-git"):
  {family, source, sourceType, pinnedRef, ref, sha, updateCommand,
   hashBasis, baselineHash, capturedAt}

source/ref come from skills-sources.json; sha from skills/<name>/.vendored.json
(written by scripts/vendor_skill.py). The baseline hash is of the PATCHED result,
so R10 fails on any local edit made after vendoring.

Usage:
  python3 scripts/build_provenance.py              # write registry (keeps existing baselines)
  python3 scripts/build_provenance.py --recapture  # recapture ALL baselines
  python3 scripts/build_provenance.py --check      # run R10 against the current tree
  python3 scripts/build_provenance.py --rebaseline <skill>  # after a verified re-vendor
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import skills_lib as sl

PROV_PATH = sl.HOOKS_DIR / "skills-provenance.json"


def _marker(name: str) -> dict:
    try:
        return json.loads((sl.SKILLS_DIR / name / ".vendored.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build(recapture: bool | set = False) -> dict:
    """recapture=True -> every baseline; a set -> only those names."""
    sources = sl.vendored_sources()
    existing = {}
    if PROV_PATH.exists():
        try:
            existing = json.loads(PROV_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    now = dt.date.today().isoformat()
    reg: dict = {}
    for name in sorted(sources):
        d = sl.SKILLS_DIR / name
        if not (d / "SKILL.md").exists():
            continue
        src, mk = sources[name], _marker(name)
        prior = existing.get(name) if isinstance(existing.get(name), dict) else {}
        again = recapture is True or (isinstance(recapture, set) and name in recapture)
        if not again and prior.get("baselineHash") and prior.get("family") == "vendored-git":
            baseline, captured = prior["baselineHash"], prior.get("capturedAt", now)
        else:
            baseline, captured = sl.dir_content_hash(d), now
        reg[name] = {
            "family": "vendored-git",
            "source": src["repo"],
            "sourceType": "vendored-git",
            "subpath": src.get("subpath", "."),
            "pinnedRef": src["ref"],
            "ref": mk.get("ref"),
            "sha": mk.get("sha"),
            "updateCommand": f"python3 ~/.claude/scripts/vendor_skill.py {name}",
            "hashBasis": "content-hash",
            "baselineHash": baseline,
            "capturedAt": captured,
        }
    return reg


def write_registry(reg: dict) -> None:
    header = {
        "_meta": {
            "purpose": "R10 provenance + baseline registry for vendored-git skills",
            "count": len(reg),
            "source_of_truth": "hooks/skills-sources.json (+ skills/<name>/.vendored.json)",
            "note": "Vendored skills are never hand-edited: change skills-sources.json "
                    "(frontmatter_overrides/patches) and re-run vendor_skill.py. R10 "
                    "(validate_skills.py / doctor / CI) re-hashes and FAILS on any local edit.",
        }
    }
    PROV_PATH.write_text(json.dumps({**header, **reg}, indent=2) + "\n", encoding="utf-8", newline="\n")


def run_check() -> int:
    if not PROV_PATH.exists():
        print("R10: no provenance registry — run build first", file=sys.stderr)
        return 2
    reg = {k: v for k, v in json.loads(PROV_PATH.read_text(encoding="utf-8")).items()
           if not k.startswith("_")}
    results = sl.r10_check(reg)
    missing = [n for n in sl.vendored_sources() if n not in reg]
    results += [(n, "FAIL", "declared in skills-sources.json but not vendored/registered")
                for n in missing]
    for n, meta in reg.items():
        pin, ref = meta.get("pinnedRef"), _marker(n).get("ref")
        if pin and ref != pin:
            results.append((n, "FAIL", f"on-disk ref {ref} != pinned {pin}"))
    fails = [r for r in results if r[1] == "FAIL"]
    skips = [r for r in results if r[1] == "SKIP"]
    print(f"R10: {len(reg)} locked skills, {len(fails)} FAIL, {len(skips)} SKIP")
    for name, status, detail in fails + skips:
        print(f"  {status:4} {name}: {detail}")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recapture", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--rebaseline", metavar="SKILL")
    args = ap.parse_args()
    if args.check:
        return run_check()
    if args.rebaseline and args.rebaseline not in sl.vendored_sources():
        print(f"{args.rebaseline} not in skills-sources.json", file=sys.stderr)
        return 2
    reg = build(recapture={args.rebaseline} if args.rebaseline else args.recapture)
    write_registry(reg)
    print(f"wrote {PROV_PATH.name}: {len(reg)} vendored-git skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())

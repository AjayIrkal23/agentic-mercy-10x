#!/usr/bin/env python3
"""
sync-gstack-pointers.py — P5-T12 gstack de-symlink via GENERATED POINTER SKILLS.

Each of the 47 top-level `skills/<name>/SKILL.md` symlinks into the gstack clone
is replaced by a small GENERATED real file whose description is copied VERBATIM
from the clone member (trigger parity by construction) and whose body is a two-line
pointer. The CLONE at `skills/gstack/` is NEVER edited — `git pull` via
`gstack-upgrade` stays pristine. Re-run this after gstack-upgrade, at SessionStart
(cheap), and from the installer so upstream description changes propagate.

  python3 scripts/sync-gstack-pointers.py            # (re)generate pointers
  python3 scripts/sync-gstack-pointers.py --check    # doctor: pointer desc == clone desc

Rationale (SKILL-FATE §1.1): pointers live OUTSIDE the clone (pull stays clean),
have no body to drift, are Windows-safe (real files, no symlink), and propagate
upstream description changes automatically. Copies were REJECTED (duplicate
800-1600 line bodies ×47 that drift silently between pull and next sync).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import skills_lib as sl

CLONE = sl.SKILLS_DIR / "gstack"


def gstack_twins() -> list[str]:
    """Top-level twin dirs whose SKILL.md points into the clone, OR already-generated
    pointers (provenance gstack-clone) — i.e. every gstack twin, symlink or pointer."""
    out = []
    for d in sorted(sl.SKILLS_DIR.iterdir()):
        if not d.is_dir() or d.name == "gstack":
            continue
        sk = d / "SKILL.md"
        if sk.is_symlink() and "/skills/gstack/" in os.readlink(sk):
            out.append(d.name)
        elif sk.is_file():
            fm, _, ok = sl.read_frontmatter(sk)
            if ok and fm.get("provenance") == "gstack-clone":
                out.append(d.name)
    return out


def clone_desc(name: str) -> str:
    fm, _, ok = sl.read_frontmatter(CLONE / name / "SKILL.md")
    return str(fm.get("description", "")) if ok else ""


def make_pointer(name: str) -> str:
    desc = clone_desc(name)
    fm = {
        "name": name,
        "description": desc,
        "platforms": ["linux", "darwin"],
        "schema": 1,
        "provenance": "gstack-clone",
    }
    body = (f"\nGenerated pointer to the upstream gstack clone. Read and follow "
            f"`~/.claude/skills/gstack/{name}/SKILL.md`.\n")
    return sl.dump_frontmatter(fm, body)


def sync() -> int:
    twins = gstack_twins()
    converted = 0
    for name in twins:
        sk = sl.SKILLS_DIR / name / "SKILL.md"
        new = make_pointer(name)
        if sk.is_symlink():
            sk.unlink()
            sk.write_text(new, encoding="utf-8")
            converted += 1
        else:
            cur = sk.read_text(encoding="utf-8")
            if cur != new:
                sk.write_text(new, encoding="utf-8")
                converted += 1
    # materialize sections/ dir symlinks into the clone as real copies (zero-symlinks
    # probe; Windows-safe). Regenerated on every sync so upstream updates propagate.
    import shutil
    for n in twins:
        sec = sl.SKILLS_DIR / n / "sections"
        if sec.is_symlink():
            target = Path(os.readlink(sec))
            sec.unlink()
            if target.is_dir():
                shutil.copytree(target, sec)
                print(f"  materialized sections/: {n}")

    remaining = sum(1 for n in twins if (sl.SKILLS_DIR / n / "SKILL.md").is_symlink())
    print(f"gstack pointers: {len(twins)} twins, {converted} (re)generated, "
          f"{remaining} symlinks remaining")
    return 1 if remaining else 0


def check() -> int:
    twins = gstack_twins()
    bad = []
    for name in twins:
        sk = sl.SKILLS_DIR / name / "SKILL.md"
        if sk.is_symlink():
            bad.append((name, "still a symlink"))
            continue
        fm, _, ok = sl.read_frontmatter(sk)
        if not ok:
            bad.append((name, "unreadable pointer"))
        elif sl.sha256_text(str(fm.get("description", ""))) != sl.sha256_text(clone_desc(name)):
            bad.append((name, "description drifted from clone"))
    print(f"gstack pointer doctor: {len(twins)} twins, {len(bad)} problems")
    for n, why in bad:
        print(f"  {n}: {why}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    sys.exit(main())

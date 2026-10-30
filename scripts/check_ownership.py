#!/usr/bin/env python3
"""check_ownership.py — every changed path in the worktree belongs to exactly one package.

Reads PACKAGES.json (``--packages``, else env CLAUDE_ECC_PACKAGES), lists the worktree's
changes with ``git status --porcelain -z --untracked-files=all`` (renames: both names) and
maps each path to the packages whose ``owned_paths`` contain it (exact path, or a directory
prefix). Exit 0 = every path has exactly one owner; 1 = an unowned or multi-owned path
(plan 6.10.1: stop and report); 2 = no PACKAGES.json or git unavailable. ``--json`` prints
{"changed","unowned","multi","by_package"}; the text form prints ``OK <n> changed paths, all
owned`` or ``BREACH`` lines. golive.py step 01 calls it with no arguments (env + cwd).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def changed_paths(worktree: Path) -> list[str]:
    git = shutil.which("git")
    if not git:
        raise RuntimeError("git not on PATH")
    out = subprocess.run([git, "-C", str(worktree), "status", "--porcelain", "-z", "--untracked-files=all"],
                         capture_output=True, text=True, timeout=120, check=True).stdout
    items, paths, i = out.split("\0"), [], 0
    while i < len(items):
        it = items[i]
        if it:
            st, path = it[:2], it[3:]
            paths.append(path.replace("\\", "/"))
            if "R" in st or "C" in st:  # the next NUL field is the source name
                i += 1
                paths.append(items[i].replace("\\", "/"))
        i += 1
    return paths


def owners(path: str, table: list[tuple[str, str]]) -> list[str]:
    return sorted({pid for owned, pid in table if path == owned or path.startswith(owned.rstrip("/") + "/")})


def check(packages: dict, worktree: Path) -> dict:
    table = [(o.strip("/").replace("\\", "/"), p["id"]) for p in packages["packages"] for o in p["owned_paths"]]
    paths = changed_paths(worktree)
    unowned, multi, by = [], [], Counter()
    for p in paths:
        who = owners(p, table)
        if not who:
            unowned.append(p)
        elif len(who) > 1:
            multi.append([p, who])
        else:
            by[who[0]] += 1
    return {"changed": len(paths), "unowned": unowned, "multi": multi, "by_package": dict(sorted(by.items()))}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--packages", default=os.environ.get("CLAUDE_ECC_PACKAGES"))
    ap.add_argument("--worktree", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.packages or not Path(a.packages).is_file():
        print("check_ownership: no PACKAGES.json (--packages or CLAUDE_ECC_PACKAGES)", file=sys.stderr)
        return 2
    try:
        res = check(json.loads(Path(a.packages).read_text(encoding="utf-8")), Path(a.worktree))
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        print(f"check_ownership: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    bad = bool(res["unowned"] or res["multi"])
    if a.json:
        print(json.dumps(res, indent=1))
    elif bad:
        for p in res["unowned"]:
            print(f"BREACH unowned  {p}")
        for p, who in res["multi"]:
            print(f"BREACH multi    {p} -> {', '.join(who)}")
    else:
        print(f"OK {res['changed']} changed paths, all owned; per package: {res['by_package']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

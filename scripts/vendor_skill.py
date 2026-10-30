#!/usr/bin/env python3
"""
vendor_skill.py — vendor third-party skills from hooks/skills-sources.json.

  vendor_skill.py <name> [--ref R]   clone the pinned ref, copy subpath -> skills/<name>/,
                                     prune, apply frontmatter_overrides / prepend_body /
                                     patches, write .vendored.json, rebaseline R10
  vendor_skill.py --all              every entry at its pinned ref
  vendor_skill.py --all --check      table: pinned vs on-disk vs newest upstream tag.
                                     Exit 1 on local DRIFT (disk != pin); BEHIND is info.

Clones live in ~/.claude/.cache/vendor/ (gitignored), one per repo@ref. Stdlib + git
(+ PyYAML only when a skill has frontmatter overrides). Never touches ~/.agents, never
runs anything from the vendored tree.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import skills_lib as sl

SOURCES = sl.HOOKS_DIR / "skills-sources.json"
CACHE = sl.CLAUDE_DIR / ".cache" / "vendor"
MARKER = ".vendored.json"
_SHA = re.compile(r"^[0-9a-f]{40}$")


def load_sources() -> dict:
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=300).stdout.strip()


def _slug(repo: str, ref: str) -> str:
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", repo)
    base = f"{m.group(1)}__{m.group(2)}" if m else re.sub(r"\W+", "_", repo)
    return f"{base}@{ref[:12]}"


def fetch(repo: str, ref: str) -> tuple[Path, str]:
    """Shallow checkout of repo@ref in the cache; returns (dir, commit sha)."""
    dest = CACHE / _slug(repo, ref)
    if (dest / ".git").is_dir():
        return dest, _git("rev-parse", "HEAD", cwd=dest)
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    if _SHA.match(ref):
        tmp.mkdir(parents=True)
        _git("init", "-q", cwd=tmp)
        _git("fetch", "-q", "--depth", "1", repo, ref, cwd=tmp)
        _git("checkout", "-q", "FETCH_HEAD", cwd=tmp)
    else:
        _git("clone", "-q", "--depth", "1", "--branch", ref, repo, str(tmp))
    tmp.rename(dest)
    return dest, _git("rev-parse", "HEAD", cwd=dest)


# --------------------------------------------------------------------------- #
# patching
# --------------------------------------------------------------------------- #
def _deep_merge(base: dict, over: dict) -> dict:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        elif v is None:
            base.pop(k, None)
        else:
            base[k] = v
    return base


def _split_fm(text: str) -> tuple[str, str]:
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.DOTALL)
    if not m:
        raise ValueError("SKILL.md has no frontmatter")
    return m.group(1), text[m.end():]


def apply_overrides(skill_md: Path, overrides: dict, prepend: str) -> None:
    if not overrides and not prepend:
        return  # leave upstream bytes untouched
    text = skill_md.read_text(encoding="utf-8")
    fm_text, body = _split_fm(text)
    if overrides:
        import yaml  # required only on this write path
        fm = yaml.safe_load(fm_text) or {}
        _deep_merge(fm, json.loads(json.dumps(overrides)))
        fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=100).rstrip("\n")
    if prepend:
        body = prepend + body.lstrip("\n")
    skill_md.write_text(f"---\n{fm_text}\n---\n\n{body}" if prepend else f"---\n{fm_text}\n---\n{body}",
                        encoding="utf-8", newline="\n")


def apply_patches(root: Path, patches: list) -> None:
    for p in patches or []:
        f = root / p["file"]
        text = f.read_text(encoding="utf-8")
        if p["find"] not in text:
            raise ValueError(f"patch target not found in {f}: {p['find'][:60]!r}")
        f.write_text(text.replace(p["find"], p["replace"]), encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- #
# vendor
# --------------------------------------------------------------------------- #
def vendor(name: str, entry: dict, ref: str | None = None) -> str:
    ref = ref or entry["ref"]
    src_root, sha = fetch(entry["repo"], ref)
    src = (src_root / entry.get("subpath", ".")).resolve()
    if not (src / "SKILL.md").is_file():
        raise FileNotFoundError(f"{name}: no SKILL.md at {entry.get('subpath')} in {entry['repo']}@{ref}")
    dst = sl.SKILLS_DIR / name
    old = _marker(name)  # read before the tree is replaced: an unchanged sha keeps its vendored_at
    # FIX-r3 I12: build in a staging dir; swap only when the bytes differ, so an unchanged skill keeps
    # every mtime (and its marker) across installs. Staging sits in .cache/ (gitignored, same filesystem
    # for os.replace), so not even skills/ itself moves when nothing changed.
    stage_dir = sl.SKILLS_DIR.parent / ".cache" / "vendor-staging"
    stage_dir.mkdir(parents=True, exist_ok=True)
    staged, prev = stage_dir / name, stage_dir / f"{name}.old"
    _remove(staged)
    shutil.copytree(src, staged, symlinks=False,
                    ignore=shutil.ignore_patterns(".git", ".git-upstream", ".gitmodules"))
    for rel in entry.get("prune", []) or []:
        _remove(staged / rel)
    for gp in list(staged.rglob(".git*")):  # .gitignore/.gitattributes etc.
        _remove(gp)
    apply_patches(staged, entry.get("patches"))
    apply_overrides(staged / "SKILL.md", entry.get("frontmatter_overrides") or {},
                    entry.get("prepend_body") or "")
    stamp = old.get("vendored_at") if old.get("sha") == sha and old.get("vendored_at") else \
        dt.date.today().isoformat()
    (staged / MARKER).write_text(json.dumps({
        "repo": entry["repo"], "ref": ref, "sha": sha, "vendored_at": stamp,
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    if dst.is_dir() and not dst.is_symlink() and tree_digest(staged) == tree_digest(dst):
        _remove(staged)
        return sha
    _remove(prev)
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.exists():
        os.replace(dst, prev)
    os.replace(staged, dst)
    _remove(prev)
    return sha


def _remove(p: Path) -> None:
    if p.is_dir() and not p.is_symlink():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists() or p.is_symlink():
        p.unlink()


def tree_digest(root: Path) -> str:
    """sha256 over sorted (relpath, exec bit, sha256 of bytes) of every file and every dir name."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix().encode("utf-8")
        if p.is_file():
            h.update(b"F" + rel + b"\0" + bytes([bool(p.stat().st_mode & 0o111)]) +
                     hashlib.sha256(p.read_bytes()).digest())
        elif p.is_dir():
            h.update(b"D" + rel + b"\0")
    return h.hexdigest()


def _marker(name: str) -> dict:
    try:
        return json.loads((sl.SKILLS_DIR / name / MARKER).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _vkey(tag: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", tag)]


def _remote(repo: str, cache: dict) -> dict:
    if repo not in cache:
        try:
            out = _git("ls-remote", "--tags", "--heads", repo)
        except (subprocess.SubprocessError, OSError):
            cache[repo] = {}
            return cache[repo]
        tags, head = [], ""
        for line in out.splitlines():
            sha, ref = line.split("\t", 1)
            if ref.startswith("refs/tags/") and not ref.endswith("^{}"):
                tags.append(ref[len("refs/tags/"):])
            elif ref in ("refs/heads/main", "refs/heads/master"):
                head = sha
        cache[repo] = {"tag": max(tags, key=_vkey) if tags else "", "head": head}
    return cache[repo]


def check(sources: dict) -> int:
    prov = {}
    try:
        prov = json.loads((sl.HOOKS_DIR / "skills-provenance.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    cache: dict = {}
    drift = 0
    print(f"{'skill':32} {'pinned':14} {'on-disk':14} {'newest':14} status")
    for name, e in sorted(sources.items()):
        ref, mk, rem = e["ref"], _marker(name), _remote(e["repo"], cache)
        disk = mk.get("ref", "-")
        status = "OK"
        base = (prov.get(name) or {}).get("baselineHash")
        if disk != ref or (sl.SKILLS_DIR / name).is_symlink():
            status, drift = "DRIFT", drift + 1
        elif base and sl.dir_content_hash(sl.SKILLS_DIR / name) != base:
            status, drift = "DRIFT(edited)", drift + 1
        if not rem:
            newest = "?"
        elif _SHA.match(ref):
            newest = rem["head"][:12]
            if rem["head"] and rem["head"] != ref and status == "OK":
                status = "BEHIND(head)"
        else:
            newest = rem["tag"]
            if newest and newest != ref and status == "OK":
                status = "BEHIND"
        short = lambda r: r[:12] if _SHA.match(r) else r  # noqa: E731
        print(f"{name:32} {short(ref):14} {short(disk):14} {newest:14} {status}")
    print(f"\n{len(sources)} vendored skills, {drift} drift")
    return 1 if drift else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--ref")
    a = ap.parse_args()
    sources = load_sources()
    if a.check:
        return check(sources if a.all or not a.name else {a.name: sources[a.name]})
    names = sorted(sources) if a.all else [a.name] if a.name else []
    if not names:
        ap.error("give a skill name or --all")
    unknown = [n for n in names if n not in sources]
    if unknown:
        ap.error(f"not in skills-sources.json: {unknown}")
    if a.ref and len(names) != 1:
        ap.error("--ref needs exactly one skill")
    for n in names:
        sha = vendor(n, sources[n], a.ref)
        print(f"vendored {n} @ {a.ref or sources[n]['ref']} ({sha[:12]})")
    import build_provenance as bp  # rebaseline exactly what was vendored
    bp.write_registry(bp.build(recapture=set(names)))
    print(f"rebaselined {len(names)} skill(s) in skills-provenance.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

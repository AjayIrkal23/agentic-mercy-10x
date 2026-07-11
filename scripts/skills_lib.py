#!/usr/bin/env python3
"""
skills_lib.py — shared primitives for the P5 skill consolidation toolchain.

Home of: front-matter parse/emit, distinctive-trigger-word tokenisation +
token-diff (the trigger-law proof), directory content hashing (R10),
provenance family derivation (all from disk, never hardcoded), and skill
enumeration. Imported by validate_skills.py, build_skills_index.py,
build_provenance.py, migrate_frontmatter.py, apply_merge.py, make_alias.py.

Pure stdlib + PyYAML. No network, no external state.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import yaml

CLAUDE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = CLAUDE_DIR / "skills"
HOOKS_DIR = CLAUDE_DIR / "hooks"
COMMANDS_DIR = CLAUDE_DIR / "commands"

# ---------------------------------------------------------------------------
# Front-matter
# ---------------------------------------------------------------------------
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def read_frontmatter(path: Path) -> tuple[dict, str, bool]:
    """Return (frontmatter_dict, body, ok). ok=False if no valid front-matter."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, "", False
    m = _FM_RE.match(text)
    if not m:
        return {}, text, False
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}, text, False
    if not isinstance(fm, dict):
        return {}, text, False
    return fm, m.group(2), True


def dump_frontmatter(fm: dict, body: str) -> str:
    """Deterministic front-matter + body serialisation.

    Native/ordering-significant keys are emitted first in a stable order so
    diffs stay readable; the rest follow alphabetically.
    """
    order = [
        "name", "description", "disable-model-invocation", "user-invocable",
        "allowed-tools", "preamble-tier", "version",
        "schema", "category", "surfaces", "platforms", "model-hint",
        "token-cost", "requires", "triggers", "links", "alias_of", "provenance",
    ]
    ordered: dict = {}
    for k in order:
        if k in fm:
            ordered[k] = fm[k]
    for k in sorted(fm):
        if k not in ordered:
            ordered[k] = fm[k]
    dumped = yaml.dump(
        ordered, sort_keys=False, default_flow_style=False, allow_unicode=True,
        width=100,
    )
    body = body if body.startswith("\n") or not body else body
    return f"---\n{dumped}---\n{body}"


def write_skill(path: Path, fm: dict, body: str) -> None:
    Path(path).write_text(dump_frontmatter(fm, body), encoding="utf-8")


# ---------------------------------------------------------------------------
# Trigger-word tokenisation + token-diff (the trigger-law proof)
# ---------------------------------------------------------------------------
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "by",
    "is", "are", "be", "being", "been", "this", "that", "these", "those", "it",
    "as", "with", "when", "use", "used", "using", "into", "any", "all", "not",
    "no", "yes", "do", "does", "if", "then", "else", "than", "which", "what",
    "who", "how", "why", "where", "your", "you", "our", "we", "they", "them",
    "its", "their", "from", "but", "so", "up", "out", "via", "per", "each",
    "before", "after", "during", "over", "under", "about", "between", "across",
    "also", "just", "only", "very", "more", "most", "some", "one", "two",
    "three", "here", "there", "them", "get", "set", "run", "make", "made",
    "keep", "kept", "new", "old", "own", "same", "e", "g", "eg", "ie",
    "alias",
}
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.\-/]*", re.IGNORECASE)


def trigger_words(text: str) -> set[str]:
    """Distinctive lowercase trigger words in a description/keyword blob."""
    words = {w.lower().strip("-._/") for w in _WORD_RE.findall(text or "")}
    return {w for w in words if len(w) >= 3 and w not in _STOP}


def token_diff(old_desc: str, new_desc: str, keywords) -> set[str]:
    """Trigger words in old_desc missing from (new_desc ∪ keywords).

    Empty set == pass (no distinctive trigger word was lost).
    """
    old = trigger_words(old_desc)
    kw_blob = " ".join(keywords) if not isinstance(keywords, str) else keywords
    survived = trigger_words(new_desc) | trigger_words(kw_blob)
    return old - survived


# ---------------------------------------------------------------------------
# Directory content hashing (R10 upstream-intactness)
# ---------------------------------------------------------------------------
_HASH_EXCLUDE_DIRS = {".git", ".git-upstream", "__pycache__", ".pytest_cache"}
_HASH_EXCLUDE_SUFFIX = {".pyc", ".pyo"}


def dir_content_hash(root: Path, follow_symlinks: bool = True) -> str:
    """Stable sha256 over (relpath, filehash) of all non-volatile files."""
    root = Path(root)
    entries: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = [d for d in dirnames if d not in _HASH_EXCLUDE_DIRS]
        for fn in filenames:
            if Path(fn).suffix in _HASH_EXCLUDE_SUFFIX:
                continue
            fp = Path(dirpath) / fn
            rel = str(fp.relative_to(root))
            try:
                data = fp.read_bytes()
            except OSError:
                continue
            entries.append((rel, hashlib.sha256(data).hexdigest()))
    entries.sort()
    h = hashlib.sha256()
    for rel, fh in entries:
        h.update(rel.encode())
        h.update(fh.encode())
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Skill enumeration + provenance family derivation (ALL from disk)
# ---------------------------------------------------------------------------
VENDORED_DESIGN = ["impeccable", "taste-skill", "ui-ux-pro-max", "huashu-design",
                   "design-extract"]
EMBEDDED_GIT = {"vite-react-best-practices": "github.com/claudiocebpaz/vite-react-best-practices"}
SKILLS_CLI = {"find-skills": "npx skills ecosystem"}


def skill_dirs() -> list[Path]:
    """All 218 skill directories (a dir with a resolvable SKILL.md)."""
    out = []
    for d in sorted(SKILLS_DIR.iterdir()):
        if not (d.is_dir() or d.is_symlink()):
            continue
        if d.name in {"node_modules"}:
            continue
        if (d / "SKILL.md").exists():
            out.append(d)
    return out


def skill_names() -> list[str]:
    return [d.name for d in skill_dirs()]


def is_gstack_twin(d: Path) -> bool:
    sk = d / "SKILL.md"
    if not sk.is_symlink():
        return False
    try:
        return "/skills/gstack/" in os.readlink(sk)
    except OSError:
        return False


def derive_families() -> dict[str, str]:
    """skill_name -> family, for the 128 upstream-locked skills only.

    Families: gstack-clone, installer-managed, gsd, vendored-design,
    embedded-git, skills-cli.
    """
    fam: dict[str, str] = {}
    for d in skill_dirs():
        n = d.name
        if n == "gstack":
            fam[n] = "gstack-clone"
        elif is_gstack_twin(d):
            fam[n] = "gstack-clone"
        elif d.is_symlink() and ".agents/skills" in (os.readlink(d) if d.is_symlink() else ""):
            fam[n] = "installer-managed"
        elif n.startswith("gsd-"):
            fam[n] = "gsd"
        elif n in VENDORED_DESIGN:
            fam[n] = "vendored-design"
        elif n in EMBEDDED_GIT:
            fam[n] = "embedded-git"
        elif n in SKILLS_CLI:
            fam[n] = "skills-cli"
    return fam


def locked_skills() -> set[str]:
    return set(derive_families())


def user_authored_skills() -> list[str]:
    """The 90 skills with full merge/modify freedom (NOT upstream-locked)."""
    locked = locked_skills()
    return [n for n in skill_names() if n not in locked]


def estimate_token_cost(skill_dir: Path) -> int:
    """~chars/4 of the SKILL.md body (front-matter excluded)."""
    fm, body, ok = read_frontmatter(skill_dir / "SKILL.md")
    text = body if ok else (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
    return max(1, round(len(text) / 4))


def clone_member_description(name: str) -> str:
    """Description string of a gstack clone member (skills/gstack/<name>)."""
    fm, _, ok = read_frontmatter(SKILLS_DIR / "gstack" / name / "SKILL.md")
    return str(fm.get("description", "")) if ok else ""


def skill_description(name: str) -> str:
    fm, _, ok = read_frontmatter(SKILLS_DIR / name / "SKILL.md")
    return str(fm.get("description", "")) if ok else ""


def r10_check(provenance: dict) -> list[tuple[str, str, str]]:
    """R10 upstream-intactness probe.

    Returns [(skill, status, detail)] with status OK|FAIL|SKIP.
    - gstack clone dir  -> `git status --porcelain` clean (tracked only)
    - gstack twin       -> pointer/symlink description == recorded baseline
    - all other locked  -> dir content hash == recorded baseline
    """
    import subprocess
    out: list[tuple[str, str, str]] = []
    for name, meta in provenance.items():
        basis = meta.get("hashBasis")
        baseline = meta.get("baselineHash")
        d = SKILLS_DIR / name
        if basis == "git-clean":
            try:
                r = subprocess.run(
                    ["git", "-C", str(d), "status", "--porcelain",
                     "--untracked-files=no"],
                    capture_output=True, text=True, timeout=30)
                out.append((name, "OK" if not r.stdout.strip() else "FAIL",
                            "clean" if not r.stdout.strip() else r.stdout.strip()[:200]))
            except Exception as e:  # noqa: BLE001
                out.append((name, "SKIP", f"git error: {e}"))
        elif basis == "pointer-desc":
            cur = sha256_text(skill_description(name))
            clone = sha256_text(clone_member_description(name))
            if cur == baseline and clone == baseline:
                out.append((name, "OK", "pointer==clone==baseline"))
            elif cur == clone:
                out.append((name, "OK", "pointer==clone (upstream moved; rebaseline)"))
            else:
                out.append((name, "FAIL", "pointer description drifted from clone"))
        elif basis == "content-hash":
            cur = dir_content_hash(d)
            out.append((name, "OK" if cur == baseline else "FAIL",
                        "match" if cur == baseline else "local edit detected"))
        else:
            out.append((name, "SKIP", f"unknown basis {basis}"))
    return out


if __name__ == "__main__":
    fams = derive_families()
    from collections import Counter
    print("skills on disk:", len(skill_names()))
    print("locked:", len(fams), dict(Counter(fams.values())))
    print("user-authored:", len(user_authored_skills()))

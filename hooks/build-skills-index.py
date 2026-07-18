#!/usr/bin/env python3
"""build-skills-index.py — deterministic ranked-routing catalog (P1-T5).

Emits ``hooks/skills-index.json`` covering ALL skills on disk (no tiering out of
the ranked set — Charter §4a). Bootstrap source order per skill (Spec A §5.2):
  (a) schema-v1 front-matter fields when present (keywords/surfaces/intents/
      path_rules — added by the P5 corpus pass), else
  (b) a fallback reverse-import from ``trigger-floor.json`` (skills referenced by
      path-route rules inherit those match patterns as path_rules + surface; the
      skill name + description are tokenised into keywords) — so S2 ranking works
      BEFORE the front-matter enrichment lands (bridges P1 -> P5).

Deterministic: same input -> same bytes (stable sorting). Rebuilt automatically
when any SKILL.md mtime > index mtime. Pure Python 3 stdlib; Windows+POSIX
portable; never raises on a single unreadable/half-written skill (P5 may be
editing skills/ concurrently).

Usage:
  python3 build-skills-index.py            # rebuild if stale, else no-op
  python3 build-skills-index.py --force    # always rebuild
  python3 build-skills-index.py --check    # assert index count == on-disk skill count
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_FLOOR_PATH = _HOOKS / "trigger-floor.json"
_INDEX_PATH = _HOOKS / "skills-index.json"


def _skills_root() -> Path:
    # derive from ~ — never a literal absolute path
    return Path("~/.claude/skills").expanduser()


_STOP = {
    "the", "and", "for", "with", "when", "use", "used", "using", "this", "that",
    "from", "into", "your", "you", "are", "any", "all", "not", "but", "via",
    "per", "our", "its", "was", "were", "has", "have", "will", "can", "may",
    "skill", "skills", "usewhen", "alias", "of", "a", "an", "to", "in", "on",
    "or", "is", "it", "be", "as", "by", "at", "we", "do", "get", "set", "new",
    "code", "work", "task", "file", "files", "user", "before", "after", "over",
}


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", (text or "").lower())
    out: list[str] = []
    seen = set()
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


# --------------------------------------------------------------------------- #
# minimal front-matter parser (no pyyaml dependency)
# --------------------------------------------------------------------------- #
def _front_matter(md_text: str) -> dict:
    if not md_text.startswith("---"):
        return {}
    end = md_text.find("\n---", 3)
    if end == -1:
        return {}
    block = md_text[3:end].strip("\n")
    fm: dict = {}
    cur_key = None
    for raw in block.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        # list item under a key
        m_item = re.match(r"^\s*-\s+(.*)$", line)
        if m_item and cur_key:
            fm.setdefault(cur_key, [])
            if isinstance(fm[cur_key], list):
                fm[cur_key].append(m_item.group(1).strip().strip("\"'"))
            continue
        m_kv = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if m_kv:
            key, val = m_kv.group(1).strip(), m_kv.group(2).strip()
            cur_key = key
            if val == "":
                fm[key] = []  # a following indented list or block
            elif val.startswith("[") and val.endswith("]"):
                fm[key] = [x.strip().strip("\"'") for x in val[1:-1].split(",") if x.strip()]
            else:
                fm[key] = val.strip("\"'")
    return fm


# --------------------------------------------------------------------------- #
# floor -> skill fallback map
# --------------------------------------------------------------------------- #
def _floor_skill_map() -> dict[str, dict]:
    """skill_name -> {path_rules:[match...], surfaces:set, intents:set, keywords:set}."""
    out: dict[str, dict] = {}
    try:
        floor = json.loads(_FLOOR_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for e in floor.get("entries", []):
        if e.get("kind") == "path_route":
            rule = e.get("value", {})
            rid = rule.get("id", "")
            surface = "frontend" if rid.startswith("fe_") else ("backend" if rid.startswith("be_") else "")
            for sk in rule.get("skills", []):
                d = out.setdefault(sk, {"path_rules": [], "surfaces": set(), "intents": set(), "keywords": set()})
                m = rule.get("match", {})
                if m:
                    d["path_rules"].append(m)
                if surface:
                    d["surfaces"].add(surface)
                for kw in m.get("path_contains_any", []) + m.get("filename_contains_any", []):
                    d["keywords"].add(str(kw).strip("/.").lower())
        elif e.get("kind") == "cross_cutting":
            v = e.get("value", {})
            group = v.get("group", "")
            for sk in v.get("skills", []):
                d = out.setdefault(sk, {"path_rules": [], "surfaces": set(), "intents": set(), "keywords": set()})
                if group == "debug":
                    d["intents"].add("DEBUG")
                elif group == "verification":
                    d["intents"].update({"REVIEW", "TEST", "QA"})
                elif group == "implementation":
                    d["intents"].update({"IMPLEMENT", "SPEC", "PLAN"})
    return out


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _iter_skill_files(root: Path):
    for p in sorted(root.glob("*/SKILL.md")):
        yield p


def _skill_entry(md_path: Path, floor_map: dict) -> tuple[str, dict] | None:
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm = _front_matter(text)
    # Key by DIRECTORY name (guaranteed 1:1 with SKILL.md files, and the name an
    # agent invokes). Front-matter name kept as a display field. This avoids a
    # dict collapse when two skills declare the same front-matter name (e.g. an
    # alias created mid-merge by P5).
    key = md_path.parent.name
    fm_name = fm.get("name") or key
    desc = fm.get("description") or ""
    if isinstance(desc, list):
        desc = " ".join(desc)

    fl = floor_map.get(key, {}) or floor_map.get(fm_name, {})
    # keywords: front-matter schema-v1 first, else derived
    kw = fm.get("keywords")
    keywords: list[str]
    if isinstance(kw, list) and kw:
        keywords = [str(x).lower() for x in kw]
    else:
        derived = set(_tokenize(str(desc))[:25])
        derived.update(_tokenize(key))
        derived.update(_tokenize(fm_name))
        derived.update(fl.get("keywords", set()))
        keywords = sorted(derived)

    surfaces = set(fm.get("surfaces") or []) | set(fl.get("surfaces", set()))
    intents = set(fm.get("intents") or []) | set(fl.get("intents", set()))
    path_rules = fl.get("path_rules", [])
    try:
        weight = float(fm.get("weight", 1.0))
    except (TypeError, ValueError):
        weight = 1.0

    return key, {
        "name": fm_name,
        "description": str(desc)[:400],
        "keywords": sorted(set(keywords)),
        "surfaces": sorted(surfaces),
        "intents": sorted(intents),
        "path_rules": path_rules,
        "weight": weight,
        "source": "front-matter" if isinstance(kw, list) and kw else "floor-fallback",
    }


def build() -> dict:
    root = _skills_root()
    floor_map = _floor_skill_map()
    skills: dict[str, dict] = {}
    if root.is_dir():
        for md in _iter_skill_files(root):
            try:
                res = _skill_entry(md, floor_map)
            except Exception:  # noqa: BLE001 - skip a half-written/racing skill (P5 concurrency)
                res = None
            if res:
                skills[res[0]] = res[1]
    payload = {
        "_meta": {
            "purpose": "Ranked-routing catalog (Spec A §5.2). Covers all on-disk skills; "
                       "schema-v1 front-matter where present, else floor-fallback keywords.",
            "generator": "build-skills-index.py",
            "skill_count": len(skills),
            "checksum": _checksum(skills),
        },
        "skills": dict(sorted(skills.items())),
    }
    _INDEX_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _checksum(skills: dict) -> str:
    canon = json.dumps(skills, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _is_stale() -> bool:
    if not _INDEX_PATH.exists():
        return True
    try:
        idx_mtime = _INDEX_PATH.stat().st_mtime
    except OSError:
        return True
    root = _skills_root()
    if not root.is_dir():
        return False
    for md in _iter_skill_files(root):
        try:
            if md.stat().st_mtime > idx_mtime:
                return True
        except OSError:
            continue
    return False


def _count_on_disk() -> int:
    root = _skills_root()
    return sum(1 for _ in _iter_skill_files(root)) if root.is_dir() else 0


def main(argv: list[str]) -> int:
    if "--hook" in argv:
        # dispatch-link mode: do the work silently, emit the JSON no-op hooks expect
        try:
            if _is_stale():
                build()
        except Exception:  # noqa: BLE001
            pass
        print("{}")
        return 0
    if "--check" in argv:
        idx = json.loads(_INDEX_PATH.read_text(encoding="utf-8")) if _INDEX_PATH.exists() else {"skills": {}}
        n_idx = len(idx.get("skills", {}))
        n_disk = _count_on_disk()
        ok = n_idx == n_disk
        print(f"index skills: {n_idx}  on-disk SKILL.md: {n_disk}  {'OK' if ok else 'MISMATCH'}")
        return 0 if ok else 1
    if "--force" in argv or _is_stale():
        payload = build()
        m = payload["_meta"]
        print(f"Wrote skills-index.json: {m['skill_count']} skills  checksum {m['checksum'][:16]}")
    else:
        print("skills-index.json up to date (no SKILL.md newer than index)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

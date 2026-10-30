#!/usr/bin/env python3
"""
build_skills_index.py — the ONE skills-index generator (hooks/skills-index.json).

Called via the shim hooks/build-skills-index.py (dispatch session-start
``skills-index-guard --hook``, installer post_steps, selfheal) or directly.

Per local skill (every skills/*/SKILL.md):
  routing metadata comes from frontmatter ``metadata:`` (sanctioned home:
  ``metadata.triggers.{keywords,paths,intents}``, ``category``, ``surfaces``,
  ``platforms``, ``links``, ``requires``) with fallback to the legacy top-level
  keys; native ``paths:`` is read too. Descriptions are tokenised ONLY when no
  keywords exist anywhere (``source`` records which path produced the keywords:
  ``metadata`` | ``frontmatter-legacy`` | ``description``).
Plugin skills: every ``plugins/installed_plugins.json`` entry is scanned for
  ``<installPath>/skills/*/SKILL.md`` → ``plugin:skill`` entries, ``source:"plugin"``
  (curated metadata) or ``"plugin-description"`` (keywords derived from the description:
  the router counts those at half weight, RQ-5).
Aliases: hooks/skill-aliases.json is emitted as a top-level ``aliases`` map; alias
  names never get their own entry (stubs are gone) but floor path rules that still
  name an alias are attributed to the canonical.

Output shape stays compatible with prompt_router/select.py and the session-start
aggregator: ``skills[name] = {name, description, keywords, surfaces, intents,
path_rules, weight, source, ...}``.

Flags: --hook (rebuild if stale, print {}), --check, --force. Deterministic bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import skills_lib as sl

_HOOKS = sl.HOOKS_DIR
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib.skill_aliases import canonical as _canonical, load as _load_aliases
except Exception:  # noqa: BLE001 — never crash a session-start hook
    def _canonical(name: str) -> str:  # type: ignore[misc]
        return name

    def _load_aliases() -> dict:  # type: ignore[misc]
        return {}

FLOOR = _HOOKS / "trigger-floor.json"
INDEX = _HOOKS / "skills-index.json"
SIDECAR = sl.CLAUDE_DIR / "state" / "skills-index.plugins.json"  # gitignored: plugin skills, per machine
ALIASES = _HOOKS / "skill-aliases.json"
INSTALLED_PLUGINS = sl.CLAUDE_DIR / "plugins" / "installed_plugins.json"
TEMPLATE = sl.CLAUDE_DIR / "settings.template.json"

# Legacy top-level custom keys (pre-2026-09-27) that now live under ``metadata:``.
LEGACY_META_KEYS = ("schema", "triggers", "surfaces", "category", "platforms",
                    "token-cost", "keywords", "intents", "origin", "requires",
                    "model-hint", "links", "version")

_STOP = {
    "the", "and", "for", "with", "when", "use", "used", "using", "this", "that",
    "from", "into", "your", "you", "are", "any", "all", "not", "but", "via",
    "per", "our", "its", "was", "were", "has", "have", "will", "can", "may",
    "skill", "skills", "alias", "of", "a", "an", "to", "in", "on", "or", "is",
    "it", "be", "as", "by", "at", "we", "do", "get", "set", "new", "code",
    "work", "task", "file", "files", "user", "before", "after", "over",
    "always", "must", "invoke", "mandatory",
    # generic task words: plugin descriptions are full of them (RQ-5: "implementation plan"
    # pushed superpowers:executing-plans onto a feature request)
    "what", "current", "feature", "features", "tasks", "every", "did", "list", "needs",
    "tools", "tool", "session", "report", "changes", "change", "implementation", "plan",
}


def _is_plugin(entry: dict) -> bool:
    """``plugin`` (curated metadata) or ``plugin-description`` (keywords from the description)."""
    return str((entry or {}).get("source") or "").startswith("plugin")


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def skill_meta(fm: dict) -> dict:
    """Routing metadata: ``metadata:`` first, legacy top-level keys as fallback."""
    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    out = dict(meta)
    for k in LEGACY_META_KEYS:
        if k not in out and k in fm:
            out[k] = fm[k]
    return out


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", (text or "").lower())
    out: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _floor_skill_map() -> dict[str, dict]:
    """canonical skill -> {path_rules, surfaces, intents, keywords} from trigger-floor.json."""
    out: dict[str, dict] = {}
    floor = _load(FLOOR)

    def slot(name: str) -> dict:
        return out.setdefault(_canonical(name), {"path_rules": [], "surfaces": set(),
                                                "intents": set(), "keywords": set()})

    for e in floor.get("entries", []) or []:
        if not isinstance(e, dict):
            continue
        val = e.get("value") if isinstance(e.get("value"), dict) else {}
        if e.get("kind") == "path_route":
            rid = str(val.get("id", ""))
            surface = "frontend" if rid.startswith("fe_") else ("backend" if rid.startswith("be_") else "")
            m = val.get("match", {}) or {}
            for sk in val.get("skills", []) or []:
                d = slot(sk)
                if m and m not in d["path_rules"]:
                    d["path_rules"].append(m)
                if surface:
                    d["surfaces"].add(surface)
                for kw in (m.get("path_contains_any", []) or []) + (m.get("filename_contains_any", []) or []):
                    d["keywords"].add(str(kw).strip("/.").lower())
        elif e.get("kind") == "cross_cutting":
            group = val.get("group", "")
            for sk in val.get("skills", []) or []:
                d = slot(sk)
                if group == "debug":
                    d["intents"].add("DEBUG")
                elif group == "verification":
                    d["intents"].update({"REVIEW", "TEST", "QA"})
                elif group == "implementation":
                    d["intents"].update({"IMPLEMENT", "SPEC", "PLAN"})
    return out


def _entry(name: str, fm: dict, floor_map: dict, *, source_kind: str | None = None,
           locked: bool = False, provenance: str | None = None) -> dict:
    desc = fm.get("description", "")
    if isinstance(desc, list):
        desc = " ".join(str(x) for x in desc)
    desc = str(desc or "")
    meta = skill_meta(fm)
    trig = meta.get("triggers") if isinstance(meta.get("triggers"), dict) else {}
    fl = floor_map.get(name, {})

    meta_block = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    meta_trig = meta_block.get("triggers") if isinstance(meta_block.get("triggers"), dict) else {}
    if meta_trig.get("keywords"):
        keywords = [str(x).lower() for x in meta_trig["keywords"]]
        source = "metadata"
    elif trig.get("keywords") or meta.get("keywords"):
        keywords = [str(x).lower() for x in (trig.get("keywords") or meta.get("keywords") or [])]
        source = "frontmatter-legacy"
    else:
        derived = set(_tokenize(desc)[:25]) | set(_tokenize(name)) | set(fl.get("keywords", set()))
        keywords = sorted(derived)
        source = "description"
    if source_kind:
        source = f"{source_kind}-description" if source == "description" else source_kind

    surfaces = set(meta.get("surfaces") or []) | set(fl.get("surfaces", set()))
    intents = set(trig.get("intents") or meta.get("intents") or []) | set(fl.get("intents", set()))
    paths = fm.get("paths") if isinstance(fm.get("paths"), list) else (
        [fm["paths"]] if isinstance(fm.get("paths"), str) else [])
    entry: dict = {
        "name": name,
        "description": desc,
        "keywords": sorted(set(keywords)),
        "surfaces": sorted(surfaces),
        "intents": sorted(intents),
        "path_rules": fl.get("path_rules", []),
        "paths": [str(p) for p in paths],
        "weight": 1.0,
        "source": source,
    }
    for k in ("category", "platforms", "links", "requires"):
        if meta.get(k):
            entry[k] = meta[k]
    if fm.get("when_to_use"):
        entry["when_to_use"] = str(fm["when_to_use"])
    if fm.get("disable-model-invocation") in (True, "true", "yes", "on", 1):
        entry["hidden"] = True
    if locked:
        entry["locked"] = True
        if provenance:
            entry["provenance"] = provenance
    return entry


def _plugin_skill_files() -> list[tuple[str, Path]]:
    """[(plugin_short_name, SKILL.md path)] for every installed plugin skill, minus
    plugins the template disables (their skills cannot load)."""
    out: list[tuple[str, Path]] = []
    plugins = _load(INSTALLED_PLUGINS).get("plugins") or {}
    enabled = _load(TEMPLATE).get("enabledPlugins") or {}
    for key, installs in plugins.items():
        if enabled.get(key) is False:
            continue
        short = str(key).split("@", 1)[0]
        for inst in installs if isinstance(installs, list) else []:
            root = Path(str((inst or {}).get("installPath") or ""))
            if not root.is_dir():
                continue
            for md in sorted((root / "skills").glob("*/SKILL.md")):
                out.append((short, md))
    return out


def build() -> dict:
    floor_map = _floor_skill_map()
    locked = sl.locked_skills()
    provenance = _load(_HOOKS / "skills-provenance.json")
    aliases = _load_aliases()

    entries: dict[str, dict] = {}
    for d in sl.skill_dirs():
        name = d.name
        if name in aliases:  # a stale stub — the alias map resolves it, never index it
            continue
        fm, _body, ok = sl.read_frontmatter(d / "SKILL.md")
        if not ok:
            fm = {"description": ""}
        is_locked = name in locked
        entries[name] = _entry(
            name, fm, floor_map, locked=is_locked,
            provenance=(provenance.get(name, {}) or {}).get("family") if is_locked else None)

    for short, md in _plugin_skill_files():
        fm, _body, ok = sl.read_frontmatter(md)
        if not ok:
            continue
        key = f"{short}:{md.parent.name}"
        entries[key] = _entry(key, fm, floor_map, source_kind="plugin")
        entries[key]["plugin"] = short

    skills = dict(sorted(entries.items()))
    canon = json.dumps(skills, sort_keys=True, ensure_ascii=False)
    n_local = sum(1 for e in skills.values() if not _is_plugin(e))
    return {
        "_meta": {
            "purpose": "Ranked-routing catalog: every local skill (metadata-first, aliases resolved) "
                       "plus installed plugin skills as plugin:skill.",
            "generator": "build_skills_index.py",
            "skill_count": n_local,
            "plugin_count": len(skills) - n_local,
            "alias_count": len(aliases),
            "checksum": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
        },
        "aliases": dict(sorted(aliases.items())),
        "skills": skills,
    }


def _split(payload: dict) -> tuple[dict, dict]:
    """(tracked local-only index, per-machine plugin sidecar). The tracked file never names a plugin
    skill: plugin inventories differ per machine (Windows replica), and an install must not dirty git."""
    skills = payload.get("skills") or {}
    local = {k: v for k, v in skills.items() if not _is_plugin(v)}
    plug = {k: v for k, v in skills.items() if _is_plugin(v)}

    def _sum(d: dict) -> str:
        return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    meta = dict(payload["_meta"], plugin_count=0, checksum=_sum(local),
                plugin_sidecar=f"state/{SIDECAR.name} (gitignored, per machine)")
    tracked = {"_meta": meta, "aliases": payload.get("aliases") or {}, "skills": local}
    side = {"_meta": {"generator": "build_skills_index.py", "plugin_count": len(plug), "checksum": _sum(plug)},
            "skills": plug}
    return tracked, side


def _write_if_changed(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_index() -> dict:
    """Write both files; returns the merged payload (local + plugin), as before."""
    payload = build()
    tracked, side = _split(payload)
    _write_if_changed(INDEX, tracked)
    _write_if_changed(SIDECAR, side)
    if INDEX.exists():
        INDEX.touch()  # the staleness check compares this mtime, also when the bytes were unchanged
    return payload


def _is_stale() -> bool:
    if not INDEX.exists() or not SIDECAR.exists():
        return True
    try:
        idx_mtime = INDEX.stat().st_mtime
    except OSError:
        return True
    candidates = [ALIASES, INSTALLED_PLUGINS]
    candidates += [d / "SKILL.md" for d in sl.skill_dirs()]
    candidates += [md for _s, md in _plugin_skill_files()]
    for p in candidates:
        try:
            if p.exists() and p.stat().st_mtime > idx_mtime:
                return True
        except OSError:
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--hook" in argv:
        try:
            if _is_stale():
                write_index()
        except Exception:  # noqa: BLE001
            pass
        print("{}")
        return 0
    if "--check" in argv:
        idx = _load(INDEX)
        n_idx = int((idx.get("_meta") or {}).get("skill_count") or
                    sum(1 for e in (idx.get("skills") or {}).values() if not _is_plugin(e)))
        aliases = _load_aliases()
        n_disk = sum(1 for d in sl.skill_dirs() if d.name not in aliases)
        ok = n_idx == n_disk
        print(f"index local skills: {n_idx}  on-disk SKILL.md: {n_disk}  {'OK' if ok else 'MISMATCH'}")
        return 0 if ok else 1
    if "--force" in argv or _is_stale() or not argv:
        payload = write_index()
        m = payload["_meta"]
        print(f"wrote {INDEX.name}: {m['skill_count']} local + {m['plugin_count']} plugin skills, "
              f"{m['alias_count']} aliases, checksum {m['checksum'][:16]}")
    else:
        print("skills-index.json up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())

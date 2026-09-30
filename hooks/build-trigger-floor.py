#!/usr/bin/env python3
"""build-trigger-floor.py — builds ``trigger-floor.json``, the router's keyword
taxonomy (v2 floor, 2026-09-27).

Mechanically reverse-imports every trigger rule from the source configs into one
file that ``prompt_router/classify.py`` evaluates in full. ``--check`` proves —
for CI and pytest — that (a) every rule currently in the sources is present in
the on-disk floor, (b) every source file exists and contributes at least one
entry (the 2026-08-15 incident: a deleted source silently zeroed the UI
vocabulary and ``--check`` stayed green), and (c) the router consumes the whole
floor. Any argv this script does not recognise is refused (exit 2) WITHOUT
writing — the pre-v2 builder rebuilt the floor on ``--help``.

Sources (verbatim, then filtered by the <= 3-char rule):
  1. skill_router.config.json          frontend_rules / backend_rules / cross_cutting
  2. skill_router.py builtins          _BUILTIN_FRONTEND_RULES / _BUILTIN_BACKEND_RULES /
                                        _BUILTIN_CROSS_CUTTING (UNION with 1, by id)
  3. autonomous-skill-router.config    categories[*].keywords (act keywords)
  4. fullstack-skills-reminder.config  frontend/backend/documentation path segments
  5. ui-keywords.json                  ui_keywords + ui_path_suffixes + exclude_keywords
  6. graphify-enforce.config           arch_keywords + explore_keywords

Keyword filter: act / ui keywords of <= 3 chars are dropped unless they are in
``classify._SHORT_ALLOW`` (``cr``, ``off``, ``odd``, ``sse``, ``dos`` … caused
61% of prompts to misroute under substring matching; with word-boundary matching
they are still too ambiguous to keep).

Charter: removals from the floor require a ``_meta.charter`` bump (this file
bumped it to v2 when the historic ``/invoke-*`` command names and the
``invoke_command_map`` entries were retired with the commands/ directory).

Usage:
  python3 build-trigger-floor.py                  # (re)build trigger-floor.json
  python3 build-trigger-floor.py --check [--quiet] # verify; exit 1 on any miss
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_FLOOR_PATH = _HOOKS / "trigger-floor.json"
_ROUTER_CONFIG = _HOOKS / "prompt_router" / "router.config.json"

CHARTER = "v2 floor (2026-09-27): removals require a charter bump"
_KNOWN_ARGS = {"--check", "--quiet"}

# JSON sources (name -> path). A missing file or a zero-entry bucket FAILS --check.
_SOURCES = {
    "skill_router.config.json": _HOOKS / "skill_router.config.json",
    "autonomous-skill-router.config.json": _HOOKS / "autonomous-skill-router.config.json",
    "fullstack-skills-reminder.config.json": _HOOKS / "fullstack-skills-reminder.config.json",
    "ui-keywords.json": _HOOKS / "ui-keywords.json",
    "graphify-enforce.config.json": _HOOKS / "graphify-enforce.config.json",
}

# Same allow-list as prompt_router/classify.py::_SHORT_ALLOW (imported when the
# package is importable so the two can never drift; literal fallback otherwise).
try:
    sys.path.insert(0, str(_HOOKS))
    from prompt_router.classify import _SHORT_ALLOW as SHORT_ALLOW  # noqa: E402
except Exception:  # noqa: BLE001
    SHORT_ALLOW = frozenset({"api", "ui", "ux", "sql", "css", "tdd", "e2e", "a11y", "seo",
                             "glb", "r3f", "ci", "cd", "go", "tsx", "3d"})

# Keywords that are legitimate but noisy — kept, but down-weighted so they still
# surface a suggestion without dominating ranking.
_VAGUE = {
    "wrong", "weird", "bad", "broken", "button", "input", "form",
    "card", "menu", "page", "screen", "view", "change", "tweak",
    "ui", "ux", "css", "flex", "grid", "font", "icon", "image", "photo",
    "find", "search", "where", "count", "scan", "flow", "trace", "graph",
    "module", "structure", "overview", "shape", "polish", "refine", "clean",
    "test", "rename", "typo", "small", "medium", "large",
}


# --------------------------------------------------------------------------- #
# IO helpers (fail-soft)
# --------------------------------------------------------------------------- #
def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _weight_for(kw: str) -> float:
    return 0.4 if kw.strip().lower() in _VAGUE else 1.0


def keyword_ok(kw) -> bool:
    k = str(kw).strip().lower()
    return bool(k) and (len(k) > 3 or k in SHORT_ALLOW)


# --------------------------------------------------------------------------- #
# Source 2: skill_router.py builtins via AST (side-effect-free, no import)
# --------------------------------------------------------------------------- #
def _extract_builtins() -> dict:
    """Return {name: literal_value} for the three _BUILTIN_* module constants."""
    wanted = {"_BUILTIN_FRONTEND_RULES", "_BUILTIN_BACKEND_RULES", "_BUILTIN_CROSS_CUTTING"}
    out: dict = {}
    src_path = _HOOKS / "skill_router.py"
    try:
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in wanted:
                    try:
                        out[tgt.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            tgt = node.target
            if isinstance(tgt, ast.Name) and tgt.id in wanted:
                try:
                    out[tgt.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return out


# --------------------------------------------------------------------------- #
# Entry construction
# --------------------------------------------------------------------------- #
def _entry(kind: str, value, source_file: str, source_key: str, weight: float = 1.0) -> dict:
    return {
        "kind": kind,
        "value": value,
        "source_file": source_file,
        "source_key": source_key,
        "weight": weight,
    }


def _collect() -> list[dict]:
    entries: list[dict] = []

    # --- Source 1 + 2: path/route rules (config UNION builtins by id) --------
    sr_cfg = _load_json(_SOURCES["skill_router.config.json"])
    builtins = _extract_builtins()

    fe_by_id: dict[str, tuple] = {}
    be_by_id: dict[str, tuple] = {}
    for r in sr_cfg.get("frontend_rules", []) or []:
        if isinstance(r, dict):
            fe_by_id[r.get("id", "")] = ("skill_router.config.json", r)
    for r in sr_cfg.get("backend_rules", []) or []:
        if isinstance(r, dict):
            be_by_id[r.get("id", "")] = ("skill_router.config.json", r)
    for r in builtins.get("_BUILTIN_FRONTEND_RULES", []) or []:
        rid = r.get("id", "")
        if rid not in fe_by_id:
            fe_by_id[rid] = ("skill_router.py:_BUILTIN_FRONTEND_RULES", r)
    for r in builtins.get("_BUILTIN_BACKEND_RULES", []) or []:
        rid = r.get("id", "")
        if rid not in be_by_id:
            be_by_id[rid] = ("skill_router.py:_BUILTIN_BACKEND_RULES", r)
    for rid, (src, rule) in {**fe_by_id, **be_by_id}.items():
        entries.append(_entry("path_route", rule, src, rid))

    xcut = sr_cfg.get("cross_cutting") or builtins.get("_BUILTIN_CROSS_CUTTING") or {}
    xcut_src = ("skill_router.config.json" if sr_cfg.get("cross_cutting")
                else "skill_router.py:_BUILTIN_CROSS_CUTTING")
    for group, skills in xcut.items():
        entries.append(_entry("cross_cutting", {"group": group, "skills": skills}, xcut_src, group))
    for group, skills in (builtins.get("_BUILTIN_CROSS_CUTTING") or {}).items():
        if group not in xcut:
            entries.append(_entry("cross_cutting", {"group": group, "skills": skills},
                                  "skill_router.py:_BUILTIN_CROSS_CUTTING", group))

    # --- Source 3: autonomous categories (act keywords) ----------------------
    auto = _load_json(_SOURCES["autonomous-skill-router.config.json"])
    for cat, spec in (auto.get("categories") or {}).items():
        if not isinstance(spec, dict):
            continue
        for kw in spec.get("keywords", []) or []:
            if keyword_ok(kw):
                entries.append(_entry("act_keyword", kw, "autonomous-skill-router.config.json",
                                      f"categories.{cat}", _weight_for(str(kw))))

    # --- Source 4: fullstack path segments -----------------------------------
    fs = _load_json(_SOURCES["fullstack-skills-reminder.config.json"])
    for key in ("frontend_path_segments", "backend_path_segments", "documentation_path_segments"):
        for seg in fs.get(key, []) or []:
            entries.append(_entry("path_segment", seg, "fullstack-skills-reminder.config.json", key))

    # --- Source 5: ui keywords / suffixes / excludes -------------------------
    ui = _load_json(_SOURCES["ui-keywords.json"])
    for kw in ui.get("ui_keywords", []) or []:
        if keyword_ok(kw):
            entries.append(_entry("ui_keyword", kw, "ui-keywords.json", "ui_keywords",
                                  _weight_for(str(kw))))
    for suf in ui.get("ui_path_suffixes", []) or []:
        entries.append(_entry("ui_suffix", suf, "ui-keywords.json", "ui_path_suffixes"))
    for kw in ui.get("exclude_keywords", []) or []:
        entries.append(_entry("ui_exclude", kw, "ui-keywords.json", "exclude_keywords"))

    # --- Source 6: graphify arch / explore keywords --------------------------
    gr = _load_json(_SOURCES["graphify-enforce.config.json"])
    for kw in gr.get("arch_keywords", []) or []:
        entries.append(_entry("arch_keyword", kw, "graphify-enforce.config.json", "arch_keywords",
                              _weight_for(str(kw))))
    for kw in gr.get("explore_keywords", []) or []:
        entries.append(_entry("explore_keyword", kw, "graphify-enforce.config.json",
                              "explore_keywords", _weight_for(str(kw))))

    return _dedup(entries)


def _dedup(entries: list[dict]) -> list[dict]:
    """Dedup by identical (kind, value, source_file, source_key) tuple ONLY."""
    seen = set()
    out = []
    for e in entries:
        key = _value_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _value_key(e: dict) -> tuple:
    return (e["kind"], json.dumps(e["value"], sort_keys=True, ensure_ascii=False),
            e["source_file"], e["source_key"])


def _checksum(entries: list[dict]) -> str:
    canon = json.dumps(sorted(_value_key(e) for e in entries), ensure_ascii=False)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _source_counts() -> dict:
    sr = _load_json(_SOURCES["skill_router.config.json"])
    auto = _load_json(_SOURCES["autonomous-skill-router.config.json"])
    ui = _load_json(_SOURCES["ui-keywords.json"])
    gr = _load_json(_SOURCES["graphify-enforce.config.json"])
    fs = _load_json(_SOURCES["fullstack-skills-reminder.config.json"])
    b = _extract_builtins()
    return {
        "skill_router.config.rules": len(sr.get("frontend_rules", []) or []) + len(sr.get("backend_rules", []) or []),
        "skill_router.builtins": len(b.get("_BUILTIN_FRONTEND_RULES", []) or []) + len(b.get("_BUILTIN_BACKEND_RULES", []) or []),
        "autonomous.category_keywords": sum(
            sum(1 for k in (v.get("keywords", []) or []) if keyword_ok(k))
            for v in (auto.get("categories") or {}).values() if isinstance(v, dict)),
        "ui.keywords": sum(1 for k in (ui.get("ui_keywords", []) or []) if keyword_ok(k)),
        "graphify.arch+explore": len(gr.get("arch_keywords", []) or []) + len(gr.get("explore_keywords", []) or []),
        "fullstack.segments": sum(len(fs.get(k, []) or []) for k in ("frontend_path_segments", "backend_path_segments", "documentation_path_segments")),
    }


# --------------------------------------------------------------------------- #
# build / check
# --------------------------------------------------------------------------- #
def build() -> dict:
    entries = _collect()
    floor = {
        "_meta": {
            "purpose": "Prompt-router trigger floor — word-boundary keyword taxonomy consumed in full by prompt_router/classify.py.",
            "charter": CHARTER,
            "generated": datetime.now(timezone.utc).isoformat(),
            "generator": "build-trigger-floor.py",
            "checksum": _checksum(entries),
            "entry_count": len(entries),
            "short_allow": sorted(SHORT_ALLOW),
            "source_counts": _source_counts(),
        },
        "entries": entries,
    }
    _FLOOR_PATH.write_text(json.dumps(floor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return floor


def check(quiet: bool = False) -> int:
    """0 when: every source file exists; every source bucket is non-zero
    (skill_router.builtins may be 0 — it is a UNION supplement to source 1,
    reported as WARN); the on-disk floor is a superset of the sources; and the
    router consumes the whole floor. Else 1."""
    problems = 0

    # (b) source files present + non-zero buckets
    for name, path in _SOURCES.items():
        if not path.is_file():
            problems += 1
            if not quiet:
                print(f"FAIL: source file missing: {name}", file=sys.stderr)
    counts = _source_counts()
    for bucket, n in counts.items():
        if n == 0:
            if bucket == "skill_router.builtins":
                if not quiet:
                    print("WARN: skill_router.builtins is 0 (UNION supplement — allowed)", file=sys.stderr)
                continue
            problems += 1
            if not quiet:
                print(f"FAIL: source bucket is 0: {bucket}", file=sys.stderr)

    on_disk = _load_json(_FLOOR_PATH)
    if not on_disk:
        print("FLOOR MISSING — run build-trigger-floor.py first", file=sys.stderr)
        return 1
    disk_entries = on_disk.get("entries", [])
    disk_keys = {_value_key(e) for e in disk_entries}

    # (a) sources ⊆ floor
    rebuilt = _collect()
    missing_from_disk = [e for e in rebuilt if _value_key(e) not in disk_keys]
    if missing_from_disk:
        problems += len(missing_from_disk)
        if not quiet:
            print(f"FAIL: {len(missing_from_disk)} source rule(s) missing from floor (rebuild):", file=sys.stderr)
            for e in missing_from_disk[:20]:
                print(f"  - [{e['kind']}] {e['value']!r} ({e['source_file']}::{e['source_key']})", file=sys.stderr)

    # (c) floor -> router coverage
    cfg = _load_json(_ROUTER_CONFIG)
    if cfg and cfg.get("consumes_entire_floor") is not True:
        problems += 1
        if not quiet:
            print("FAIL: router.config.json does not set consumes_entire_floor=true", file=sys.stderr)

    if not quiet:
        print(f"floor entries: {len(disk_entries)}  checksum(disk): {_checksum(disk_entries)[:16]}  "
              f"stored: {on_disk.get('_meta', {}).get('checksum', '')[:16]}")
        print(f"checksum(sources rebuilt): {_checksum(rebuilt)[:16]}  charter: {on_disk.get('_meta', {}).get('charter', '?')}")
        print(f"source_counts: {json.dumps(counts)}")
        if problems == 0:
            print("OK: floor is a superset of all sources; every source present and non-empty.")
    return 0 if problems == 0 else 1


def value_keys(floor: dict) -> list[str]:
    """Public helper: stringified value-keys (kept for external tooling)."""
    return ["|".join(str(x) for x in _value_key(e)) for e in floor.get("entries", [])]


def main(argv: list[str]) -> int:
    unknown = [a for a in argv if a not in _KNOWN_ARGS]
    if unknown:
        print(f"build-trigger-floor.py: unknown argument(s) {unknown} — nothing written. "
              f"Usage: build-trigger-floor.py [--check] [--quiet]", file=sys.stderr)
        return 2
    quiet = "--quiet" in argv
    if "--check" in argv:
        return check(quiet=quiet)
    floor = build()
    if not quiet:
        m = floor["_meta"]
        print(f"Wrote {_FLOOR_PATH.name}: {m['entry_count']} entries  checksum {m['checksum'][:16]}")
        print(f"source_counts: {json.dumps(m['source_counts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""build-trigger-floor.py — Charter §2 prime-directive tool (P1-T3).

Mechanically, VERBATIM, reverse-imports EVERY trigger rule from all legacy
taxonomies into a single ``trigger-floor.json`` that the unified router's
``router.config.json`` is generated as a superset of. Removals are impossible;
additions are allowed. A ``--check`` mode proves — for CI and pytest — that:
  (a) every rule currently in the source configs is present in the on-disk
      floor (no source rule silently dropped), and
  (b) every floor entry is reachable in the generated router.config.json.

Sources reverse-imported (verbatim):
  1. skill_router.config.json          frontend_rules / backend_rules / cross_cutting
  2. skill_router.py builtins          _BUILTIN_FRONTEND_RULES / _BUILTIN_BACKEND_RULES /
                                        _BUILTIN_CROSS_CUTTING   (UNION — captures the
                                        drifted be_security_audit + gstack `cso` route)
  3. autonomous-skill-router.config    categories[*].keywords (act keywords) + invoke_commands
  4. fullstack-skills-reminder.config  frontend/backend/documentation path segments
  5. ui-ux-stack-orchestrator.config   ui_keywords + ui_path_suffixes + exclude_keywords
  6. graphify-enforce.config           arch_keywords + explore_keywords
  7. commands/                         all 139 historic /invoke-* command NAMES (floor-protected;
                                        the parametric collapse retires 120 files, names survive
                                        + the invoke_compat translator resolves them — Charter §5)

Pure Python 3 stdlib. No hardcoded absolute paths. Windows+POSIX portable.

Usage:
  python3 build-trigger-floor.py            # (re)build trigger-floor.json
  python3 build-trigger-floor.py --check    # verify coverage + print checksum; exit 1 on any miss
  python3 build-trigger-floor.py --check --quiet
"""

from __future__ import annotations

import ast
import hashlib
import json
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_COMMANDS = _HOOKS.parent / "commands"
_FLOOR_PATH = _HOOKS / "trigger-floor.json"
_ROUTER_CONFIG = _HOOKS / "prompt_router" / "router.config.json"

# Keywords that are legitimate but noisy — kept (never pruned, Charter §2) but
# down-weighted so they still surface a suggestion without dominating ranking.
_VAGUE = {
    "off", "wrong", "weird", "bad", "broken", "button", "btn", "input", "form",
    "card", "menu", "page", "screen", "view", "fix", "change", "tweak", "off ",
    "ui", "ux", "css", "flex", "grid", "gap", "font", "icon", "image", "photo",
    "find", "search", "where", "count", "map", "scan", "flow", "trace", "graph",
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
        # plain assignment:  _BUILTIN_X = [...]
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in wanted:
                    try:
                        out[tgt.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
        # annotated assignment:  _BUILTIN_X: list[dict] = [...]
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


def _route_entries(rules: list, source_file: str) -> list[dict]:
    entries = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        rid = rule.get("id", "")
        entries.append(_entry("path_route", rule, source_file, rid))
    return entries


def _collect() -> list[dict]:
    entries: list[dict] = []

    # --- Source 1 + 2: path/route rules (config UNION builtins by id) --------
    sr_cfg = _load_json(_HOOKS / "skill_router.config.json")
    builtins = _extract_builtins()

    fe_by_id: dict[str, dict] = {}
    be_by_id: dict[str, dict] = {}
    for r in sr_cfg.get("frontend_rules", []) or []:
        if isinstance(r, dict):
            fe_by_id[r.get("id", "")] = ("skill_router.config.json", r)
    for r in sr_cfg.get("backend_rules", []) or []:
        if isinstance(r, dict):
            be_by_id[r.get("id", "")] = ("skill_router.config.json", r)
    # builtin-only rules are ADDED (never override a config rule) — this is the
    # verbatim capture of the drift (be_security_audit + cso) so it can never be lost.
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

    # cross_cutting (config, else builtin)
    xcut = sr_cfg.get("cross_cutting") or builtins.get("_BUILTIN_CROSS_CUTTING") or {}
    xcut_src = "skill_router.config.json" if sr_cfg.get("cross_cutting") else "skill_router.py:_BUILTIN_CROSS_CUTTING"
    for group, skills in xcut.items():
        entries.append(_entry("cross_cutting", {"group": group, "skills": skills}, xcut_src, group))
    # builtin cross_cutting groups not present in config are also captured
    b_xcut = builtins.get("_BUILTIN_CROSS_CUTTING") or {}
    for group, skills in b_xcut.items():
        if group not in xcut:
            entries.append(_entry("cross_cutting", {"group": group, "skills": skills},
                                  "skill_router.py:_BUILTIN_CROSS_CUTTING", group))

    # --- Source 3: autonomous categories (act keywords) + invoke_commands ----
    auto = _load_json(_HOOKS / "autonomous-skill-router.config.json")
    for cat, spec in (auto.get("categories") or {}).items():
        if not isinstance(spec, dict):
            continue
        for kw in spec.get("keywords", []) or []:
            entries.append(_entry("act_keyword", kw,
                                  "autonomous-skill-router.config.json",
                                  f"categories.{cat}", _weight_for(kw)))
    for cat, spec in (auto.get("invoke_commands") or {}).items():
        entries.append(_entry("invoke_command_map", {"category": cat, "spec": spec},
                              "autonomous-skill-router.config.json", f"invoke_commands.{cat}"))

    # --- Source 4: fullstack path segments -----------------------------------
    fs = _load_json(_HOOKS / "fullstack-skills-reminder.config.json")
    for key in ("frontend_path_segments", "backend_path_segments", "documentation_path_segments"):
        for seg in fs.get(key, []) or []:
            entries.append(_entry("path_segment", seg,
                                  "fullstack-skills-reminder.config.json", key))

    # --- Source 5: ui-ux keywords / suffixes / excludes ----------------------
    ui = _load_json(_HOOKS / "ui-ux-stack-orchestrator.config.json")
    for kw in ui.get("ui_keywords", []) or []:
        entries.append(_entry("ui_keyword", kw,
                              "ui-ux-stack-orchestrator.config.json", "ui_keywords", _weight_for(kw)))
    for suf in ui.get("ui_path_suffixes", []) or []:
        entries.append(_entry("ui_suffix", suf,
                              "ui-ux-stack-orchestrator.config.json", "ui_path_suffixes"))
    for kw in ui.get("exclude_keywords", []) or []:
        entries.append(_entry("ui_exclude", kw,
                              "ui-ux-stack-orchestrator.config.json", "exclude_keywords"))

    # --- Source 6: graphify arch / explore keywords --------------------------
    gr = _load_json(_HOOKS / "graphify-enforce.config.json")
    for kw in gr.get("arch_keywords", []) or []:
        entries.append(_entry("arch_keyword", kw,
                              "graphify-enforce.config.json", "arch_keywords", _weight_for(kw)))
    for kw in gr.get("explore_keywords", []) or []:
        entries.append(_entry("explore_keyword", kw,
                              "graphify-enforce.config.json", "explore_keywords", _weight_for(kw)))

    # --- Source 7: all historic /invoke-* command NAMES ----------------------
    for name in _command_names():
        entries.append(_entry("command_name", name, "commands/", name))

    return _dedup(entries)


def _command_names() -> list[str]:
    """All historic /invoke-* command names (Charter §5): the UNION of the names
    on disk now AND the frozen historic list. This guarantees the parametric
    139->20 collapse (P5) can never drop a retired name from the floor — the
    names stay trigger-protected forever (the invoke_compat translator resolves
    each to /invoke <acts>)."""
    names: set[str] = set()
    try:
        for p in _COMMANDS.glob("invoke*.md"):
            names.add(p.stem)
    except OSError:
        pass
    frozen = _HOOKS / "historic-invoke-commands.json"
    if frozen.is_file():
        try:
            data = json.loads(frozen.read_text(encoding="utf-8"))
            names.update(data.get("names", []))
        except (OSError, json.JSONDecodeError):
            pass
    return sorted(names)


def _dedup(entries: list[dict]) -> list[dict]:
    """Dedup by identical (kind, value, source_file, source_key) tuple ONLY."""
    seen = set()
    out = []
    for e in entries:
        key = (e["kind"], json.dumps(e["value"], sort_keys=True, ensure_ascii=False),
               e["source_file"], e["source_key"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _checksum(entries: list[dict]) -> str:
    canon = json.dumps(
        sorted((e["kind"], json.dumps(e["value"], sort_keys=True, ensure_ascii=False),
                e["source_file"], e["source_key"]) for e in entries),
        ensure_ascii=False,
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _source_counts() -> dict:
    sr = _load_json(_HOOKS / "skill_router.config.json")
    auto = _load_json(_HOOKS / "autonomous-skill-router.config.json")
    ui = _load_json(_HOOKS / "ui-ux-stack-orchestrator.config.json")
    gr = _load_json(_HOOKS / "graphify-enforce.config.json")
    fs = _load_json(_HOOKS / "fullstack-skills-reminder.config.json")
    b = _extract_builtins()
    return {
        "skill_router.config.rules": len(sr.get("frontend_rules", []) or []) + len(sr.get("backend_rules", []) or []),
        "skill_router.builtins": len(b.get("_BUILTIN_FRONTEND_RULES", []) or []) + len(b.get("_BUILTIN_BACKEND_RULES", []) or []),
        "autonomous.category_keywords": sum(len(v.get("keywords", []) or []) for v in (auto.get("categories") or {}).values()),
        "ui.keywords": len(ui.get("ui_keywords", []) or []),
        "graphify.arch+explore": len(gr.get("arch_keywords", []) or []) + len(gr.get("explore_keywords", []) or []),
        "fullstack.segments": sum(len(fs.get(k, []) or []) for k in ("frontend_path_segments", "backend_path_segments", "documentation_path_segments")),
        "command_names": len(_command_names()),
    }


# --------------------------------------------------------------------------- #
# build / check
# --------------------------------------------------------------------------- #
def build() -> dict:
    entries = _collect()
    floor = {
        "_meta": {
            "purpose": "Charter v3 §2 verbatim trigger floor — removals forbidden, additions allowed.",
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generator": "build-trigger-floor.py",
            "checksum": _checksum(entries),
            "entry_count": len(entries),
            "source_counts": _source_counts(),
        },
        "entries": entries,
    }
    _FLOOR_PATH.write_text(json.dumps(floor, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return floor


def _value_key(e: dict) -> tuple:
    return (e["kind"], json.dumps(e["value"], sort_keys=True, ensure_ascii=False),
            e["source_file"], e["source_key"])


def check(quiet: bool = False) -> int:
    """Return 0 if the floor is a superset of all sources AND router.config
    (if present) covers every floor entry; else 1. Prints a checksum."""
    on_disk = _load_json(_FLOOR_PATH)
    if not on_disk:
        print("FLOOR MISSING — run build-trigger-floor.py first", file=sys.stderr)
        return 1
    disk_entries = on_disk.get("entries", [])
    disk_keys = {_value_key(e) for e in disk_entries}

    rebuilt = _collect()
    missing_from_disk = [e for e in rebuilt if _value_key(e) not in disk_keys]

    problems = 0
    if missing_from_disk:
        problems += len(missing_from_disk)
        if not quiet:
            print(f"FAIL: {len(missing_from_disk)} source rule(s) missing from floor:", file=sys.stderr)
            for e in missing_from_disk[:20]:
                print(f"  - [{e['kind']}] {e['value']!r} ({e['source_file']}::{e['source_key']})", file=sys.stderr)

    # floor -> router.config coverage (only if the generated config exists)
    cfg = _load_json(_ROUTER_CONFIG)
    if cfg:
        if cfg.get("consumes_entire_floor") is True:
            pass  # router evaluates the whole floor at runtime -> every entry reachable
        else:
            floor_ref = set(cfg.get("_floor_entry_keys", []))
            if floor_ref:
                uncovered = [e for e in disk_entries if _keystr(_value_key(e)) not in floor_ref]
                if uncovered:
                    problems += len(uncovered)
                    if not quiet:
                        print(f"FAIL: {len(uncovered)} floor entries not reachable in router.config.json",
                              file=sys.stderr)
            elif not quiet:
                print("WARN: router.config.json neither sets consumes_entire_floor nor "
                      "lists _floor_entry_keys — floor->config coverage unverified", file=sys.stderr)

    checksum = _checksum(disk_entries)
    stored = on_disk.get("_meta", {}).get("checksum", "")
    live = _checksum(rebuilt)
    if not quiet:
        print(f"floor entries: {len(disk_entries)}  checksum(disk): {checksum[:16]}")
        print(f"checksum(sources rebuilt): {live[:16]}  stored: {stored[:16]}")
        print(f"source_counts: {json.dumps(_source_counts())}")
    if problems == 0 and not quiet:
        print("OK: floor is a verbatim superset of all legacy taxonomies.")
    return 0 if problems == 0 else 1


def _keystr(key_tuple: tuple) -> str:
    return "|".join(str(x) for x in key_tuple)


def value_keys(floor: dict) -> list[str]:
    """Public helper: stringified value-keys for router.config to embed (--check hook)."""
    return [_keystr(_value_key(e)) for e in floor.get("entries", [])]


def main(argv: list[str]) -> int:
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

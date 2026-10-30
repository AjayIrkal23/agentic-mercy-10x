#!/usr/bin/env python3
"""build_library_index.py — library/INDEX.json from library/ecc/** and library/ecc/digests/**.

  build_library_index.py [--root DIR] [--ecc <ECC checkout>] [--check]

Deterministic (sorted ids, indent=1, sort_keys, LF). --check exits 1 on drift and writes nothing.
Command titles and context-pack trigger phrases come from library/ecc/catalogue.json (written by
vendor_library.py); --ecc re-reads them from a checkout instead (same result at the same sha).
The router (hooks/prompt_router/modules/library_routes.py) reads this file through a compact cache.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import skills_lib  # noqa: E402

KINDS = ("rules-pack", "agent", "skill", "command", "digest", "guide", "doc", "example")
GENERIC = {"code", "data", "file", "files", "tool", "tools", "project", "agent", "agents", "claude", "skill",
           "skills", "workflow", "workflows", "task", "tasks"}
# description filler (never a trigger on its own): words that appear in most ECC descriptions
_FILLER = set("""best practice practices pattern patterns expert must should change changes project projects guide
guidance help helps support supports include includes including cover covers build building builds create creates
creating write writing review reviews reviewer reviewing development developer developers engineering management
quality specialist specializing specialized comprehensive proactively need needs work working works based approach
user users system systems application applications apps app implement implementation implementing test tests testing
fix fixes fixing issue issues error errors analysis analyze invoke invokes mode model models through without within
while other like such multiple ensure ensuring high level production design modern common standard standards
convention conventions idiom idioms idiomatic clean safe simple real full complete automatic automatically setup
configuration config manage tracking covering focused focus focuses across every well good better first full-stack
end-to-end step steps guided level-up strategies strategy techniques technique tips handling handle handles""".split())
_STACK_ALIASES = {"python": ["python", "django", "fastapi", "pytorch", "celery"], "rust": ["rust"],
                  "java": ["java", "springboot", "quarkus", "jpa", "mybatis", "gradle"],
                  "kotlin": ["kotlin", "android", "ktor", "compose"], "swift": ["swift", "swiftui", "ios"],
                  "php": ["php", "laravel"], "ruby": ["ruby", "rails"], "dart": ["dart", "flutter"],
                  "csharp": ["csharp", "dotnet"], "fsharp": ["fsharp"], "cpp": ["cpp"], "perl": ["perl"],
                  "angular": ["angular"], "vue": ["vue"], "nuxt": ["nuxt"], "arkts": ["arkts", "harmonyos"],
                  "go": ["go", "golang"], "typescript": ["typescript"], "react": ["react"]}
_HEADER_RE = re.compile(r"^<!-- ecc:(\S+)@([0-9a-f]{40}) -->$", re.M)
_DIGEST_RE = re.compile(r"^<!-- ecc-digest:(\S+)@([0-9a-f]{40}) -->$", re.M)
_CONFLICT_RE = re.compile(r"<!-- ecc-conflict: ([a-z-]+) -->")
_TRIGGER_KINDS = {"skill", "digest", "command", "agent"}


def stacks_for(name: str, rules_dirs=()) -> list[str]:
    tokens = set(re.split(r"[-_]", name.lower()))
    out = {s for s, aliases in _STACK_ALIASES.items() if tokens & set(aliases)}
    out |= {d for d in rules_dirs if d != "common" and d in tokens}
    return sorted(out)


def surfaces_for(name: str) -> list[str]:
    if name.endswith("-reviewer"):
        return ["review"]
    if name.endswith(("-build-resolver", "-build")):
        return ["build"]
    if name.endswith("-test"):
        return ["test"]
    if re.search(r"security|hardening|compliance", name):
        return ["security"]
    return []


def _first_heading(body: str) -> str | None:
    m = re.search(r"(?m)^# (.+)$", body)
    return m.group(1).strip() if m else None


def _first_paragraph(body: str) -> str:
    for block in re.split(r"\n\s*\n", body):
        b = block.strip()
        if b and not b.startswith(("#", "<!--", "```")):
            return b
    return ""


def triggers_for(name: str, description: str, extra=()) -> list[str]:
    """Name words first (always), then sorted description words minus GENERIC and _FILLER, capped at 12,
    then the context-pack phrases. _FILLER keeps two-hit routing from firing on "best practices"."""
    named = sorted(skills_lib.trigger_words(name.replace("-", " ")) - GENERIC)
    desc = sorted(skills_lib.trigger_words(description or "") - GENERIC - _FILLER - set(named))
    words = [w for w in (named + desc)[:12] if not w.isdigit()]
    return list(dict.fromkeys(w.lower() for w in [*words, *extra] if w))


def entry_for(path: Path, kind: str, root: Path, eid: str, name: str, ctx: dict) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        print(f"warning: empty {path.relative_to(root).as_posix()} skipped", file=sys.stderr)
        return None
    fm, body, _ = skills_lib.read_frontmatter(path)
    fm = fm if isinstance(fm, dict) else {}
    desc = str(fm.get("description") or "").strip() or _first_paragraph(body)
    title = str(fm.get("name") or "") or _first_heading(body) or path.stem
    if kind == "command":
        title = ctx["catalogue"].get("command_titles", {}).get(name) or desc or title
    extra = ctx["catalogue"].get("skill_triggers", {}).get(name, []) if kind == "skill" else []
    hdr = (_DIGEST_RE if kind == "digest" else _HEADER_RE).search(text)
    up_path = "digest" if kind == "digest" else (hdr.group(1) if hdr else "")
    extras = sorted(p for p in ctx["extras"] if kind == "skill" and p.startswith(f"skills/{name}/"))
    return {"id": eid, "path": path.relative_to(root).as_posix(), "kind": kind, "title": title,
            "triggers": triggers_for(name, desc, extra) if kind in _TRIGGER_KINDS else [],
            "surfaces": surfaces_for(name), "stacks": stacks_for(name, ctx["rules_dirs"]),
            "token_estimate": len(text) // 4, "conflicts": sorted(set(_CONFLICT_RE.findall(text))),
            "upstream": {"path": up_path, "sha": hdr.group(2) if hdr else ctx["sha"], "extras": extras}}


def _pack(d: Path, root: Path, sha: str) -> dict:
    files = sorted(d.glob("*.md"))
    texts = [p.read_text(encoding="utf-8") for p in files]
    conflicts = set()
    for p, t in zip(files, texts):
        if p.name in ("coding-style.md", "patterns.md"):  # the two files the router line names
            conflicts |= set(_CONFLICT_RE.findall(t))
    return {"id": f"rules:{d.name}", "path": d.relative_to(root).as_posix() + "/", "kind": "rules-pack",
            "title": f"{d.name} rules pack ({len(files)} files)", "triggers": [], "surfaces": [],
            "stacks": [] if d.name == "common" else [d.name], "token_estimate": sum(len(t) // 4 for t in texts),
            "conflicts": sorted(conflicts), "upstream": {"path": f"rules/{d.name}", "sha": sha, "extras": []}}


def _load_json(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _catalogue_from_checkout(ecc: Path, cfg: dict) -> dict:
    spec = importlib.util.spec_from_file_location("vendor_library", ROOT / "scripts" / "vendor_library.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.catalogue(ecc, cfg)


def build(root: Path, ecc: Path | None = None) -> dict:
    lib = root / "library" / "ecc"
    upstream = _load_json(lib / "UPSTREAM.json")
    cfg = _load_json(lib / "VENDOR.json")
    sha = str(upstream.get("sha", ""))
    rules_root = lib / "rules"
    rules_dirs = sorted(p.name for p in rules_root.iterdir() if p.is_dir()) if rules_root.is_dir() else []
    ctx = {"sha": sha, "rules_dirs": rules_dirs,
           "extras": list(upstream.get("code_not_vendored") or cfg.get("skills_code_not_vendored") or []),
           "catalogue": _catalogue_from_checkout(ecc, cfg) if ecc else _load_json(lib / "catalogue.json")}
    entries: list[dict] = [_pack(rules_root / d, root, sha) for d in rules_dirs]
    plan: list[tuple[Path, str, str, str]] = []
    plan += [(p, "skill", f"skill:{p.parent.name}", p.parent.name) for p in sorted(lib.glob("skills/*/SKILL.md"))]
    for sub, kind in (("agents", "agent"), ("commands", "command"), ("guides", "guide"), ("docs", "doc")):
        plan += [(p, kind, f"{kind}:{p.stem}", p.stem) for p in sorted((lib / sub).glob("*.md"))]
    for p in sorted((lib / "digests").glob("*.md")):
        plan.append((p, "digest", f"digest:{p.stem}", p.stem))
    for p in sorted((lib / "examples").rglob("*.md")):
        rel = p.relative_to(lib / "examples").with_suffix("").as_posix().replace("/", "-")
        plan.append((p, "example", f"example:{rel}", p.stem))
    for path, kind, eid, name in plan:
        e = entry_for(path, kind, root, eid, name, ctx)
        if e:
            entries.append(e)
    entries.sort(key=lambda e: e["id"])
    up = {k: upstream.get(k, "") for k in ("repo", "sha", "commit_date")}
    return {"schema": 1, "generated_from": "library/ecc/UPSTREAM.json", "upstream": up, "count": len(entries),
            "entries": entries}


def render(index: dict) -> str:
    return json.dumps(index, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="build_library_index.py", description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--ecc", default=None)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not (root / "library" / "ecc").is_dir():
        print("library/ecc missing: run vendor_library.py")
        return 1
    index = build(root, Path(a.ecc) if a.ecc else None)
    text = render(index)
    target = root / "library" / "INDEX.json"
    if a.check:
        try:
            current = target.read_text(encoding="utf-8")
        except OSError:
            print("INDEX drift: library/INDEX.json missing (run build_library_index.py)")
            return 1
        if current == text:
            print(f"OK library/INDEX.json in sync ({index['count']} entries)")
            return 0
        try:
            old = {e.get("id"): e for e in json.loads(current).get("entries", [])}
        except (ValueError, AttributeError):
            old = {}
        new = {e["id"]: e for e in index["entries"]}
        diff = sorted(i for i in set(old) | set(new) if old.get(i) != new.get(i))
        print(f"INDEX drift: {len(diff)} entries differ" + (": " + ", ".join(map(str, diff[:10])) if diff else
                                                             " (formatting)"))
        return 1
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote library/INDEX.json ({index['count']} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

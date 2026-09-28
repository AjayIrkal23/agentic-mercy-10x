#!/usr/bin/env python3
"""add-db-mcp.py — add read-only Supabase / MongoDB MCP servers to THIS repo's .mcp.json.

  cd <repo> && python3 ~/.claude/scripts/add-db-mcp.py [--supabase] [--mongodb]
                                                       [--project-ref REF] [--dry-run]

Project scope only (never user scope). Source: ~/.claude/templates/mcp/db-readonly.mcp.json.
With no --supabase/--mongodb flag the servers are auto-detected from the repo
(supabase/ dir or @supabase/* dep; mongodb/mongoose/pymongo/motor/mongo-driver dep).
The Supabase project ref comes from --project-ref, else supabase/.temp/project-ref
(written by `supabase link`), else stays ${SUPABASE_PROJECT_REF}. Secrets are always
${ENV} references, never literals. Merges: other servers in .mcp.json are kept.
Refuses in $HOME, in ~/.claude, and outside a git repo. Asks nothing; prints what it wrote.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
TEMPLATE = HOME / ".claude" / "templates" / "mcp" / "db-readonly.mcp.json"
REF_RX = re.compile(r"^[a-z0-9]{20}$")
MONGO_DEPS = ("mongodb", "mongoose", "pymongo", "motor", "go.mongodb.org/mongo-driver")


def git_root() -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return Path(out).resolve() if out else None


def _near(root: Path, rel: str) -> list[Path]:
    """rel at the repo root and one directory down (monorepo / nested app)."""
    return [p for p in [root / rel, *(d / rel for d in root.iterdir() if d.is_dir()
                                      and not d.name.startswith(".") and d.name != "node_modules")]
            if p.exists()]


def _dep_text(root: Path) -> str:
    text = []
    for rel in ("package.json", "go.mod", "requirements.txt", "pyproject.toml"):
        for p in _near(root, rel):
            try:
                text.append(p.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
    return "\n".join(text)


def detect(root: Path) -> set[str]:
    deps, found = _dep_text(root), set()
    if _near(root, "supabase/config.toml") or "@supabase/" in deps:
        found.add("supabase")
    if any(re.search(rf'["\s/]{re.escape(d)}["\s@=<>~^]', deps) for d in MONGO_DEPS):
        found.add("mongodb")
    return found


def project_ref(root: Path, given: str | None) -> str | None:
    if given:
        return given
    for p in _near(root, "supabase/.temp/project-ref"):
        ref = p.read_text(encoding="utf-8", errors="ignore").strip()
        if REF_RX.match(ref):
            return ref
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--supabase", action="store_true")
    ap.add_argument("--mongodb", action="store_true")
    ap.add_argument("--project-ref")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    a = ap.parse_args()

    if a.project_ref and not REF_RX.match(a.project_ref):
        print(f"add-db-mcp: '{a.project_ref}' is not a Supabase project ref (20 lowercase chars)", file=sys.stderr)
        return 2
    root = git_root()
    if root is None:
        print("add-db-mcp: not inside a git repo — refusing (project scope only).", file=sys.stderr)
        return 2
    if root in (HOME.resolve(), (HOME / ".claude").resolve()):
        print(f"add-db-mcp: refusing to write into {root} (home / agent infra, not a project).", file=sys.stderr)
        return 2

    wanted = {n for n, on in (("supabase", a.supabase), ("mongodb", a.mongodb)) if on} or detect(root)
    if not wanted:
        print("add-db-mcp: no Supabase/MongoDB usage detected; pass --supabase and/or --mongodb.", file=sys.stderr)
        return 1

    servers = json.loads(TEMPLATE.read_text(encoding="utf-8"))["mcpServers"]
    ref = project_ref(root, a.project_ref)
    if "supabase" in wanted and ref:
        servers["supabase"]["args"] = [x.replace("${SUPABASE_PROJECT_REF}", ref)
                                       for x in servers["supabase"]["args"]]

    target = root / ".mcp.json"
    try:
        data = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except json.JSONDecodeError:
        print(f"add-db-mcp: {target} is not valid JSON — fix it first.", file=sys.stderr)
        return 2
    block = data.setdefault("mcpServers", {})
    for name in sorted(wanted):
        verb = "replaced" if name in block and block[name] != servers[name] else \
               "unchanged" if name in block else "added"
        block[name] = servers[name]
        print(f"{verb}: {name}")
    out = json.dumps(data, indent=2) + "\n"
    if not a.dry_run:
        target.write_text(out, encoding="utf-8")
    print(f"{'would write' if a.dry_run else 'wrote'} {target}:\n{out}")

    need = []
    if "supabase" in wanted:
        need.append("SUPABASE_ACCESS_TOKEN")
        if not ref:
            need.append("SUPABASE_PROJECT_REF (or re-run with --project-ref)")
    if "mongodb" in wanted:
        need.append("MDB_MCP_CONNECTION_STRING (dev/staging, read-only user)")
    print("export before launching claude: " + ", ".join(need))

    local = ((json.loads((HOME / ".claude.json").read_text(encoding="utf-8")).get("projects") or {})
             .get(str(root)) or {}).get("mcpServers") or {} if (HOME / ".claude.json").exists() else {}
    for name in sorted(wanted & set(local)):
        print(f"NOTE: local-scope '{name}' in ~/.claude.json overrides this .mcp.json entry "
              f"(and may not be read-only). To use the template: cd {root} && claude mcp remove {name} -s local")
    print("Claude Code asks to approve new .mcp.json servers on the next launch in this repo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""retention-report.py — READ-ONLY list of reclaimable disk space (audit 2026-10-05
J-07, J-08, J-13, G-10, G-15). It deletes nothing: it prints sizes, the reason and
the command the user can run. Automatic purges stay in state-cleanup.py; these
items need a human decision (indexes, transcripts, plugin versions).

Reports:
  plugins/cache/<mk>/<plugin>/<version>  not referenced by installed_plugins.json
  ~/.claude/graphify-out                  frozen duplicate graph (no writer)
  projects/<slug>                         newest transcript older than keep_days
  ~/.doc-index/local/<name>.json          recorded source_root no longer exists
  ~/.code-index/<name>.db                 recorded source_root no longer exists
  (projects/ dirs holding memory/ are never listed)

Usage: python3 hooks/tools/retention-report.py [--keep-days N]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import time
from pathlib import Path

_SRC_RE = re.compile(r'"source_root"\s*:\s*"((?:[^"\\]|\\.)*)"')
_DOC_SIDECARS = {"related", "summary", "terms", "duplicates", "boilerplate"}


def _size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _dead(root) -> bool:
    return not root or not os.path.isdir(root)


def _doc_root(manifest: Path):
    with manifest.open("rb") as f:  # source_root sits near the end of big manifests
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 65536))
        hits = _SRC_RE.findall(f.read().decode("utf-8", "replace"))
    return json.loads(f'"{hits[-1]}"') if hits else None


def _code_root(db: Path):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM meta WHERE key='source_root'").fetchone()
    finally:
        con.close()
    return row[0] if row else None


def report(claude: Path, docs: Path, code: Path, keep_days: int = 30) -> list:
    """[(bytes, path, reason, command)] — never modifies anything."""
    rows: list = []

    def add(path: Path, reason: str, cmd: str) -> None:
        try:
            rows.append((_size(path), path, reason, cmd))
        except OSError:
            pass

    cache = claude / "plugins" / "cache"
    try:
        installed = json.loads((claude / "plugins/installed_plugins.json").read_text(encoding="utf-8"))
        live = {os.path.realpath(e.get("installPath", "")) for v in installed.get("plugins", {}).values()
                for e in (v if isinstance(v, list) else [v])}
    except (OSError, ValueError, AttributeError):
        live = None  # unknown → report no plugin versions
    if live is not None and cache.is_dir():
        for ver in sorted(cache.glob("*/*/*")):
            if ver.is_dir() and not ver.parent.parent.name.startswith("temp_git_") \
                    and os.path.realpath(ver) not in live:
                add(ver, "plugin version not installed", f"rm -rf {shlex.quote(str(ver))}")

    graph = claude / "graphify-out"
    if graph.is_dir():
        add(graph, "frozen graph under ~/.claude (no writer)", f"rm -rf {shlex.quote(str(graph))}")

    cutoff = time.time() - keep_days * 86400
    for proj in sorted((claude / "projects").glob("*")):
        if not proj.is_dir() or (proj / "memory").exists():
            continue  # never suggest deleting a project's auto-memory
        transcripts = [f for f in proj.rglob("*.jsonl") if f.is_file()]
        if transcripts and max(f.stat().st_mtime for f in transcripts) < cutoff:
            add(proj, f"no transcript newer than {keep_days} d", f"rm -rf {shlex.quote(str(proj))}")

    for man in sorted(docs.glob("*.json")) if docs.is_dir() else []:
        name = man.name[:-5]
        if name.rsplit(".", 1)[-1] in _DOC_SIDECARS:
            continue  # <name>.related.json …, not a manifest (names may contain dots)
        try:
            root = _doc_root(man)
        except OSError:
            continue
        if root and _dead(root):
            add(man, f"doc index for missing root {root}",
                f"(MCP) mcp__jdocmunch__delete_index repo=local/{name}")

    for db in sorted(code.glob("*.db")) if code.is_dir() else []:
        try:
            root = _code_root(db)
        except sqlite3.Error:
            continue
        if root and _dead(root):
            add(db, f"code index for missing root {root}",
                f"rm -rf {shlex.quote(str(db))}* {shlex.quote(str(db)[:-3])}")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="read-only list of reclaimable disk space")
    home = Path.home()
    ap.add_argument("--claude-dir", default=os.environ.get("CLAUDE_CONFIG_DIR") or str(home / ".claude"))
    ap.add_argument("--doc-index", default=str(home / ".doc-index" / "local"))
    ap.add_argument("--code-index", default=str(home / ".code-index"))
    ap.add_argument("--keep-days", type=int, default=30)
    a = ap.parse_args(argv)
    rows = report(Path(a.claude_dir), Path(a.doc_index), Path(a.code_index), a.keep_days)
    total = sum(r[0] for r in rows)
    print(f"=== retention-report: {len(rows)} item(s), {total / 1e6:.1f} MB reclaimable (nothing deleted) ===")
    for size, path, reason, _ in sorted(rows, key=lambda r: -r[0]):
        print(f"  {size / 1e6:9.1f} MB  {path}  — {reason}")
    if rows:
        print("To reclaim, review then run:")
        for *_, cmd in sorted(rows, key=lambda r: -r[0]):
            print(f"  {cmd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

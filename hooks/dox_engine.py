#!/usr/bin/env python3
"""dox_engine.py — shared scaffolding engine for the dox CLAUDE.md tree.

Single source of truth for *creating* and *syncing* the dox documentation tree.
Used by:
  - dox-tree-guard.py   (SessionStart full sweep + prompt-path root stub)
  - dox-child-scaffold.py (PostToolUse: a write happened in dir X -> document X)
  - the `dox_engine.py sweep <repo>` CLI (manual / agent-driven full sweep)

What it guarantees (the user contract):
  * EVERY non-skipped directory in a repo carries a local `CLAUDE.md` (the real
    doc) AND an `AGENTS.md` (a 1-line cross-tool pointer). `documentAllDirs` (default
    true) drops the old ">=3 code files" significance gate so coverage is end-to-end.
  * The ROOT `CLAUDE.md` carries an auto-synced index block listing every child doc,
    nested by depth. The block lives between `<!-- dox:index:start -->` and
    `<!-- dox:index:end -->` markers and is rebuilt from what is actually on disk.
  * The ROOT `AGENTS.md` points at that index.

Invariants:
  * Idempotent — a second sweep with no structural change writes nothing.
  * Never clobbers a hand-written doc (only fills the auto-managed index block, and
    only ever CREATES a missing child; existing files are left untouched).
  * Pure stdlib, fails soft (raises only in the CLI; library calls swallow IO errors).

Python 3.8+ stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
ROOT_DOC = "CLAUDE.md"
POINTER_DOC = "AGENTS.md"

ROOT_MARKER = "<!-- dox:root v1 -->"
CHILD_MARKER = "<!-- dox:child v1 -->"
POINTER_MARKER = "<!-- dox:pointer -->"

INDEX_START = "<!-- dox:index:start -->"
INDEX_END = "<!-- dox:index:end -->"
LEGACY_INDEX_PREFIX = "<!-- dox:index"  # old single-line marker (pre-sync)

REFS_DIR = Path.home() / ".claude" / "skills" / "dox-doc-tree" / "references"

DEFAULTS = {
    "enabled": True,
    "exemptRepos": [],
    # New (end-to-end) behaviour ------------------------------------------------
    "documentAllDirs": True,    # document EVERY non-skipped dir, not just "significant" ones
    "autoCreateChildren": True,  # session sweep auto-creates missing child docs
    "syncRootIndex": True,       # keep the root CLAUDE.md index block in sync
    "sweepMaxDepth": 12,         # how deep to descend (root = depth 0)
    "maxSweepDirs": 500,         # safety cap on how many dirs one sweep documents
    # Absolute path prefixes (~ ok) that NEVER get dox docs, at any depth.
    # Used for roster-scanned dirs (~/.claude/{agents,commands,skills,plugins})
    # where stray CLAUDE.md/AGENTS.md files pollute Claude Code's skill/agent
    # rosters as phantom entries. Configure in dox-tree-guard.config.json.
    "skipPaths": [],
    # Legacy fallback (used only when documentAllDirs is false) ------------------
    "significantDirThreshold": 3,
    "rootDoxMarker": ROOT_MARKER,
    "codeExtensions": [
        ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
        ".py", ".go", ".rs", ".java", ".kt",
        ".rb", ".php", ".c", ".cpp", ".h", ".hpp", ".swift", ".scala",
    ],
}

# Directories that never get a dox doc (build artifacts, VCS, deps, caches).
SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", "out",
    "coverage", "testdata", ".venv", "venv", "__pycache__", ".claude",
    "target", "bin", "obj", ".turbo", ".cache", "graphify-out", ".planning",
    ".code-index", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".idea",
    ".vscode", ".gradle", ".dart_tool", "Pods", ".terraform",
    "REFFER_ONLY_UDP_CODE_OLD",
}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_cfg(config_path: "str | Path | None" = None) -> dict:
    cfg = dict(DEFAULTS)
    if config_path:
        try:
            p = Path(config_path)
            if p.is_file():
                user = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(user, dict):
                    cfg.update(user)
        except Exception:
            pass
    return cfg


def _exts(cfg: dict) -> "set[str]":
    return {e.lower() for e in (cfg.get("codeExtensions") or DEFAULTS["codeExtensions"])}


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def _is_skip_dir(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def _skip_paths(cfg: dict) -> "list[Path]":
    """Resolve cfg['skipPaths'] (absolute, ~-expandable) to real Paths."""
    out: "list[Path]" = []
    for raw in (cfg.get("skipPaths") or []):
        try:
            out.append(Path(os.path.expanduser(str(raw))).resolve())
        except Exception:
            continue
    return out


def _under_skip_path(path: Path, skips: "list[Path]") -> bool:
    """True if `path` IS one of the skip paths or lives anywhere beneath one."""
    if not skips:
        return False
    try:
        rp = path.resolve()
    except OSError:
        return False
    return any(rp == s or s in rp.parents for s in skips)


def _count_code_files(dirpath: str, filenames: "list[str]", exts: "set[str]") -> int:
    return sum(1 for f in filenames if os.path.splitext(f)[1].lower() in exts)


def collect(root: Path, cfg: dict) -> dict:
    """Walk the repo -> the set of directories that should carry a local CLAUDE.md.

    Returns: {
      "dirs":        [rel_posix, ...]  documentable dirs, sorted (root excluded),
      "missing":     [rel_posix, ...]  documentable dirs with NO CLAUDE.md yet,
      "has_code":    bool,             repo contains >=1 code file,
      "truncated":   bool,             hit maxSweepDirs / depth cap,
    }
    """
    root = root.resolve()
    exts = _exts(cfg)
    document_all = bool(cfg.get("documentAllDirs", True))
    threshold = int(cfg.get("significantDirThreshold") or 3)
    max_depth = int(cfg.get("sweepMaxDepth") or 12)
    max_dirs = int(cfg.get("maxSweepDirs") or 500)
    skips = _skip_paths(cfg)

    dirs: "list[str]" = []
    missing: "list[str]" = []
    has_code = False
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).resolve().relative_to(root)
        depth = len(rel.parts)
        # prune
        dirnames[:] = sorted(d for d in dirnames if not _is_skip_dir(d))
        if skips:
            dirnames[:] = [d for d in dirnames
                           if not _under_skip_path(Path(dirpath) / d, skips)]
        if depth >= max_depth:
            dirnames[:] = []

        code_here = _count_code_files(dirpath, filenames, exts)
        if code_here:
            has_code = True
        if depth == 0:
            continue  # repo root is the dox ROOT, not a child

        documentable = document_all or code_here >= threshold
        if not documentable:
            continue

        rel_posix = rel.as_posix()
        if len(dirs) >= max_dirs:
            truncated = True
            dirnames[:] = []
            continue
        dirs.append(rel_posix)
        if not (Path(dirpath) / ROOT_DOC).is_file():
            missing.append(rel_posix)

    return {
        "dirs": sorted(dirs),
        "missing": sorted(missing),
        "has_code": has_code,
        "truncated": truncated,
    }


def fingerprint(collected: dict) -> str:
    parts = [f"d:{d}" for d in collected.get("dirs", [])]
    return hashlib.sha1("|".join(sorted(parts)).encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Document bodies
# --------------------------------------------------------------------------- #
def _read_template(name: str, fallback: str) -> str:
    try:
        return (REFS_DIR / name).read_text(encoding="utf-8")
    except Exception:
        return fallback


_FALLBACK_CHILD = (
    "# `<dir-path>/` — local rules (dox)\n\n"
    "> Local doc for this directory only. Read after the root `CLAUDE.md`. Update\n"
    "> this file whenever you add, remove, or rename files here, or change a local\n"
    "> convention.\n\n"
    "## What lives here\n\nTODO: the responsibility of this directory.\n\n"
    "## Local conventions\n\n- TODO\n\n"
    "## Key files\n\n| File | Role |\n|------|------|\n| TODO | TODO |\n\n"
    "## Up / down\n\n- Parent: [`../CLAUDE.md`](../CLAUDE.md)\n"
)
_FALLBACK_POINTER = (
    f"{POINTER_MARKER}\n"
    "See `CLAUDE.md` in this directory for agent instructions (dox documentation tree).\n"
    "This `AGENTS.md` is a cross-tool pointer; the authoritative local rules live in `CLAUDE.md`.\n"
)


def child_doc_text(rel_posix: str, cfg: dict) -> str:
    body = _read_template("child-template.md", _FALLBACK_CHILD).replace("<dir-path>", rel_posix)
    if CHILD_MARKER in body[:120]:
        return body
    return f"{CHILD_MARKER}\n{body}"


def pointer_text(cfg: dict) -> str:
    return _read_template("agents-pointer.md", _FALLBACK_POINTER)


def root_stub_text(root_name: str, cfg: dict) -> str:
    marker = cfg.get("rootDoxMarker") or ROOT_MARKER
    return (
        f"{marker}\n"
        f"# {root_name} — Agent Guide (dox root)\n\n"
        "> Auto-stubbed by dox. Flesh this out via the `dox-doc-tree` skill BEFORE\n"
        "> code work. Root of the dox documentation tree: project-wide rules + an\n"
        "> auto-synced index linking to a `CLAUDE.md` in every directory.\n\n"
        "## What this is\n\nTODO: one-paragraph overview of the project.\n\n"
        "## Non-negotiables (project-wide)\n\nTODO: rules that apply everywhere.\n\n"
        "## dox index (children)\n\n"
        f"{INDEX_START}\n"
        "<!-- dox auto-syncs this block from the tree on disk; edit directories, not these lines -->\n"
        f"{INDEX_END}\n\n"
        "## Related docs (link, don't duplicate)\n\n"
        "- Working decisions & known pitfalls -> `CODEX.md`\n"
        "- Repo docs -> `frontend_docs/` / `server_docs/` / `docs/`\n"
        "- Symbol map / graph -> jcodemunch / graphify\n"
    )


def root_pointer_text(cfg: dict) -> str:
    return (
        f"{POINTER_MARKER}\n"
        "See `CLAUDE.md` in this directory for the project's agent instructions "
        "(dox documentation tree root).\n"
        "The full per-directory index is auto-synced into `CLAUDE.md` under "
        "\"dox index (children)\".\n"
    )


# --------------------------------------------------------------------------- #
# Index rendering / sync
# --------------------------------------------------------------------------- #
def render_index(dirs: "list[str]") -> str:
    """Nested markdown list of every documented dir, indented by depth."""
    lines = [
        INDEX_START,
        "<!-- dox auto-syncs this block from the tree on disk; edit directories, not these lines -->",
    ]
    if not dirs:
        lines.append("_No child directories documented yet._")
    else:
        for rel in sorted(dirs):
            depth = rel.count("/")
            indent = "  " * depth
            lines.append(f"{indent}- [`{rel}/`]({rel}/{ROOT_DOC})")
    lines.append(INDEX_END)
    return "\n".join(lines)


def _norm_post(post: str) -> str:
    """Guarantee a blank line between the index block and a following heading."""
    if post.startswith("\n## "):
        return "\n" + post  # -> blank line before the heading
    return post


def _splice_index(text: str, block: str) -> str:
    """Replace (or append) the auto-managed index block inside a root doc."""
    # 1) Paired markers already present -> replace between them.
    if INDEX_START in text and INDEX_END in text:
        pre = text.split(INDEX_START, 1)[0]
        post = text.split(INDEX_END, 1)[1]
        return f"{pre}{block}{post}"
    # 2) Only the start marker -> replace from it to the next heading / EOF.
    if INDEX_START in text:
        pre = text.split(INDEX_START, 1)[0]
        rest = text.split(INDEX_START, 1)[1]
        nxt = rest.find("\n## ")
        post = _norm_post(rest[nxt:]) if nxt != -1 else "\n"
        return f"{pre}{block}{post}"
    # 3) Legacy single-line marker (pre-sync stubs) -> replace its block.
    if LEGACY_INDEX_PREFIX in text:
        idx = text.find(LEGACY_INDEX_PREFIX)
        pre = text[:idx]
        rest = text[idx:]
        nxt = rest.find("\n## ")
        post = _norm_post(rest[nxt:]) if nxt != -1 else "\n"
        return f"{pre}{block}{post}"
    # 4) Hand-written root, no index at all -> append a managed section once.
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}\n## dox index (children)\n\n{block}\n"


# --------------------------------------------------------------------------- #
# Filesystem writers (idempotent, never clobber)
# --------------------------------------------------------------------------- #
def _write_if_absent(path: Path, content: str) -> bool:
    try:
        if path.exists():
            return False
        path.write_text(content, encoding="utf-8")
        return True
    except OSError:
        return False


def ensure_root(root: Path, cfg: dict) -> dict:
    """Stub the root CLAUDE.md (+ AGENTS.md pointer) if missing. Never clobbers."""
    root_doc = root / ROOT_DOC
    created = False
    if not root_doc.exists():
        created = _write_if_absent(root_doc, root_stub_text(root.name, cfg))
    # Root pointer: only create if absent (don't overwrite a hand-written one).
    _write_if_absent(root / POINTER_DOC, root_pointer_text(cfg))
    marker = cfg.get("rootDoxMarker") or ROOT_MARKER
    try:
        dox_managed = marker in root_doc.read_text(encoding="utf-8")[:400]
    except Exception:
        dox_managed = created
    return {"created": created, "dox_managed": dox_managed}


def ensure_child(root: Path, rel_posix: str, cfg: dict) -> "list[str]":
    """Create CLAUDE.md + AGENTS.md in one directory. Returns created basenames."""
    d = (root / rel_posix)
    made: "list[str]" = []
    try:
        if not d.is_dir():
            return made
    except OSError:
        return made
    if _write_if_absent(d / ROOT_DOC, child_doc_text(rel_posix, cfg)):
        made.append(ROOT_DOC)
    if _write_if_absent(d / POINTER_DOC, pointer_text(cfg)):
        made.append(POINTER_DOC)
    return made


def sync_root_index(root: Path, dirs: "list[str]", cfg: dict) -> bool:
    """Rewrite the root index block from `dirs`. Returns True if the file changed."""
    if not cfg.get("syncRootIndex", True):
        return False
    root_doc = root / ROOT_DOC
    try:
        old = root_doc.read_text(encoding="utf-8")
    except OSError:
        return False
    block = render_index(dirs)
    new = _splice_index(old, block)
    if new == old:
        return False
    try:
        root_doc.write_text(new, encoding="utf-8")
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def sweep(root: Path, cfg: dict, create: bool = True) -> dict:
    """Full end-to-end pass: root + every dir gets docs, root index synced.

    create=False -> dry run (report only; index reflects existing docs).
    """
    root = root.resolve()
    summary = {
        "root_created": False,
        "documented_dirs": [],   # dirs created this pass
        "created_files": 0,
        "index_synced": False,
        "total_dirs": 0,
        "truncated": False,
    }

    rootinfo = ensure_root(root, cfg) if create else {"created": False}
    summary["root_created"] = bool(rootinfo.get("created"))

    collected = collect(root, cfg)
    summary["total_dirs"] = len(collected["dirs"])
    summary["truncated"] = collected["truncated"]

    if create and cfg.get("autoCreateChildren", True):
        for rel in collected["missing"]:
            made = ensure_child(root, rel, cfg)
            if made:
                summary["documented_dirs"].append(rel)
                summary["created_files"] += len(made)
        # re-collect so the index reflects freshly-created docs
        collected = collect(root, cfg)
        summary["total_dirs"] = len(collected["dirs"])

    # Index reflects dirs that actually have a CLAUDE.md on disk.
    indexed = [d for d in collected["dirs"] if (root / d / ROOT_DOC).is_file()]
    summary["index_synced"] = sync_root_index(root, indexed, cfg)
    summary["fingerprint"] = fingerprint(collected)
    summary["collected"] = collected
    return summary


def ensure_dir_documented(root: Path, target_dir: Path, cfg: dict) -> "list[str]":
    """Document a single directory (used by the PostToolUse child-scaffold path),
    then re-sync the root index. Returns created basenames for `target_dir`."""
    root = root.resolve()
    try:
        rel = target_dir.resolve().relative_to(root).as_posix()
    except Exception:
        return []
    if not rel or rel == ".":
        return []
    if any(_is_skip_dir(part) for part in rel.split("/")):
        return []
    if _under_skip_path(target_dir, _skip_paths(cfg)):
        return []
    made = ensure_child(root, rel, cfg)
    if made and cfg.get("syncRootIndex", True):
        collected = collect(root, cfg)
        indexed = [d for d in collected["dirs"] if (root / d / ROOT_DOC).is_file()]
        sync_root_index(root, indexed, cfg)
    return made


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _git_root(start: Path) -> "Path | None":
    cur = start if start.is_dir() else start.parent
    for _ in range(30):
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _cli(argv: "list[str]") -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(
            "dox_engine — scaffold & sync the CLAUDE.md/AGENTS.md tree\n\n"
            "Usage:\n"
            "  dox_engine.py sweep [path]   create docs in every dir + sync root index\n"
            "  dox_engine.py plan  [path]   dry run: list dirs that WOULD be documented\n"
        )
        return 0

    cmd = argv[0]
    target = Path(argv[1]).resolve() if len(argv) > 1 else Path(os.getcwd())
    root = _git_root(target) or target
    cfg = load_cfg(Path(__file__).resolve().parent / "dox-tree-guard.config.json")

    if cmd == "plan":
        collected = collect(root, cfg)
        print(f"repo: {root}")
        print(f"documentable dirs: {len(collected['dirs'])} "
              f"(missing docs: {len(collected['missing'])}, truncated: {collected['truncated']})")
        for d in collected["missing"]:
            print(f"  + {d}/CLAUDE.md  (+ AGENTS.md)")
        return 0

    if cmd == "sweep":
        s = sweep(root, cfg, create=True)
        print(f"repo: {root}")
        if s["root_created"]:
            print("  + root CLAUDE.md stubbed")
        print(f"  documented {len(s['documented_dirs'])} new dir(s), "
              f"{s['created_files']} file(s) created")
        print(f"  root index {'synced' if s['index_synced'] else 'unchanged'} "
              f"({s['total_dirs']} dirs total)")
        if s["truncated"]:
            print(f"  ⚠ truncated at maxSweepDirs={cfg.get('maxSweepDirs')}; "
                  "raise the cap to cover the rest")
        return 0

    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))

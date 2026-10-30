"""blast_radius.py — the ONE importer counter and the sensitive-target classifier behind
gateguard-write-gate.py (Write/Edit) and bash-write-gate.py (shell redirects).

Importers: a pure Python walk (Windows has no grep, and grep's `path:line:text` cannot be split on
`:` after a drive letter), quoted-specifier regexes for TS/JS (a comment or a sibling stem
`WidgetGroup` is no importer), comment lines never count, a wall-clock budget (over budget = [] =
fail-open). Sensitivity: path-string only (no filesystem), segment based, so `authors.md` and
`monkey.ts` are not matches and a path under a docs segment is never sensitive. Stdlib only.
"""
from __future__ import annotations

import os
import re
import time

THRESHOLD = 5  # files importing the target -> the write asks
EXCLUDE_DIRS = frozenset({"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv",
                          ".next", ".turbo", "coverage", "target", ".state"})
SHORT_STEMS = frozenset({"app", "main", "index", "types", "routes", "gorm", "db", "api", "lib", "util"})
DEFAULT_BUDGET_S = 5.0  # stays under gateguard's 8 s dispatch link timeout
_COMMENT_HEADS = ("//", "/*", "*", "#")


def project_root(file_path: str) -> str:
    """HOME-guarded git root (lib.code_files); else the file's own dir, so a ~-rooted write never
    walks the whole home tree (A03-B17)."""
    try:
        from lib.code_files import git_root, is_home
        root = git_root(file_path)
        if root is not None and not is_home(root):
            return str(root)
    except Exception:  # noqa: BLE001 - fail open to the narrowest root
        pass
    return os.path.dirname(os.path.abspath(file_path))


def import_regex_for(file_path: str) -> tuple:
    """(compiled per-line import regex, file suffixes to scan) for this target."""
    basename = os.path.basename(file_path)
    s = re.escape(os.path.splitext(basename)[0])
    ext = os.path.splitext(basename)[1].lower()
    if ext == ".go":
        return re.compile(f'".*/{s}"|package {s}'), (".go",)
    if ext == ".py":
        # `from [pkg.|.|..x.]stem import`, or an `import` / `from X import` line naming stem as a whole
        # word after `import`.
        w = r"[^A-Za-z0-9_]"
        return re.compile(rf"^\s*(from\s+([.A-Za-z0-9_]*[.])?{s}\s+import"
                          rf"|(from\s+[.A-Za-z0-9_]+\s+)?import\s(.*{w})?{s}({w}|$))"), (".py",)
    # A quoted module specifier ending in /<stem> (optional extension or /index). Covers `from '…'`,
    # `require('…')`, `import('…')`, `export … from '…'` (B1-08).
    spec = rf"""['"][^'"\n]*/{s}(?:\.[A-Za-z]+|/index(?:\.[A-Za-z]+)?)?['"]"""
    return (re.compile(rf"""(?:\bfrom\s*|\brequire\s*\(\s*|\bimport\s*\(\s*|^\s*import\s+){spec}"""),
            (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"))


def importers(file_path: str, root: str | None = None, budget_s: float = DEFAULT_BUDGET_S) -> list:
    """[{path, lines: [{lineno, text}]}] for every file under ``root`` (default: the project root)
    that imports ``file_path``. Short or common stems are never scanned; over budget -> []."""
    stem = os.path.splitext(os.path.basename(file_path))[0]
    if not stem or len(stem) < 6 or stem.lower() in SHORT_STEMS:
        return []
    search_root = root or project_root(file_path)
    rx, suffixes = import_regex_for(file_path)
    self_abs = os.path.abspath(file_path)
    deadline = time.monotonic() + budget_s
    by_file: dict = {}
    for dirpath, dirnames, filenames in os.walk(search_root):
        if time.monotonic() >= deadline:
            return []
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for name in filenames:
            if not name.endswith(suffixes):
                continue
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == self_abs:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    hits = [{"lineno": i, "text": line.rstrip("\r\n")}
                            for i, line in enumerate(fh, 1)
                            if not line.lstrip().startswith(_COMMENT_HEADS) and rx.search(line)]
            except OSError:
                continue
            if hits:
                by_file[path] = hits
    return [{"path": p, "lines": lines} for p, lines in sorted(by_file.items())]


def count(file_path: str, root: str | None = None, budget_s: float = DEFAULT_BUDGET_S) -> int:
    return len(importers(file_path, root, budget_s))


# --- sensitive / secret targets --------------------------------------------------------------------
_SENSITIVE_SEG = frozenset({"auth", "authn", "authz", "security", "payment", "payments", "billing",
                            "migration", "migrations"})
_SECRET_SEG = frozenset({"secret", "secrets", "credential", "credentials", "key", "keys"})
_SECRET_FILE = re.compile(r"^\.env(?:$|\.(?!example$|sample$|template$|test$|dist$))"
                          r"|^id_(?:rsa|ed25519|ecdsa|dsa)(?:\.pub)?$"
                          r"|\.(?:pem|key|p12|pfx|jks|keystore)$|^(?:secrets?|credentials?)(?:\.|$)", re.IGNORECASE)
_DOC_SEG = frozenset({"docs", "doc", "server_docs", "frontend_docs"})
_WORKFLOWS = "/.github/workflows/"


def _classify(path: str) -> tuple:
    """(class, label): class 'secret' | 'sensitive' | None; label = what matched."""
    p = str(path).replace("\\", "/").lower()
    segs = [s for s in p.split("/") if s]
    if not segs:
        return None, ""
    base, dirs = segs[-1], segs[:-1]
    if any(d in _DOC_SEG for d in dirs):
        return None, ""
    m = _SECRET_FILE.search(base)
    if m:
        return "secret", m.group(0).rstrip(".")
    for d in dirs:
        if d in _SECRET_SEG:
            return "secret", d + "/"
    for d in dirs:
        if d in _SENSITIVE_SEG:
            return "sensitive", d + "/"
    if base.startswith("dockerfile") or "dockerfile" in re.split(r"[._-]", base):
        return "sensitive", "Dockerfile"
    if _WORKFLOWS in "/" + "/".join(dirs) + "/":
        return "sensitive", ".github/workflows/"
    return None, ""


def sensitivity(path: str) -> str | None:
    """'secret' (asks even with .blast-bypass), 'sensitive' (asks unless bypassed) or None. Give it a
    repo-relative path: an ancestor dir named `auth` or `keys` above the repo is not the file's role."""
    return _classify(path)[0]


def sensitivity_label(path: str) -> str:
    """The matched segment or suffix (`auth/`, `.env`, `Dockerfile`) for the ask text; '' when none."""
    return _classify(path)[1]


__all__ = ["THRESHOLD", "EXCLUDE_DIRS", "SHORT_STEMS", "DEFAULT_BUDGET_S", "project_root", "import_regex_for",
           "importers", "count", "sensitivity", "sensitivity_label"]

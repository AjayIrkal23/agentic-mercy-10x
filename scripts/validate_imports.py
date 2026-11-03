#!/usr/bin/env python3
"""validate_imports.py — public-repo hygiene for vendored/imported text (grep gate G7).

Classes: U unicode tags/bidi/zero-width, P personal absolute paths, V unpinned npx/@latest,
W GitHub Actions unsafe patterns (YAML only), S secret patterns, M machine data (RFC1918,
terms from scripts/grep_gates.machine_terms.json, ptyxis-spawn), E unreadable file.
At most one finding per (file, line, class). Files carrying a vendored-upstream header
(``<!-- ecc:<path>@<sha> -->``, written by vendor_library.py) skip the four prose-level rules
(``_VENDORED_SKIP``): upstream example subnets (homelab/VLAN skills), ``@latest`` discussed as an
anti-pattern, and ``password = "..."`` bad-practice examples are upstream's public text, not this
machine's data. Unicode, personal paths, workflow, token-shaped secrets and machine terms still apply.
Allowlist: ``_ALLOW`` below (or ``--allowlist FILE``, JSON ``{"allow": [...]}``) drops findings by path glob
(relative to ``--root``, default cwd; ``*`` spans directories) and rule name (fnmatch, so ``unicode-*`` works);
every entry carries a ``why``. ``--no-allowlist`` shows everything it hides. Gitignored ``.claude/`` sidecars
and ``.state/`` hook state (its breadcrumbs hold the workspace path) are never scanned; inside a git work
tree a directory walk also skips every gitignored file (``skills/synced/``, ``hooks/.telemetry/``) unless
``--no-gitignore``.
Exit 0 clean, 1 findings, 2 usage error (a path that does not exist).
Usage: validate_imports.py [--json] [--class U,P,...] [--terms FILE] [--max-bytes N]
                           [--allowlist FILE | --no-allowlist] [--root DIR] PATH...
Adopted from ECC's check-unicode-safety, validate-no-personal-paths, validate-workflow-security,
build-pi-core's path sanitiser and the security guide's sanitisation chapter (one Python gate).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from fnmatch import fnmatchcase
from pathlib import Path

ALL = frozenset("UPVWSM")
_DEFAULT_TERMS = Path(__file__).with_name("grep_gates.machine_terms.json")
# G7 suppressions for the go-live run over library skills agents hooks docs (paths relative to the repo root).
# A new entry needs a reason a reviewer can check; `*` as a rule only for docs/archive.
_ALLOW = (
    {"path": "skills/*", "rules": ["at-latest", "npx-unpinned"],
     "why": "upstream-locked skill text (R10 hash-clean) quotes unpinned npx installs; pinning breaks the hash"},
    {"path": "hooks/skills-sources.json", "rules": ["at-latest", "npx-unpinned"],
     "why": "vendor manifest records upstream install lines verbatim (find/replace patches)"},
    {"path": "docs/archive/*", "rules": ["at-latest", "npx-unpinned"],
     "why": "2026-07 audits quote the skills and MCP launch lines they audited"},
    {"path": "hooks/tests/*", "rules": ["ptyxis-spawn", "rfc1918", "assignment"],
     "why": "OOM-guard fixtures name the scope unit; test_instincts feeds 10.0.0.5 to the private-address block; "
            "scrubber and doc-enforcer tests hold password-assignment inputs"},
    {"path": "hooks/lib/platform.py", "rules": ["ptyxis-spawn"], "why": "cgroup_of docstring names the unit it parses"},
    {"path": "docs/OOM-GUARD.md", "rules": ["ptyxis-spawn"], "why": "design doc of the OOM guard"},
    {"path": "hooks/tools/instincts.py", "rules": ["unicode-feff"], "why": "deliberate BOM strip (lstrip of U+FEFF)"},
    {"path": "skills/img2threejs/integrations/vision/uv.lock", "rules": ["rfc1918"],
     "why": "a PyPI version string (10.4.0.35) shaped like a private address"},
    {"path": "skills/img2threejs/integrations/glb_character_pipeline/node/capture-character.mjs",
     "rules": ["users-path"], "why": "upstream author's macOS path in a comment of a locked skill"},
    {"path": "skills/higgsfield-websites/references/security.md", "rules": ["assignment"],
     "why": "bad-practice example (hard-coded API_KEY) in a security guide"},
    {"path": "skills/hallmark/references/brand-truth.md", "rules": ["rfc1918"],
     "why": "the fetch-safety rule lists the private ranges it refuses (SSRF guard), not an address in use"},
    {"path": "skills/hallmark/scripts/sloplint.mjs", "rules": ["unicode-200d"],
     "why": "emoji-as-icon detector: the regex has to match the zero-width joiner inside emoji sequences"},
    {"path": "skills/ui-ux-pro-max/data/stacks/*.csv", "rules": ["windows-user-path", "users-path"],
     "why": "UX rule rows quote hard-coded user paths as the anti-pattern to avoid"},
)

_U_RE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿]|[\U000e0000-\U000e007f]")
_PLACE = r"(?!(?:\.\.\.|user|username)/)(?!<)"
_HOME_RE = re.compile("/home/" + _PLACE + r"[A-Za-z0-9._-]+/")
_USERS_RE = re.compile("/Users/" + _PLACE + r"[A-Za-z0-9._-]+/")
_WIN_RE = re.compile("C:" + r"\\+Users\\+(?!<)[A-Za-z0-9._-]+")  # never spell the pattern literally
_NPX_RE = re.compile(r"\bnpx\s+(?:-y|--yes)\s+((?:@[\w.-]+/)?[\w.-]+)(?!@)(?=\s|$|[`'\")])")
_LATEST_RE = re.compile(r"@latest\b")
_RFC1918_RE = re.compile(r"\b(?:10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b")
_SECRET_RES = [(n, re.compile(p)) for n, p in [
    ("aws-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b|\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    ("slack", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ("openai", r"\bsk-(?!ant-)[A-Za-z0-9]{20,}\b"),
    ("anthropic", r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    ("google", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    ("private-key", r"-----BEGIN (?:RSA |EC |OPENSSH |PGP |DSA )?PRIVATE KEY-----"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ("assignment", r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b"
                   r"\s*[:=]\s*['\"]([^'\"]{8,})['\"]"),
]]
_PLACEHOLDER_RE = re.compile(r"^(<.*>|\$\{?\w+\}?|\*+|x{4,}|your[-_ ].*|example.*|changeme.*|redacted.*|placeholder.*)$",
                             re.I)
_WF_TARGET_RE = re.compile(r"\bpull_request_target\b")
_WF_HEAD_REF_RE = re.compile(r"ref:\s*\$\{\{\s*github\.event\.pull_request\.head\.(?:sha|ref)\s*\}\}")
_WF_INJECT_RE = re.compile(r"\$\{\{\s*github\.event\.(?:issue|comment|pull_request|review|discussion)\."
                           r"(?:title|body|head_ref)[^}]*\}\}")
_WF_RUN_RE = re.compile(r"^(\s*(?:-\s+)?)run:(.*)$")
_VENDORED_RE = re.compile(r"^<!-- ecc:[^\s@]+@[0-9a-f]{40} -->$", re.M)
_VENDORED_SKIP = frozenset({"rfc1918", "npx-unpinned", "at-latest", "assignment"})
_EXCLUDE_PARTS = {".git", "node_modules", "__pycache__", ".cache", ".pytest_cache", "attic", ".claude", ".state",
                  "synced", ".telemetry"}
RESPECT_GITIGNORE = True  # --no-gitignore turns it off (scan every file under a dir argument)
_BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".tgz", ".woff", ".woff2",
                  ".ttf", ".ico", ".mp4", ".mp3", ".pyc"}


def _git_visible(base: Path) -> set[Path] | None:
    """Tracked + untracked-not-ignored files under base, or None when base is not in a git work tree."""
    import subprocess  # noqa: PLC0415
    try:
        top = subprocess.run(["git", "-C", str(base), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if top.returncode != 0:
            return None
        ls = subprocess.run(["git", "-C", str(base), "ls-files", "-z", "--cached", "--others", "--exclude-standard",
                             "--full-name", "--", "."], capture_output=True, timeout=20)
        if ls.returncode != 0:
            return None
        root = Path(top.stdout.strip())
        return {(root / p).resolve() for p in ls.stdout.decode("utf-8", "replace").split("\0") if p}
    except (OSError, subprocess.SubprocessError):
        return None


def iter_files(paths, max_bytes: int = 2_000_000):
    """Regular text files under each path (a file argument yields itself), sorted. A directory walk
    skips gitignored files when the directory is inside a git work tree (RESPECT_GITIGNORE)."""
    out: list[Path] = []
    for base in paths:
        base = Path(base)
        cands = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        vis = _git_visible(base) if (RESPECT_GITIGNORE and not base.is_file()) else None
        if vis is not None:
            cands = [p for p in cands if p.resolve() in vis]
        for p in cands:
            rel_parts = p.relative_to(base).parts if p != base else ()
            if any(part in _EXCLUDE_PARTS for part in rel_parts) or p.suffix.lower() in _BINARY_SUFFIX:
                continue
            try:
                if p.stat().st_size > max_bytes:
                    continue
                with p.open("rb") as fh:
                    if b"\0" in fh.read(8192):
                        continue
            except OSError:
                pass  # unreadable: scan() reports it as class E
            out.append(p)
    return sorted(set(out))


def load_terms(path: Path | None = None) -> list[str]:
    """Machine terms: {"terms": [...]} or a bare list; lowercased, >= 4 chars; absent/invalid -> []."""
    src = Path(path) if path else _DEFAULT_TERMS
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    terms = data.get("terms", []) if isinstance(data, dict) else data
    if not isinstance(terms, list):
        return []
    return [t.strip().lower() for t in terms if isinstance(t, str) and len(t.strip()) >= 4]


def load_allowlist(path: Path | None = None) -> list[dict]:
    """Entries {"path": glob, "rules": [name | pattern], "why": str}: the built-in ``_ALLOW`` when path is None,
    else {"allow": [...]} or a bare list from the file; absent/invalid file -> [] (never an error)."""
    if path is None:
        entries = [dict(e) for e in _ALLOW]
    else:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        entries = data.get("allow", []) if isinstance(data, dict) else data
        if not isinstance(entries, list):
            return []
    return [e for e in entries if isinstance(e, dict) and isinstance(e.get("path"), str)
            and isinstance(e.get("rules"), list)]


def _allowed(rel: str, rule: str, allow) -> bool:
    """fnmatch semantics: `*` also matches `/`, so `skills/*` covers the whole tree."""
    rel = rel.replace("\\", "/")
    return any(fnmatchcase(rel, e["path"]) and any(fnmatchcase(rule, r) for r in e["rules"]) for e in allow)


def _root_rel(file: str, root: Path) -> str:
    p = Path(file)
    p = p if p.is_absolute() else Path.cwd() / p
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file


def _drop_allowed(found: list[dict], allow, root) -> list[dict]:
    if not allow:
        return found
    root = Path(root) if root else Path.cwd()
    return [f for f in found if not _allowed(_root_rel(f["file"], root), f["rule"], allow)]


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def _cut(s: str) -> str:
    s = s.strip()
    return s if len(s) <= 80 else s[:77] + "..."


def _f(cls, rel, line, rule, excerpt) -> dict:
    return {"cls": cls, "file": rel, "line": line, "rule": rule, "excerpt": _cut(excerpt)}


def _line_findings(rel: str, n: int, line: str, classes, terms, vendored: bool) -> list[dict]:
    out: list[dict] = []
    if "U" in classes and (m := _U_RE.search(line)):
        cp = f"{ord(m.group(0)):04x}"
        out.append(_f("U", rel, n, f"unicode-{cp}", _U_RE.sub(lambda x: f"<U+{ord(x.group(0)):04X}>", line)))
    if "P" in classes:
        for rule, rx in (("home-path", _HOME_RE), ("users-path", _USERS_RE), ("windows-user-path", _WIN_RE)):
            if rx.search(line):
                out.append(_f("P", rel, n, rule, line))
                break
    if "V" in classes and not vendored:
        m = _NPX_RE.search(line)
        if m and not re.search(re.escape(m.group(1)) + r"@\d", line):
            out.append(_f("V", rel, n, "npx-unpinned", line))
        elif _LATEST_RE.search(line):
            out.append(_f("V", rel, n, "at-latest", line))
    if "S" in classes:
        for rule, rx in _SECRET_RES:
            m = rx.search(line)
            if not m or (vendored and rule in _VENDORED_SKIP):
                continue
            if rule == "assignment":
                if _PLACEHOLDER_RE.match(m.group(2)):
                    continue
                excerpt = line[: m.start(2) - 1] + "***"  # key and separator kept, quote + value masked
            else:
                excerpt = line[: m.start()] + "***"
            out.append(_f("S", rel, n, rule, excerpt))
            break
    if "M" in classes:
        low = line.lower()
        hit_term = next((i for i, t in enumerate(terms, 1) if t in low), None)
        masked = line
        for t in terms:
            masked = re.sub(re.escape(t), "***", masked, flags=re.I)
        if not vendored and _RFC1918_RE.search(line):
            out.append(_f("M", rel, n, "rfc1918", masked))
        elif hit_term is not None:
            out.append(_f("M", rel, n, f"machine-term:{hit_term}", masked))
        elif "ptyxis-spawn" in low:
            out.append(_f("M", rel, n, "ptyxis-spawn", masked))
    return out


def _workflow_findings(rel: str, text: str) -> list[dict]:
    out: list[dict] = []
    lines = text.split("\n")
    if _WF_TARGET_RE.search(text):
        for n, line in enumerate(lines, 1):
            if _WF_HEAD_REF_RE.search(line):
                out.append(_f("W", rel, n, "workflow-pr-target-checkout", line))
    run_indent = None
    for n, line in enumerate(lines, 1):
        m = _WF_RUN_RE.match(line)
        if m:
            run_indent = len(m.group(1))
            body = m.group(2)
        elif run_indent is not None and line.strip():
            if len(line) - len(line.lstrip(" ")) > run_indent:
                body = line
            else:
                run_indent, body = None, ""
        else:
            body = ""
        if run_indent is not None and _WF_INJECT_RE.search(body):
            out.append(_f("W", rel, n, "workflow-script-injection", line))
    return out


def scan_text(rel: str, text: str, classes=ALL, terms=(), is_yaml: bool = False) -> list[dict]:
    vendored = bool(_VENDORED_RE.search(text[:8192]))
    out: list[dict] = []
    for n, line in enumerate(text.split("\n"), 1):
        out += _line_findings(rel, n, line, classes, terms, vendored)
    if "W" in classes and is_yaml:
        out += _workflow_findings(rel, text)
    return out


def scan(paths, classes=ALL, terms=None, max_bytes: int = 2_000_000, allow=None, root=None) -> list[dict]:
    """Findings minus the allowlisted ones (allow=None -> built-in ``_ALLOW``; [] -> no allowlist)."""
    allow = load_allowlist(None) if allow is None else allow
    return _drop_allowed(_scan_all(paths, classes, terms, max_bytes), allow, root)


def _scan_all(paths, classes=ALL, terms=None, max_bytes: int = 2_000_000) -> list[dict]:
    classes = set(classes)
    terms = load_terms(None) if terms is None else [t.lower() for t in terms if len(t) >= 4]
    out: list[dict] = []
    for p in iter_files(paths, max_bytes):
        rel = _rel(p)
        try:
            text = p.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
        except OSError as exc:
            out.append(_f("E", rel, 0, "unreadable", type(exc).__name__))
            continue
        out += scan_text(rel, text, classes, terms, p.suffix.lower() in (".yml", ".yaml"))
    return sorted(out, key=lambda f: (f["file"], f["line"], f["cls"]))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="validate_imports.py", description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--class", dest="classes", default="".join(sorted(ALL)))
    ap.add_argument("--terms", default=None)
    ap.add_argument("--max-bytes", type=int, default=2_000_000)
    ap.add_argument("--allowlist", default=None, help="JSON allowlist file instead of the built-in one")
    ap.add_argument("--no-allowlist", action="store_true", help="report every finding")
    ap.add_argument("--root", default=None, help="base for allowlist path globs (default: cwd)")
    ap.add_argument("--no-gitignore", action="store_true", help="also scan gitignored files under a dir argument")
    a = ap.parse_args(argv)
    global RESPECT_GITIGNORE
    RESPECT_GITIGNORE = not a.no_gitignore
    paths = [Path(p) for p in a.paths]
    missing = [p for p in paths if not p.exists()]
    if missing:
        print(f"validate_imports: no such path: {missing[0]}", file=sys.stderr)
        return 2
    classes = {c.strip().upper() for c in a.classes.replace(",", "") if c.strip()}
    if not classes <= ALL:
        print(f"validate_imports: unknown class in {a.classes}", file=sys.stderr)
        return 2
    terms = load_terms(Path(a.terms)) if a.terms else None
    allow = [] if a.no_allowlist else load_allowlist(Path(a.allowlist) if a.allowlist else None)
    raw = _scan_all(paths, classes, terms, a.max_bytes)
    found = _drop_allowed(raw, allow, a.root)
    hidden = len(raw) - len(found)
    counts: dict[str, int] = {}
    for f in found:
        counts[f["cls"]] = counts.get(f["cls"], 0) + 1
    if a.json:
        print(json.dumps({"findings": found, "counts": counts}, indent=1, sort_keys=True))
    elif found:
        for f in found:
            print(f"{f['cls']} {f['file']}:{f['line']} {f['rule']} {f['excerpt']}")
        print("counts " + " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
              + (f" ({hidden} allowlisted)" if hidden else ""))
    else:
        print(f"OK validate_imports: {len(iter_files(paths, a.max_bytes))} files scanned"
              + (f" ({hidden} allowlisted)" if hidden else ""))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

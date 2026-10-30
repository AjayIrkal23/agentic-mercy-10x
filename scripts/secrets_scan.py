#!/usr/bin/env python3
"""secrets_scan.py — layer 2 of the go-live secrets check: known VALUES, never patterns.

  secrets_scan.py --known-values --tree DIR [--diff REV_RANGE] [--values-from FILE ...] [--live]
                  [--claude-dir DIR] [--min-len 8] [--allow TERM ...] [--debug-lengths]

Loads live secret/machine values (~/.claude/.env, .credentials.json token fields, settings.user.json env,
the machines file + journal, ~/.config/lean-ctx/config.toml sensitive keys, scripts/grep_gates.machine_terms.json)
unless --values-from is given without --live; searches the tree (inside a git work tree: the files git would
commit, i.e. tracked + untracked-not-ignored) and the diff for each value in plain, URL-encoded, base64,
JSON-escaped and slash-escaped form; prints `KEY file:line` only, never a value. A form matches only on token
boundaries (no letter or digit right before or after it), so a short value inside a longer public word is not a hit.
Exit 0 clean, 1 hits, 2 error (fail closed).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

try:
    import tomllib  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001  Python < 3.11: line regex fallback
    tomllib = None  # type: ignore[assignment]

_SENSITIVE_KEY = re.compile(r"(?i)token|secret|passw|api[_-]?key|private")
# public words and stock default credentials (a dev DB left on "postgres" matches every Postgres doc line)
_PUBLIC = {"true", "false", "yes", "no", "localhost", "0.0.0.0", "127.0.0.1", "::1", "postgres", "postgresql",
           "password", "changeme", "administrator"}
_USER_KEY_RE = re.compile(r"(?i)_(?:USER|USERNAME|LOGIN)$")
_VERSION_RE = re.compile(r"^v?\d+(\.\d+)+(-\d+)?$")
_MODEL_TAG_RE = re.compile(r":\d+(\.\d+)?b$", re.I)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LOGIN_RE = re.compile(r"\b[\w.-]+@(?:\d{1,3}\.){3}\d{1,3}\b|\b[\w.-]+@[\w-]+(?:\.[\w-]+)+\b")
_TICK_RE = re.compile(r"`([^`\s]{6,})`")
_WINHOME_RE = re.compile("[A-Za-z]:" + r"\\Users\\[^\\`\s]+")
_FILENAME_RE = re.compile(r"\.(md|json|jsonc|py|sh|ps1|js|ts|yml|yaml|toml|txt|conf|service|timer|env|log|cfg|ini)$", re.I)
_CODE_CHARS = set("$%{}<>()*|;\"',\\=[]!?#")
_COMMON = {"python3", "sha256", "sha256sum", "base64", "x86_64", "aarch64", "amd64", "arm64", "win32", "win64",
           "ed25519", "id_ed25519", "utf-16", "http/2", "http/3", "ipv4", "ipv6", "pbkdf2", "argon2", "x509"}
_EXCLUDE_PARTS = {".git", "node_modules", "__pycache__", ".cache", ".pytest_cache"}
_BINARY_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".tgz", ".woff", ".woff2",
                  ".ttf", ".ico", ".mp4", ".mp3", ".pyc"}
_MAX_BYTES = 2_000_000


def _env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key.strip()] = val
    return out


def _leaves(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, (*path, str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _leaves(v, (*path, str(i)))
    elif isinstance(obj, str):
        yield path, obj


def _json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def machine_terms(text: str) -> dict[str, str]:
    """IPs, logins/emails, Windows profile dirs and distinctive backticked tokens of a machines file."""
    out: dict[str, str] = {}
    seen: set[str] = set()

    def add(prefix: str, value: str) -> None:
        if value not in seen:
            seen.add(value)
            n = sum(1 for k in out if k.startswith(prefix)) + 1
            out[f"{prefix}{n}"] = value

    for m in _IPV4_RE.finditer(text):
        ip = m.group(0)
        if not ip.startswith("127.") and ip != "0.0.0.0":
            add("MACHINES_IPV4_", ip)
    for m in _LOGIN_RE.finditer(text):
        add("MACHINES_LOGIN_", m.group(0))
    for m in _WINHOME_RE.finditer(text):
        add("MACHINES_WINHOME_", m.group(0))
    for m in _TICK_RE.finditer(text):
        tok = m.group(1)
        if (not re.search(r"[\d.]", tok) or tok[0] in "/~.-" or _FILENAME_RE.search(tok) or "://" in tok
                or "@" in tok or _VERSION_RE.match(tok) or _MODEL_TAG_RE.search(tok) or _IPV4_RE.search(tok)
                or set(tok) & _CODE_CHARS or tok.lower() in _COMMON
                or not (len(tok) >= 8 or "-" in tok or "." in tok)):
            continue
        add("MACHINES_TERM_", tok)
    return out


def _keep(value: str, min_len: int, allow, key: str = "") -> bool:
    v = value.strip()
    if _USER_KEY_RE.search(key) and re.fullmatch(r"[a-z]+", v):
        return False  # a plain-word username ("postgres") is not distinctive; user@host logins are kept
    return (len(v) >= min_len and "\n" not in v and v.lower() not in _PUBLIC and not _VERSION_RE.match(v)
            and not _MODEL_TAG_RE.search(v) and v not in allow)


def load_values(values_from=(), live: bool = True, claude_dir: Path | None = None, min_len: int = 8, allow=(),
                home: Path | None = None, allow_keys=()) -> dict[str, str]:
    claude_dir = Path(claude_dir) if claude_dir else plat.claude_dir()
    home = Path(home) if home else Path.home()
    cands: list[tuple[str, str]] = []
    for f in values_from or ():
        cands += list(_env_file(Path(f)).items())
    if live:
        cands += list(_env_file(claude_dir / ".env").items())
        for path, v in _leaves(_json_file(claude_dir / ".credentials.json")):
            if path and "token" in path[-1].lower():
                cands.append(("CREDENTIALS_" + "_".join(path), v))
        settings = _json_file(claude_dir / "settings.user.json")
        for path, v in _leaves(settings):
            if (path and path[0] == "env") or any(_SENSITIVE_KEY.search(p) for p in path[-1:]):
                cands.append(("SETTINGS_" + "_".join(path), v))
        for name in ("CLAUDE.machines.local.md", "CLAUDE.machines.journal.local.md"):
            try:
                cands += list(machine_terms((claude_dir / name).read_text(encoding="utf-8", errors="replace")).items())
            except OSError:
                pass
        cands += _lean_ctx(home / ".config" / "lean-ctx" / "config.toml")
        terms = _json_file(claude_dir / "scripts" / "grep_gates.machine_terms.json")
        terms = terms.get("terms", []) if isinstance(terms, dict) else terms
        for i, t in enumerate(terms if isinstance(terms, list) else [], 1):
            if isinstance(t, str):
                cands.append((f"MACHINE_TERMS_{i}", t))
    out: dict[str, str] = {}
    seen: set[str] = set()
    skip_keys = set(allow_keys)
    for key, value in cands:
        if key in skip_keys:
            continue
        if isinstance(value, str) and _keep(value, min_len, set(allow), key) and value not in seen:
            seen.add(value)
            out[key] = value
    return out


def _lean_ctx(path: Path) -> list[tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    pairs: list[tuple[str, str]] = []
    if tomllib is not None:
        try:
            for p, v in _leaves(tomllib.loads(text)):
                if _SENSITIVE_KEY.search(p[-1]):
                    pairs.append(("LEANCTX_" + "_".join(p), v))
            return pairs
        except Exception:  # noqa: BLE001  fall through to the regex
            pairs = []
    for m in re.finditer(r'(?m)^\s*([\w.-]+)\s*=\s*"([^"]+)"', text):
        if _SENSITIVE_KEY.search(m.group(1)):
            pairs.append(("LEANCTX_" + m.group(1), m.group(2)))
    return pairs


def forms(value: str) -> set[str]:
    raw = {value, quote(value, safe=""), base64.b64encode(value.encode("utf-8")).decode().rstrip("="),
           json.dumps(value)[1:-1], value.replace("/", "\\/")}
    return {f for f in raw if len(f) >= 6}


def _text_files(root: Path) -> list[Path]:
    cp = plat.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], timeout=60)
    if cp.returncode == 0 and cp.stdout:
        files = [root / p for p in cp.stdout.split("\0") if p]
    else:
        files = [p for p in root.rglob("*") if not set(p.relative_to(root).parts) & _EXCLUDE_PARTS]
    out = []
    for p in files:
        if not p.is_file() or p.suffix.lower() in _BINARY_SUFFIX:
            continue
        try:
            if p.stat().st_size > _MAX_BYTES:
                continue
            with p.open("rb") as fh:
                if b"\0" in fh.read(8192):
                    continue
        except OSError:
            continue
        out.append(p)
    return sorted(set(out))


def _bounded(form: str) -> re.Pattern:
    """An alphanumeric edge of the form must not touch another alphanumeric character."""
    head = r"(?<![A-Za-z0-9])" if form[:1].isalnum() else ""
    tail = r"(?![A-Za-z0-9])" if form[-1:].isalnum() else ""
    return re.compile(head + re.escape(form) + tail)


def _pairs(values: dict[str, str]) -> list[tuple[str, re.Pattern]]:
    """(key, compiled form). Token-bounded, so a value that is a prefix or substring of a public identifier
    (a bucket name, a hash, a longer word) is not a hit; `=`, quotes, `:`, `@`, `/` and spaces are boundaries."""
    return [(k, _bounded(f)) for k, v in values.items() for f in sorted(forms(v))]


def _scan_lines(lines, pairs, label: str, numbers) -> list[tuple[str, str, int]]:
    hits = []
    for line, n in zip(lines, numbers):
        for key in dict.fromkeys(k for k, rx in pairs if rx.search(line)):
            hits.append((key, label, n))
    return hits


def scan_tree(root: Path, values: dict[str, str]) -> list[tuple[str, str, int]]:
    root = Path(root)
    pairs = _pairs(values)
    hits: list[tuple[str, str, int]] = []
    if not pairs:
        return hits
    for p in _text_files(root):
        rel = p.relative_to(root.parent).as_posix()
        lines = p.read_bytes().decode("utf-8", errors="replace").splitlines()
        hits += _scan_lines(lines, pairs, rel, range(1, len(lines) + 1))
    return sorted(set(hits), key=lambda h: (h[1], h[2], h[0]))


def scan_diff(diff_text: str, values: dict[str, str]) -> list[tuple[str, str, int]]:
    pairs = _pairs(values)
    hits: list[tuple[str, str, int]] = []
    path, n = "", 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith("b/") else path
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            hits += _scan_lines([line[1:]], pairs, f"diff:{path}", [n])
            n += 1
        elif line.startswith(" "):
            n += 1
    return sorted(set(hits), key=lambda h: (h[1], h[2], h[0]))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="secrets_scan.py", description=__doc__.split("\n")[0])
    ap.add_argument("--known-values", action="store_true")
    ap.add_argument("--tree")
    ap.add_argument("--diff")
    ap.add_argument("--values-from", action="append", default=[])
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--claude-dir")
    ap.add_argument("--min-len", type=int, default=8)
    ap.add_argument("--allow", action="append", default=[])
    ap.add_argument("--allow-key", action="append", default=[],
                    help="drop a value by KEY NAME (the operator never types the value); repeatable")
    ap.add_argument("--debug-lengths", action="store_true")
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not a.known_values or not a.tree or not Path(a.tree).is_dir():
        print("secrets_scan: --known-values and an existing --tree are required", file=sys.stderr)
        return 2
    live = a.live or not a.values_from
    try:
        values = load_values([Path(v) for v in a.values_from], live, Path(a.claude_dir) if a.claude_dir else None,
                             a.min_len, a.allow, allow_keys=a.allow_key)
    except Exception as exc:  # noqa: BLE001  fail closed
        print(f"secrets_scan: cannot load values: {type(exc).__name__}", file=sys.stderr)
        return 2
    if a.debug_lengths:
        for k, v in sorted(values.items()):
            print(f"{k} {len(v)} chars")
    if not values:
        print("secrets_scan: 0 values loaded")
    tree = Path(a.tree)
    hits = scan_tree(tree, values)
    if a.diff:
        cp = plat.run(["git", "-C", str(tree), "diff", a.diff], timeout=120)
        if cp.returncode != 0:
            print(f"secrets_scan: git diff failed: rc={cp.returncode}", file=sys.stderr)
            return 2
        hits += scan_diff(cp.stdout or "", values)
    for key, f, n in hits:
        print(f"{key} {f}:{n}")
    files = len(_text_files(tree)) if values else 0
    diff = f", diff {'y' if a.diff else 'n'}" if a.diff else ""
    print(f"secrets_scan: {len(hits)} hits ({len(values)} values, {files} files{diff})")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

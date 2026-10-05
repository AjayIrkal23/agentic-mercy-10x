#!/usr/bin/env python3
"""PostToolUse(Write|Edit) hook: record security-sensitive files for the Stop gate.

Fires when a Write/Edit touches a file whose basename TOKENS (not substrings)
name a security concern (auth, session, middleware, password, token, upload,
crypto …) — exact tokens, plus prefix match on unambiguous stems so derived
forms like authentication/sessions count — or whose path runs through a
security directory, and appends it to
``.state/<cid>.security-scan.json`` (Gate 3 in hard-completion-gate.py).

Output: always ``{}`` — the semgrep nudge itself comes from mcp-post-hints.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Exact TOKENS of the basename (split on non-alphanumerics, lower-cased). The old
# substring match flagged Spinner.tsx ("pin"), useQuery.ts ("query"), validators.go,
# mapping.ts ("pin") … and every hit made Gate 3 a hard stop-block (A03-B9).
SECURITY_TOKENS = frozenset({
    "auth", "login", "signin", "signup", "register", "session", "password", "passwd",
    "token", "refresh_token", "access_token", "api_key", "apikey", "middleware",
    "upload", "multipart", "crypto", "encrypt", "decrypt", "bcrypt", "argon", "secret",
    "credential", "private_key", "oauth", "jwt", "bearer", "oidc", "saml", "cookie",
    "samesite", "permission", "rbac", "sanitize", "sanitizer", "cors", "csp", "helmet",
    "xss", "csrf", "nonce", "ratelimit", "rate_limit", "throttle",
})
# Unambiguous stems matched as token PREFIXES so plurals / derived forms count
# (authentication, sessions, permissions, tokens, oauth2, credentials, passwords).
# Short ambiguous words (pin, query, role, validate) are never stems (Santa A1).
SECURITY_STEMS = (
    "auth", "session", "token", "permission", "credential", "passw", "oauth", "jwt",
    "login", "signup", "csrf", "cors", "crypt", "secret", "acl", "rbac", "middleware",
)
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
# camelCase → separate tokens ("refreshToken" → refresh, token; "RateLimit" → rate, limit).
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _basename_tokens(basename: str) -> set:
    stem = os.path.splitext(basename)[0]
    stem = _CAMEL.sub("_", stem)
    toks = {t for t in _TOKEN_SPLIT.split(stem.lower()) if t}
    # snake_case compounds that are themselves tokens (refresh_token, api_key …)
    toks |= {t for t in SECURITY_TOKENS if "_" in t and t in stem.lower()}
    return toks

SECURITY_PATH_SEGMENTS = [
    "/middleware/", "/auth/", "/security/", "/crypto/",
    "/session/", "/guard/", "/permission/",
    "/login/", "/register/", "/password/", "/token/",
    "/upload/", "/cors/", "/policy/", "/access/",
    "/rbac/", "/role/", "/secret/",
]

SKIP_PATTERNS = [
    ".claude/", "node_modules/", ".git/", "dist/", "build/",
    "__pycache__", ".state/", "graphify-out/", "_test.go",
    ".test.ts", ".test.tsx", ".spec.ts", "docs/", "_docs/",
]

STATE_DIR = Path(os.environ.get("CLAUDE_HOOK_DOTSTATE_DIR") or Path(__file__).resolve().parent / ".state")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.platform import locked_update  # noqa: E402


def _is_security_sensitive(fp: str) -> bool:
    norm = fp.replace("\\", "/")
    toks = _basename_tokens(os.path.basename(norm))
    if toks & SECURITY_TOKENS or any(t.startswith(SECURITY_STEMS) for t in toks):
        return True
    return any(seg in norm.lower() for seg in SECURITY_PATH_SEGMENTS)


def _should_skip(fp: str) -> bool:
    return any(skip in fp for skip in SKIP_PATTERNS)


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    return STATE_DIR / f"{safe}.security-scan.json"


def _add_file(state: dict, rel_str: str) -> dict:
    files = state.get("security_files")
    files = files if isinstance(files, list) else []
    if rel_str not in files:
        files.append(rel_str)
    state["security_files"] = files
    state.setdefault("reminded", False)
    return state


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        print("{}")
        return 0

    cid = payload.get("conversation_id") or payload.get("session_id") or ""
    if not cid:
        print("{}")
        return 0

    ti = payload.get("tool_input") or {}
    fp = ti.get("file_path") or ""

    if not fp or _should_skip(fp):
        print("{}")
        return 0

    if not _is_security_sensitive(fp):
        print("{}")
        return 0

    rel = fp.split("/")[-2:] if "/" in fp else [fp]
    rel_str = "/".join(rel)

    # Bookkeeping only (read by hard-completion-gate Gate 3). The model-facing
    # nudge is mcp-post-hints.py's "call mcp__semgrep__semgrep_scan" line — one
    # nudge per file, not two (the old CLI `semgrep scan` line here was a duplicate).
    # security-semgrep-tracker writes the same file: locked RMW (audit J-01).
    locked_update(_state_path(cid), lambda s: _add_file(s, rel_str))
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""PostToolUse(Write|Edit) hook: trigger semgrep reminder on security-sensitive files.

Fires when a Write/Edit touches files matching security-sensitive patterns
(auth, session, middleware, password, token, upload, query, crypto).
Reminds the agent to run semgrep scan before completing.

Output: hookSpecificOutput with additionalContext reminder (PostToolUse format).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SECURITY_PATTERNS = [
    "auth", "login", "signin", "sign-in", "signup", "sign-up", "register",
    "session", "password", "passwd", "passphrase", "pin",
    "token", "refresh_token", "access_token", "api_key", "apikey",
    "middleware", "upload", "file_upload", "multipart",
    "crypto", "encrypt", "decrypt", "hash", "bcrypt", "argon",
    "secret", "credential", "private_key", "cert",
    "oauth", "jwt", "bearer", "oidc", "saml",
    "cookie", "httponly", "secure_cookie", "samesite",
    "permission", "access-control", "access_control", "rbac", "role",
    "sanitiz", "escap", "inject", "query",
    "cors", "csp", "helmet", "x-frame", "xss",
    "rate_limit", "ratelimit", "throttle", "brute",
    "csrf", "nonce", "origin_check",
    "guard", "protect", "restrict", "whitelist", "blacklist", "allowlist",
    "validate", "validator", "input_check",
    "tls", "ssl", "https",
]

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

STATE_DIR = Path(__file__).resolve().parent / ".state"


def _is_security_sensitive(fp: str) -> bool:
    norm = fp.replace("\\", "/").lower()
    basename = os.path.basename(norm)
    if any(pat in basename for pat in SECURITY_PATTERNS):
        return True
    if any(seg in norm for seg in SECURITY_PATH_SEGMENTS):
        return True
    return False


def _should_skip(fp: str) -> bool:
    return any(skip in fp for skip in SKIP_PATTERNS)


def _state_path(cid: str) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cid)
    return STATE_DIR / f"{safe}.security-scan.json"


def _load_state(cid: str) -> dict:
    p = _state_path(cid)
    if not p.is_file():
        return {"security_files": [], "reminded": False}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"security_files": [], "reminded": False}


def _save_state(cid: str, state: dict) -> None:
    _state_path(cid).write_text(json.dumps(state, indent=2), encoding="utf-8")


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

    state = _load_state(cid)
    security_files = state.get("security_files", [])

    rel = fp.split("/")[-2:] if "/" in fp else [fp]
    rel_str = "/".join(rel)

    if rel_str not in security_files:
        security_files.append(rel_str)
    state["security_files"] = security_files

    n = len(security_files)

    if n >= 1 and not state.get("reminded"):
        state["reminded"] = True
        _save_state(cid, state)
        msg = (
            f"[SECURITY SCAN GATE] {n} security-sensitive file(s) modified: "
            f"{', '.join(security_files[:5])}. "
            f"Before completing: run `semgrep scan --config auto` on these files "
            f"and apply OWASP checklist (owasp-security skill). "
            f"Fix all HIGH/CRITICAL findings."
        )
        print(json.dumps({
            "additionalContext": msg,
        }))
        return 0

    if n >= 1 and state.get("reminded"):
        _save_state(cid, state)
        print("{}")
        return 0

    _save_state(cid, state)
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

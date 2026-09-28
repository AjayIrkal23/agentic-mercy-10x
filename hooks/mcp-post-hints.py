#!/usr/bin/env python3
"""mcp-post-hints.py — PostToolUse advisory: "call this MCP now" after a write.

Fires on Write | Edit | MultiEdit | NotebookEdit. Each hint is deduped once per
(kind, file|lib) per session and is availability-aware (the server must be
registered and not waiting on auth — same check as the prompt router):

  security file (auth / session / middleware / input validation …) → semgrep_scan <file>
  new third-party import in the written text                       → context7 docs for <lib>
  FE component edit inside a repo, AND a dev server is listening   → reticle / playwright verify
  migration or .sql                                                → postgres-patterns checklist
  more than 3 distinct code files touched this session (once)      → jcodemunch blast radius

Advisory only, fast (no network; the dev-port probe is `ss -ltn`, 1 s cap), fail-open:
any error prints {}. State: hooks/.state/<sid>.mcp-post-hints.json (no-op write when
CLAUDE_HOOK_DOCTOR is set).

stdin : PostToolUse payload {session_id, tool_name, tool_input, cwd}
stdout: {"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"…"}} | {}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

STATE_DIR = _HOOKS / ".state"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
BLAST_THRESHOLD = 3
MAX_CHARS = 900

_SEC_PATH = re.compile(
    r"(?:^|[/_.-])(auth\w*|session\w*|middlewares?|login|logout|oauth\w*|jwt|passwords?|"
    r"credentials?|permissions?|rbac|acl|csrf|sanitiz\w*|validat\w*|guards?|policy|policies)"
    r"(?:[/_.-]|$)", re.IGNORECASE)
_FE_EXT = (".tsx", ".jsx", ".vue", ".svelte")
_JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")

_JS_IMPORT = re.compile(
    r"""(?:\bimport\s+(?:[\w*{}\s,$]+\s+from\s+)?|\bexport\s+[\w*{}\s,$]+\s+from\s+|\brequire\(\s*|\bimport\(\s*)['"]([^'"\s]+)['"]""")
_PY_IMPORT = re.compile(r"^\s*(?:from\s+([A-Za-z_]\w*)[\w.]*\s+import\b|import\s+([A-Za-z_]\w*))", re.M)
_GO_IMPORT = re.compile(r'"((?:[a-z0-9-]+\.)+[a-z]{2,}/[\w./-]+)"')

_NODE_BUILTINS = {
    "assert", "buffer", "child_process", "crypto", "dns", "events", "fs", "http", "https",
    "net", "os", "path", "process", "querystring", "readline", "stream", "timers", "tls",
    "url", "util", "worker_threads", "zlib", "react", "react-dom",
}
_PY_STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}


def _state_path(sid: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (sid or "nosession"))
    return STATE_DIR / f"{safe}.mcp-post-hints.json"


def _load(sid: str) -> dict:
    try:
        d = json.loads(_state_path(sid).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(sid: str, state: dict) -> None:
    if os.environ.get("CLAUDE_HOOK_DOCTOR"):
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _state_path(sid).with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(_state_path(sid))
    except OSError:
        pass


def _server(name: str) -> bool:
    try:
        from prompt_router.modules import mcp_routes as _mcp  # noqa: PLC0415
        return _mcp.server_available([name]) is not None
    except Exception:  # noqa: BLE001
        return False


def _dev_port():
    try:
        from prompt_router.modules import mcp_routes as _mcp  # noqa: PLC0415
        return _mcp.dev_server_port()
    except Exception:  # noqa: BLE001
        return None


def _texts(tool_input: dict) -> tuple[str, str]:
    """(new_text, old_text) written by the tool call."""
    if not isinstance(tool_input, dict):
        return "", ""
    new = [str(tool_input.get(k) or "") for k in ("content", "new_string", "new_source")]
    old = [str(tool_input.get("old_string") or "")]
    for e in tool_input.get("edits") or []:
        if isinstance(e, dict):
            new.append(str(e.get("new_string") or ""))
            old.append(str(e.get("old_string") or ""))
    return "\n".join(new), "\n".join(old)


def _pkg(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") else parts[0]


def imports(text: str, path: str) -> set[str]:
    """Third-party library names imported in ``text`` (relative / builtin / stdlib dropped)."""
    out: set[str] = set()
    low = path.lower()
    if low.endswith(_JS_EXT):
        for m in _JS_IMPORT.finditer(text):
            spec = m.group(1)
            if spec.startswith((".", "/", "@/", "~", "#", "node:", "virtual:", "http")):
                continue
            name = _pkg(spec)
            if name and name not in _NODE_BUILTINS:
                out.add(name)
    elif low.endswith((".py", ".pyi")):
        for m in _PY_IMPORT.finditer(text):
            name = m.group(1) or m.group(2)
            if name and name not in _PY_STDLIB:
                out.add(name)
    elif low.endswith(".go"):
        for m in _GO_IMPORT.finditer(text):
            out.add("/".join(m.group(1).split("/")[:3]))
    return out


def _is_local(name: str, file_path: str, root) -> bool:
    """A bare import that is really a module of this repo (python pkg / sibling file)."""
    here = Path(file_path).parent
    cands = [here / name, here / f"{name}.py"]
    if root is not None:
        r = Path(str(root))
        cands += [r / name, r / "src" / name, r / f"{name}.py"]
    return any(c.exists() for c in cands)


def hints(payload: dict, state: dict) -> list[str]:
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    fp = str((ti.get("file_path") or ti.get("notebook_path") or "") if isinstance(ti, dict) else "")
    if tool not in WRITE_TOOLS or not fp:
        return []
    seen = set(state.get("seen") or [])
    files = list(state.get("files") or [])
    out: list[str] = []

    def once(key: str) -> bool:
        if key in seen:
            return False
        seen.add(key)
        return True

    try:
        from lib import code_files as _cf  # noqa: PLC0415
        from lib import repo_context as _rc  # noqa: PLC0415
        is_code = _cf.is_code_file(fp)
        root = _rc.git_root(fp)
    except Exception:  # noqa: BLE001
        is_code, root = fp.lower().endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".go")), None
    low = fp.replace("\\", "/").lower()
    name = low.rsplit("/", 1)[-1]

    if is_code and _SEC_PATH.search(low) and _server("semgrep") and once(f"sec:{fp}"):
        out.append(f"Security-sensitive file → call mcp__semgrep__semgrep_scan on {fp} now "
                   "(satisfies Gate 3); owasp-security for the checklist.")

    if is_code and _server("context7"):
        new, old = _texts(ti)
        fresh = sorted(imports(new, fp) - imports(old, fp))
        libs = [lib for lib in fresh if not _is_local(lib, fp, root) and once(f"c7:{lib}")][:3]
        if libs:
            out.append(f"New third-party import ({', '.join(libs)}) → call context7 resolve-library-id → "
                       "query-docs now before relying on its API.")

    if low.endswith(".sql") or "/migrations/" in low or "/migrate/" in low:
        if once(f"sql:{fp}"):
            out.append(f"Migration/SQL ({name}) → postgres-patterns checklist: reversible up/down, "
                       "CONCURRENTLY for big-table indexes, no table-rewriting default, RLS on new "
                       "tables, FK indexes, backfill in batches.")

    if (low.endswith(_FE_EXT) and root is not None and once(f"fe:{fp}")
            and (_server("reticle") or _server("playwright"))):
        port = _dev_port()
        if port:
            out.append(f"FE component edited and your app is running on :{port} → verify with reticle "
                       "(Skill verify-ui-change) or playwright browser_snapshot. Never start a server.")

    if is_code and fp not in files:
        files.append(fp)
    if len(files) > BLAST_THRESHOLD and _server("jcodemunch") and once("blast"):
        out.append(f"{len(files)} code files touched this session → call jcodemunch get_blast_radius / "
                   "find_references on the shared symbols before continuing.")

    state["seen"] = sorted(seen)
    state["files"] = files[-200:]
    return out


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError
        sid = str(payload.get("session_id") or payload.get("sessionId") or "nosession")
        state = _load(sid)
        lines = hints(payload, state)
        _save(sid, state)
        if not lines:
            print("{}")
            return 0
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(lines)[:MAX_CHARS],
        }}))
    except Exception:  # noqa: BLE001
        print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""observe-log.py: async exec links ``observe-log`` (PostToolUse) and ``observe-log-failure``
(PostToolUseFailure) (package learning, docs/LEARNING.md).

One scrubbed row per tool call, appended to state/learning/<repo_key>/observations.jsonl:
  {"ts": <float epoch s>, "sid": "<session_id>", "tool": "Edit", "summary": "<scrubbed>",
   "ok": true, "files": ["rel/path.py"], "error"?: "<scrubbed, <= 160 chars>"}
A PostToolUseFailure payload (or any top-level ``error``) gives ok=false plus the clipped error.
one JSON object per line, <= max_row_bytes (2048) per line, via plat.append_line.

Skips: CLAUDE_HOOK_DOCTOR, the link-doctor probe, ``enabled: false``, tools in
``skip_tools``, payloads without a cwd, and the infra roots ($HOME, ~/.claude, ~/.codex,
this checkout) unless ``observe_infra`` is true (hooks/learning.config.json).
Write-tool rows hold paths and lengths, never content. No network, no child processes.

stdin: PostToolUse JSON; stdout: {} ; exit: always 0.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
try:
    from lib import platform as plat
except Exception:  # noqa: BLE001 - no platform, no hook
    plat = None
try:
    from lib import scrub as _scrub
except Exception:  # noqa: BLE001
    _scrub = None
try:
    from lib import code_files as _cf
except Exception:  # noqa: BLE001
    _cf = None

_CONFIG_PATH = _HOOKS / "learning.config.json"  # test seam
DEFAULTS: dict = {
    "enabled": True,
    "max_row_bytes": 2048,
    "skip_tools": ["Read", "Glob", "Grep", "LS", "TodoWrite", "TodoRead", "NotebookRead",
                   "ListMcpResourcesTool", "ReadMcpResourceTool"],
    "observe_infra": False,
}
_HEAD = 400  # chars of a Bash command / default summary kept
_MAX_FILES = 8
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "StrReplace", "TabWrite")


def _config() -> dict:
    """DEFAULTS merged with the file's dict; any error -> DEFAULTS."""
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(Path(_CONFIG_PATH).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS and type(v) is type(DEFAULTS[k])})
    except Exception:  # noqa: BLE001
        pass
    return cfg


def _repo_key(cwd: str) -> str | None:
    try:
        from lib.model_mode import repo_key
        return repo_key(cwd)
    except Exception:  # noqa: BLE001
        try:  # same formula, hooks-hygiene-mod's public twin
            from lib import repo_context as rc
            root = rc.git_root(cwd) or Path(cwd).expanduser().resolve()
            return rc.repo_key(root, digits=12)
        except Exception:  # noqa: BLE001
            return None


def _root_of(cwd: str) -> Path:
    """Git root of cwd, else the resolved cwd."""
    try:
        from lib import repo_context as rc
        root = rc.git_root(cwd)
        if root is not None:
            return Path(root)
    except Exception:  # noqa: BLE001
        pass
    return Path(cwd).expanduser().resolve()


def _is_infra(root: Path) -> bool:
    try:
        if _cf is not None and _cf.is_infra_root(root):
            return True
        root.resolve().relative_to(plat.claude_dir().expanduser().resolve())
        return True
    except Exception:  # noqa: BLE001 - ValueError: not under ~/.claude
        return False


def _rel(p: str, root: Path) -> str:
    """POSIX path relative to root; a path outside root keeps only its basename."""
    s = str(p).replace("\\", "/")
    pp = Path(str(p)).expanduser()
    if not pp.is_absolute():
        return s[:200]
    try:
        return pp.resolve().relative_to(root).as_posix()
    except (ValueError, OSError, RuntimeError):
        return pp.name or s[-80:]


def _files(tool_input: dict, root: Path) -> list:
    raw = [tool_input.get(k) for k in ("file_path", "path", "notebook_path")]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        raw += [e.get("file_path") for e in edits if isinstance(e, dict)]
    out: list = []
    for p in raw:
        if isinstance(p, str) and p:
            r = _rel(p, root)
            if r not in out:
                out.append(r)
    return out


def _ok(resp) -> bool:
    if isinstance(resp, dict):
        return not any(resp.get(k) for k in ("is_error", "error", "interrupted"))
    if isinstance(resp, str):
        return not resp.lstrip().startswith(("Error", "error:", "ENOENT", "Traceback"))
    return True


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"


def _summary(tool: str, tool_input, files: list) -> str:
    """Shape, never content: write tools give lengths, Bash the command head, MCP the scalar args."""
    ti = tool_input if isinstance(tool_input, dict) else {}
    first = files[0] if files else "?"
    if not isinstance(tool_input, dict):
        text = json.dumps(tool_input, ensure_ascii=False, default=str)[:_HEAD]
    elif tool in _WRITE_TOOLS:
        if isinstance(ti.get("edits"), list):
            text = f"{len(ti['edits'])} edits in {first}"
        elif "content" in ti:
            text = f"{first} (write {len(str(ti.get('content') or ''))} chars)"
        elif "new_source" in ti:
            text = f"{first} ({ti.get('edit_mode') or 'replace'}, new {len(str(ti.get('new_source') or ''))})"
        else:
            text = f"{first} (old {len(str(ti.get('old_string') or ''))}, new {len(str(ti.get('new_string') or ''))})"
    elif tool in ("Bash", "PowerShell"):
        text = _clip(str(ti.get("command") or ""), _HEAD)
    elif tool in ("Agent", "Task"):
        text = _clip(f"{ti.get('subagent_type') or 'general'}: {ti.get('description') or ''}", 200)
    elif tool == "Skill":
        text = f"skill {ti.get('skill') or ''} {str(ti.get('args') or '')[:80]}".strip()
    elif tool == "Workflow":
        text = f"workflow {ti.get('name') or 'inline'} {len(str(ti.get('script') or ''))} chars"
    elif tool.startswith("mcp__"):
        pairs = [f"{k}={_clip(str(v), 60)}" for k, v in sorted(ti.items())
                 if isinstance(v, (str, int, float, bool)) and not isinstance(k, bool)]
        text = " ".join(pairs)[:200]
    else:
        text = json.dumps(ti, sort_keys=True, ensure_ascii=False, default=str)[:_HEAD]
    if _scrub is not None:
        return _scrub.scrub(text)
    import re  # fallback scrubber when lib.scrub is missing
    return re.sub(r"(?i)(key|token|secret|password)(\s*[:=]\s*)\S+", r"\1\2[REDACTED]", text)


def _encode(row: dict) -> bytes:
    return (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8", "replace")


def _cap(row: dict, limit: int) -> bytes:
    """Encoded row <= limit bytes: trim summary by 25 % steps (min 40 chars), then files to
    _MAX_FILES + "+N", then files to []. b"" when even that does not fit (cannot happen with
    the 80-char tool name and 64-char sid at 2048)."""
    row = dict(row)
    data = _encode(row)
    orig, keep = str(row.get("summary") or ""), len(str(row.get("summary") or ""))
    while len(data) > limit and keep > 40:
        keep = max(40, int(keep * 0.75))
        row["summary"] = orig[:keep] + "…"
        data = _encode(row)
    files = list(row.get("files") or [])
    if len(data) > limit and len(files) > _MAX_FILES:
        row["files"] = files[:_MAX_FILES] + [f"+{len(files) - _MAX_FILES}"]
        data = _encode(row)
    if len(data) > limit and row.get("files"):
        row["files"] = []
        data = _encode(row)
    if len(data) > limit:
        row["summary"] = ""
        data = _encode(row)
    return data if len(data) <= limit else b""


def _append(path: Path, data: bytes) -> bool:  # test seam
    return plat.append_line(path, data)


def _tel(kind: str, **fields) -> None:
    try:
        from lib import hook_telemetry
        hook_telemetry.record("PostToolUse", "observe-log", kind=kind, **fields)
    except Exception:  # noqa: BLE001
        pass


def _done() -> int:
    print("{}")
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        if plat is None or os.environ.get("CLAUDE_HOOK_DOCTOR"):
            return _done()
        cfg = _config()
        if not cfg.get("enabled", True):
            return _done()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except ValueError:
            return _done()
        if not isinstance(data, dict):
            return _done()
        tool = data.get("tool_name")
        cwd = data.get("cwd")
        if not isinstance(tool, str) or not tool or not isinstance(cwd, str) or not cwd:
            return _done()
        if data.get("session_id") == "link-doctor" or tool in set(cfg["skip_tools"]):
            return _done()
        root = _root_of(cwd)
        if _is_infra(root) and not cfg.get("observe_infra"):
            return _done()
        key = _repo_key(cwd)
        if not key:
            return _done()
        raw_input = data.get("tool_input")
        tool_input = raw_input if isinstance(raw_input, dict) else {}
        files = _files(tool_input, root)
        clean = _scrub.scrub_obj(raw_input) if _scrub is not None else raw_input
        # failed calls arrive on PostToolUseFailure: top-level `error`, no tool_response
        failed = data.get("hook_event_name") == "PostToolUseFailure" or bool(data.get("error"))
        row = {"ts": round(time.time(), 3), "sid": str(data.get("session_id") or "?")[:64], "tool": tool[:80],
               "summary": _summary(tool, clean, files), "ok": not failed and _ok(data.get("tool_response")),
               "files": files}
        err = str(data.get("error") or "") if failed else ""
        if err:
            row["error"] = _clip(_scrub.scrub(err) if _scrub is not None else "[unscrubbed error dropped]", 160)
        line = _cap(row, int(cfg["max_row_bytes"]))
        if not line:
            return _done()
        target = plat.state_dir() / "learning" / key / "observations.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            written = _append(target, line)
        except OSError:
            written = False
        if not written:
            _tel("write_failed")
    except Exception as exc:  # noqa: BLE001 - never block a tool call
        _tel("error", error=type(exc).__name__)
    return _done()


if __name__ == "__main__":
    sys.exit(main())

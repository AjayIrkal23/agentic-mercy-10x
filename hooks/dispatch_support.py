#!/usr/bin/env python3
"""dispatch_support.py — helpers dispatch.py imports (kept out of it to hold its size).

  adapt(payload)          lean-ctx write/shell tools -> the Bash / Edit / Write shapes the
                          gates read (B1-04). Returns a list of payloads, or None.
  spawn_deferred(...)     run a ``"defer": true`` advisory detached; its context is queued
                          (B1-02: tdd-guard off the PreToolUse critical path).
  drain(sid)              queued contexts for this session, removed on read.
  cap(text, limit)        cut on a line boundary with a ``[truncated]`` marker (B1-16).

``python3 dispatch_support.py run-deferred`` is the detached worker: stdin is
``{"cmd", "timeout_s", "payload", "sid", "event", "link_id"}``. Never raises.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

_SHELL_TOOLS = ("mcp__lean-ctx__ctx_shell", "mcp__lean-ctx__shell")
_PATCH_TOOL = "mcp__lean-ctx__ctx_patch"
_CALL_TOOL = "mcp__lean-ctx__ctx_call"
_MAX_PATCH_PATHS = 4
_QUEUE_MAX_AGE_S = 1800  # an advisory older than 30 min no longer describes the work


def _patch_payload(base: dict, op: dict) -> dict | None:
    path = op.get("path")
    if not isinstance(path, str) or not path:
        return None
    if op.get("op") == "create":
        tool, ti = "Write", {"file_path": path, "content": str(op.get("new_text") or "")}
    else:
        tool, ti = "Edit", {"file_path": path, "old_string": str(op.get("old_text") or op.get("find") or ""),
                            "new_string": str(op.get("new_text") or op.get("replace") or "")}
    return {**base, "tool_name": tool, "tool_input": ti}


def adapt(payload: dict) -> list | None:
    """Gate-shaped payloads for a lean-ctx write/shell call; None for any other tool."""
    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool == _CALL_TOOL:  # ctx_call(name=..., arguments={command|path...})
        args = ti.get("arguments") if isinstance(ti.get("arguments"), dict) else {}
        name = str(ti.get("name") or "")
        if isinstance(args.get("command"), str):
            tool, ti = _SHELL_TOOLS[0], args
        elif "patch" in name:
            tool, ti = _PATCH_TOOL, args
        else:
            return None
    if tool in _SHELL_TOOLS:
        cmd = ti.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return None
        return [{**payload, "tool_name": "Bash", "tool_input": {"command": cmd}}]
    if tool == _PATCH_TOOL:
        ops = ti.get("ops") if isinstance(ti.get("ops"), list) else [ti]
        out, seen = [], set()
        for op in ops:
            p = _patch_payload(payload, op) if isinstance(op, dict) else None
            if p and p["tool_input"]["file_path"] not in seen:
                seen.add(p["tool_input"]["file_path"])
                out.append(p)
        return out[:_MAX_PATCH_PATHS] or None
    return None


# --------------------------------------------------------------------------- #
# deferred advisories
# --------------------------------------------------------------------------- #
def _queue_path(sid: str) -> Path:
    try:
        from lib import platform as _plat
        base = _plat.state_dir()
    except Exception:  # noqa: BLE001
        # same dir platform.state_dir() returns (it was hooks/.state here: two homes)
        base = Path(os.environ.get("CLAUDE_HOOK_STATE_DIR") or _HOOKS.parent / "state")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:120]
    return base / "advisory-queue" / f"{safe}.jsonl"


def spawn_deferred(cmd: list, timeout_s: float, payload_text: str, sid: str, event: str, link_id: str) -> bool:
    """Start the detached worker. False when it could not start (caller runs inline)."""
    job = json.dumps({"cmd": cmd, "timeout_s": timeout_s, "payload": payload_text,
                      "sid": sid, "event": event, "link_id": link_id})
    try:
        from lib import platform as _plat
        return _plat.spawn_worker([sys.executable or "python3", str(Path(__file__).resolve()), "run-deferred"],
                                  stdin_text=job) is not None
    except Exception:  # noqa: BLE001
        return False


def _context_of(out: str) -> str:
    s = out.strip()
    if not s:
        return ""
    if not s.startswith("{"):
        return s[:8000]
    try:
        obj = json.loads(s)
    except ValueError:
        return ""
    hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
    if isinstance(hso, dict) and hso.get("additionalContext"):
        return str(hso["additionalContext"])
    return str(obj.get("additionalContext") or "") if isinstance(obj, dict) else ""


def run_deferred(job: dict) -> None:
    t0 = time.perf_counter()
    rc, ctx = 1, ""
    try:
        from lib import platform as _plat
        proc = subprocess.run(job["cmd"], input=job.get("payload") or "{}", capture_output=True,  # noqa: S603
                              text=True, timeout=float(job.get("timeout_s") or 15), check=False,
                              **_plat.no_window_kwargs())
        rc = proc.returncode
        ctx = _context_of(proc.stdout or "") if rc == 0 else ""
    except subprocess.TimeoutExpired:
        rc = 124
    except Exception:  # noqa: BLE001
        rc = 1
    if ctx:
        enqueue(str(job.get("sid") or ""), str(job.get("link_id") or ""), ctx)
    try:
        from lib import hook_telemetry as _tel
        _tel.record(str(job.get("event") or ""), str(job.get("link_id") or "?"), via="deferred",
                    ms=round((time.perf_counter() - t0) * 1000, 2), exit=rc, chars_out=len(ctx),
                    decision="run" if rc == 0 else ("timeout" if rc == 124 else "error"),
                    session=str(job.get("sid") or ""), type="advisory")
    except Exception:  # noqa: BLE001
        pass


def enqueue(sid: str, link_id: str, ctx: str) -> bool:
    """Queue ``ctx`` for this session's next prompt (the model reads it; the user's screen
    never shows it). One ``plat.append_line`` record (locked on Windows), safe beside a
    concurrent drain. True when written."""
    if not sid or not ctx:
        return False
    try:
        from lib import platform as _plat
        q = _queue_path(sid)
        q.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": time.time(), "link": link_id, "ctx": ctx}) + "\n"
        return _plat.append_line(q, line.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return False


def drain(sid: str) -> list:
    """Queued advisory texts for ``sid`` (oldest first); the queue is emptied."""
    if not sid:
        return []
    q = _queue_path(sid)
    tmp = q.with_name(f"{q.name}.{os.getpid()}.draining")
    try:
        from lib import platform as _plat
        _plat.replace_file(q, tmp)  # atomic hand-off: a worker appending now starts a new file
    except Exception:  # noqa: BLE001
        return []
    out = []
    try:
        for line in tmp.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if time.time() - float(r.get("ts") or 0) <= _QUEUE_MAX_AGE_S and r.get("ctx"):
                out.append(str(r["ctx"]))
    except OSError:
        pass
    try:
        tmp.unlink()
    except OSError:
        pass
    return out


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
_MARK = "[truncated]"


def cap(text: str, limit: int) -> str:
    if not limit or len(text) <= limit:
        return text
    room = max(0, limit - len(_MARK) - 1)
    cut = text[:room]
    nl = cut.rfind("\n")
    if nl > 0:
        cut = cut[:nl]
    return cut.rstrip() + "\n" + _MARK


if __name__ == "__main__":
    if sys.argv[1:2] == ["run-deferred"]:
        try:
            run_deferred(json.loads(sys.stdin.read() or "{}"))
        except Exception:  # noqa: BLE001
            pass
    raise SystemExit(0)

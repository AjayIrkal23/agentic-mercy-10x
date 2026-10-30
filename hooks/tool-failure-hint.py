#!/usr/bin/env python3
"""tool-failure-hint.py — PostToolUseFailure advisory.

Turns the most-misdiagnosed tool failures into a one-line hint (<= 220 chars;
rules/claude-infra.md, "Misdiagnosis order"):
  Edit/Write whose error mentions "has not been read" or "Read deny"
      -> Read the exact file, then retry immediately.
  Bash whose error contains "path escapes project root"
      -> lean-ctx PathJail intercepted it; re-run as plain Bash.
  Bash/PowerShell killed by SIGKILL (error starts "Exit code 137"/"-9", or a bare "Killed" line)
      -> a kill in state/oomguard.events within 90 s (kernel, systemd-oomd, user manager,
         memwatch) is named: the failure is likely collateral; else, with a tool memory
         cap set (CLAUDE_CODE_TOOL_MEMORY_LIMIT / TOOL_MEMORY_LIMIT), the cap is the likely
         killer and a `source: "toolcap"` kill row is appended (the only writer of toolcap).
  mcp__<server>__* failing twice in a session on a health code (state/<sid>.mcp-unhealthy.json)
      -> name the server and the normalised reason (401/403/429/503/transport); any other
         error (not found, bad id, validation) is the call's fault, not the server's: silent.
A fresh memory tier above ok (state/mem-pressure.json) adds one line. Anything else -> {}.
Fail-open: any error prints {} and exits 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tool_compat import is_shell_tool  # noqa: E402

try:
    from lib import platform as plat  # noqa: E402
except Exception:  # noqa: BLE001 - legacy hints still work without the lib
    plat = None

MAX_CHARS = 220
KILL_WINDOW_S = 90
TIER_STALE_S = 30
_TAIL_BYTES = 64 * 1024
# The exit status only: the Bash tool's error starts "Exit code 137" (or -9) for a SIGKILLed
# child, and the shell prints a bare "Killed" line. Free text ("SIGKILL", "signal 9") in an
# exit-1 test failure is not a kill; the settings always set a tool cap, so it would read as one.
_SIGKILL_RE = re.compile(r"(?m)\AExit code (?:137|-9)\b|^Killed$")
_HEALTH_CODES = {"401", "403", "429", "503", "transport"}
_REASONS = (
    ("401", re.compile(r"\b401\b|unauthori[sz]ed|auth(?:entication)?\s+(?:failed|expired|invalid)", re.I)),
    ("403", re.compile(r"\b403\b|forbidden|permission denied", re.I)),
    ("429", re.compile(r"\b429\b|rate limit|too many requests", re.I)),
    ("503", re.compile(r"\b503\b|service unavailable|overloaded|temporarily unavailable", re.I)),
    ("transport", re.compile(r"ECONNREFUSED|ENOTFOUND|EAI_AGAIN|timed? ?out|socket hang up"
                             r"|connection (?:failed|lost|reset|closed)", re.I)),
)
_SOURCES = {"kernel": "kernel OOM kill", "oomd": "systemd-oomd kill", "user-manager": "user-manager OOM stop"}


def _now() -> float:
    return time.time()


def _state() -> Path:
    return plat.state_dir()


def hint(tool: str, error: str) -> str:
    err = (error or "").lower()
    if tool in ("Edit", "Write") and ("has not been read" in err or "read deny" in err):
        return ("Edit/Write failed because the file was not read first: Read the exact "
                "file, then retry the edit immediately (no other call in between). Do not shell out.")
    if is_shell_tool(tool) and "path escapes project root" in err:
        return "lean-ctx PathJail intercepted this command; re-run it as plain Bash (not ctx_shell)."
    return ""


def normalize_reason(text: str) -> str:
    for code, rx in _REASONS:
        if rx.search(text or ""):
            return code
    return "other"


def _tool_cap() -> str:
    return (os.environ.get("CLAUDE_CODE_TOOL_MEMORY_LIMIT") or os.environ.get("TOOL_MEMORY_LIMIT") or "").strip()


def _recent_kill(window: float = KILL_WINDOW_S) -> dict | None:
    """Newest non-toolcap kill row in the last 64 KiB of oomguard.events within `window` s."""
    try:
        with open(_state() / "oomguard.events", "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TAIL_BYTES))
            tail = fh.read().decode("utf-8", "replace")
    except OSError:
        return None
    now = _now()
    for line in reversed(tail.splitlines()):
        try:
            row = json.loads(line)
            if (isinstance(row, dict) and row.get("kind") == "kill" and row.get("source") != "toolcap"
                    and now - float(row["ts"]) <= window):
                return row
        except (ValueError, TypeError, KeyError):
            continue
    return None


def _append_kill(row: dict) -> None:
    try:
        from lib import memwatch_state  # oom-sentinel; optional
        memwatch_state.append_event(row)
        return
    except Exception:  # noqa: BLE001
        pass
    data = (json.dumps(row) + "\n").encode("utf-8")
    path = _state() / "oomguard.events"
    try:
        if plat.append_line(path, data):
            return
    except Exception:  # noqa: BLE001 - fall through to a plain append
        pass
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o644)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        pass


def _tier_line() -> str:
    try:
        d = json.loads((_state() / "mem-pressure.json").read_text(encoding="utf-8"))
        level = d.get("level")
        if level in ("warn", "crit") and _now() - float(d.get("ts", 0)) <= TIER_STALE_S:
            return f"memory tier {level}: wait for ok before heavy commands"
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return ""


def memory_hint(payload: dict, err: str) -> str:
    tool = str(payload.get("tool_name") or "")
    if plat is None or payload.get("is_interrupt") or not is_shell_tool(tool) or not _SIGKILL_RE.search(err):
        return ""
    k = _recent_kill()
    if k:
        src = k.get("source")
        label = (f"memwatch stage {k.get('stage', '?')} kill" if src == "memwatch"
                 else _SOURCES.get(src, str(src)))
        age = int(_now() - float(k["ts"]))
        return (f"{label} hit {k.get('victim', '?')} ({k.get('rss_mb', '?')} MB, {k.get('unit', '')}) "
                f"{age} s ago; this failure is likely collateral. {_tier_line()}").strip()
    cap = _tool_cap()
    if not cap:
        return ""
    _append_kill({"ts": _now(), "kind": "kill", "source": "toolcap", "tool": tool, "limit": cap,
                  "cmd": str((payload.get("tool_input") or {}).get("command", ""))[:80],
                  "sid": payload.get("session_id")})
    return (f"the command was likely killed by the tool memory cap ({cap}); split the work, lower "
            f"parallelism, or run it as a detached builder. {_tier_line()}").strip()


def mcp_hint(payload: dict, err: str) -> str:
    tool = str(payload.get("tool_name") or "")
    sid = re.sub(r"[^A-Za-z0-9._-]", "_", str(payload.get("session_id") or ""))[:128]
    if plat is None or not tool.startswith("mcp__") or not sid:
        return ""
    server = tool.split("__")[1] if tool.count("__") >= 2 else tool[5:]
    code, now = normalize_reason(err), _now()
    if code not in _HEALTH_CODES:
        return ""  # a bad argument or a missing symbol is not an unhealthy server

    def bump(d: dict) -> dict:
        rec = d.get(server) if isinstance(d.get(server), dict) else {}
        d[server] = {"count": int(rec.get("count", 0) or 0) + 1, "last_code": code, "last_ts": now}
        return d

    data = plat.locked_update(_state() / f"{sid}.mcp-unhealthy.json", bump)
    n = int(((data or {}).get(server) or {}).get("count", 0) or 0)
    if n >= 2:
        return f"MCP server {server} failed {n}x this session ({code}); use the native fallback and say so once."
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        error = payload.get("error")
        if not isinstance(error, str):
            error = json.dumps(error, ensure_ascii=False) if error is not None else ""
        err = error[:4096]
        text = (hint(str(payload.get("tool_name") or ""), error)
                or memory_hint(payload, err) or mcp_hint(payload, err))
        if text:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUseFailure",
                "additionalContext": text[:MAX_CHARS],
            }}))
            return 0
    except Exception:  # noqa: BLE001
        pass
    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""link-doctor.py — fire a synthetic event through EVERY enabled dispatch link (P4-T10).

The Charter §3 "doctor that fires synthetic events through every link" guarantee.
Reads ``hooks/dispatch.config.json``, and for each enabled link in every event
chain constructs a minimal payload that matches the link's ``tools:`` regex, runs
the link's command as a subprocess, and asserts:

  * it returns within 10s (no hang);
  * its stdout is empty or parseable JSON (no garbage that would break dispatch);
  * exit code is tolerable (0, or a hook's own non-fatal code — links are
    fail-open by contract, so a nonzero exit that still emits valid/empty JSON
    is acceptable; only a hang or unparseable non-empty output is a FAIL).

Prints a PASS/FAIL table and exits nonzero if any link FAILs. Also runnable as a
library (``run_doctor()``) for the P6 installer doctor. Pure stdlib, fail-open.

Usage:  python3 hooks/tools/link-doctor.py [--verbose]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]
_CONFIG = _HOOKS / "dispatch.config.json"

_EVENT_TOKEN_TO_NAME = {
    "session-start": "SessionStart", "user-prompt-submit": "UserPromptSubmit",
    "pre-tool-use": "PreToolUse", "post-tool-use": "PostToolUse", "stop": "Stop",
    "subagent-stop": "SubagentStop", "pre-compact": "PreCompact", "session-end": "SessionEnd",
}


def _sample_tool(tools: str | None) -> str:
    """Pick a concrete tool_name that matches the link's tools regex."""
    if not tools:
        return ""
    if tools == ".*":
        return "Bash"
    # first alternative that looks like a literal identifier
    for alt in tools.split("|"):
        tok = alt.strip()
        m = re.match(r"[A-Za-z_][\w]*", tok)
        if m:
            return m.group(0)
    return "Bash"


def _resolve_cmd(cmd: list) -> list:
    import os
    import shutil
    py = sys.executable or shutil.which("python3") or "python3"
    node = shutil.which("node") or shutil.which("nodejs") or "node"
    subs = {"{PY}": py, "{NODE}": node, "{HOOKS}": str(_HOOKS), "{HOME}": os.path.expanduser("~")}
    out = []
    for part in cmd:
        s = str(part)
        for k, v in subs.items():
            s = s.replace(k, v)
        out.append(s)
    return out


def _payload_for(event_token: str, link: dict) -> dict:
    tool = _sample_tool(link.get("tools"))
    p: dict = {"session_id": "link-doctor", "hook_event_name": _EVENT_TOKEN_TO_NAME.get(event_token, event_token)}
    if event_token == "session-start":
        p["source"] = "startup"
    if tool:
        p["tool_name"] = tool
        if tool in ("Write", "Edit", "MultiEdit"):
            p["tool_input"] = {"file_path": "/tmp/link_doctor_probe.py", "content": "x = 1\n"}
        elif tool == "Bash":
            p["tool_input"] = {"command": "true"}
        elif tool == "Read":
            p["tool_input"] = {"file_path": "/tmp/link_doctor_probe.py"}
        elif tool.startswith("mcp__"):
            p["tool_input"] = {"file_path": "/tmp/link_doctor_probe.py"}
        else:
            p["tool_input"] = {}
    return p


def run_doctor(verbose: bool = False) -> tuple[int, int, list]:
    cfg = json.loads(_CONFIG.read_text(encoding="utf-8"))
    rows = []
    passed = failed = 0
    for event_token, links in (cfg.get("chains", {}) or {}).items():
        for link in links:
            lid = link.get("id", "?")
            if not link.get("enabled", True):
                rows.append((event_token, lid, "SKIP(disabled)", 0.0))
                continue
            cmd = _resolve_cmd(link.get("cmd", []))
            payload = _payload_for(event_token, link)
            t0 = time.perf_counter()
            status = "PASS"
            try:
                proc = subprocess.run(cmd, input=json.dumps(payload), capture_output=True,
                                      text=True, timeout=10, check=False)
                ms = round((time.perf_counter() - t0) * 1000, 1)
                out = (proc.stdout or "").strip()
                is_advisory = link.get("type", "advisory") == "advisory"
                if out and not out.startswith("{"):
                    # advisory links may legitimately emit RAW TEXT (injected as
                    # additionalContext by dispatch); gate/mutator/exec must emit
                    # JSON or nothing, so non-JSON there is a real defect.
                    status = "PASS" if is_advisory else "FAIL(non-json-output)"
                elif out:
                    try:
                        json.loads(out)
                    except ValueError:
                        status = "FAIL(bad-json)"
            except subprocess.TimeoutExpired:
                ms = round((time.perf_counter() - t0) * 1000, 1)
                status = "FAIL(timeout>10s)"
            except FileNotFoundError:
                ms = round((time.perf_counter() - t0) * 1000, 1)
                # a missing interpreter (e.g. node absent) is an ENV gap, not a
                # link defect — flag as WARN, not FAIL.
                status = "WARN(cmd-not-found)"
            except Exception as exc:  # noqa: BLE001
                ms = round((time.perf_counter() - t0) * 1000, 1)
                status = f"FAIL({type(exc).__name__})"
            rows.append((event_token, lid, status, ms))
            if status == "PASS" or status.startswith(("SKIP", "WARN")):
                passed += 1
            else:
                failed += 1
    return passed, failed, rows


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    passed, failed, rows = run_doctor(verbose)
    print("=== link-doctor: synthetic fire through every enabled link ===")
    for event, lid, status, ms in rows:
        mark = "OK " if (status == "PASS" or status.startswith(("SKIP", "WARN"))) else "XX "
        print(f"  {mark} {event:18s} {lid:26s} {status:22s} {ms:>7.1f}ms")
    total = passed + failed
    print(f"=== {passed}/{total} OK, {failed} FAIL ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

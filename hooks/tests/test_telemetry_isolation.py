"""Hook telemetry follows CLAUDE_HOOK_TELEMETRY_DIR (audit 2026-10-05 I-01/J-02).

Scripts derived `hooks/.telemetry` from `__file__`, so a sandbox HOME never isolated
them: ~70% of the production dir was test residue that fed the weights loop.
Every writer and reader of per-session telemetry and of `telemetry/hook-fires-*`
honours the override; conftest.py points it at a temp dir for the whole suite.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def test_suite_runs_with_an_isolated_telemetry_dir():
    d = os.environ.get("CLAUDE_HOOK_TELEMETRY_DIR", "")
    assert d and HOOKS.parent not in Path(d).resolve().parents


def test_router_and_dispatch_write_only_to_the_override(tmp_path):
    sid = f"t-iso-{os.getpid()}-{int(time.time())}"
    env = dict(os.environ, CLAUDE_HOOK_TELEMETRY_DIR=str(tmp_path), CLAUDE_HOOK_DOCTOR="1")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": sid, "cwd": str(repo),
               "prompt": "add a REST endpoint with pagination, filtering and a vitest test",
               "transcript_path": ""}
    subprocess.run([sys.executable, str(HOOKS / "prompt_router" / "router.py")],
                   input=json.dumps(payload), text=True, capture_output=True,
                   env=env, timeout=30, check=False)
    pre = {"hook_event_name": "PreToolUse", "session_id": sid, "tool_name": "Read",
           "tool_input": {"file_path": str(repo / "a.md")}, "cwd": str(repo)}
    subprocess.run([sys.executable, str(HOOKS / "dispatch.py"), "pre-tool-use"],
                   input=json.dumps(pre), text=True, capture_output=True,
                   env=env, timeout=30, check=False)
    assert not list((HOOKS / ".telemetry").glob(f"{sid}.*")), "router wrote the real hooks/.telemetry"
    assert list(tmp_path.glob(f"{sid}.*")), "router did not write to the override"
    fires = list(tmp_path.glob("hook-fires-*.jsonl"))
    assert fires and sid in fires[0].read_text(encoding="utf-8"), "dispatch fires not redirected"

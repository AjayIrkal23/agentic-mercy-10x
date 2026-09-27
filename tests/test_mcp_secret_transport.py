"""Regression checks for secret-safe user MCP registrations."""

from __future__ import annotations

import json
from pathlib import Path


LIVE_CONFIG = Path.home() / ".claude.json"


def test_context7_key_is_not_exposed_in_process_arguments() -> None:
    config = json.loads(LIVE_CONFIG.read_text(encoding="utf-8"))
    context7 = config["mcpServers"]["context7"]
    args = context7.get("args", [])
    if "--api-key" in args or any(
        isinstance(value, str) and value.startswith("ctx7sk-") for value in args
    ):
        raise AssertionError("Context7 credentials must not be stored in MCP argv")

    env = context7.get("env", {})
    if not isinstance(env.get("CONTEXT7_API_KEY"), str) or not env["CONTEXT7_API_KEY"]:
        raise AssertionError("Context7 must receive its credential through the MCP env map")

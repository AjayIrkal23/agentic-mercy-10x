"""Regression checks for secret-safe user MCP registrations."""

from __future__ import annotations

import json
from pathlib import Path


LIVE_CONFIG = Path.home() / ".claude.json"


def test_context7_key_is_not_exposed_in_process_arguments() -> None:
    import pytest
    try:
        context7 = json.loads(LIVE_CONFIG.read_text(encoding="utf-8"))["mcpServers"]["context7"]
    except (OSError, ValueError, KeyError):
        pytest.skip("no live ~/.claude.json context7 entry (fresh machine / CI)")
    args = context7.get("args", [])
    if "--api-key" in args or any(
        isinstance(value, str) and value.startswith("ctx7sk-") for value in args
    ):
        raise AssertionError("Context7 credentials must not be stored in MCP argv")

    env = context7.get("env", {})
    if "CONTEXT7_API_KEY" in env and not (isinstance(env["CONTEXT7_API_KEY"], str) and env["CONTEXT7_API_KEY"]):
        raise AssertionError("a declared CONTEXT7_API_KEY must be a non-empty env value")


def test_manifest_never_embeds_secrets() -> None:
    """Secrets reach `claude mcp add` only from the installer's environment (env_from)."""
    manifest = json.loads((Path(__file__).resolve().parents[1] / "installer" / "manifest.json")
                          .read_text(encoding="utf-8"))
    for srv in manifest["mcp_servers"]:
        for var in srv.get("env_from", []):
            assert not any(str(a).startswith(f"{var}=") for a in srv["add"]), srv["name"]
    assert "ctx7sk-" not in json.dumps(manifest)

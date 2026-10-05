"""Manifest invariants added by WP7 (audit 2026-10-05 I-12, I-13, G-01, I-10)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "installer"))

import doctor_mcp  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
SERVERS = {s["name"]: s for s in M["mcp_servers"]}


def test_manifest_version_matches_the_changelog_head():
    head = re.search(r"^## v(\d+\.\d+\.\d+)", (_ROOT / "docs" / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
    assert head and M["version"] == head.group(1)


def test_windows_github_launcher_runs_the_manifest_pin():
    want = doctor_mcp.npx_spec(" ".join(SERVERS["github"]["add"]))
    text = (_ROOT / "scripts" / "github-mcp-launcher.py").read_text(encoding="utf-8")
    assert f'"{want}"' in text


def test_playwright_post_step_matches_the_server_pin():
    want = doctor_mcp.npx_spec(" ".join(SERVERS["playwright"]["add"]))
    step = next(s for s in M["post_steps"] if s["id"] == "playwright-chromium")
    assert want in step["cmd"]


def test_python_tool_installs_are_pinned():
    """I-12: semgrep / jcodemunch / graphify serve MCP servers too; a fresh machine must
    get the versions this one runs (the serve venv pins graphifyy separately)."""
    loose = []
    for d in M["deps"]:
        for key in ("install_posix", "install_windows"):
            argv = d.get(key) or []
            start = 3 if argv[:3] == ["uv", "tool", "install"] else 2 if argv[:2] == ["pipx", "install"] else 0
            if start:
                loose += [f"{d['id']}:{key}:{a}" for a in argv[start:] if not a.startswith("-") and "==" not in a]
    assert not loose, loose


def test_ponytail_is_the_mandatory_plugin():
    mandatory = [p["id"] for p in M["plugins"]["install"] if p.get("mandatory")]
    assert mandatory == ["ponytail@ponytail"]

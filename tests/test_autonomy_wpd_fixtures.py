"""Shared sandbox for the WP-D (autonomy) tests: a fake ``claude`` executable on PATH.

The fake records argv (one JSON list per line) and edits a fake ``$HOME/.claude.json``
for ``mcp remove`` / ``mcp add-json``. HOME is a tmp dir, CLAUDE_CONFIG_DIR is unset (so
``deps.user_config_file()`` is ``$HOME/.claude.json``), the real ``claude`` is never run.
Set ``FAKE_CLAUDE_FAIL_SPEC=<substr>`` to make ``add-json`` fail when its JSON has it.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402

SECRET = "sentinel-secret-value-9f3a"

FAKE_CLAUDE = """#!{py}
import json, os, sys
cfg = os.path.join(os.environ["HOME"], ".claude.json")
argv = sys.argv[1:]
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as fh:
    fh.write(json.dumps(argv) + "\\n")
data = json.load(open(cfg)) if os.path.exists(cfg) else {{}}
servers = data.setdefault("mcpServers", {{}})
if argv[:2] == ["mcp", "remove"]:
    servers.pop(argv[-1], None)
elif argv[:2] == ["mcp", "add-json"]:
    bad = os.environ.get("FAKE_CLAUDE_FAIL_SPEC")
    if bad and bad in argv[-1]:
        sys.exit(1)
    servers[argv[-2]] = json.loads(argv[-1])
json.dump(data, open(cfg, "w"))
"""


class Box:
    def __init__(self, tmp: Path):
        self.home, self.bin = tmp / "home", tmp / "bin"
        self.state = tmp / "state"
        for d in (self.home, self.bin, self.state):
            d.mkdir()
        self.log = tmp / "claude-calls.log"
        exe = self.bin / "claude"
        exe.write_text(FAKE_CLAUDE.format(py=sys.executable), encoding="utf-8")
        exe.chmod(0o755)
        if plat.IS_WINDOWS:  # no shebangs: a .cmd shim, like an npm-installed claude
            (self.bin / "claude.cmd").write_text(f'@"{sys.executable}" "%~dp0claude" %*\r\n',
                                                 encoding="utf-8")

    def write_live(self, servers: dict) -> None:
        (self.home / ".claude.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")

    def live(self) -> dict:
        return json.loads((self.home / ".claude.json").read_text(encoding="utf-8"))["mcpServers"]

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf-8").splitlines()]


def npx(name: str, pkg: str, **kw) -> dict:
    return {"name": name, "add": ["claude", "mcp", "add", "--scope", "user", name, "--", "npx", "-y", pkg], **kw}


def manifest(*servers: dict, deps: list | None = None) -> dict:
    return {"mcp_servers": list(servers), "deps": deps or [],
            "doctor_probes": {"mcp_roster": [s["name"] for s in servers]}}


@pytest.fixture
def box(tmp_path, monkeypatch):
    b = Box(tmp_path)
    monkeypatch.setenv("HOME", str(b.home))
    monkeypatch.setenv("USERPROFILE", str(b.home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("PATH", f"{b.bin}{os.pathsep}/usr/bin{os.pathsep}/bin")
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(b.log))
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(b.state))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    monkeypatch.delenv("FAKE_CLAUDE_FAIL_SPEC", raising=False)
    return b

"""Manifest invariants added by WP7 (audit 2026-10-05 I-12, I-13, G-01, I-10)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

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
            if argv[:3] == ["uv", "tool", "install"]:
                loose += [f"{d['id']}:{key}:{a}" for a in argv[3:] if not a.startswith("-") and "==" not in a]
    assert not loose, loose


def test_ponytail_is_the_mandatory_plugin():
    mandatory = [p["id"] for p in M["plugins"]["install"] if p.get("mandatory")]
    assert mandatory == ["ponytail@ponytail"]


# --- Windows base tools (v4.1): pinned version + SHA-256 for every download -------------------- #
WIN = M["user_space"]["windows"]
WIN_TOOLS = {k: v for k, v in WIN.items() if isinstance(v, dict) and "url" in v}


def test_every_windows_download_is_pinned_with_a_sha256_per_arch():
    assert set(WIN_TOOLS) == {"python", "git", "node", "claude", "uv", "gh", "ollama"}
    for name, t in WIN_TOOLS.items():
        assert t["version"] and "{version}" in t["url"] and t["url"].startswith("https://"), name
        assert t["sha256"] and set(t["sha256"]) <= set(t["arch"]) and "x64" in t["sha256"], name
        assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in t["sha256"].values()), name
    assert WIN["python"]["signer"] == "Python Software Foundation"


def test_windows_pins_agree_with_the_pins_they_mirror():
    assert WIN["claude"]["version"] == M["mods"]["claude_version"]
    assert WIN["gh"]["version"] == M["user_space"]["gh"]["version"]
    assert WIN["ollama"]["version"] == M["user_space"]["ollama"]["version"]
    assert WIN["node"]["version"].split(".")[0] == str(M["user_space"]["node"]["major"])


def test_no_windows_installer_runs_a_remote_script_and_no_hint_says_winget():
    for d in M["deps"]:
        text = " ".join(map(str, d.get("install_windows") or [])).lower()
        assert "iex" not in text and "irm " not in text, d["id"]
    for p in M["prereqs"]:
        assert "winget" not in str(p.get("install_windows", "")).lower(), p["id"]


def test_the_python_prereq_probes_the_interpreter_instead_of_trusting_a_name():
    py = next(p for p in M["prereqs"] if p["id"] == "python3")
    assert py["probe"] == "python"


# --- ollama URLs: 127.0.0.1, never localhost (A4v2-05 / A6v2-06) ------------------------------------ #
_OLLAMA_ENV = (("jcodemunch", "OPENAI_API_BASE"), ("jcodemunch", "OPENAI_BASE_URL"),
               ("jdocmunch", "JDOCMUNCH_OPENAI_COMPAT_URL"))


def _literal_env(server: str) -> dict:
    add = SERVERS[server]["add"]
    return dict(add[i + 1].split("=", 1) for i, a in enumerate(add) if a == "-e")


def _env_of(server: str, key: str) -> str:
    return _literal_env(server)[key]


def test_no_ollama_url_in_the_manifest_names_localhost():
    """`localhost` resolves ::1 first and ollama listens on 127.0.0.1 only: 2.05 s per new connection
    (urlopen x5 = 2041-2100 ms, `127.0.0.1` 5-31 ms). Works on Linux too."""
    assert "localhost:11434" not in json.dumps(M)
    for server, key in _OLLAMA_ENV:
        assert urlparse(_env_of(server, key)).hostname == "127.0.0.1", (server, key)


def test_a_live_registration_with_the_old_url_is_picked_up_by_the_env_reconcile(tmp_path, monkeypatch):
    """The live `~/.claude.json` entries update through `deps.reconcile_mcp_env` on the next install /
    self-heal: the dry-run plan names the three keys, and nothing once they match."""
    import deps
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))
    old = {s: {"command": "x", "env": {k: "http://localhost:11434/v1" for sv, k in _OLLAMA_ENV if sv == s}}
           for s in ("jcodemunch", "jdocmunch")}
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": old}), encoding="utf-8")
    plan = dict(deps.reconcile_mcp_env(dry_run=True))
    assert "OPENAI_API_BASE" in plan["jcodemunch"] and "OPENAI_BASE_URL" in plan["jcodemunch"]
    assert "JDOCMUNCH_OPENAI_COMPAT_URL" in plan["jdocmunch"]
    new = {s: {"command": "x", "env": _literal_env(s)} for s in ("jcodemunch", "jdocmunch")}
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": new}), encoding="utf-8")
    assert deps.reconcile_mcp_env(dry_run=True) == []

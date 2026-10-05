"""Smoke tests for the 18 dispatch links no other test named (audit 2026-10-05 I-05, WP7).

Each link fires from a COPY of hooks/ in a tmp root, so the scripts that keep state
next to their own file (`hooks/.state`) write into the sandbox, never the live tree.
HOME, CLAUDE_CONFIG_DIR, telemetry and state dirs point at tmp too. Assertions are
stable contracts (exit 0, empty-or-JSON stdout, decision keys), never message wording:
other packages edit some of these scripts in parallel.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LIVE_HOOKS = _ROOT / "hooks"

UNTESTED = [
    "settings-permissions-selfheal", "state-cleanup", "ponytail-session",
    "first-write-skill-gate", "dox-write-gate-write", "bash-write-gate", "jdoc-doc-steer",
    "graphify-enforce", "skill-invocation-tracker", "codex-capture", "post-write-aggregator",
    "desloppify-cleanup", "santa-method-writer", "security-semgrep-tracker", "weights-loop",
    "subagent-context", "permissions-deny-guard", "settings-permissions-selfheal-end",
]
_EVENT = {"session-start": "SessionStart", "pre-tool-use": "PreToolUse",
          "post-tool-use": "PostToolUse", "stop": "Stop", "subagent-start": "SubagentStart",
          "config-change": "ConfigChange", "session-end": "SessionEnd"}


@pytest.fixture(scope="module")
def box(tmp_path_factory):
    base = tmp_path_factory.mktemp("wp7-links")
    root = base / "claude"
    shutil.copytree(_LIVE_HOOKS, root / "hooks",
                    ignore=shutil.ignore_patterns(".state", ".telemetry", "__pycache__", "tests"))
    shutil.copy2(_ROOT / "settings.template.json", root / "settings.template.json")
    home, ws = base / "home", base / "ws"
    for d in (home / ".claude", ws, base / "tel", base / "state"):
        d.mkdir(parents=True)
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "CLAUDE_CONFIG_DIR": str(home / ".claude"), "CLAUDE_HOOK_DOCTOR": "1",
           "CLAUDE_HOOK_TELEMETRY_DIR": str(base / "tel"), "CLAUDE_HOOK_STATE_DIR": str(base / "state"),
           "CLAUDE_PROJECT_DIR": str(ws)}
    env.pop("BASH_WRITE_GATE_DENY_SHELL_WRITES", None)
    return {"root": root, "home": home, "ws": ws, "env": env}


def _links(root: Path) -> dict:
    cfg = json.loads((root / "hooks" / "dispatch.config.json").read_text(encoding="utf-8"))
    return {link["id"]: (chain, link) for chain, links in cfg["chains"].items() for link in links}


def _tool_input(tool: str, ws: Path) -> dict:
    return {"Write": {"file_path": str(ws / "notes.txt"), "content": "x\n"},
            "Bash": {"command": "ls"},
            "Read": {"file_path": str(ws / "README.txt")},
            "Skill": {"skill": "verification-loop"},
            "Task": {"prompt": "hi", "subagent_type": "general-purpose", "description": "d"},
            }.get(tool, {})


def _payload(chain: str, link: dict, ws: Path) -> dict:
    p = {"hook_event_name": _EVENT[chain], "session_id": "wp7-smoke", "cwd": str(ws)}
    tools = link.get("tools")
    if tools:
        tool = tools.split("|")[0]
        p.update(tool_name=tool, tool_input=_tool_input(tool, ws))
        if chain == "post-tool-use":
            p["tool_response"] = {}
    if chain == "session-start":
        p["source"] = "startup"
    if chain == "subagent-start":
        p.update(agent_id="a1", agent_type="general-purpose")
    if chain == "config-change":
        p.update(source="user_settings", file_path=str(ws / "settings.json"))
    return p


def _fire(box, cmd: list, payload: dict, **env_over) -> subprocess.CompletedProcess:
    subs = {"{PY}": sys.executable, "{HOOKS}": str(box["root"] / "hooks"), "{HOME}": str(box["home"])}
    argv = [subs.get(c, c) if c in subs else
            c.replace("{HOOKS}", subs["{HOOKS}"]).replace("{HOME}", subs["{HOME}"]) for c in cmd]
    env = {**box["env"], **env_over}
    return subprocess.run(argv, input=json.dumps(payload), capture_output=True, text=True,
                          timeout=30, cwd=str(box["ws"]), env=env)


def _json_or_empty(out: str):
    out = out.strip()
    return {} if not out else json.loads(out)


def test_every_listed_link_is_still_wired(box):
    links = _links(box["root"])
    missing = [i for i in UNTESTED if i not in links]
    assert not missing, f"renamed or removed dispatch links: {missing}"


@pytest.mark.parametrize("link_id", UNTESTED)
def test_link_fires_clean(box, link_id):
    chain, link = _links(box["root"])[link_id]
    script = next(c for c in link["cmd"] if c.endswith(".py"))
    assert Path(script.replace("{HOOKS}", str(box["root"] / "hooks"))).is_file(), script
    cp = _fire(box, link["cmd"], _payload(chain, link, box["ws"]))
    assert cp.returncode == 0, cp.stderr[-400:]
    assert "Traceback" not in cp.stderr, cp.stderr[-400:]
    assert isinstance(_json_or_empty(cp.stdout), dict)


def _decision(out: str) -> str:
    data = _json_or_empty(out)
    return ((data.get("hookSpecificOutput") or {}).get("permissionDecision")
            or data.get("decision") or "allow")


def test_ponytail_session_injects_the_directive(box):
    chain, link = _links(box["root"])["ponytail-session"]
    ctx = _json_or_empty(_fire(box, link["cmd"], _payload(chain, link, box["ws"])).stdout)
    assert "ponytail" in ctx["hookSpecificOutput"]["additionalContext"].lower()


def test_subagent_context_carries_the_write_protocol(box):
    chain, link = _links(box["root"])["subagent-context"]
    ctx = _json_or_empty(_fire(box, link["cmd"], _payload(chain, link, box["ws"])).stdout)
    text = ctx["hookSpecificOutput"]["additionalContext"]
    assert "Edit" in text and "Write" in text


def test_bash_write_gate_is_advisory_by_default_and_denies_when_armed(box):
    chain, link = _links(box["root"])["bash-write-gate"]
    payload = _payload(chain, link, box["ws"])
    payload["tool_input"] = {"command": "sed -i 's/a/b/' src/app.py"}
    assert _decision(_fire(box, link["cmd"], payload).stdout) != "deny"
    armed = _fire(box, link["cmd"], payload, BASH_WRITE_GATE_DENY_SHELL_WRITES="1")
    assert _decision(armed.stdout) == "deny"


def test_dox_write_gate_denies_code_in_a_rootless_repo_then_allows_the_override(box, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    chain, link = _links(box["root"])["dox-write-gate-write"]
    payload = _payload(chain, link, box["ws"])
    payload.update(session_id="wp7-dox", tool_input={"file_path": str(repo / "app.py"), "content": "x=1\n"})
    assert _decision(_fire(box, link["cmd"], payload).stdout) == "deny"
    assert _decision(_fire(box, link["cmd"], payload).stdout) != "deny"  # same edit again = override
    doc = dict(payload, tool_input={"file_path": str(repo / "NOTES.md"), "content": "x\n"})
    assert _decision(_fire(box, link["cmd"], doc).stdout) != "deny"
    (repo / "CLAUDE.md").write_text("# r\n", encoding="utf-8")
    other = dict(payload, session_id="wp7-dox-2")
    assert _decision(_fire(box, link["cmd"], other).stdout) != "deny"


def _selfheal_module(box):
    spec = importlib.util.spec_from_file_location(
        "wp7_selfheal", box["root"] / "hooks" / "settings-permissions-selfheal.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_permissions_deny_guard_heals_and_blocks(box, tmp_path, capsys):
    mod = _selfheal_module(box)
    live = tmp_path / "settings.json"
    live.write_text(json.dumps({"permissions": {"deny": ["Read"], "allow": ["Bash"]}}), encoding="utf-8")
    mod.LIVE = live
    assert mod.config_change() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    data = json.loads(live.read_text(encoding="utf-8"))
    assert data["permissions"] == {"deny": [], "allow": ["Bash"]}


def test_selfheal_resyncs_deny_from_the_template_and_is_silent_in_sync(box, tmp_path, capsys):
    mod = _selfheal_module(box)
    mod.LIVE, mod.TEMPLATE = tmp_path / "settings.json", tmp_path / "settings.template.json"
    mod.TEMPLATE.write_text(json.dumps({"permissions": {"deny": []}}), encoding="utf-8")
    mod.LIVE.write_text(json.dumps({"permissions": {"deny": ["Grep"]}}), encoding="utf-8")
    assert mod.heal_from_template() == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    assert json.loads(mod.LIVE.read_text(encoding="utf-8"))["permissions"]["deny"] == []
    mod.heal_from_template()
    assert capsys.readouterr().out == ""


def test_doctor_mode_never_touches_settings(box):
    live = box["root"] / "settings.json"
    live.write_text(json.dumps({"permissions": {"deny": ["Read"]}}), encoding="utf-8")
    chain, link = _links(box["root"])["permissions-deny-guard"]
    cp = _fire(box, link["cmd"], _payload(chain, link, box["ws"]))
    assert cp.returncode == 0 and _decision(cp.stdout) != "block"
    assert json.loads(live.read_text(encoding="utf-8"))["permissions"]["deny"] == ["Read"]

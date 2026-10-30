"""settings-protection-gate.py (R2-F2): a Write/Edit of a file that grants permissions or routes models
(`.claude/settings{,.local,.user}.json` in any repo or ~/.claude, ~/.claude/hooks/model-policy.json,
~/.claude.json) asks, new files included, never downgraded for subagents or unattended sessions; the turn's
human prompt naming the file by its `.claude/` path or a permission-rule phrase is the escape (bare
"settings"/"permission" and a bare `settings.json` basename are not), and (FIX2 item 1) a move, delete,
truncate or `git checkout|restore` of the gates' wiring."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


@pytest.fixture(autouse=True)
def _attended(monkeypatch):
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "1")


@pytest.fixture()
def sp(monkeypatch):
    spec = importlib.util.spec_from_file_location(f"sp_{uuid.uuid4().hex}", HOOKS / "settings-protection-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    calls: list[dict] = []
    monkeypatch.setattr(mod, "_telemetry", lambda **kw: calls.append(kw))
    mod.calls = calls
    return mod


def _run(mod, monkeypatch, payload) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert mod.main() == 0
    return json.loads(out.getvalue() or "{}")


def _write(path, tool="Write", transcript=None, **extra) -> dict:
    ti = {"file_path": str(path), "content": '{"permissions":{"allow":["Bash(*)"]}}'} if tool == "Write" else \
        {"file_path": str(path), "old_string": "a", "new_string": "b"}
    p = {"tool_name": tool, "tool_input": ti, "session_id": f"sp-{uuid.uuid4().hex}", **extra}
    if transcript:
        p["transcript_path"] = str(transcript)
    return p


def _decision(out: dict) -> str | None:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision")


def _transcript(tmp_path: Path, text: str) -> Path:
    t = tmp_path / f"t-{uuid.uuid4().hex}.jsonl"
    t.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": text},
                             "timestamp": "2026-10-30T10:00:00Z"}) + "\n", encoding="utf-8")
    return t


def test_new_repo_settings_local_asks(sp, monkeypatch):
    out = _run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json"))
    assert _decision(out) == "ask"
    assert "settings.local.json" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert sp.calls[-1]["decision"] == "ask"


def test_subagent_is_denied_never_downgraded(sp, monkeypatch):
    out = _run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", agent_id="a1"))
    assert _decision(out) == "deny" and "subagent" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert sp.calls[-1]["decision"] == "deny"


def test_unattended_env_is_denied(sp, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    assert _decision(_run(sp, monkeypatch, _write("/x/repo/.claude/settings.json"))) == "deny"


def test_headless_print_session_is_denied(sp, monkeypatch):
    """Live r3: under `claude -p --permission-mode bypassPermissions` an `ask` let the Write through
    (no prompt, no permission_denials); the harness marks such a session CLAUDE_CODE_SESSION_ATTENDED=0."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    out = _run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", permission_mode="bypassPermissions"))
    assert _decision(out) == "deny" and "unattended" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_headless_prompt_naming_the_file_still_escapes(sp, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    t = _transcript(tmp_path, "add an allow rule to settings.local.json")
    assert _run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", transcript=t)) == {}


def test_prompt_naming_the_file_escapes(sp, monkeypatch, tmp_path):
    t = _transcript(tmp_path, "add an allow rule to settings.local.json")
    assert _run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", transcript=t)) == {}
    assert sp.calls[-1]["decision"] == "escape"


def test_prompt_saying_permissions_escapes(sp, monkeypatch, tmp_path):
    t = _transcript(tmp_path, "Allow npm commands: add a permission rule please")
    assert _run(sp, monkeypatch, _write("/x/repo/.claude/settings.json", transcript=t)) == {}


@pytest.mark.parametrize("prompt", [
    "fix the spacing on the user settings page of the web app",
    "fix the permission denied error when uploading a file",
    "the settings modal loses its state on refresh",
    "permissions look wrong on the uploads folder (chmod)",
    "Allow npm commands: update the Permissions please",
    "add app-dev.example.com to the CORS allowlist in server/.env",
    "fix the IP allow list check in the nginx config",
    "format .vscode/settings.json with 2 spaces",
    "the .vscode/settings.json has a trailing comma",
    "update the task rules in the plan before the sprint",  # SANTA-GATE 1: "ask rule" inside "task rules"
    "a shallow rule of thumb for the cache",                 # "allow rule" inside "shallow rule"
])
def test_incidental_settings_or_permission_word_does_not_escape(sp, monkeypatch, tmp_path, prompt):
    """Live r3: the bare words "settings"/"permission" let an unrelated turn write Bash(*) into settings."""
    t = _transcript(tmp_path, prompt)
    assert _decision(_run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", transcript=t))) == "ask"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    assert _decision(_run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", transcript=t))) == "deny"


@pytest.mark.parametrize("prompt", ["format .vscode/settings.json with 2 spaces",
                                    "the .vscode/settings.json has a trailing comma"])
@pytest.mark.parametrize("path", ["/x/repo/.claude/settings.json", str(Path.home() / ".claude/settings.json")])
def test_vscode_settings_basename_does_not_escape(sp, monkeypatch, tmp_path, prompt, path):
    """FINAL-REVERIFY R1: VS Code's `.vscode/settings.json` shares the basename; it must not open the Claude file."""
    t = _transcript(tmp_path, prompt)
    assert _decision(_run(sp, monkeypatch, _write(path, transcript=t))) == "ask"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    assert _decision(_run(sp, monkeypatch, _write(path, transcript=t))) == "deny"


def test_bare_basename_without_claude_dir_asks(sp, monkeypatch, tmp_path):
    """Option A: the settings files escape only when the prompt names them by their `.claude/` path."""
    path = "/x/repo/.claude/settings.local.json"
    t = _transcript(tmp_path, "edit settings.local.json and add Bash(npm *)")
    assert _decision(_run(sp, monkeypatch, _write(path, transcript=t))) == "ask"
    t = _transcript(tmp_path, "edit .claude/settings.local.json and add Bash(npm *)")
    assert _run(sp, monkeypatch, _write(path, transcript=t)) == {}
    assert sp.calls[-1]["decision"] == "escape"


@pytest.mark.parametrize("prompt,rel", [
    ("add an allow rule to settings.local.json", ".claude/settings.local.json"),
    ("edit .claude/settings.json and allow npm", ".claude/settings.json"),
    ("edit .claude\\settings.json and allow npm", ".claude/settings.json"),
    ("add a permission rule for Bash(npm *) in this repo", ".claude/settings.local.json"),
    ("update permissions.allow for the reticle MCP", ".claude/settings.local.json"),
    ("bump the judge effort in model-policy.json", ".claude/hooks/model-policy.json"),
    ("set the theme in ~/.claude.json", ".claude.json"),
])
def test_named_file_or_permission_rule_phrase_escapes(sp, monkeypatch, tmp_path, prompt, rel):
    t = _transcript(tmp_path, prompt)
    path = Path.home() / rel if "settings" not in rel else f"/x/repo/{rel}"
    assert _run(sp, monkeypatch, _write(path, transcript=t)) == {}
    assert sp.calls[-1]["decision"] == "escape"


def test_unrelated_prompt_still_asks(sp, monkeypatch, tmp_path):
    t = _transcript(tmp_path, "fix the failing test in calc.py")
    assert _decision(_run(sp, monkeypatch, _write("/x/repo/.claude/settings.local.json", transcript=t))) == "ask"


@pytest.mark.parametrize("rel", [".claude/settings.json", ".claude/settings.user.json", ".claude/hooks/model-policy.json",
                                 ".claude.json"])
def test_home_files_ask(sp, monkeypatch, rel):
    assert _decision(_run(sp, monkeypatch, _write(Path.home() / rel, tool="Edit"))) == "ask"


def test_relative_path_resolves_against_cwd(sp, monkeypatch):
    out = _run(sp, monkeypatch, _write(".claude/settings.local.json", cwd="/x/repo"))
    assert _decision(out) == "ask"


def test_multiedit_and_notebook_keys(sp, monkeypatch):
    p = {"tool_name": "MultiEdit", "tool_input": {"file_path": "/x/r/.claude/settings.json", "edits": []}, "session_id": "s"}
    assert _decision(_run(sp, monkeypatch, p)) == "ask"


@pytest.mark.parametrize("path", ["/x/repo/src/settings.json", "/x/repo/.claude/settings.template.json",
                                  "/x/repo/.claude/hooks/model-policy.json", "/x/repo/package.json"])
def test_other_files_are_free(sp, monkeypatch, path):
    assert _run(sp, monkeypatch, _write(path)) == {}
    assert sp.calls == []


def test_non_write_tools_are_free(sp, monkeypatch):
    p = {"tool_name": "Read", "tool_input": {"file_path": "/x/repo/.claude/settings.json"}, "session_id": "s"}
    assert _run(sp, monkeypatch, p) == {}


# --- SANTA-FINAL fix 4: a Bash/PowerShell command that writes a protected file ----------------------
def _bash(cmd, tool="Bash", **extra) -> dict:
    return {"tool_name": tool, "tool_input": {"command": cmd}, "session_id": f"sp-{uuid.uuid4().hex}",
            "cwd": "/x/repo", **extra}


@pytest.mark.parametrize("cmd,tool", [
    ("cat > .claude/settings.local.json <<'EOF'\n{\"permissions\":{\"allow\":[\"Bash(*)\"]}}\nEOF", "Bash"),
    ("cat <<'EOF' > .claude/settings.local.json\n{}\nEOF", "Bash"),
    ("cp /tmp/x.json .claude/settings.local.json", "Bash"),
    ("python3 - <<'EOF'\nopen(\".claude/settings.local.json\",\"w\").write(\"{}\")\nEOF", "Bash"),
    ("echo '{}' > $HOME/.claude/settings.json", "Bash"),
    ("sed -i 's/a/b/' ~/.claude/hooks/model-policy.json", "Bash"),
    ("Set-Content -Path .claude\\settings.local.json -Value '{}'", "PowerShell"),
])
def test_shell_write_of_a_protected_file_is_denied_for_a_subagent(sp, monkeypatch, cmd, tool):
    out = _run(sp, monkeypatch, _bash(cmd, tool=tool, agent_id="a1"))
    assert _decision(out) == "deny", (cmd, out)


@pytest.mark.parametrize("cmd", ["cat .claude/settings.json", "jq . .claude/settings.json > /tmp/out.json",
                                 "python3 installer/render.py", "cp .claude/settings.json /tmp/backup.json"])
def test_shell_reads_of_a_protected_file_are_free(sp, monkeypatch, cmd):
    assert _run(sp, monkeypatch, _bash(cmd, agent_id="a1")) == {}


def test_dispatcher_denies_a_subagent_heredoc_every_time(tmp_path):
    cmd = "cat > .claude/settings.local.json <<'EOF'\n{\"permissions\":{\"allow\":[\"Bash(*)\"]}}\nEOF"
    p = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd},
                    "session_id": f"sp-{uuid.uuid4().hex}", "agent_id": "a1", "cwd": str(tmp_path)})
    import os  # noqa: PLC0415
    env = {**os.environ, "CLAUDE_HOOK_STATE_DIR": str(tmp_path / "state"), "CLAUDE_CODE_SESSION_ATTENDED": "1"}
    for _ in range(2):
        cp = subprocess.run([sys.executable, str(HOOKS / "dispatch.py"), "pre-tool-use"], input=p,
                            capture_output=True, text=True, timeout=60, env=env)
        assert '"permissionDecision": "deny"' in cp.stdout.replace('":"', '": "'), (cp.stdout, cp.stderr[-400:])


# --- SANTA-FINAL B/F3: NTFS is case-insensitive -------------------------------------------------------
def test_windows_basename_is_case_folded(sp, monkeypatch):
    monkeypatch.setattr(sp.plat, "IS_WINDOWS", True)
    assert sp.protected("/x/repo/.Claude/Settings.JSON") == "settings.json"
    assert sp.protected(str(Path.home() / ".Claude.json")) == ".claude.json"
    monkeypatch.setattr(sp.plat, "IS_WINDOWS", False)
    assert sp.protected("/x/repo/.claude/Settings.JSON") is None


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", '{"tool_name": "Write", "tool_input": "x"}'])
def test_garbage_stdin_is_quiet(sp, monkeypatch, raw):
    assert _run(sp, monkeypatch, raw) == {}


# --- audit2 C6 (SP-2, RT-1): the gates protect their own wiring; a read-only open( passes ---------------
def _cd(sp) -> Path:
    return sp.plat.claude_dir()


@pytest.mark.parametrize("make", [
    lambda cd: _write(cd / "hooks" / "dispatch.config.json"),
    lambda cd: _write(cd / "hooks" / "dangerous-bash-gate.py", tool="Edit"),
    lambda cd: _write(cd / "settings.template.json"),
    lambda cd: _write(cd / "installer" / "manifest.json"),
    lambda cd: _bash(f"touch {cd}/.blast-bypass"),
    lambda cd: _bash(f"sed -i 's/true/false/' {cd}/hooks/dispatch.config.json"),
])
def test_gate_wiring_asks_and_denies_unattended(sp, monkeypatch, make):
    cd = _cd(sp)
    assert _decision(_run(sp, monkeypatch, make(cd))) == "ask"
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ATTENDED", "0")
    assert _decision(_run(sp, monkeypatch, make(cd))) == "deny"


@pytest.mark.parametrize("rel,prompt", [
    ("hooks/dispatch.config.json", "enable the observe link in dispatch.config.json"),
    ("hooks/dangerous-bash-gate.py", "tighten dangerous-bash-gate.py for HUSKY=0"),
    ("installer/manifest.json", "pin pyright in manifest.json"),
])
def test_prompt_naming_the_wiring_file_escapes(sp, monkeypatch, tmp_path, rel, prompt):
    t = _transcript(tmp_path, prompt)
    assert _run(sp, monkeypatch, _write(_cd(sp) / rel, transcript=t)) == {}
    assert sp.calls[-1]["decision"] == "escape"


def test_wiring_names_outside_claude_dir_are_free(sp, monkeypatch, tmp_path):
    assert _run(sp, monkeypatch, _write(tmp_path / "repo" / "installer" / "manifest.json")) == {}
    assert _run(sp, monkeypatch, _write(tmp_path / "repo" / "hooks" / "x-gate.py")) == {}


def test_read_only_open_is_not_a_write(sp, monkeypatch):
    home = Path.home()
    read = f"python3 -c \"import json;print(len(json.load(open('{home}/.claude.json'))))\""
    assert _run(sp, monkeypatch, _bash(read, agent_id="a1")) == {}
    write = f"python3 -c \"open('{home}/.claude.json','w').write('{{}}')\""
    assert _decision(_run(sp, monkeypatch, _bash(write, agent_id="a1"))) == "deny"
    pw = f"python3 -c \"import pathlib; pathlib.Path('{_cd(sp)}/settings.json').write_text('x')\""
    assert _decision(_run(sp, monkeypatch, _bash(pw, agent_id="a1"))) == "deny"


# --- FIX2 item 1 (REVERIFY R3): moving, deleting, emptying or restoring the wiring is a write too ------------
@pytest.fixture()
def home_cd(monkeypatch):
    """The probes spell `~/.claude` as REVERIFY did: the config dir must be the default one."""
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)


_R3_PROBES = [
    "mv ~/.claude/hooks/dispatch.config.json /tmp/x.json",                    # b1
    "rm ~/.claude/hooks/dangerous-bash-gate.py",                              # b2
    "cd ~/.claude/hooks && cp /tmp/x.json dispatch.config.json",              # b3
    "mv ~/.claude/hooks ~/.claude/hooks.off",                                 # b4
    "dd if=/dev/null of=$HOME/.claude/hooks/dispatch.config.json",            # b5
    "git -C ~/.claude checkout HEAD~5 -- hooks/dangerous-bash-gate.py",       # b6
]
_R3_MORE = [
    "rm -rf ~/.claude/hooks",
    "unlink ~/.claude/settings.template.json",
    "truncate ~/.claude/hooks/dispatch.config.json -s 0",
    "sudo mv ~/.claude/installer/manifest.json /tmp/m.json",
    "cd ~/.claude && git restore --source=HEAD~3 hooks/settings-protection-gate.py",
    "cd ~/.claude && git checkout -- .",
    "cp /tmp/dispatch.config.json ~/.claude/hooks/",
    "bash -c 'rm ~/.claude/hooks/dispatch.config.json'",
    "rm ~/.claude/state/dispatch.config.lkg.json",
    "mv ~/.claude/hooks/dispatch.config.json /tmp/x.json; echo '",            # an unbalanced quote
    "cd ~/.claude/hooks\nrm dispatch.config.json",
]


@pytest.mark.parametrize("cmd", _R3_PROBES + _R3_MORE)
def test_move_delete_or_restore_of_the_wiring_asks_and_denies_unattended(sp, monkeypatch, home_cd, cmd):
    assert _decision(_run(sp, monkeypatch, _bash(cmd))) == "ask", cmd
    assert _decision(_run(sp, monkeypatch, _bash(cmd, agent_id="a1"))) == "deny", cmd
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    assert _decision(_run(sp, monkeypatch, _bash(cmd))) == "deny", cmd


def test_powershell_remove_item_of_the_wiring_asks(sp, monkeypatch, home_cd):
    out = _run(sp, monkeypatch, _bash("Remove-Item -Path ~/.claude/hooks/dispatch.config.json", tool="PowerShell"))
    assert _decision(out) == "ask"


@pytest.mark.parametrize("cmd", [
    "cp ~/.claude/hooks/dispatch.config.json /tmp/x.json",
    "cd ~/.claude/hooks && cat dispatch.config.json",
    "cd ~/.claude && git diff -- hooks/dispatch.config.json",
    "cd ~/.claude && git checkout -b fix/x",
    "git -C ~/.claude status --short",
    "rm -rf ~/.claude/hooks/__pycache__",
    "mv /tmp/a.json /tmp/b.json",
    "cd /tmp && rm -f settings.json",
    "rm hooks/x-gate.py",
    "cd ~/.claude/hooks && python3 -m pytest tests -q",
    "truncate -s 0 /tmp/log.txt",
    "cp /tmp/notes.md ~/.claude/hooks/",
])
def test_reads_and_unrelated_moves_stay_free(sp, monkeypatch, home_cd, cmd):
    assert _run(sp, monkeypatch, _bash(cmd, agent_id="a1")) == {}, cmd


def test_a_moved_hooks_dir_cannot_be_escaped_by_the_prompt(sp, monkeypatch, home_cd, tmp_path):
    t = _transcript(tmp_path, "move ~/.claude/hooks/ to hooks.off and edit .claude/settings.json")
    assert _decision(_run(sp, monkeypatch, _bash("mv ~/.claude/hooks ~/.claude/hooks.off", transcript_path=str(t)))) \
        == "ask"


def test_script_exits_zero_on_garbage():
    cp = subprocess.run([sys.executable, str(HOOKS / "settings-protection-gate.py")], input="{oops",
                        capture_output=True, text=True, timeout=20)
    assert cp.returncode == 0 and cp.stdout.strip() == "{}"

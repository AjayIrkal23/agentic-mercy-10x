"""replica_sync.py — key-only SSH pull + render + init check on the Windows replica (fake ssh on PATH)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

_spec = importlib.util.spec_from_file_location("replica_sync", _ROOT / "scripts" / "replica_sync.py")
R = importlib.util.module_from_spec(_spec)
sys.modules["replica_sync"] = R  # dataclasses resolve string annotations through sys.modules
_spec.loader.exec_module(R)  # type: ignore[union-attr]

HOME_FWD = "C:/Users/Someone"
HOME_BS = HOME_FWD.replace("/", "\\")

_FAKE_SSH = """#!/usr/bin/env python3
import json, os, sys
cmd = sys.argv[-1]
with open(os.environ["FAKE_SSH_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
fail = os.environ.get("FAKE_SSH_FAIL")
if fail and fail in cmd:
    sys.exit(1)
if "claude -p" in cmd:
    print(os.environ.get("FAKE_SSH_INIT", json.dumps({"type": "system", "subtype": "init", "model": "x", "tools": []})))
elif "render.py" in cmd:
    print("rendered settings.json")
elif "git " in cmd:
    print("Already up to date.")
"""

posix_only = pytest.mark.skipif(plat.IS_WINDOWS, reason="fake ssh is a POSIX shebang script")


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setattr(R.plat, "IS_WINDOWS", False)
    for k in ("CLAUDE_REPLICA_SSH", "CLAUDE_REPLICA_HOME", "FAKE_SSH_FAIL", "FAKE_SSH_INIT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    b = tmp_path / "bin"
    b.mkdir()
    ssh = b / "ssh"
    ssh.write_text(_FAKE_SSH, encoding="utf-8")
    ssh.chmod(0o755)
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    monkeypatch.setenv("PATH", f"{b}{os.pathsep}{os.environ['PATH']}")
    return log


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []


def _use_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_REPLICA_SSH", "someone@198.51.100.5")
    monkeypatch.setenv("CLAUDE_REPLICA_HOME", HOME_FWD)


def _machines(tmp_path) -> Path:
    claude = HOME_BS + "\\.claude"
    text = ("# Machines\n- **This PC** — `me@198.51.100.1`\n"
            "- **Dev PC #2** — `someone@198.51.100.5` (static; was .50 earlier, try both: `someone@198.51.100.50`)\n"
            f"  Claude replica: full `~/.claude` -> `{claude}` (native claude).\n"
            "- **Cloud VMs** — `root@203.0.113.9`\n")
    p = tmp_path / "machines.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_host_from_env_wins(monkeypatch, tmp_path):
    _use_env(monkeypatch)
    rep = R.discover(os.environ, _machines(tmp_path))
    steps = R.plan(rep)
    assert len(steps) == 3
    argv = R.ssh_argv(rep.host, steps[0].cmd, rep.home_fwd)
    assert argv[:6] == ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "someone@198.51.100.5"]
    want = (f"set USERPROFILE={HOME_BS}&& set HOME={HOME_BS}&& set PYTHONUTF8=1&& "
            f"set LOCALAPPDATA={HOME_BS}\\AppData\\Local&& set APPDATA={HOME_BS}\\AppData\\Roaming&& "
            f"set PATH={HOME_BS}\\.local\\bin;%PATH%&& ")
    assert argv[6].startswith(want)


@posix_only
def test_three_commands_in_order(monkeypatch, _env, capsys):
    _use_env(monkeypatch)
    assert R.main(["--machines", "/nonexistent"]) == 0
    cmds = [c[-1] for c in _calls(_env)]
    assert len(cmds) == 3
    assert f"git -C {HOME_BS}\\.claude -c safe.directory=* pull --ff-only" in cmds[0]
    assert f"py -3 {HOME_BS}\\.claude\\installer\\render.py" in cmds[1]
    assert "claude -p --bare --output-format stream-json --verbose --max-turns 1 ok" in cmds[2]
    assert capsys.readouterr().out.rstrip().endswith("replica_sync: PASS")


def test_machines_file_fallback(tmp_path):
    rep = R.discover({}, _machines(tmp_path))
    assert rep.host == "someone@198.51.100.5"
    assert rep.fallbacks == ["someone@198.51.100.50"]
    assert rep.home_fwd == HOME_FWD


def test_missing_host_is_skip(tmp_path, capsys):
    assert R.main(["--machines", str(tmp_path / "none.md")]) == 0
    assert ("replica_sync: SKIP (no replica host: set CLAUDE_REPLICA_SSH or add the Dev PC bullet to the "
            "machines file)") in capsys.readouterr().out


@posix_only
def test_ssh_failure_is_warn_not_fail(monkeypatch, _env, capsys):
    _use_env(monkeypatch)
    monkeypatch.setenv("FAKE_SSH_FAIL", "pull")
    assert R.main(["--machines", "/nonexistent"]) == 0
    out = capsys.readouterr().out
    assert "pull WARN(rc=1)" in out and "render SKIP(pull failed)" in out
    assert out.rstrip().endswith("replica_sync: WARN")
    cmds = [c[-1] for c in _calls(_env)]
    assert len(cmds) == 2 and "claude -p" in cmds[1]


@posix_only
def test_init_check_requires_init_event(monkeypatch, _env, capsys):
    _use_env(monkeypatch)
    monkeypatch.setenv("FAKE_SSH_INIT", json.dumps({"type": "result"}))
    assert R.main(["--machines", "/nonexistent"]) == 0
    assert "init WARN(no init event)" in capsys.readouterr().out


def test_connection_error_tries_fallback(monkeypatch, tmp_path):
    rep = R.discover({}, _machines(tmp_path))
    seen = []

    def fake_run(argv, **kw):
        seen.append(argv[5])
        rc = 255 if argv[5] == rep.host else 0
        return plat.subprocess.CompletedProcess(argv, rc, "Already up to date.", "")
    status = R.run_step(R.plan(rep)[0], rep, run=fake_run)
    assert status == "OK" and seen == ["someone@198.51.100.5", "someone@198.51.100.50"]


def test_dry_run_prints_plan_only(monkeypatch, _env, capsys):
    _use_env(monkeypatch)
    assert R.main(["--dry-run", "--machines", "/nonexistent"]) == 0
    out = capsys.readouterr().out
    assert _calls(_env) == []
    assert sum(1 for line in out.splitlines() if line.startswith("plan ")) == 3


def test_windows_host_side_refuses(monkeypatch, capsys):
    monkeypatch.setattr(R.plat, "IS_WINDOWS", True)
    assert R.main([]) == 2
    assert "run replica_sync from the Linux workstation" in capsys.readouterr().out


# ---- FI-9: a POSIX replica (another Ubuntu box) ----------------------------------------------------------
def test_posix_dry_run_prints_the_pull_and_render(_env, capsys):
    assert R.main(["--posix", "--host", "u@h", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert ("ssh -o BatchMode=yes u@h 'git -C ~/.claude pull --ff-only && "
            "python3 ~/.claude/installer/render.py'") in out
    assert _calls(_env) == []


@posix_only
def test_posix_run_uses_plain_ssh_and_the_doctor(_env, capsys):
    assert R.main(["--posix", "--host", "u@h"]) == 0
    calls = _calls(_env)
    assert calls[0][-1] == "git -C ~/.claude pull --ff-only && python3 ~/.claude/installer/render.py"
    assert calls[1][-1] == "python3 ~/.claude/installer/doctor.py | tail -1"
    assert all("USERPROFILE" not in c[-1] for c in calls)
    assert "replica_sync: PASS" in capsys.readouterr().out


def test_posix_without_a_host_is_a_skip(_env, capsys):
    assert R.main(["--posix"]) == 0
    assert "SKIP" in capsys.readouterr().out and _calls(_env) == []

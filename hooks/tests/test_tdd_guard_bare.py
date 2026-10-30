"""tdd-guard: one init mode, stack detection, `claude -p --bare` validator, ≤500-char advisory
(PKG hooks-hygiene-mod steps 8-9). Fake `claude` / `tdd-guard` binaries on PATH; nothing real runs."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "TDD_GUARD_VALIDATOR")
_WIN = "C:" + "\\"  # split so the G3 drive-literal gate never matches this file


def _load(alias, fname):
    spec = importlib.util.spec_from_file_location(alias, HOOKS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _active_repo(tmp_path, sidecar=None, failing=()) -> Path:
    repo = tmp_path / "proj"
    data = repo / ".claude" / "tdd-guard" / "data"
    data.mkdir(parents=True)
    (data / "config.json").write_text("{}", encoding="utf-8")
    if sidecar is not None:
        (data / ".autoinit.json").write_text(json.dumps(sidecar), encoding="utf-8")
    if failing:
        tests = [{"fullName": n, "state": "failed"} for n in failing] + [{"fullName": "ok one", "state": "passed"}]
        (data / "test.json").write_text(json.dumps({"testModules": [{"tests": tests}]}), encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo


def _fake(bindir: Path, name: str, body: str) -> None:
    bindir.mkdir(exist_ok=True)
    f = bindir / name
    f.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    f.chmod(0o755)
    (bindir / f"{name}.cmd").write_text(f'@"{sys.executable}" "%~dp0{name}" %*\r\n', encoding="utf-8")


def _fake_tdd_guard(tmp_path) -> Path:
    bindir = tmp_path / "bin"
    marker = tmp_path / "tdd-called"
    _fake(bindir, "tdd-guard", "import sys, pathlib\nsys.stdin.read()\n"
          f"pathlib.Path({str(marker)!r}).touch()\n"
          "print('{\"decision\":\"block\",\"reason\":\"write a test\"}')\n")
    return bindir


def _fake_claude(tmp_path, out: str, rc: int = 0) -> Path:
    bindir = tmp_path / "bin"
    rec = tmp_path / "claude-rec.json"
    _fake(bindir, "claude", "import sys, json, pathlib\n"
          "stdin = sys.stdin.read()\n"
          f"pathlib.Path({str(rec)!r}).write_text(json.dumps({{'argv': sys.argv[1:], 'stdin': stdin}}))\n"
          f"sys.stdout.write({out!r})\n"
          f"sys.exit({rc})\n")
    return bindir


def _launch(tmp_path, repo: Path, file_path: str, *, key: bool = False) -> str:
    env = {k: v for k, v in os.environ.items() if k not in _KEYS}
    env.update({"CLAUDE_PROJECT_DIR": str(repo), "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"})
    if key:
        env["ANTHROPIC_API_KEY"] = "test-key"
    payload = {"session_id": "t", "tool_name": "Edit",
               "tool_input": {"file_path": file_path, "old_string": "a", "new_string": "b"}}
    proc = subprocess.run([sys.executable, str(HOOKS / "tdd_guard_launcher.py")], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=60, env=env)
    return proc.stdout


def test_init_guard_has_one_mode(tmp_path):
    ig = _load("tdd_init", "tdd-guard-init-guard.py")
    assert not hasattr(ig, "run_prompt")
    cp = subprocess.run([sys.executable, str(HOOKS / "tdd-guard-init-guard.py"), "prompt"],
                        input=json.dumps({"cwd": str(tmp_path)}), text=True, capture_output=True, timeout=30)
    assert cp.returncode == 0 and cp.stdout.strip() in ("{}", "")


def test_launcher_skips_a_dormant_auto_managed_repo(tmp_path):
    repo = _active_repo(tmp_path, sidecar={"autoManaged": True, "runners": []})
    _fake_tdd_guard(tmp_path)
    assert _launch(tmp_path, repo, str(repo / "src" / "a.ts")).strip() == ""
    assert not (tmp_path / "tdd-called").exists()
    side = repo / ".claude" / "tdd-guard" / "data" / ".autoinit.json"
    side.write_text(json.dumps({"autoManaged": True, "runners": ["py"]}), encoding="utf-8")
    assert "write a test" in _launch(tmp_path, repo, str(repo / "src" / "a.ts"))


def test_manual_config_without_sidecar_counts_as_a_stack(tmp_path):
    repo = _active_repo(tmp_path)
    _fake_tdd_guard(tmp_path)
    assert "write a test" in _launch(tmp_path, repo, str(repo / "src" / "a.ts"))


def test_bare_validator_argv_and_prompt(tmp_path):
    repo = _active_repo(tmp_path, failing=("Cart adds an item",))
    _fake_claude(tmp_path, json.dumps({"result": json.dumps({"decision": "block", "reason": "no failing test for a.ts"})}))
    out = _launch(tmp_path, repo, str(repo / "src" / "a.ts"), key=True)
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    assert "no failing test" in ctx and len(ctx) <= 500
    rec = json.loads((tmp_path / "claude-rec.json").read_text(encoding="utf-8"))
    for flag in ("-p", "--bare", "--model", "haiku", "--max-turns", "1"):
        assert flag in rec["argv"], flag
    assert "src/a.ts" in rec["stdin"].replace("\\", "/") and "Cart adds an item" in rec["stdin"]
    assert "ok one" not in rec["stdin"]


def test_bare_allow_and_garbage_are_silent(tmp_path):
    repo = _active_repo(tmp_path)
    _fake_claude(tmp_path, json.dumps({"result": json.dumps({"decision": "allow"})}))
    assert _launch(tmp_path, repo, str(repo / "src" / "a.ts"), key=True).strip() == ""
    _fake_claude(tmp_path, "not json")
    assert _launch(tmp_path, repo, str(repo / "src" / "a.ts"), key=True).strip() == ""
    _fake(tmp_path / "bin", "tdd-guard", "import sys\nsys.stdin.read()\n")  # a silent allow, never the real one
    _fake_claude(tmp_path, json.dumps({"result": json.dumps({"decision": "block", "reason": "x"})}), rc=1)
    assert _launch(tmp_path, repo, str(repo / "src" / "a.ts"), key=True).strip() == ""


def test_oauth_token_alone_never_selects_bare(monkeypatch):
    """`claude -p --bare` reads only ANTHROPIC_API_KEY / apiKeyHelper, never the OAuth token."""
    gate = _load("tdd_gate_oauth", "tdd-guard-gate.py")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TDD_GUARD_VALIDATOR", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "t")
    monkeypatch.setattr(gate.shutil, "which", lambda n: f"/x/{n}")
    assert gate._validator_argv() is None
    assert gate._validator("/r") == ("binary", ["/x/tdd-guard"])
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert "--bare" in gate._validator_argv()


def test_failed_bare_run_falls_back_to_the_binary(tmp_path):
    repo = _active_repo(tmp_path)
    _fake_tdd_guard(tmp_path)
    _fake_claude(tmp_path, "auth error", rc=1)
    assert "write a test" in _launch(tmp_path, repo, str(repo / "src" / "a.ts"), key=True)
    assert (tmp_path / "claude-rec.json").exists() and (tmp_path / "tdd-called").exists()


def test_failed_bare_run_without_binary_is_silent(monkeypatch, capsys):
    gate = _load("tdd_gate_nobin", "tdd-guard-gate.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("TDD_GUARD_VALIDATOR", raising=False)
    monkeypatch.setattr(gate.shutil, "which", lambda n: "/x/claude" if n == "claude" else None)
    calls = []

    def run(argv, **_kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="no key")

    monkeypatch.setattr(gate.subprocess, "run", run)
    monkeypatch.setattr(gate.sys, "stdin", io.StringIO(json.dumps({"tool_name": "Edit", "tool_input": {}})))
    assert gate.main() == 0
    assert len(calls) == 1 and capsys.readouterr().out == ""


def test_without_api_key_the_binary_path_is_used(tmp_path):
    repo = _active_repo(tmp_path)
    _fake_tdd_guard(tmp_path)
    _fake_claude(tmp_path, "{}")
    assert "write a test" in _launch(tmp_path, repo, str(repo / "src" / "a.ts"))
    assert (tmp_path / "tdd-called").exists() and not (tmp_path / "claude-rec.json").exists()


def test_advisory_caps_at_500_chars():
    gate = _load("tdd_gate_cap", "tdd-guard-gate.py")
    msg = json.loads(gate._advisory("x" * 2000))["hookSpecificOutput"]["additionalContext"]
    assert len(msg) <= 500 and "test-driven-development" in msg


def test_windows_which_resolution(monkeypatch):
    gate = _load("tdd_gate_win", "tdd-guard-gate.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("TDD_GUARD_VALIDATOR", raising=False)
    monkeypatch.setattr(gate.shutil, "which", lambda n: _WIN + "x\\claude.cmd" if n == "claude" else None)
    argv = gate._validator_argv()
    assert argv[0] == _WIN + "x\\claude.cmd" and "--bare" in argv


def test_validator_env_override_forces_the_binary(monkeypatch):
    gate = _load("tdd_gate_ovr", "tdd-guard-gate.py")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("TDD_GUARD_VALIDATOR", "binary")
    monkeypatch.setattr(gate.shutil, "which", lambda n: f"/x/{n}")
    assert gate._validator("/r") == ("binary", ["/x/tdd-guard"])

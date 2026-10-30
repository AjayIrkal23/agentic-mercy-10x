"""stop-format-typecheck.py: once-per-turn Stop gate (formatter --check + tsc --noEmit).

Fake tsc / biome / prettier / ruff binaries go first on PATH (Python scripts that log
their argv); HOME is a temp dir so the root walk's HOME stop is testable. The fake-binary
cases are POSIX-only (shebang scripts); the Windows path is covered with stubs.
"""
from __future__ import annotations

import importlib.util
import inspect
import io
import json
import os
import re
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

posix_only = pytest.mark.skipif(plat.IS_WINDOWS, reason="fake binaries are shebang scripts")
TS = "2026-10-29T10:00:00+00:00"


@pytest.fixture
def sft(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("sft_t", _HOOKS / "stop-format-typecheck.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    (tmp_path / "home" / ".claude").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "home" / ".claude"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    (tmp_path / "bin").mkdir()
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    return m


_CONFIG = {"biome": "biome.json", "prettier": ".prettierrc", "ruff": "ruff.toml"}


def _project(tmp_path, kind: str, ts: bool = False, py: bool = False) -> Path:
    proj = tmp_path / "home" / "proj"
    (proj / "src").mkdir(parents=True, exist_ok=True)
    (proj / "package.json").write_text("{}", encoding="utf-8")
    if kind in _CONFIG:
        (proj / _CONFIG[kind]).write_text("{}" if kind != "ruff" else "", encoding="utf-8")
    if ts or kind == "tsconfig":
        (proj / "tsconfig.json").write_text("{}", encoding="utf-8")
    f = proj / "src" / ("a.py" if py else "a.ts")
    f.write_text("x = 1\n" if py else "export const a: number = 1;\n", encoding="utf-8")
    return f


def _transcript(tmp_path, files, name="t.jsonl") -> Path:
    rows = [{"type": "user", "timestamp": TS, "message": {"role": "user", "content": "do it"}}]
    rows += [{"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": str(f)}}]}} for f in files]
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _fake_bin(tmp_path, name, rc, out="", where=None) -> Path:
    d = where or tmp_path / "bin"
    d.mkdir(parents=True, exist_ok=True)
    log = d / f"{name}.argv"
    p = d / name
    p.write_text(f"#!{sys.executable}\nimport json, sys\n"
                 f"open({str(log)!r}, 'a', encoding='utf-8').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                 f"sys.stdout.write({out!r})\nsys.exit({rc})\n", encoding="utf-8")
    p.chmod(0o755)
    return log


def _argv(log: Path) -> list:
    if not log.is_file():
        return []
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]


def _main(m, monkeypatch, payload) -> dict:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    buf = io.StringIO()
    with redirect_stdout(buf):
        m.main()
    return json.loads(buf.getvalue())


def _state(tmp_path, sid="s1") -> dict:
    p = tmp_path / "state" / f"{sid}.typecheck.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def _pl(tr, sid="s1", **kw) -> dict:
    return {"session_id": sid, "transcript_path": str(tr) if tr else None, **kw}


@posix_only
def test_passes_silently_when_nothing_was_edited_or_no_config(sft, monkeypatch, tmp_path):
    assert _main(sft, monkeypatch, {"session_id": "s0"}) == {}
    plain = tmp_path / "home" / "plain"
    plain.mkdir(parents=True)
    (plain / "a.ts").write_text("x", encoding="utf-8")
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [plain / "a.ts"]))) == {}
    assert not list((tmp_path / "bin").glob("*.argv"))


@posix_only
def test_tsc_errors_in_an_edited_file_block_once_with_capped_reason(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    out = ("src/a.ts(1,14): error TS2322: Type 'string' is not assignable to type 'number'.\n"
           + "".join(f"src/other.ts({i},1): error TS2304: Cannot find name 'x{i}'.\n" for i in range(40)))
    log = _fake_bin(tmp_path, "tsc", 2, out)
    tr = _transcript(tmp_path, [f])
    res = _main(sft, monkeypatch, _pl(tr))
    assert res["decision"] == "block"
    reason = res["reason"]
    assert "TS2322" in reason and "a.ts" in reason and "edited this turn" in reason
    assert len(reason) <= 1200 and "other.ts" not in reason
    assert "other errors elsewhere: 40" in reason
    assert len([ln for ln in reason.splitlines() if "error TS" in ln]) <= 20
    argv = _argv(log)[0]
    for flag in ("--noEmit", "--pretty", "false", "--incremental", "--tsBuildInfoFile", "-p"):
        assert flag in argv
    info = argv[argv.index("--tsBuildInfoFile") + 1]
    assert info.startswith(str(plat.state_dir() / "typecheck")) and info.endswith(".tsbuildinfo")
    assert Path(argv[argv.index("-p") + 1]).resolve() == f.parent.parent.resolve()
    assert not [p for p in f.parent.parent.rglob("*") if "tsbuildinfo" in p.name]
    assert _main(sft, monkeypatch, _pl(tr)) == {}
    st = _state(tmp_path)
    assert st["result"] == "block" and st["turn_key"]
    assert len(_argv(log)) == 1


@posix_only
def test_clean_tsc_and_formatter_pass_and_record(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "biome", ts=True)
    _fake_bin(tmp_path, "tsc", 0)
    blog = _fake_bin(tmp_path, "biome", 0)
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f]))) == {}
    st = _state(tmp_path)
    assert st["result"] == "pass" and st["tools"] == ["biome", "tsc"] and st["files"] == [str(f.resolve())]
    assert _argv(blog) == [["format", str(f.resolve())]]


@posix_only
def test_formatter_diff_blocks_and_names_the_fix(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "prettier")
    _fake_bin(tmp_path, "prettier", 1, "[warn] src/a.ts\n[warn] Code style issues found.\n")
    res = _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f])))
    assert res["decision"] == "block"
    reason = res["reason"]
    assert "prettier --check" in reason and "a.ts" in reason and "Fix:" in reason and "--write" in reason
    assert re.search(r"run /", reason) is None


@posix_only
def test_ruff_project_runs_format_check_and_check(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "ruff", py=True)
    log = _fake_bin(tmp_path, "ruff", 1, "Would reformat: src/a.py\n")
    res = _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f])))
    assert res["decision"] == "block"
    assert _argv(log)[0] == ["format", "--check", str(f.resolve())]


@posix_only
def test_stop_hook_active_doctor_and_tier_skip(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    log = _fake_bin(tmp_path, "tsc", 0)
    tr = _transcript(tmp_path, [f])
    assert _main(sft, monkeypatch, _pl(tr, stop_hook_active=True)) == {}
    assert _argv(log) == []
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert _main(sft, monkeypatch, _pl(tr, sid="d1")) == {}
    assert _state(tmp_path, "d1") == {}
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR")
    from lib import memwatch_state as mws
    mws.write_atomic(mws.State(level="warn", ts=time.time()))
    assert _main(sft, monkeypatch, _pl(tr, sid="w1")) == {}
    st = _state(tmp_path, "w1")
    assert st["result"] == "skip" and st["reason"] == "memory warn"
    assert _argv(log) == []


@posix_only
def test_budget_exhaustion_fails_open(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    _fake_bin(tmp_path, "tsc", 2, "src/a.ts(1,1): error TS1: x\n")
    tr = _transcript(tmp_path, [f])
    monkeypatch.setattr(sft, "DEADLINE_S", 0.001)
    assert _main(sft, monkeypatch, _pl(tr, sid="b1")) == {}
    st = _state(tmp_path, "b1")
    assert st["result"] == "skip" and st["reason"] == "budget"
    monkeypatch.setattr(sft, "DEADLINE_S", 5.4)
    monkeypatch.setattr(sft.plat, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 124, "", ""))
    assert _main(sft, monkeypatch, _pl(tr, sid="b2")) == {}
    assert _state(tmp_path, "b2")["result"] == "timeout"


@posix_only
def test_more_than_twenty_files_or_plugin_paths_skip(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    log = _fake_bin(tmp_path, "tsc", 0)
    many = []
    for i in range(21):
        p = f.parent / f"f{i}.ts"
        p.write_text("x", encoding="utf-8")
        many.append(p)
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, many), sid="m1")) == {}
    assert _state(tmp_path, "m1")["reason"] == "too many files"
    plug = tmp_path / "home" / ".claude" / "plugins" / "x"
    plug.mkdir(parents=True)
    (plug / "a.ts").write_text("x", encoding="utf-8")
    nm = f.parent.parent / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "b.ts").write_text("x", encoding="utf-8")
    tr = _transcript(tmp_path, [plug / "a.ts", nm / "b.ts"], name="t2.jsonl")
    assert _main(sft, monkeypatch, _pl(tr, sid="m2")) == {}
    assert _argv(log) == []


@posix_only
def test_binary_resolution_prefers_node_modules_bin_then_which_never_npx(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    proj = f.parent.parent
    local = _fake_bin(tmp_path, "tsc", 0, where=proj / "node_modules" / ".bin")
    onpath = _fake_bin(tmp_path, "tsc", 0)
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f]), sid="r1")) == {}
    assert len(_argv(local)) == 1 and _argv(onpath) == []
    (proj / "node_modules" / ".bin" / "tsc").unlink()
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f]), sid="r2")) == {}
    assert len(_argv(onpath)) == 1
    monkeypatch.setattr(sft.shutil, "which", lambda name, *a, **k: None)
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [f]), sid="r3")) == {}
    assert _state(tmp_path, "r3")["reason"] == "no binary"
    assert "npx" not in inspect.getsource(sft)


def test_windows_uses_cmd_shims_and_is_a_noop_without_binaries(sft, monkeypatch, tmp_path):
    f = _project(tmp_path, "tsconfig")
    tr = _transcript(tmp_path, [f])
    monkeypatch.setattr(sft.plat, "IS_WINDOWS", True)
    monkeypatch.setattr(sft.shutil, "which", lambda name, *a, **k: None)
    assert _main(sft, monkeypatch, _pl(tr, sid="w1")) == {}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(sft.shutil, "which", lambda name, *a, **k: f"C:/x/{name}.cmd")
    monkeypatch.setattr(sft.plat, "run", fake_run)
    assert _main(sft, monkeypatch, _pl(tr, sid="w2")) == {}
    argv = calls[0]
    assert argv[0].endswith("tsc.cmd")
    info = argv[argv.index("--tsBuildInfoFile") + 1]
    assert info.startswith(str(plat.state_dir()))


def test_project_root_never_climbs_into_home(sft, monkeypatch, tmp_path):
    home = tmp_path / "home"
    (home / ".prettierrc").write_text("{}", encoding="utf-8")
    proj = home / "proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "a.ts").write_text("x", encoding="utf-8")
    assert sft._formatter(sft._project_root((proj / "src" / "a.ts").resolve()), False) is None
    (proj / "package.json").write_text("{}", encoding="utf-8")
    calls = []
    monkeypatch.setattr(sft.plat, "run", lambda cmd, **kw: calls.append(cmd) or
                        subprocess.CompletedProcess(cmd, 0, "", ""))
    assert _main(sft, monkeypatch, _pl(_transcript(tmp_path, [proj / "src" / "a.ts"]))) == {}
    assert calls == []

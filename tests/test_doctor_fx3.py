"""Audit #2 (Windows parity v4.1), doctor / self-heal half: a dead pinned interpreter is noticed and
healed (A3v2-02, A6v2-05), `hook-command` runs under --ci when a rendered file exists and routes to a
re-render (A6v2-04, -10), `secret-perms` never passes over zero files (A6v2-08), the doctor survives a
cp1252 pipe (A6v2-02) and the mods-runtime classifier is not inverted (A6v2-01). Runners are injected."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_host  # noqa: E402
import doctor_hook  # noqa: E402
import doctor_mods  # noqa: E402
import selfheal  # noqa: E402

GONE = (Path("nowhere") / "gone" / "python").absolute().as_posix()  # absolute on every OS, never a file
GONE_SPACED = (Path("no where") / "gone" / "python").absolute().as_posix()


def _write(root, command="X:/py/python.exe /x/scripts/statusline.py", key="statusLine"):
    (root / "settings.json").write_text(json.dumps({key: {"type": "command", "command": command}}), encoding="utf-8")
    return command


# --- A3v2-02 / A6v2-05: the status line command runs ------------------------------------------- #
def test_statusline_passes_on_exit_0_with_output(tmp_path):
    cmd, got = _write(tmp_path), []

    def ok(command, payload, env):
        got.append((command, json.loads(payload), env))
        return 0, "◆ Claude\n"
    assert doctor_hook.check_statusline(tmp_path, False, run=ok)[0] == "PASS"
    command, payload, env = got[0]
    assert command == cmd and isinstance(payload, dict) and payload["workspace"]["current_dir"]
    assert env["CLAUDE_STATUSLINE_CACHE_DIR"] and not Path(env["CLAUDE_STATUSLINE_CACHE_DIR"]).is_relative_to(tmp_path)


def test_statusline_fails_on_a_missing_interpreter_and_on_blank_output(tmp_path):
    _write(tmp_path)
    st, det = doctor_hook.check_statusline(tmp_path, False, run=lambda *a: (127, ""))
    assert st == "FAIL" and "interpreter" in det and "re-render" in det
    assert doctor_hook.check_statusline(tmp_path, False, run=lambda *a: (0, "  \n"))[0] == "FAIL"
    assert doctor_hook.check_statusline(tmp_path, False, run=lambda *a: (1, "x"))[0] == "FAIL"


def test_statusline_skips_without_settings_and_fails_without_a_command(tmp_path):
    never = lambda *a: pytest.fail("must not run")  # noqa: E731
    for ci in (False, True):
        assert doctor_hook.check_statusline(tmp_path, ci, run=never)[0] == "SKIP"
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")
    assert doctor_hook.check_statusline(tmp_path, False, run=never)[0] == "FAIL"


def test_statusline_runs_under_ci_when_a_rendered_file_exists(tmp_path):
    _write(tmp_path)
    assert doctor_hook.check_statusline(tmp_path, True, run=lambda *a: (0, "x"))[0] == "PASS"


def test_statusline_default_runner_runs_the_real_command(tmp_path):
    script = tmp_path / "sl.py"
    script.write_text("import json, sys\njson.load(sys.stdin)\nprint('line')\n", encoding="utf-8")
    _write(tmp_path, f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"')
    st, det = doctor_hook.check_statusline(tmp_path, False)
    assert st == "PASS", det


def test_doctor_lists_the_statusline_row_after_hook_command():
    src = (_ROOT / "installer" / "doctor.py").read_text(encoding="utf-8")
    assert src.index("check_hook_command") < src.index("check_statusline") < src.index('"settings-safety"')


# --- repair routes ------------------------------------------------------------------------------ #
@pytest.mark.parametrize("row", ["statusline", "hook-command"])
def test_a_dead_interpreter_row_routes_to_a_forced_re_render(row, monkeypatch):
    seen: list = []
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda *a, **k: seen.append(k))
    selfheal._repair(Path("."), {row}, None, lambda *a: None)
    assert seen == [{"force": True}]


# --- the daily self-heal: a path that no longer exists is stale ---------------------------------- #
def test_stale_when_the_pinned_status_line_interpreter_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    st = tmp_path / "settings.json"
    _write(tmp_path, f"{GONE} /x/statusline.py")
    assert selfheal._stale(st)
    _write(tmp_path, f'"{GONE_SPACED}" /x/statusline.py')  # quoted: a token with a space is one word
    assert selfheal._stale(st)
    hooks = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"{GONE} a.py"}]}]}}  # deeper in the tree
    st.write_text(json.dumps(hooks), encoding="utf-8")
    assert selfheal._stale(st)


def test_not_stale_when_the_interpreter_exists_or_is_a_bare_launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    st = tmp_path / "settings.json"
    for command in (f'"{Path(sys.executable).as_posix()}" /x/s.py', "py -3 /x/dispatch.py pre", "python3 /x/s.py", ""):
        _write(tmp_path, command)
        assert not selfheal._stale(st), command


def test_daily_settings_step_rerenders_when_the_interpreter_is_gone(tmp_path, monkeypatch):
    import importlib.util
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    spec = importlib.util.spec_from_file_location("selfheal_daily_fx3", _ROOT / "hooks" / "tools" / "selfheal-daily.py")
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)  # type: ignore[union-attr]
    rendered: list = []
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda t, env, emit, **k: rendered.append(1))
    ctx = sd.Ctx(False, tmp_path, 60.0)
    ctx._env = object()
    _write(tmp_path, f"{GONE} /x/statusline.py")
    sd._settings(ctx)
    assert rendered == [1]
    _write(tmp_path, f'"{Path(sys.executable).as_posix()}" /x/statusline.py')
    sd._settings(ctx)
    assert rendered == [1]
    dry = sd.Ctx(True, tmp_path, 60.0)
    _write(tmp_path, f"{GONE} /x/statusline.py")
    assert "WOULD-RENDER" in sd._settings(dry)[0][2]


# --- A6v2-08: zero files is not a pass -------------------------------------------------------------- #
@pytest.mark.parametrize("windows", [False, True])
def test_secret_perms_skips_when_there_is_nothing_to_check(tmp_path, windows):
    root, home = tmp_path / "claude", tmp_path / "home"
    root.mkdir()
    home.mkdir()
    st, det = doctor_host.check_secret_perms(root, is_windows=windows, home=home,
                                             icacls_save=lambda p: pytest.fail("no file to read"),
                                             user_sid=lambda: "S-1-5-21-1-2-3-1000")
    assert st == "SKIP" and "no secret files found" in det


# --- A6v2-02: a piped cp1252 stdout with a non-ANSI path ------------------------------------------ #
def test_doctor_main_survives_a_cp1252_pipe_with_a_non_ansi_path():
    code = (f"import sys, pathlib; sys.path[:0] = {[str(_ROOT / 'installer'), str(_ROOT / 'hooks')]!r}\n"
            "import doctor\n"
            "doctor._ROOT = pathlib.Path('C:/Users/\\u0418\\u0432\\u0430\\u043d/.claude')\n"
            "doctor.run_doctor = lambda ci=False: [('x', 'PASS', '\\u0418')]\n"
            "raise SystemExit(doctor.main([]))\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"} | {"PYTHONUTF8": "0",
                                                                               "PYTHONIOENCODING": "cp1252"}
    cp = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, timeout=60, check=False)
    assert cp.returncode == 0, cp.stderr.decode("utf-8", "replace")[-400:]
    assert "Иван" in cp.stdout.decode("utf-8")


# --- A6v2-01: the load classifier --------------------------------------------------------------------- #
TEARDOWN = ("(fail) the file ran to its end\n  a rejection nothing handled: environment 16: $.state.set refused: "
            "no hooks module of that name is loaded")
TIMEOUT = "(fail) resume > waits [5001.2ms]\n  Error: timed out after 5000 ms"


@pytest.mark.parametrize("text", [
    "(fail) the file ran to its end\n  a rejection nothing handled: TypeError: undefined is not a function",
    "(fail) the file ran to its end\n  a rejection nothing handled: ReferenceError: x is not defined",
    "(fail) the file ran to its end\n  a rejection nothing handled: Error: boom",
    TIMEOUT + "\n(fail) b [2ms]\n  TypeError: nope",
    "(fail) t [2ms]\n  error: expect(received).toBeLessThan(expected)\n  Expected: < 200\n  Received: 603.3",
])
def test_a_typed_rejection_or_an_assertion_is_never_load(text):
    assert doctor_mods._load_only(text) is False


@pytest.mark.parametrize("text", [TEARDOWN, TIMEOUT, TEARDOWN + "\n" + TIMEOUT])
def test_a_timeout_or_the_known_teardown_rejection_is_load(text):
    assert doctor_mods._load_only(text) is True


def _which(*present):
    return lambda name: f"/bin/{name}" if name in present else None


def _runtime(tmp_path, results):
    calls, it = [], iter(results)

    def run(argv, cwd=None):
        calls.append(argv)
        return next(it)
    mod = tmp_path / "mods" / "m"
    mod.mkdir(parents=True)
    return doctor_mods.check_mods_runtime(tmp_path, ["m"], False, _which("claude"), run), calls


def test_a_deterministic_type_error_rejection_is_a_fail_without_a_retry(tmp_path):
    bad = "(fail) the file ran to its end\n  a rejection nothing handled: TypeError: x"
    (st, det), calls = _runtime(tmp_path, [(1, bad)])
    assert st == "FAIL" and len(calls) == 1


def test_load_then_a_clean_rerun_passes_and_load_then_a_type_error_fails(tmp_path):
    (st, _), calls = _runtime(tmp_path / "a", [(1, TEARDOWN), (0, "227 pass")])
    assert st == "PASS" and len(calls) == 2
    (st, _), calls = _runtime(tmp_path / "b", [(1, TEARDOWN), (1, TEARDOWN + "\n(fail) q [1ms]\n  TypeError: y")])
    assert st == "FAIL" and len(calls) == 2
    (st, det), _ = _runtime(tmp_path / "c", [(1, TEARDOWN), (1, TIMEOUT)])
    assert st == "WARN" and "load-sensitive" in det


# --- A7v2-03: the render's interpreter is injectable ---------------------------------------------- #
def test_pin_makes_the_render_use_an_injected_interpreter(monkeypatch):
    import live_interpreter
    import render  # type: ignore
    live_interpreter.pin(monkeypatch, "Z:/injected/python.exe")
    assert render.machine_subs()["PYTHON_EXE"] == "Z:/injected/python.exe"

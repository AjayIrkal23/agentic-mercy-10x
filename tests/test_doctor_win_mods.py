"""W7 (Windows parity v4.1), the mods-runtime half: a load flake is not a failure (A6-02),
`tsc` gets no path in argv (A6-13), the doctor helpers decode UTF-8 whatever the console
code page is (A6-03). Every external tool is injected: no claude, no tsc."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_mods  # noqa: E402
import selfheal  # noqa: E402

FLAKE = "(fail) user consent > a stop is never blocked [5053.58ms]\n  Error: timed out after 5000 ms"
REJECT = ("(fail) the file ran to its end\n  a rejection nothing handled: environment 16: $.state.set refused: "
          "no hooks module of that name is loaded")  # the one teardown rejection a slow run leaves (A6v2-01)
ASSERT = "(fail) shapes\n  error: expect(received).toBe(expected)\n  Expected: 1\n  Received: 2"


def _mod(tmp_path, types=True):
    mod = tmp_path / "mods" / "m"
    (mod / ".claude-plugin" / ("types" if types else "x")).mkdir(parents=True)
    (mod / "tsconfig.json").write_text("{}", encoding="utf-8")
    return tmp_path


def _seq(*results):
    calls, it = [], iter(results)

    def run(argv, cwd=None):
        calls.append((argv, cwd))
        return next(it)
    run.calls = calls
    return run


def _which(*present):
    return lambda name: f"/bin/{name}" if name in present else None


def _runtime(tmp_path, run, *tools, types=False):
    return doctor_mods.check_mods_runtime(_mod(tmp_path, types), ["m"], False, _which(*tools), run)


# --- A6-02: a load flake is not a failure, and never re-renders settings ----------- #
def test_timeouts_twice_are_a_load_sensitive_warn(tmp_path):
    run = _seq((1, FLAKE), (1, FLAKE + "\n" + REJECT))
    st, det = _runtime(tmp_path, run, "claude")
    assert st == "WARN" and "load-sensitive" in det and len(run.calls) == 2


def test_a_timeout_then_a_clean_run_passes(tmp_path):
    run = _seq((1, REJECT), (0, "156 pass"))
    st, det = _runtime(tmp_path, run, "claude")
    assert st == "PASS", det
    assert len(run.calls) == 2


def test_an_assertion_failure_stays_a_fail_without_a_retry(tmp_path):
    run = _seq((1, ASSERT))
    assert _runtime(tmp_path, run, "claude")[0] == "FAIL" and len(run.calls) == 1


def test_a_timeout_mixed_with_an_assertion_failure_is_a_fail(tmp_path):
    run = _seq((1, FLAKE + "\n" + ASSERT), (1, FLAKE + "\n" + ASSERT))
    assert _runtime(tmp_path, run, "claude")[0] == "FAIL"


def test_failures_without_a_failing_test_line_are_not_load(tmp_path):
    """P1: a signature alone proves nothing; every `(fail)` test must be explained by a timeout / rejection."""
    run = _seq((1, "TypeError: boom\n a rejection nothing handled"))
    assert _runtime(tmp_path, run, "claude")[0] == "FAIL" and len(run.calls) == 1


def test_one_unexplained_failing_test_makes_the_run_a_fail(tmp_path):
    """A timeout elsewhere in the output must not vouch for a test that failed another way."""
    other = "(fail) loads the mod [3.00ms]\n  TypeError: undefined is not a function"
    for n, text in enumerate((other + "\n" + FLAKE, FLAKE + "\n" + other)):
        run = _seq((1, text))
        assert _runtime(tmp_path / str(n), run, "claude")[0] == "FAIL" and len(run.calls) == 1


def test_one_timeout_cannot_explain_two_failing_tests(tmp_path):
    two = "(fail) a [5001ms]\n(fail) b [5001ms]\n  Error: timed out after 5000 ms"
    run = _seq((1, two))
    assert _runtime(tmp_path, run, "claude")[0] == "FAIL" and len(run.calls) == 1


def test_the_error_printed_before_the_fail_line_counts_too(tmp_path):
    """bun prints a test's error above its `(fail)` line."""
    native = 'error: Test "slow" timed out after 5000ms\n(fail) slow [5001.2ms]\n(pass) other [1ms]'
    run = _seq((1, native), (1, native))
    st, det = _runtime(tmp_path, run, "claude")
    assert st == "WARN" and "load-sensitive" in det and len(run.calls) == 2


def test_a_second_run_that_fails_another_way_is_a_fail(tmp_path):
    run = _seq((1, FLAKE), (1, "(fail) t [2ms]\n  TypeError: boom"))
    assert _runtime(tmp_path, run, "claude")[0] == "FAIL" and len(run.calls) == 2


def test_a_load_warn_does_not_hide_a_type_error(tmp_path):
    run = _seq((1, FLAKE), (1, FLAKE), (2, "x.ts(1,1): error TS2322"))
    assert _runtime(tmp_path, run, "claude", "tsc", types=True)[0] == "FAIL"


def test_the_rollout_marker_is_still_a_warn_and_is_not_retried(tmp_path):
    run = _seq((1, "hooks modules are turned off"))
    assert _runtime(tmp_path, run, "claude")[0] == "WARN" and len(run.calls) == 1


def test_a_mods_runtime_fail_does_not_re_render_settings(monkeypatch):
    seen: list = []
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda *a, **k: seen.append(k))
    selfheal._repair(Path("."), {"mods-runtime"}, None, lambda *a: None)
    assert seen == []
    selfheal._repair(Path("."), {"mods"}, None, lambda *a: None)
    assert seen == [{"force": True}]


# --- A6-13: tsc gets `-p .` and a cwd, never a path in argv ------------------------ #
def test_tsc_runs_in_the_mod_folder_with_no_path_in_argv(tmp_path):
    run = _seq((0, ""))
    assert _runtime(tmp_path, run, "tsc", types=True)[0] == "PASS"
    (argv, cwd), = run.calls
    assert argv == ["/bin/tsc", "-p", ".", "--noEmit"]
    assert Path(cwd) == tmp_path / "mods" / "m"


# --- A6-03: helpers decode UTF-8 whatever the code page is ------------------------- #
def test_helpers_decode_utf8_without_pythonutf8(tmp_path):
    child = tmp_path / "child.py"
    child.write_text("import sys; sys.stdout.buffer.write(b'ok \\xd0\\x81')", encoding="utf-8")
    argv = [sys.executable, str(child)]
    code = (f"import sys; sys.path[:0] = {[str(_ROOT / 'installer'), str(_ROOT / 'hooks')]!r}\n"
            "import doctor, doctor_host, doctor_mods\n"
            f"print(ascii([doctor_mods._run({argv!r})[1], doctor_host._stdout({argv!r}),"
            f" doctor._run_with_stdin({argv!r}, '').stdout]))")
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252", "PYTHONWARNINGS": "ignore"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, env=env, timeout=60, check=False)
    assert out.stdout.decode("ascii").count("ok \\u0401") == 3, out.stderr.decode("utf-8", "replace")


def test_every_text_mode_subprocess_call_names_its_encoding():
    bad = []
    for rel in ("installer/doctor.py", "installer/doctor_host.py", "installer/doctor_mods.py",
                "installer/doctor_hook.py", "scripts/validate_mods.py"):
        tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                kws = {k.arg for k in node.keywords}
                if "text" in kws and "encoding" not in kws:
                    bad.append(f"{rel}:{node.lineno}")
    assert not bad, bad

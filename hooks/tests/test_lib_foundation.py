"""Unit tests for hooks/lib foundation (P1-T1).

Pure stdlib + pytest-style asserts. Runnable via `pytest hooks/tests/` or
directly: `python3 hooks/tests/test_lib_foundation.py`.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import hook_telemetry as tel  # noqa: E402
from lib import platform as plat  # noqa: E402
from lib import repo_context as rc  # noqa: E402


# --------------------------------------------------------------------------- #
# platform
# --------------------------------------------------------------------------- #
def test_is_windows_is_bool():
    assert isinstance(plat.IS_WINDOWS, bool)


def test_claude_dir_ends_with_dotclaude():
    assert plat.claude_dir().name == ".claude"


def test_python_exe_nonempty():
    assert plat.python_exe()


def test_state_and_telemetry_dirs_created():
    assert plat.state_dir().is_dir()
    assert plat.telemetry_dir().is_dir()


def test_slugify_deterministic_and_safe():
    a = plat.slugify_path("/a/b/My Repo/")
    b = plat.slugify_path("/a/b/My Repo")
    assert a == b  # trailing slash ignored
    assert a.startswith("My-Repo-")
    assert "/" not in a and " " not in a


def test_materialize_substitutes_and_leaves_unknown():
    out = plat.materialize(["{PY}", "{HOOKS}/x.py", "{UNKNOWN}"], {"PY": "py", "HOOKS": "/h"})
    assert out == ["py", "/h/x.py", "{UNKNOWN}"]


def test_ollama_url_reads_every_ollama_host_form():
    for raw, want in [("", "http://127.0.0.1:11434"), ("localhost", "http://127.0.0.1:11434"),
                      ("0.0.0.0", "http://127.0.0.1:11434"), ("192.0.2.10", "http://192.0.2.10:11434"),
                      ("192.0.2.10:8080", "http://192.0.2.10:8080"),
                      ("http://192.0.2.10:11434/", "http://192.0.2.10:11434"),
                      ("https://ai.example/ollama", "https://ai.example:443/ollama"),  # as ollama's client
                      ("http://192.0.2.10", "http://192.0.2.10:80"),
                      ("[::1]:11434", "http://[::1]:11434"), ("host:notaport", "http://host:11434")]:
        assert plat.ollama_url({"OLLAMA_HOST": raw}) == want, raw
    assert plat.is_loopback_url(plat.ollama_url({})) and plat.is_loopback_url("http://[::1]:11434")
    assert not plat.is_loopback_url("http://192.0.2.10:11434")


def test_ollama_url_falls_back_to_settings_user_json_outside_claude():
    """install.py / doctor.py from a terminal have no settings env: the key is read from the file;
    a present-but-empty env value (the conftest's) still means the default."""
    saved = {k: os.environ.get(k) for k in ("OLLAMA_HOST", "CLAUDE_CONFIG_DIR")}
    with tempfile.TemporaryDirectory() as d:
        try:
            pathlib.Path(d, "settings.user.json").write_text('{"env": {"OLLAMA_HOST": "192.0.2.10"}}',
                                                             encoding="utf-8")
            os.environ["CLAUDE_CONFIG_DIR"] = d
            os.environ.pop("OLLAMA_HOST", None)
            assert plat.ollama_url() == "http://192.0.2.10:11434"
            os.environ["OLLAMA_HOST"] = ""
            assert plat.ollama_url() == "http://127.0.0.1:11434"
            os.environ.pop("OLLAMA_HOST")
            pathlib.Path(d, "settings.user.json").write_text("not json", encoding="utf-8")
            assert plat.ollama_url() == "http://127.0.0.1:11434"
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_atomic_write_roundtrip():
    with tempfile.TemporaryDirectory() as d:  # removed afterwards (FIX2 item 6); no fixture: _run_all calls it bare
        tmp = pathlib.Path(d) / "deep" / "f.txt"
        assert plat.atomic_write(tmp, "payload")
        assert tmp.read_text(encoding="utf-8") == "payload"
        assert plat.atomic_write(tmp, "second")  # overwrite atomically
        assert tmp.read_text(encoding="utf-8") == "second"


def test_run_never_raises_on_bad_command():
    cp = plat.run(["___definitely_not_a_binary___"])
    assert cp.returncode != 0  # synthetic 127, no exception


def test_run_timeout_output_is_text(monkeypatch):
    """RT-7 / FIX2 item 7: on POSIX TimeoutExpired carries BYTES even with text=True; run() passed them
    through and index-lifecycle's `_ok` died on `.startswith("Deprecated:")` (jcodemunch build_error)."""
    import subprocess  # noqa: PLC0415

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1, output=b"partial \xff", stderr=b"Deprecated: x\nerr\n")

    monkeypatch.setattr(plat.subprocess, "run", boom)
    cp = plat.run(["x"], timeout=1)
    assert cp.returncode == 124 and cp.stdout == "partial �"
    assert [ln for ln in cp.stderr.splitlines() if not ln.startswith("Deprecated:")] == ["err"]
    raw = plat.run(["x"], timeout=1, text=False)
    assert raw.returncode == 124 and raw.stdout == b"partial \xff"


def test_pid_alive_self_true_bogus_false():
    assert plat.pid_alive(os.getpid()) is True
    assert plat.pid_alive(2_147_480_000) is False


# --------------------------------------------------------------------------- #
# repo_context
# --------------------------------------------------------------------------- #
def test_active_repo_inside_claude():
    ctx = rc.active_repo(cwd=str(_HOOKS))
    assert ctx is not None
    # portable: resolve to the real git root and assert against ITS name — the dev
    # box checks out at ~/.claude, CI at the workspace dir; the invariant is that
    # active_repo returns the enclosing git repo, whatever it is named.
    root = pathlib.Path(ctx.root)
    assert (root / ".git").exists()
    assert str(_HOOKS).startswith(str(root))          # _HOOKS lives inside it
    assert ctx.name == root.name
    assert ctx.key.startswith(ctx.name + "-")
    assert len(ctx.key.rsplit("-", 1)[1]) == 8


def test_active_repo_outside_git_is_none():
    # walk-up from filesystem root can never find .git above /
    assert rc.active_repo(cwd=os.path.abspath(os.sep)) is None


def test_active_repo_resolution_order_payload_workspace_roots():
    # workspace_roots[0] wins over cwd=os.sep (which would resolve to None)
    ctx = rc.active_repo({"workspace_roots": [str(_HOOKS)], "cwd": os.sep})
    assert ctx is not None
    root = pathlib.Path(ctx.root)
    assert (root / ".git").exists()
    assert ctx.name == root.name
    assert str(_HOOKS).startswith(str(root))


def test_home_is_never_a_repo_root():
    # $HOME is a container dir: a stray `git init` there must not make every
    # session register the whole home tree (indexes/graph/dox).
    home = str(pathlib.Path.home())
    assert rc.active_repo(cwd=home) is None
    assert rc.git_root(home) is None
    # ...but a real repo BELOW home still resolves
    ctx = rc.active_repo(cwd=str(_HOOKS))
    assert ctx is not None and ctx.root != home
    # unnormalized paths must not slip the guard (git_root used to miss these)
    assert rc.git_root(home + os.sep + "nonexistent-dir" + os.sep + "..") is None


def test_infra_roots_match_index_lifecycle_never_index():
    """One helper for every hook; it once drifted (the read gate missed ~/.codex and this checkout)."""
    from lib.code_files import is_infra_root
    home = pathlib.Path.home()
    for root in (home, home / ".claude", home / ".codex", _HOOKS.parent):
        assert is_infra_root(root), root
    assert not is_infra_root(home / "CODE_FILES" / "proj")
    assert not is_infra_root(None)


def test_is_inside_containment():
    ctx = rc.active_repo(cwd=str(_HOOKS))
    assert rc.is_inside(ctx, str(_HOOKS / "lib" / "platform.py"))
    assert not rc.is_inside(ctx, os.sep + "etc")
    assert not rc.is_inside(None, str(_HOOKS))


# --------------------------------------------------------------------------- #
# hook_telemetry
# --------------------------------------------------------------------------- #
def test_record_appends_jsonl():
    tel.record("UserPromptSubmit", "unit_test_link", session="t", ms=0.5, exit=0)
    day = time.strftime("%Y%m%d")
    f = plat.telemetry_dir() / f"hook-fires-{day}.jsonl"
    assert f.exists()
    assert "unit_test_link" in f.read_text(encoding="utf-8")


def test_timer_records_ms_and_swallows_exception():
    # exception inside Timer is swallowed (reraise=False default) and recorded
    with tel.Timer("PreToolUse", "unit_timer_link", session="t") as tm:
        tm.set(decision="x")
        raise ValueError("boom")  # must be swallowed
    day = time.strftime("%Y%m%d")
    f = plat.telemetry_dir() / f"hook-fires-{day}.jsonl"
    body = f.read_text(encoding="utf-8")
    assert "unit_timer_link" in body and "boom" in body


def test_popen_new_group_roundtrip_and_kill():
    # POSIX/live path: launch a short-lived child in its own group, prove the
    # handle is live and poll-able, then kill_tree it.
    proc = plat.popen_new_group(
        [plat.python_exe(), "-c", "import time; time.sleep(30)"],
        stdout=None,
        stderr=None,
    )
    try:
        assert proc.poll() is None  # still running
        assert plat.pid_alive(proc.pid)
    finally:
        plat.kill_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()
    assert proc.poll() is not None  # reaped


def test_popen_new_group_windows_flags(monkeypatch):
    # Windows branch: assert CREATE_NEW_PROCESS_GROUP is passed and
    # start_new_session is NOT (that kwarg is POSIX-only) — without spawning.
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            self.pid = 4321

    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setattr(plat.subprocess, "Popen", _FakePopen)
    plat.popen_new_group("echo hi", shell=True)
    assert captured["kwargs"].get("creationflags") == 0x00000200
    assert "start_new_session" not in captured["kwargs"]
    assert captured["kwargs"].get("shell") is True


# --------------------------------------------------------------------------- #
# repo_context.repo_key (PKG hooks-hygiene-mod step 2)
# --------------------------------------------------------------------------- #
def test_repo_key_is_public_and_matches_ctx_key(tmp_path):
    (tmp_path / ".git").mkdir()
    ctx = rc.active_repo(cwd=tmp_path)
    assert rc.repo_key(tmp_path) == ctx.key and len(ctx.key.rsplit("-", 1)[1]) == 8
    long, short = rc.repo_key(tmp_path, digits=12), rc.repo_key(tmp_path)
    assert long.rsplit("-", 1)[1].startswith(short.rsplit("-", 1)[1])   # same digest, longer


def test_repo_key_twelve_digits_equals_model_mode_scheme(tmp_path):
    from lib import model_mode as mm            # model-routing's file; read-only use
    (tmp_path / ".git").mkdir()
    assert mm.repo_key(tmp_path) == rc.repo_key(tmp_path, digits=12)


def test_write_gates_import_the_one_write_tool_set():
    for name in ("dox-write-gate.py", "first-write-skill-gate.py", "mcp-post-hints.py"):
        assert "tool_compat" in (_HOOKS / name).read_text(encoding="utf-8"), name


# --------------------------------------------------------------------------- #
# settings-permissions-selfheal (step 14)
# --------------------------------------------------------------------------- #
def test_settings_selfheal_writes_live_under_lock_with_0600(tmp_path, monkeypatch):
    import importlib.util
    import io
    import json

    spec = importlib.util.spec_from_file_location("selfheal_ut", _HOOKS / "settings-permissions-selfheal.py")
    sh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sh)
    live, tmpl = tmp_path / "settings.json", tmp_path / "settings.template.json"
    live.write_text(json.dumps({"permissions": {"deny": ["Read"]}, "env": {"A": "1"}}), encoding="utf-8")
    tmpl.write_text(json.dumps({"permissions": {"deny": []}}), encoding="utf-8")
    monkeypatch.setattr(sh, "LIVE", live)
    monkeypatch.setattr(sh, "TEMPLATE", tmpl)
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    sh.heal_from_template()
    data = json.loads(live.read_text(encoding="utf-8"))
    assert data["permissions"]["deny"] == [] and data["env"] == {"A": "1"}
    assert (tmp_path / "settings.json.lock").exists() and not list(tmp_path.glob("*.tmp"))
    if not plat.IS_WINDOWS:
        assert oct(live.stat().st_mode & 0o777) == "0o600"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_lib_foundation: {len(fns)} tests PASSED")


if __name__ == "__main__":
    _run_all()

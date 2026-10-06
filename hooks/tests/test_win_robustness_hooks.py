"""W6b hook robustness on Windows, part 3: the hooks themselves (A4-06 localhost,
A4-07 commit paths, A4-10 router backslashes, A4-02/A4-16 selfheal-daily). Runs on
Ubuntu and Windows (``plat.IS_WINDOWS`` monkeypatched)."""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import types

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

import commit_docs_check as cdc  # noqa: E402
from lib import platform as plat  # noqa: E402


# --------------------------------------------------------------------------- #
# A6-03: run() decodes child output as UTF-8 (not the ANSI code page) in text mode
# --------------------------------------------------------------------------- #
def test_run_decodes_utf8_with_replacement_in_text_mode_only(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    seen: list = []

    def fake(cmd, **kw):
        seen.append(kw)
        if not kw.get("shell"):
            raise OSError(193, "shim")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(subprocess, "run", fake)
    plat.run(["x"])
    assert [(kw.get("encoding"), kw.get("errors")) for kw in seen] == [("utf-8", "replace")] * 2
    seen.clear()
    plat.run(["x"], text=False)
    assert all(kw.get("encoding") is None for kw in seen)


def test_run_survives_utf8_output_under_an_ansi_parent():
    """A fresh Windows box has no machine-wide PYTHONUTF8: the reader thread died on 0x81."""
    parent = ("import sys; sys.path.insert(0, sys.argv[1])\nfrom lib import platform as p\n"
              "r = p.run([sys.executable, '-c', \"import sys; sys.stdout.buffer.write(b'ok \\\\xd0\\\\x81')\"])\n"
              "sys.stdout.buffer.write(repr(r.stdout).encode('ascii', 'backslashreplace'))\n")
    env = dict(os.environ, PYTHONUTF8="0", PYTHONIOENCODING="cp1252")
    out = subprocess.run([sys.executable, "-X", "utf8=0", "-c", parent, str(_HOOKS)],
                         capture_output=True, env=env, check=False)
    want = repr("ok Ё").encode("ascii", "backslashreplace").decode()
    assert out.stdout.decode("ascii") == want, out.stderr.decode("utf-8", "replace")[-300:]


# --------------------------------------------------------------------------- #
# A4-06: localhost -> 127.0.0.1
# --------------------------------------------------------------------------- #
def _il():
    spec = importlib.util.spec_from_file_location("il_w6b_url", _HOOKS / "index-lifecycle.py")
    il = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(il)
    return il


@pytest.mark.parametrize("windows,expect", [(True, "http://127.0.0.1:11434/api/tags"),
                                            (False, "http://localhost:11434/api/tags")])
def test_summarizer_probe_skips_the_slow_ipv6_localhost_on_windows(monkeypatch, windows, expect):
    import urllib.request
    il, urls = _il(), []
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: urls.append(req.full_url))
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)
    assert il._summarizer_alive("http://localhost:11434/api/tags", 800) is True
    assert urls == [expect]


def test_healthcheck_url_defaults_name_ipv4():
    il = _il()
    cfg = json.loads((_HOOKS / "index-lifecycle.config.json").read_text(encoding="utf-8"))
    assert "localhost" not in cfg["summarizer_healthcheck"]["url"]
    assert "localhost" not in il._DEFAULT_CONFIG["summarizer_healthcheck"]["url"]
    assert "localhost" not in il._summarizer_cfg({})[1]


# --------------------------------------------------------------------------- #
# A4-07: commit_docs_check on Windows paths
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cmd", [
    r'git -C D:\Projects\x commit -m "y"',
    r"cd D:\Projects\x && git commit -m y",
    r'git -C "D:\Projects\x" commit -m y',
    "git -C D:/Projects/x commit -m y",
    "cd /d/Projects/x && git commit -m y",
])
def test_windows_commit_directories_survive_tokenising(monkeypatch, cmd):
    monkeypatch.setattr(cdc.plat, "IS_WINDOWS", True)
    commits, _ = cdc.git_commits(cmd, "C:/Users/me")
    assert [d for _, d in commits] == ["D:/Projects/x"]


def test_posix_commit_directories_are_untouched(monkeypatch):
    monkeypatch.setattr(cdc.plat, "IS_WINDOWS", False)
    commits, _ = cdc.git_commits("cd /d/Projects/x && git commit -m y", "/home/me")
    assert [d for _, d in commits] == [os.path.normpath("/d/Projects/x")]
    commits, _ = cdc.git_commits(r"git commit -m 'a\b'", "/home/me")
    assert commits[0][0] == ["-m", r"a\b"]


# --------------------------------------------------------------------------- #
# A4-10: the router reads backslash paths like slash paths
# --------------------------------------------------------------------------- #
def test_router_treats_backslash_and_slash_paths_alike(tmp_path):
    from prompt_router import classify as C
    from prompt_router.modules import surface as SF
    for stem in ("restyle {}", "fix {}", "refactor {} please"):
        a = stem.format(r"src\components\Button.tsx")
        b = stem.format("src/components/Button.tsx")
        assert SF.prompt_paths(a) == SF.prompt_paths(b) == ["src/components/button.tsx"]
        pa, pb = C.classify({"prompt": a, "cwd": str(tmp_path)}), C.classify({"prompt": b, "cwd": str(tmp_path)})
        assert (pa.paths, pa.surfaces, pa.surface_source, pa.intents) == \
            (pb.paths, pb.surfaces, pb.surface_source, pb.intents)
    assert SF.prompt_paths(r"server\routes\orders.js") == ["server/routes/orders.js"]


# --------------------------------------------------------------------------- #
# A4-02 second half / A4-16: selfheal-daily
# --------------------------------------------------------------------------- #
@pytest.fixture
def sd(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("selfheal_daily_w6b", _HOOKS / "tools" / "selfheal-daily.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = tmp_path / "state"
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.setenv("SELFHEAL_DAILY_ALLOW_TEST", "1")
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)  # CI exports it for the whole run
    monkeypatch.setattr(mod.plat, "claude_dir", lambda: tmp_path / "claude")
    monkeypatch.setitem(sys.modules, "selfheal", types.SimpleNamespace(pin_config_dir=lambda t: None))
    mod.state = state
    return mod


def _summary(sd) -> dict:
    return json.loads((sd.state / "selfheal-daily.json").read_text(encoding="utf-8"))


def test_a_run_where_every_step_failed_is_not_stamped(sd, monkeypatch):
    def boom(ctx):
        raise RuntimeError("kaboom")
    calls: list = []
    monkeypatch.setattr(sd, "STEPS", [("a", lambda ctx: calls.append(1) or [("dep", "x", "WARN(rc=3221225794)")]),
                                      ("b", boom)])
    sd.main([])
    s = _summary(sd)
    assert "at" not in s and s["reported"] is False and len(s["errors"]) == 2
    sd.main([])  # no stamp -> the next session tries again
    assert len(calls) == 2


def test_a_run_with_one_healthy_step_is_stamped(sd, monkeypatch):
    monkeypatch.setattr(sd, "STEPS", [("a", lambda ctx: [("dep", "x", "WARN(rc=1)")]), ("b", lambda ctx: [])])
    sd.main([])
    assert _summary(sd)["at"]


def test_the_daily_deps_step_skips_optional_deps(sd, monkeypatch):
    seen: list = []
    deps = types.SimpleNamespace(_load_manifest=lambda: {})
    deps.install_deps = lambda env, *, ci=False, dry_run=False, skip_optional=False: seen.append(skip_optional) or []
    monkeypatch.setitem(sys.modules, "deps", deps)
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    ctx = sd.Ctx(False, pathlib.Path("."), 60)
    ctx._env = object()
    sd._deps(ctx)
    assert seen == [True]  # deps.install_deps owns the filter (no manifest patching here)

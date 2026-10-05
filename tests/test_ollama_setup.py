"""ollama in user space + the embedding / summary models the code indexes use."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ollama_setup  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
CFG = M["user_space"]["ollama"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return tmp_path


def test_asset_url_uses_ollama_arch_names():
    assert ollama_setup.asset_url(CFG, "linux", "x64").endswith("ollama-linux-amd64.tar.zst")
    assert ollama_setup.asset_url(CFG, "linux", "arm64").endswith("ollama-linux-arm64.tar.zst")
    assert ollama_setup.asset_url(CFG, "darwin", "arm64") is None  # macOS: brew / the app


def test_extractor_prefers_stdlib_then_zstd_binary_then_uv():
    which = lambda have: (lambda n: f"/usr/bin/{n}" if n in have else None)  # noqa: E731
    assert ollama_setup.pick_extractor(which(set()), stdlib_zstd=True) == "stdlib"
    assert ollama_setup.pick_extractor(which({"zstd"}), stdlib_zstd=False) == "zstd"
    assert ollama_setup.pick_extractor(which({"uv"}), stdlib_zstd=False) == "uv"
    assert ollama_setup.pick_extractor(which(set()), stdlib_zstd=False) is None


def test_install_is_planned_in_ci_and_skipped_when_present(home):
    assert ollama_setup.install_ollama(CFG, ci=True, dry_run=True, which=lambda n: None,
                                       system=("linux", "x64")).startswith("WOULD-")
    assert ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: "/x/ollama") == "PRESENT"


def test_install_reports_a_blocked_download_as_warn(home):
    def boom(*_a, **_k):
        raise OSError("blocked")
    st = ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None,
                                     download=boom, extract=lambda *a: None, system=("linux", "x64"))
    assert st.startswith("WARN")


def test_install_extracts_into_the_user_prefix(home):
    seen = {}

    def extract(archive, dest):
        seen["dest"] = dest
    st = ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None,
                                     download=lambda u, d, timeout=0, **_k: Path(d).write_bytes(b"z"),
                                     extract=extract, system=("linux", "x64"))
    assert st.startswith("INSTALLED") and seen["dest"] == home / ".local"


def _run_rec(calls):
    def run(argv, **_kw):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 0, "", "")
    return run


def test_pull_models_only_pulls_missing_ones_when_the_server_is_up(home):
    calls: list = []
    rows = ollama_setup.pull_models(CFG["models"], run=_run_rec(calls), probe=lambda: {"all-minilm:latest"},
                                    ensure_server=lambda: True)
    pulls = [c for c in calls if c[:2] == ["ollama", "pull"]]
    assert pulls == [["ollama", "pull", "qwen2.5-coder:3b"]]
    assert dict(rows)["ollama:all-minilm"] == "PRESENT"


def test_pull_models_warns_when_no_server_can_be_started(home):
    rows = ollama_setup.pull_models(CFG["models"], run=_run_rec([]), probe=lambda: None,
                                    ensure_server=lambda: False)
    assert all(s.startswith("WARN") for _, s in rows)


def test_ensure_server_spawns_detached_serve_when_no_user_unit(home):
    spawned: list = []
    state = {"up": False}

    def probe():
        return {"x"} if state["up"] else None

    def spawn(cmd, **_kw):
        spawned.append(list(cmd))
        state["up"] = True
        return 123
    ok = ollama_setup.ensure_server(probe=probe, spawn=spawn, run=lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""),
                                    which=lambda n: "/x/ollama", sleep=lambda s: None, wait_s=3)
    assert ok and spawned == [["ollama", "serve"]]


def test_ensure_server_is_a_noop_when_already_up(home):
    spawned: list = []
    assert ollama_setup.ensure_server(probe=lambda: set(), spawn=lambda *a, **k: spawned.append(a),
                                      run=lambda *a, **k: None, which=lambda n: "/x", sleep=lambda s: None)
    assert spawned == []

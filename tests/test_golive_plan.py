"""golive.py (the go-live runner) + its preflight helpers (ostools.apt_available, basetools.ensure_gitleaks)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import basetools  # noqa: E402
import ostools  # noqa: E402
from lib import platform as plat  # noqa: E402

_spec = importlib.util.spec_from_file_location("golive", _ROOT / "scripts" / "golive.py")
G = importlib.util.module_from_spec(_spec)
sys.modules["golive"] = G
_spec.loader.exec_module(G)  # type: ignore[union-attr]

GL = {"version": "8.30.1",
      "download": "https://github.com/gitleaks/gitleaks/releases/download/v{version}/gitleaks_{version}_linux_{arch}.tar.gz",
      "sha256": {"x64": "a" * 64, "arm64": "b" * 64}}
MANIFEST = {"user_space": {"gitleaks": GL}}


@pytest.fixture(autouse=True)
def _posix(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)


@pytest.fixture
def calls(monkeypatch):
    seen: list[list[str]] = []

    def fake(argv, *, cwd=None, timeout=None, env=None, input=None):
        seen.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(G, "_run", fake)
    return seen


# ---------------------------------------------------------------- preflight helpers

def test_apt_available_true_only_on_linux_with_apt_get():
    which = lambda n: "/usr/bin/apt-get" if n == "apt-get" else None  # noqa: E731
    assert ostools.apt_available(which=which, system="Linux") is True
    assert ostools.apt_available(which=which, system="Darwin") is False
    assert ostools.apt_available(which=lambda n: None, system="Linux") is False


def test_ensure_gitleaks_skips_without_manifest_entry():
    assert basetools.ensure_gitleaks({}, ci=False, dry_run=False, which=lambda n: None) == (
        "gitleaks", "SKIP(no manifest entry)")


def test_ensure_gitleaks_present():
    def boom(*a, **k):
        raise AssertionError("download must not run")
    assert basetools.ensure_gitleaks(MANIFEST, ci=False, dry_run=False, download=boom,
                                     which=lambda n: "/x/gitleaks") == ("gitleaks", "PRESENT")


def test_ensure_gitleaks_plan_modes():
    for ci, dry in ((True, False), (False, True)):
        assert basetools.ensure_gitleaks(MANIFEST, ci=ci, dry_run=dry, which=lambda n: None) == (
            "gitleaks", "WOULD-INSTALL gitleaks v8.30.1")


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    return h


def _flat_tgz() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, data in (("gitleaks", b"#!/bin/sh\necho gitleaks\n"), ("LICENSE", b"MIT"), ("README.md", b"r")):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode = len(data), 0o755
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def test_ensure_gitleaks_downloads_verifies_and_extracts(home, monkeypatch):
    seen = {}

    def fake_download(url, dest, timeout=None, sha256=None):
        seen.update(url=url, sha256=sha256)
        Path(dest).write_bytes(_flat_tgz())
    monkeypatch.setattr(basetools, "_os_arch", lambda: ("linux", "x64"))
    row = basetools.ensure_gitleaks(MANIFEST, ci=False, dry_run=False, download=fake_download, which=lambda n: None)
    assert row == ("gitleaks", "INSTALLED gitleaks v8.30.1")
    binary = home / ".local" / "bin" / "gitleaks"
    assert binary.is_file()
    if os.name == "posix":  # Windows has no exec bit (st_mode reads 0o666 for any non-.exe file)
        assert binary.stat().st_mode & 0o111
    assert not (home / ".local" / "bin" / "LICENSE").exists() and not (home / ".local" / "bin" / "README.md").exists()
    assert seen["url"] == GL["download"].format(version="8.30.1", arch="x64") and seen["sha256"] == "a" * 64


def test_ensure_gitleaks_bad_sha_is_warn(home, monkeypatch):
    def bad(url, dest, timeout=None, sha256=None):
        raise ValueError("sha256 mismatch")
    monkeypatch.setattr(basetools, "_os_arch", lambda: ("linux", "x64"))
    row = basetools.ensure_gitleaks(MANIFEST, ci=False, dry_run=False, download=bad, which=lambda n: None)
    assert row == ("gitleaks", "WARN(ValueError: sha256 mismatch)")
    assert not (home / ".local" / "bin" / "gitleaks").exists()


def test_ensure_gitleaks_windows_skip(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert basetools.ensure_gitleaks(MANIFEST, ci=False, dry_run=False, which=lambda n: None) == (
        "gitleaks", "SKIP(windows)")


def test_before_deps_emits_gitleaks_row(monkeypatch):
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    monkeypatch.setattr(basetools.ostools, "install_os_tools", lambda *a, **k: ([], None))
    monkeypatch.setattr(basetools, "ensure_base_tools", lambda *a, **k: [])
    monkeypatch.setattr(basetools.detect, "detect", lambda: SimpleNamespace())
    monkeypatch.setattr(basetools.shutil, "which", lambda n: None)
    rows = []
    basetools.before_deps(SimpleNamespace(), MANIFEST, True, lambda *r: rows.append(r))
    assert ("base", "gitleaks", "WOULD-INSTALL gitleaks v8.30.1") in rows


LP = {"version": "1.0.2",
      "download": "https://github.com/lightpanda-io/browser/releases/download/{version}/{asset}",
      "assets": {"linux-x64": {"name": "lightpanda-x86_64-linux", "sha256": "c" * 64}}}


def test_ensure_lightpanda_downloads_the_pinned_binary(home, monkeypatch):
    seen = {}

    def fake_download(url, dest, timeout=None, sha256=None):
        seen.update(url=url, sha256=sha256)
        Path(dest).write_bytes(b"\x7fELF")
    monkeypatch.setattr(basetools, "_os_arch", lambda: ("linux", "x64"))
    row = basetools.ensure_lightpanda({"user_space": {"lightpanda": LP}}, ci=False, dry_run=False,
                                      download=fake_download, which=lambda n: None)
    assert row == ("lightpanda", "INSTALLED lightpanda 1.0.2")
    binary = home / ".local" / "bin" / "lightpanda"
    assert binary.is_file() and (os.name == "nt" or binary.stat().st_mode & 0o111)  # no exec bits on Windows
    assert seen == {"url": "https://github.com/lightpanda-io/browser/releases/download/1.0.2/lightpanda-x86_64-linux",
                    "sha256": "c" * 64}


def test_ensure_lightpanda_skips_windows_unpinned_arch_and_plans_in_ci(monkeypatch):
    m = {"user_space": {"lightpanda": LP}}
    assert basetools.ensure_lightpanda({}, ci=False, dry_run=False, which=lambda n: None)[1] == "SKIP(no manifest entry)"
    assert basetools.ensure_lightpanda(m, ci=True, dry_run=False, which=lambda n: None)[1] == "WOULD-INSTALL lightpanda 1.0.2"
    assert basetools.ensure_lightpanda(m, ci=False, dry_run=False, which=lambda n: "/x/lightpanda")[1] == "PRESENT"
    monkeypatch.setattr(basetools, "_os_arch", lambda: ("linux", "riscv64"))
    assert basetools.ensure_lightpanda(m, ci=False, dry_run=False, which=lambda n: None)[1] == "SKIP(linux-riscv64: no pinned asset)"
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert basetools.ensure_lightpanda(m, ci=False, dry_run=False, which=lambda n: None)[1] == "SKIP(windows)"


# ---------------------------------------------------------------- golive plan

def test_plan_prints_ordered_steps_and_runs_nothing(calls, capsys):
    assert G.main(["--plan"]) == 0
    s = capsys.readouterr().out
    ids = [st.id for st in G.STEPS]
    assert ids == ["ownership", "pytest", "validators", "render-check", "tokens", "secrets-gitleaks",
                   "secrets-known-values",
                   "git-commit", "merge", "render-live", "guard-checks", "zram", "mcp-remove", "push", "replica",
                   "memory"]
    pos = [s.index(f"{i:02d} {sid}") for i, sid in enumerate(ids, 1)]
    assert pos == sorted(pos)
    assert "secrets" in s and s.index("secrets") < s.index("git commit")
    assert calls == []


def test_refuses_without_yes_automatic(calls, capsys):
    assert G.main([]) == 2
    out = capsys.readouterr().out
    assert "refusing to run: pass --yes-automatic" in out and "01 ownership" in out
    assert calls == []


def test_no_git_before_secrets():
    ids = [s.id for s in G.STEPS]
    last_secret = max(ids.index("secrets-gitleaks"), ids.index("secrets-known-values"))
    mutating = {"add", "commit", "merge", "push", "tag"}
    for i, step in enumerate(G.STEPS):
        writes_git = any(a and a[0] == "git" and mutating & set(a) for a in step.argv)
        if writes_git or step.id.startswith(("git-", "merge", "push", "tag")):
            assert i > last_secret, step.id


def test_skip_cannot_name_a_secrets_step(calls):
    for sid in ("secrets-known-values", "secrets-gitleaks", "ownership", "pytest"):
        assert G.main(["--yes-automatic", "--skip", sid]) == 2
    assert G.main(["--yes-automatic", "--from", "no-such-step"]) == 2
    assert calls == []


def test_stops_on_first_failure_and_records_state(monkeypatch, tmp_path, capsys):
    seen = []

    def fake(argv, *, cwd=None, timeout=None, env=None, input=None):
        seen.append(list(argv))
        rc = 1 if "pytest" in argv else 0
        return subprocess.CompletedProcess(argv, rc, "out\n", "err\n")
    monkeypatch.setattr(G, "_run", fake)
    monkeypatch.setattr(G, "_script_exists", lambda p: True)
    assert G.main(["--yes-automatic", "--worktree", str(tmp_path), "--live", str(tmp_path)]) == 1
    assert "golive: FAIL at pytest" in capsys.readouterr().out
    logs = sorted((plat.state_dir() / "golive").glob("*.jsonl"))
    rows = [json.loads(x) for x in logs[-1].read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["ownership", "pytest"]
    assert {k: rows[-1][k] for k in ("id", "rc", "status")} == {"id": "pytest", "rc": 1, "status": "FAIL"}
    assert len(seen) == 2


def test_missing_script_is_fail(monkeypatch, tmp_path, calls, capsys):
    assert G.main(["--yes-automatic", "--worktree", str(tmp_path), "--live", str(tmp_path)]) == 1
    assert "golive: FAIL at ownership" in capsys.readouterr().out
    assert calls == []


def test_from_resumes_after_a_fix(calls, capsys):
    assert G.main(["--plan", "--from", "render-check"]) == 0
    out = capsys.readouterr().out.splitlines()
    for sid in ("ownership", "pytest", "validators"):
        assert any(line.startswith(tuple(f"{i:02d} {sid}" for i in range(1, 4))) and "SKIPPED(--from)" in line
                   for line in out)
    assert not any("render-check" in line and "SKIPPED" in line for line in out)


def test_windows_refuses(monkeypatch, calls):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert G.main(["--yes-automatic"]) == 2
    assert G.main(["--plan"]) == 0
    assert calls == []


def test_push_uses_ssh_url_when_workflows_changed():
    assert G._push_argv(remote_https="https://github.com/o/r.git", workflows_changed=True) == [
        "git", "push", "git@github.com:o/r.git", "main", "v4.3.0"]
    assert G._push_argv(remote_https="https://github.com/o/r.git", workflows_changed=False) == [
        "git", "push", "origin", "main", "v4.3.0"]


def test_zram_step_skips_without_askpass_or_apt():
    assert G._zram_plan(askpass_exists=False) == ("zram", "SKIP(no sudo askpass)")
    assert G._zram_plan(askpass_exists=True, apt=False) == ("zram", "SKIP(no apt)")
    low = G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=12000)
    assert isinstance(low, list) and not any("swapoff" in a for a in low)
    high = G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=20000)
    assert any("swapoff" in a for a in high)
    assert all(a[:2] == ["sudo", "-A"] for a in low)


def test_zram_restart_only_with_headroom_and_applied_check():
    """FIX-r2 O3 + SANTA-FINAL fix 7: apt's postinst only daemon-reloads, and `restart` starts an inactive
    unit. A device holding data restarts only when that data fits in RAM with 2 GB to spare; an empty or
    absent device (fresh host) always (re)starts, it costs no RAM."""
    tight = G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=5000, zram_used_mb=3600)
    assert not any("restart" in a for a in tight) and not any("start" in a for a in tight)
    roomy = G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=9000, zram_used_mb=3600)
    assert ["sudo", "-A", "systemctl", "restart", "systemd-zram-setup@zram0"] in roomy
    fresh = G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=4500, zram_used_mb=0)
    assert ["sudo", "-A", "systemctl", "restart", "systemd-zram-setup@zram0"] in fresh
    assert G._zram_applied("/dev/zram0 lzo-rle    4G") is False
    assert G._zram_applied("/dev/zram0 zstd 15G") is True
    assert G._zram_applied("") is False


def test_zram_restart_keeps_memwatch_crit_headroom():
    """FIX-r3 O8: the swapoff lands the zram data in RAM; what is left must stay 2 GB above memwatch's crit
    line, else the sentinel starts killing during the apply. 7.5 GB with 3.9 GB in zram: defer to reboot."""
    restart = ["sudo", "-A", "systemctl", "restart", "systemd-zram-setup@zram0"]
    assert G._crit_mb() == 3072
    assert restart not in G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=7500, zram_used_mb=3900)
    assert restart in G._zram_plan(askpass_exists=True, apt=True, mem_available_mb=9500, zram_used_mb=3900)
    assert "next reboot" in G._zram_deferred(3900, 7500)


def test_validators_step_runs_import_hygiene_over_five_dirs_with_root():
    step = next(s for s in G.STEPS if s.id == "validators")
    vi = next(a for a in step.argv if a[1].endswith("validate_imports.py"))
    assert vi[2:] == ["library", "skills", "agents", "hooks", "docs", "--root", "{W}"]


def _env_spy(monkeypatch):
    envs = []

    def fake(argv, *, cwd=None, timeout=None, env=None, input=None):
        envs.append((list(argv), env))
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(G, "_run", fake)
    monkeypatch.setattr(G, "_script_exists", lambda p: True)
    return envs


def test_gitleaks_step_passes_the_config_and_drops_gitleaks_config(monkeypatch, tmp_path):
    envs = _env_spy(monkeypatch)
    monkeypatch.setenv("GITLEAKS_CONFIG", str(tmp_path / "other.toml"))
    monkeypatch.setattr(G, "_gitleaks_bin", lambda a: "/x/gitleaks")
    a = SimpleNamespace(worktree=tmp_path, live=tmp_path, branch="ecc-merge", tag="v4.3.0")
    step = next(s for s in G.STEPS if s.id == "secrets-gitleaks")
    assert G._x_gitleaks(step, G._subs(a), a)[0] == "OK"
    scans = [env for argv, env in envs if argv[0] == "/x/gitleaks"]
    assert len(scans) == 2
    for env in scans:
        assert env["GITLEAKS_CONFIG_TOML"] == G.GITLEAKS_TOML and "GITLEAKS_CONFIG" not in env


def test_gitleaks_toml_parses_and_extends_the_default():
    tomllib = pytest.importorskip("tomllib")
    cfg = tomllib.loads(G.GITLEAKS_TOML)
    assert cfg["extend"]["useDefault"] is True
    assert {r["id"] for r in cfg["rules"]} == {"generic-api-key", "curl-auth-header"}


def test_gitleaks_config_flag_prints_the_toml(capsys, calls):
    assert G.main(["--gitleaks-config"]) == 0
    assert capsys.readouterr().out == G.GITLEAKS_TOML and calls == []


_GITLEAKS = shutil.which("gitleaks") or str(Path.home() / ".local" / "bin" / "gitleaks")


@pytest.mark.skipif(not Path(_GITLEAKS).is_file(), reason="gitleaks not installed")
def test_gitleaks_toml_hides_placeholders_but_still_catches_keys():
    env = {**os.environ, "GITLEAKS_CONFIG_TOML": G.GITLEAKS_TOML}
    env.pop("GITLEAKS_CONFIG", None)

    def scan(text):
        return subprocess.run([_GITLEAKS, "stdin", "--redact", "--exit-code", "1", "--no-banner"], input=text,
                              env=env, capture_output=True, text=True, timeout=60).returncode
    placeholders = 'api_key="abcdef' + '123456789"\n"Authorization: Bearer abcdef' + 'ghijklmnop"\n'
    assert scan(placeholders) == 0
    assert scan('x = "AKIA' + 'ABCDEFGHIJKLMNOP"\n') == 1
    assert scan('api_key = "Zq8Xw2Lp' + '9Rt4Vb7Nm3Kd"\n') == 1


def test_pytest_step_writes_no_bytecode(monkeypatch, tmp_path):
    envs = _env_spy(monkeypatch)
    a = SimpleNamespace(worktree=tmp_path, live=tmp_path, branch="ecc-merge", tag="v4.3.0", packages="p.json")
    step = next(s for s in G.STEPS if s.id == "pytest")
    G._x_generic(step, G._subs(a), a)
    assert envs and envs[0][1]["PYTHONDONTWRITEBYTECODE"] == "1"


def test_pytest_step_never_inherits_the_live_oom_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_TEST_LIVE_OOM", "1")
    envs = _env_spy(monkeypatch)
    a = SimpleNamespace(worktree=tmp_path, live=tmp_path, branch="ecc-merge", tag="v4.3.0", packages="p.json")
    step = next(s for s in G.STEPS if s.id == "pytest")
    G._x_generic(step, G._subs(a), a)
    assert envs and "CLAUDE_TEST_LIVE_OOM" not in envs[0][1]


def test_memory_lines_are_emitted_not_written_to_user_memory(tmp_path, monkeypatch):
    live = tmp_path / "live"
    (live / "projects").mkdir(parents=True)
    path = G._memory_note("20261029T1200", "2026-10-29")
    text = path.read_text(encoding="utf-8")
    assert path.parent == plat.state_dir() / "golive" and path.name == "20261029T1200-memory.md"
    assert sum(1 for line in text.splitlines() if line.startswith("decision::")) == 2
    assert sum(1 for line in text.splitlines() if line.startswith("- [")) == 1
    assert list((live / "projects").iterdir()) == []


# ---------------------------------------------------------------- guard-checks + release message

def _guard_run(live: str, execstart: str):
    def fake(argv, *, cwd=None, timeout=None, env=None, input=None):
        out = {"DefaultOOMPolicy": "DefaultOOMPolicy=continue\n", "ExecStart": execstart}
        text = next((v for k, v in out.items() if k in " ".join(argv)), "")
        return subprocess.CompletedProcess(argv, 0, text, "")
    return fake


def test_guard_checks_never_runs_a_real_oom_kill():
    step = next(s for s in G.STEPS if s.id == "guard-checks")
    flat = " ".join(" ".join(t) for t in step.argv)
    assert "bytearray" not in flat and "MemorySwapMax=0" not in flat


def test_guard_checks_pass_only_when_memwatch_runs_the_live_tree(monkeypatch, tmp_path):
    live = tmp_path / "live"
    (live / "state").mkdir(parents=True)
    (live / "state" / "mem-pressure.json").write_text("{}", encoding="utf-8")
    a = SimpleNamespace(live=live, worktree=tmp_path / "wt", branch="b", tag="v1", message=None)
    step = next(s for s in G.STEPS if s.id == "guard-checks")
    monkeypatch.setattr(G, "_run", _guard_run(str(live), f"ExecStart={{ argv[]=/usr/bin/python3 {live}/hooks/tools/memwatch.py }}"))
    assert G._x_guard(step, G._subs(a), a)[0] == "OK"
    monkeypatch.setattr(G, "_run", _guard_run(str(live), "ExecStart={ argv[]=/usr/bin/python3 /wt/hooks/tools/memwatch.py }"))
    with pytest.raises(G._Fail, match="does not run the live tree"):
        G._x_guard(step, G._subs(a), a)


def test_message_flag_overrides_the_release_subject():
    a = SimpleNamespace(worktree="/w", live="/l", branch="b", tag="v9", message="feat: release {T}")
    assert G._subs(a)["{MSG}"] == "feat: release v9"
    a.message = None
    assert G._subs(a)["{MSG}"] == G._COMMIT_MSG.replace("{T}", "v9")

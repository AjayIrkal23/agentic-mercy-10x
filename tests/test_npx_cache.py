"""W6b-npx: a half-written npx cache entry (`node_modules`, no `package.json`) broke
sequential-thinking and markdownify with CONNECTION_CLOSED right after a pin reconcile. The
installer prunes such entries and warms each re-pinned package once, one at a time, on both
OSes. Tmp trees and an injected runner only: no npm, no npx, no network."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_autonomy_wpd_fixtures import box, manifest, npx  # noqa: F401

import deps  # noqa: E402
import doctor_mcp  # noqa: E402
import npx_cache  # noqa: E402
import selfheal  # noqa: E402

ENV = {"KEEP": "1"}


@pytest.fixture(autouse=True)
def _pin_modules(monkeypatch):
    for mod in (deps, selfheal, doctor_mcp, npx_cache):  # other tests re-exec installer modules (I-17)
        monkeypatch.setitem(sys.modules, mod.__name__, mod)


def _use(monkeypatch, m: dict) -> None:
    monkeypatch.setattr(deps, "_load_manifest", lambda: m)


def _live(**entries) -> dict:
    return {k: {"type": "stdio", "command": "npx", "args": ["-y", v], "env": dict(ENV)} for k, v in entries.items()}


def _entry(cache: Path, name: str, *, modules=True, package=False, age_s=3600) -> Path:
    d = cache / "_npx" / name
    (d / "node_modules").mkdir(parents=True) if modules else d.mkdir(parents=True)
    if package:
        (d / "package.json").write_text("{}", encoding="utf-8")
    old = time.time() - age_s
    for p in (d / "node_modules", d):  # the entry's newest mtime is what prune judges
        if p.exists():
            os.utime(p, (old, old))
    return d


def _npm(cache: Path, calls: list | None = None, warm_rc: int = 0):
    """Injected runner for `npm config get cache` and `npx -y <spec> --version`; fails the
    test when two commands overlap (the warm-up must run one package at a time)."""
    state = {"busy": False}

    def run(argv, timeout):
        assert not state["busy"], "two commands at once"
        state["busy"] = True
        try:
            if calls is not None:
                calls.append(argv)
            return (0, f"{cache}\n") if argv[:3] == ["npm", "config", "get"] else (warm_rc, "")
        finally:
            state["busy"] = False
    return run


# --- the pure helpers ----------------------------------------------------------- #
def test_prune_removes_only_half_written_entries_inside_npx(tmp_path):
    bad = _entry(tmp_path, "aaa")
    good = _entry(tmp_path, "bbb", package=True)
    empty = _entry(tmp_path, "ccc", modules=False)
    outside = tmp_path / "keep" / "node_modules"
    outside.mkdir(parents=True)
    assert npx_cache.prune_npx_cache(tmp_path) == ["aaa"]
    assert not bad.exists() and good.exists() and empty.exists() and outside.exists()


def test_deps_exposes_the_helpers():
    assert deps.prune_npx_cache is npx_cache.prune_npx_cache and deps.warm_npx is npx_cache.warm_npx


def test_prune_keeps_an_entry_another_session_is_still_installing(tmp_path):
    fresh = _entry(tmp_path, "aaa", age_s=5)
    assert npx_cache.prune_npx_cache(tmp_path) == [] and fresh.exists()
    assert npx_cache.prune_npx_cache(tmp_path, min_age_s=0) == ["aaa"]


def _age(path: Path, age_s: float) -> None:
    t = time.time() - age_s
    os.utime(path, (t, t))


def test_prune_leaves_an_entry_for_ten_minutes(tmp_path):
    """P2: a slow cold install (a postinstall that downloads a binary) looked half-written after 120 s."""
    assert npx_cache.prune_npx_cache.__defaults__[0] >= 600
    five, eleven = _entry(tmp_path, "five", age_s=300), _entry(tmp_path, "eleven", age_s=660)
    assert npx_cache.prune_npx_cache(tmp_path) == ["eleven"] and five.exists()


def test_prune_judges_the_newest_mtime_of_the_entry_not_just_its_directory(tmp_path):
    """npm fills `node_modules` without touching the entry directory's own mtime."""
    busy = _entry(tmp_path, "busy", age_s=3600)
    _age(busy / "node_modules", 3600)
    (busy / "node_modules" / "pkg").mkdir()  # an install still writing: this child is brand new
    scoped = _entry(tmp_path, "scoped", age_s=3600)
    _age(scoped / "node_modules", 3600)
    (scoped / "node_modules" / ".package-lock.json").write_text("{}", encoding="utf-8")
    quiet = _entry(tmp_path, "quiet", age_s=3600)
    _age(quiet / "node_modules", 3600)
    (quiet / "node_modules" / "pkg").mkdir()
    _age(quiet / "node_modules" / "pkg", 3600)
    _age(quiet / "node_modules", 3600)  # making `pkg` touched it
    assert npx_cache.prune_npx_cache(tmp_path) == ["quiet"]
    assert busy.exists() and scoped.exists()


def test_prune_without_a_cache_is_a_no_op(tmp_path):
    assert npx_cache.prune_npx_cache(tmp_path / "absent") == []


def test_npm_cache_root_comes_from_npm_then_the_os_default(tmp_path, monkeypatch):
    assert npx_cache.npm_cache_root(_npm(tmp_path)) == tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    for win, want in ((False, tmp_path / ".npm"), (True, tmp_path / "local" / "npm-cache")):
        monkeypatch.setattr(npx_cache.plat, "IS_WINDOWS", win)
        for failing in (lambda argv, t: (127, ""), lambda argv, t: (0, "undefined\n")):
            assert npx_cache.npm_cache_root(failing) == want


def test_npm_and_npx_run_from_the_home_dir_so_a_repo_npmrc_cannot_steer_them(monkeypatch, tmp_path):
    """SEC1-05: the hook's cwd is the project; its `.npmrc` (cache=, registry=) must not apply."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    seen: list = []
    monkeypatch.setattr(npx_cache.plat, "run", lambda argv, **kw: seen.append((argv, kw)) or
                        subprocess.CompletedProcess(argv, 0, f"{tmp_path}\n", ""))
    npx_cache.npm_cache_root()
    npx_cache.warm_npx(["@x/a@1.0.0"])
    assert [a[0][0] for a in seen] == ["npm", "npx"]
    assert [kw["cwd"] for _, kw in seen] == [str(tmp_path)] * 2


def test_warm_runs_each_spec_once_one_at_a_time_and_tolerates_a_failure(tmp_path):
    calls: list = []
    out = npx_cache.warm_npx(["@x/a@2.0.0", "@x/b@3.0.0"], _npm(tmp_path, calls, warm_rc=1))
    assert [c[:3] for c in calls] == [["npx", "-y", "@x/a@2.0.0"], ["npx", "-y", "@x/b@3.0.0"]]
    assert all("--version" in c for c in calls)
    assert [s for _, s in out] == ["NOT-WARMED(rc=1)"] * 2 and not any(s.startswith("WARN") for _, s in out)


# --- wired into the pin reconcile and the self-heal repair --------------------------- #
def test_pin_reconcile_prunes_then_warms_only_the_changed_packages_in_order(box, monkeypatch, tmp_path):
    cache = tmp_path / "npm-cache"
    bad = _entry(cache, "aaa")
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0"), npx("b", "@x/b@3.0.0"), npx("c", "@x/c@4.0.0")))
    box.write_live(_live(a="@x/a@1.0.0", b="@x/b@2.0.0", c="@x/c@4.0.0"))
    calls: list = []
    out = deps.reconcile_mcp_pins(run=_npm(cache, calls))
    assert [c[:3] for c in calls] == [["npm", "config", "get"], ["npx", "-y", "@x/a@2.0.0"], ["npx", "-y", "@x/b@3.0.0"]]
    assert not bad.exists()
    assert out == [("a", "PINNED @x/a@1.0.0 -> @x/a@2.0.0"), ("b", "PINNED @x/b@2.0.0 -> @x/b@3.0.0"),
                   ("npx-cache", "PRUNED 1: ['aaa']"), ("a", "WARMED @x/a@2.0.0"), ("b", "WARMED @x/b@3.0.0")]


def test_pin_reconcile_prunes_even_without_drift_and_warms_nothing(box, monkeypatch, tmp_path):
    cache = tmp_path / "npm-cache"
    _entry(cache, "aaa")
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@2.0.0"))
    calls: list = []
    assert deps.reconcile_mcp_pins(run=_npm(cache, calls)) == [("npx-cache", "PRUNED 1: ['aaa']")]
    assert [c[0] for c in calls] == ["npm"]


def test_a_dry_run_a_missing_cli_and_a_failed_add_warm_nothing(box, monkeypatch, tmp_path):
    cache = tmp_path / "npm-cache"
    bad = _entry(cache, "aaa")
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    calls: list = []
    deps.reconcile_mcp_pins(dry_run=True, run=_npm(cache, calls))
    assert calls == [] and bad.exists()
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_SPEC", "@x/a@2.0.0")
    out = deps.reconcile_mcp_pins(run=_npm(cache, calls))
    assert [c[0] for c in calls] == ["npm"] and not any(s.startswith("WARMED") for _, s in out)
    monkeypatch.setenv("PATH", "")
    calls.clear()
    assert ("a", "SKIP(no-claude-cli)") in deps.reconcile_mcp_pins(run=_npm(cache, calls))
    assert all(c[0] != "npx" for c in calls)


def test_the_offline_skip_flag_keeps_the_default_runner_off_the_network(box, monkeypatch):
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    monkeypatch.setattr(npx_cache, "_run", lambda argv, timeout: pytest.fail("spawned " + " ".join(argv)))
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@1.0.0"))
    assert deps.reconcile_mcp_pins() == [("a", "PINNED @x/a@1.0.0 -> @x/a@2.0.0")]


def test_repair_of_a_roster_fail_prunes_the_npx_cache_and_reports_the_count(box, monkeypatch, tmp_path):
    cache = tmp_path / "npm-cache"
    bad = _entry(cache, "aaa")
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    monkeypatch.setattr(npx_cache, "_run", _npm(cache))
    _use(monkeypatch, manifest(npx("a", "@x/a@2.0.0")))
    box.write_live(_live(a="@x/a@2.0.0"))
    seen: list = []
    selfheal._repair(box.home, {"mcp-roster"}, None, lambda *a: seen.append(a))
    assert ("repair", "npx-cache", "PRUNED 1: ['aaa']") in seen and not bad.exists()

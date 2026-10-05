"""A re-run repairs what a failed run left behind (A5v2-02, A5v2-03, A5v2-10), on ``winfakes``.

The npm prefix is an idempotent step of its own (not a suffix of the run that extracted node), a
verified archive survives a failed extraction so the retry never downloads 1.4 GB again, a leftover
zip that cannot be deleted never turns an installed tool into a WARN, and ``CLAUDE_CODE_GIT_BASH_PATH``
is read from one place (process, HKCU, HKLM) for the installer and the doctor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import safe_fetch  # noqa: E402
import winutil  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import FakeRegistry, World, short_limit  # noqa: E402, F401  (autouse: long basetemp)

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
GIT_VAR = "CLAUDE_CODE_GIT_BASH_PATH"


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return World(tmp_path, M)


def _sets(w) -> list[list[str]]:
    return [c for c in w.run.calls if c[1:4] == ["config", "set", "prefix"]]


def test_a_failed_npm_prefix_is_set_again_by_the_next_run_and_then_left_alone(w):
    w.runs(rc={"npm.cmd": 1})  # `npm config set prefix` fails (and `get` reports nothing)
    first = dict(w.ensure())
    assert first["node"].startswith("INSTALLED") and len(_sets(w)) == 1
    w.run.rc = {}
    second = dict(w.ensure())
    assert second["node"] == "PRESENT" and len(_sets(w)) == 2 and w.prefix == str(w.tools / "npm-global")
    assert (w.tools / "npm-global").is_dir()
    w.ensure()
    assert len(_sets(w)) == 2  # prefix already right: no write


def test_a_failed_npm_prefix_is_reported_not_hidden(w):
    w.runs(rc={"npm.cmd": 1})
    rows = w.ensure()
    assert any(n == "npm-prefix" and s.startswith("WARN") for n, s in rows), rows


def test_a_users_own_node_never_gets_its_npm_prefix_rewritten(w, tmp_path):
    w.found.update(node="/n/node.exe", npm="/n/npm.cmd")
    w.runs(out={"node": "v22.9.0"})
    w.ensure()
    assert _sets(w) == []  # only OUR node (inside the tools dir) is steered to <tools>\npm-global


def test_an_undeletable_leftover_zip_does_not_turn_an_install_into_a_warn(w, monkeypatch):
    real = Path.unlink

    def unlink(self, *a, **k):
        if self.suffix == ".zip":
            raise PermissionError(5, "Access is denied")  # Defender / the indexer still hold the archive
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "unlink", unlink)
    rows = dict(w.ensure())
    assert all(rows[n].startswith("INSTALLED") for n in ("node", "uv", "gh")), rows
    assert (w.tools / "node" / "node.exe").is_file() and len(_sets(w)) == 1


def test_a_failed_extraction_keeps_the_verified_archive_and_the_rerun_downloads_nothing(w, monkeypatch):
    node = next(u for u in w.blobs if "node" in u and "x64" in u)
    real = safe_fetch.os.replace

    def denied(a, b, *x, **k):
        raise PermissionError(5, "Access is denied")
    monkeypatch.setattr(safe_fetch.os, "replace", denied)
    monkeypatch.setattr(safe_fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(safe_fetch, "RENAME_WAIT_S", 0.01)
    assert dict(w.ensure())["node"].startswith("WARN(PermissionError")
    kept = [p for p in (w.tools / "cache").glob("*") if p.is_file()]
    assert any(p.name == node.rsplit("/", 1)[-1] for p in kept), kept  # verified archive still there
    monkeypatch.setattr(safe_fetch.os, "replace", real)
    assert dict(w.ensure())["node"].startswith("INSTALLED")
    assert w.urls.count(node) == 1  # no second download
    assert not [p for p in (w.tools / "cache").glob("*node*") if p.is_file()]  # deleted only after success


def test_a_cached_archive_with_the_wrong_hash_is_downloaded_again(w):
    node = next(u for u in w.blobs if "node" in u and "x64" in u)
    cache = w.tools / "cache"
    cache.mkdir(parents=True)
    (cache / node.rsplit("/", 1)[-1]).write_bytes(b"truncated or tampered")
    assert dict(w.ensure())["node"].startswith("INSTALLED") and w.urls.count(node) == 1


def test_an_undeletable_installer_exe_is_not_a_failure_either(w, monkeypatch):
    real = Path.unlink

    def unlink(self, *a, **k):
        if self.suffix == ".exe" and self.parent.name == "cache":
            raise PermissionError(5, "Access is denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "unlink", unlink)
    rows = dict(w.ensure())
    assert rows["git"].startswith("INSTALLED") and rows["claude"].startswith("INSTALLED"), rows


def test_one_function_reads_the_git_bash_variable_from_process_user_and_machine():
    reg = FakeRegistry(values={("Environment", GIT_VAR): ("U:/hkcu/bash.exe", "REG_SZ")},
                       machine={GIT_VAR: ("M:/hklm/bash.exe", "REG_SZ")})
    assert winutil.bash_values({GIT_VAR: "P:/proc/bash.exe"}, reg) == [
        "P:/proc/bash.exe", "U:/hkcu/bash.exe", "M:/hklm/bash.exe"]
    assert winutil.bash_values({}, reg)[1:] == ["U:/hkcu/bash.exe", "M:/hklm/bash.exe"]
    assert winutil.bash_values({}, FakeRegistry()) == ["", "", ""]


def test_a_registry_that_raises_is_just_not_set():
    class Locked:
        def get(self, *_a):
            raise OSError("locked hive")
        get_machine = get
    assert winutil.bash_values({GIT_VAR: "P"}, Locked()) == ["P"]
    assert winutil.bash_values({}, None) == [""]

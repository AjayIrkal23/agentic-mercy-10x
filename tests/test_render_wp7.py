"""render.py / backups.py fixes from WP7 (audit 2026-10-05 A-09, J-11, A-11, I-15).
Everything runs in tmp dirs; the live settings.json is never read or written."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "installer"))
sys.path.insert(0, str(_ROOT / "hooks"))

import backups  # noqa: E402
import render  # noqa: E402
from lib import platform as plat  # noqa: E402


def _age(p: Path, days: float) -> None:
    t = time.time() - days * 86400
    os.utime(p, (t, t))


def test_backup_keeps_the_newest_three_dated_and_leaves_named_ones(tmp_path):
    st = tmp_path / "settings.json"
    st.write_text("{}", encoding="utf-8")
    for name in ("settings.json.bak", "settings.json.bak-wp11"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    old = ["settings.json.bak-20260930-parity", "settings.json.bak-20260930-effort", "settings.json.bak.20260718-023117"]
    for i, name in enumerate(old):
        (tmp_path / name).write_text("{}", encoding="utf-8")
        _age(tmp_path / name, 10 + i)
    made = [backups.backup(st, keep=3, stamp=f"2026100{i}T000000Z") for i in range(5)]
    dated = backups.dated_backups(st)
    assert len(dated) == 3 and dated[0] == made[-1]
    assert (tmp_path / "settings.json.bak").exists() and (tmp_path / "settings.json.bak-wp11").exists()
    if not plat.IS_WINDOWS:  # NTFS has no mode bits; chmod only toggles read-only
        assert oct(made[-1].stat().st_mode & 0o777) == "0o600"


def test_retention_orders_by_mtime_not_by_the_name(tmp_path):
    st = tmp_path / "settings.json"
    st.write_text("{}", encoding="utf-8")
    future_named = tmp_path / "settings.json.bak-20991231-mislabeled"
    future_named.write_text("{}", encoding="utf-8")
    _age(future_named, 30)
    for i in range(3):
        backups.backup(st, keep=3, stamp=f"2026100{i}T000000Z")
    assert not future_named.exists()


def test_latest_pointer_never_dangles(tmp_path):
    st = tmp_path / "settings.json"
    st.write_text("{}", encoding="utf-8")
    latest = tmp_path / "settings.json.bak-latest"
    latest.write_text(str(tmp_path / "settings.json.bak.20260718-023117") + "\n", encoding="utf-8")
    backups.prune(st, keep=3)
    assert not latest.exists()  # nothing to point at
    made = backups.backup(st, keep=3, stamp="20261005T000000Z")
    assert Path(latest.read_text(encoding="utf-8").strip()) == made


# --- A-11 / I-15: render CLI ------------------------------------------------------ #
def _sandbox(tmp_path):
    root = tmp_path / "root"
    (root / "installer").mkdir(parents=True)
    (root / "mods" / "x" / ".claude-plugin").mkdir(parents=True)
    (root / "mods" / "x" / ".claude-plugin" / "plugin.json").write_text('{"name": "x"}', encoding="utf-8")
    (root / "installer" / "manifest.json").write_text(json.dumps({"mods": {"enabled": ["x"]}}), encoding="utf-8")
    tmpl = root / "settings.template.json"
    tmpl.write_text(json.dumps({"env": {"A": "1", "CLAUDE_CODE_PLUGIN_DIRS": "{{MOD_DIRS}}"},
                                "permissions": {"deny": []}}), encoding="utf-8")
    user = root / "settings.user.json"
    user.write_text(json.dumps({"env": {"B": "2"}}), encoding="utf-8")
    return root, tmpl, user, root / "settings.json"


def test_render_reads_mods_from_the_template_root(tmp_path):
    root, tmpl, user, _ = _sandbox(tmp_path)
    data = json.loads(render.render(tmpl, user))
    assert data["env"]["CLAUDE_CODE_PLUGIN_DIRS"] == (root / "mods" / "x").as_posix()


def test_check_honours_out_and_user(tmp_path):
    root, tmpl, user, out = _sandbox(tmp_path)
    args = ["--template", str(tmpl), "--user", str(user), "--out", str(out)]
    assert render.main(args) == 0
    assert render.main(["--check", *args]) == 0
    other = root / "other.user.json"
    other.write_text(json.dumps({"env": {"B": "3"}}), encoding="utf-8")
    assert render.main(["--check", "--template", str(tmpl), "--user", str(other), "--out", str(out)]) == 1
    data = json.loads(out.read_text(encoding="utf-8"))
    data["env"]["A"] = "drift"
    out.write_text(json.dumps(data), encoding="utf-8")
    assert render.main(["--check", *args]) == 1


def test_rewrite_backs_up_the_previous_file_and_bounds_the_count(tmp_path):
    root, tmpl, user, out = _sandbox(tmp_path)
    args = ["--template", str(tmpl), "--user", str(user), "--out", str(out)]
    render.main(args)
    assert backups.dated_backups(out) == []  # first write: nothing to back up
    render.main(args)
    assert backups.dated_backups(out) == []  # same content: no churn
    for i in range(5):
        out.write_text(json.dumps({"env": {"A": str(i)}}), encoding="utf-8")
        render.main(args)
        time.sleep(0.01)
    assert 1 <= len(backups.dated_backups(out)) <= 3


def test_failed_write_leaves_no_swap_file(tmp_path, monkeypatch):
    root, tmpl, user, out = _sandbox(tmp_path)

    def boom(*_a, **_k):
        raise OSError("disk full")
    monkeypatch.setattr(render.os, "replace", boom)
    with pytest.raises(OSError):
        render.main(["--template", str(tmpl), "--user", str(user), "--out", str(out)])
    assert not list(root.glob(".settings-*.swap"))

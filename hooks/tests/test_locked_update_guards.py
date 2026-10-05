"""A4v2-04 / A4v2-08: `locked_update` never turns an unreadable file into a blank state, and a lost write
leaves a telemetry row.

A reader `PermissionError` (Windows: a scanner or another writer's replace holds the file) used to look
like "missing": `fn` ran on the default and the result replaced the real content. And an `atomic_write`
failure (disk full, ACL) inside the lock was silent: the `written` flag had no production caller.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))
from lib import hook_telemetry  # noqa: E402
from lib import platform as plat  # noqa: E402


@pytest.fixture()
def rows(monkeypatch):
    seen: list = []
    monkeypatch.setattr(hook_telemetry, "record", lambda *a, **k: seen.append((a, k)))
    return seen


def _deny_reads(monkeypatch, target: Path, times: int) -> list:
    real, calls = Path.read_text, [0]

    def read_text(self, *a, **k):
        if self.name == target.name:
            calls[0] += 1
            if calls[0] <= times:
                raise PermissionError(13, "Access is denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", read_text)
    return calls


def test_an_unreadable_file_is_left_alone(monkeypatch, tmp_path, rows):
    target = tmp_path / "s.json"
    target.write_text(json.dumps({"n": 5}), encoding="utf-8")
    _deny_reads(monkeypatch, target, 10 ** 6)
    applied: list = []
    data, ok = plat.locked_update_ok(target, lambda d: applied.append(d) or {**d, "n": 6})
    monkeypatch.undo()
    assert ok is False and applied == []
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 5}
    assert rows == [(("platform", "locked_update_unreadable"), {"path": "s.json"})]


def test_a_read_denied_twice_is_retried_and_the_update_lands(monkeypatch, tmp_path, rows):
    target = tmp_path / "s.json"
    target.write_text(json.dumps({"n": 5}), encoding="utf-8")
    calls = _deny_reads(monkeypatch, target, 2)
    assert plat.locked_update(target, lambda d: {**d, "n": d["n"] + 1}) == {"n": 6}
    monkeypatch.undo()
    assert calls[0] == 3 and rows == []
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 6}


def test_a_corrupt_file_still_restarts_from_the_default(tmp_path, rows):
    target = tmp_path / "s.json"
    target.write_text("{not json", encoding="utf-8")
    assert plat.locked_update(target, lambda d: {**d, "n": 1}, default={"a": 0}) == {"a": 0, "n": 1}
    assert rows == []


def test_a_failed_write_leaves_a_telemetry_row(monkeypatch, tmp_path, rows):
    monkeypatch.setattr(plat, "atomic_write", lambda *a, **k: False)
    data, ok = plat.locked_update_ok(tmp_path / "s.json", lambda d: {"a": 1})
    assert (data, ok) == ({"a": 1}, False)
    assert rows == [(("platform", "locked_update_write_failed"), {"path": "s.json"})]


def test_a_good_write_leaves_no_row(tmp_path, rows):
    assert plat.locked_update_ok(tmp_path / "s.json", lambda d: {"a": 1}) == ({"a": 1}, True)
    assert rows == []

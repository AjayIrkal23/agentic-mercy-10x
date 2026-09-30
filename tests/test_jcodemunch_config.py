"""test_jcodemunch_config.py — the installer keeps ~/.code-index/config.jsonc on the
workflow's jcodemunch keys (tool_surface "full", AI summaries, trusted home) and only
ever writes through `jcodemunch-mcp config set`."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load():
    spec = importlib.util.spec_from_file_location("jcodemunch_config", _ROOT / "installer" / "jcodemunch_config.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


STOCK = """// jcodemunch-mcp configuration
{
  // "trusted_folders": [],
  "version": "1.108.319",
  "tool_surface": "counter",   // a trailing comment
  "url": "http://localhost:11434/v1",
  "extra_ignore_patterns": ["keep/**"],
  /* block
     comment */
  "max_index_files": 10000,
}
"""


@pytest.fixture
def jc(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path / "idx"))
    return _load()


def test_load_jsonc_strips_comments_and_trailing_commas_not_urls(jc):
    data = jc.load_jsonc(STOCK)
    assert data["tool_surface"] == "counter"
    assert data["url"] == "http://localhost:11434/v1"
    assert "trusted_folders" not in data


def test_required_expands_home_and_pins_full_surface(jc):
    req = jc.required()
    assert req["tool_surface"] == "full"
    assert str(Path.home()) in req["trusted_folders"]
    assert req["use_ai_summaries"] is True


def test_changes_set_scalars_and_union_lists_keeping_extras(jc):
    req = {"tool_surface": "full", "extra_ignore_patterns": ["a/**"], "max_index_files": 10000}
    todo = jc.changes(jc.load_jsonc(STOCK), req)
    assert todo == {"tool_surface": "full", "extra_ignore_patterns": ["keep/**", "a/**"]}
    assert jc.changes({"tool_surface": "full", "extra_ignore_patterns": ["a/**", "x"],
                       "max_index_files": 10000}, req) == {}


def test_gaps_none_when_absent_and_lists_keys_off(jc):
    assert jc.gaps() is None
    p = jc.config_path()
    p.parent.mkdir(parents=True)
    p.write_text(STOCK, encoding="utf-8")
    assert "tool_surface" in jc.gaps() and "trusted_folders" in jc.gaps()


def test_configure_sets_only_off_keys_via_cli_with_backup(jc, monkeypatch):
    p = jc.config_path()
    p.parent.mkdir(parents=True)
    p.write_text(STOCK, encoding="utf-8")
    calls = []
    monkeypatch.setattr(jc.shutil, "which", lambda name: "/fake/jcodemunch-mcp")
    monkeypatch.setattr(jc.plat, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    name, status = jc.configure()
    assert name == "jcodemunch-config" and status.startswith("OK")
    keys = {c[3]: json.loads(c[4]) for c in calls if c[1:3] == ["config", "set"]}
    assert keys["tool_surface"] == "full"
    assert keys["trusted_folders"] == [str(Path.home())]
    assert "max_index_files" in keys and "version" not in keys
    assert p.with_name(p.name + ".bak-installer").read_text(encoding="utf-8") == STOCK


def test_configure_dry_run_and_missing_binary_never_write(jc, monkeypatch):
    monkeypatch.setattr(jc.plat, "run", lambda *a, **k: pytest.fail("must not run"))
    monkeypatch.setattr(jc.shutil, "which", lambda name: None)
    assert jc.configure()[1].startswith("SKIP")
    monkeypatch.setattr(jc.shutil, "which", lambda name: "/fake/jcodemunch-mcp")
    p = jc.config_path()
    p.parent.mkdir(parents=True)
    p.write_text(STOCK, encoding="utf-8")
    assert jc.configure(dry_run=True)[1].startswith("WOULD-SET")

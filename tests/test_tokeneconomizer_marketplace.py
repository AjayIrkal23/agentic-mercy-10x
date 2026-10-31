"""scripts/tokeneconomizer-marketplace.py: clone the fork only when the clone is missing, never touch
a directory that is something else, then register the clone as a marketplace."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("te_mkt", _ROOT / "scripts" / "tokeneconomizer-marketplace.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)  # type: ignore[union-attr]


def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path / "CODE_FILES" / "TokenEconomizer"


def test_a_missing_clone_is_cloned_at_the_backfill_branch_then_registered(tmp_path, monkeypatch):
    dest, calls = _home(tmp_path, monkeypatch), []
    assert M.main(run=lambda argv: calls.append(argv) or 0) == 0
    assert calls == [["git", "clone", "--branch", M.BRANCH, M.FORK, str(dest)],
                     ["claude", "plugin", "marketplace", "add", str(dest)]]


def test_an_existing_clone_is_only_registered(tmp_path, monkeypatch):
    dest, calls = _home(tmp_path, monkeypatch), []
    (dest / ".claude-plugin").mkdir(parents=True)
    (dest / ".claude-plugin" / "marketplace.json").write_text("{}")
    assert M.main(run=lambda argv: calls.append(argv) or 0) == 0
    assert calls == [["claude", "plugin", "marketplace", "add", str(dest)]]


def test_toolprune_is_pinned_off_and_other_keys_kept(tmp_path, monkeypatch):
    """2026-10-31: TE's default `toolprune: auto` writes deny rules that hide tools on a fresh machine."""
    import json
    _home(tmp_path, monkeypatch)
    cfg = tmp_path / ".tokeneconomizer" / "config.json"
    assert M.ensure_toolprune_off() == "SET"                           # fresh machine: file created
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"toolprune": "off"}
    cfg.write_text(json.dumps({"microskills": "envfacts+distiller", "toolprune": "propose",
                               "toolprune_protect": ["Skill"]}), encoding="utf-8")
    assert M.ensure_toolprune_off() == "SET"
    assert json.loads(cfg.read_text(encoding="utf-8")) == {"microskills": "envfacts+distiller",
                                                           "toolprune": "off", "toolprune_protect": ["Skill"]}
    assert M.ensure_toolprune_off() == "PRESENT"
    cfg.write_text("{not json", encoding="utf-8")
    assert M.ensure_toolprune_off().startswith("SKIP") and cfg.read_text(encoding="utf-8") == "{not json"


def test_a_failed_clone_stops_and_a_foreign_directory_is_left_alone(tmp_path, monkeypatch):
    dest, calls = _home(tmp_path, monkeypatch), []
    assert M.main(run=lambda argv: calls.append(argv) or 128) == 128 and len(calls) == 1
    dest.mkdir(parents=True)
    calls.clear()
    assert M.main(run=lambda argv: calls.append(argv) or 0) == 1 and calls == []

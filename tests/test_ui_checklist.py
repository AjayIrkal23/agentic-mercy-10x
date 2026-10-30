"""DU-9: the visual installer prints the end-of-run checklist to its console too (a browser tab
closed early, or a remote box viewed over a tunnel, must not hide the sudo and human steps)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ui  # noqa: E402


def test_run_install_prints_the_checklist_and_path_hint(monkeypatch, capsys, tmp_path):
    todo = ["Human-only steps (cannot be automated):", "  [ ] gh auth login"]
    monkeypatch.setitem(ui._STATE, "target", str(tmp_path))
    monkeypatch.setattr(ui._selfheal, "pin_config_dir", lambda target: None)
    monkeypatch.setattr(ui._selfheal, "self_heal", lambda target, emit=None: {"todo": todo, "success": True,
                                                                               "rounds": 1})
    monkeypatch.setattr(ui, "_path_hint", lambda: "Open a new terminal (path hint).")
    ui._run_install()
    out = capsys.readouterr().out
    assert "Human-only steps (cannot be automated):" in out and "[ ] gh auth login" in out
    assert out.count("Open a new terminal (path hint).") == 1
    assert any(s["kind"] == "todo" for s in ui._JOB["steps"])

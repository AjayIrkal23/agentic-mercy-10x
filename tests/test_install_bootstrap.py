"""bootstrap on Windows (A5-09, A5-10, A5-13, A5-15): the end-of-run hint, relocation that reports
what it could not copy (read-only retry, locked files, persistent failures), ``.pre-install`` kept
only after a real overwrite, no Zone.Identifier stream copied, and an honest message without git."""
from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bootstrap  # noqa: E402
import ostools  # noqa: E402
import relocation  # noqa: E402
from lib import platform as plat  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
FILES = {"hooks/a.py": "new a", "skills/s/SKILL.md": "s", "agents/x.md": "x", "rules/r.md": "r",
         "scripts/s.py": "s", "installer/i.py": "i", "settings.template.json": "{}",
         "install-ui.py": "ui", "CLAUDE.md": "new claude", "docs/note.md": "note"}


def _tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def clone(tmp_path):
    return _tree(tmp_path / "clone", FILES)


@pytest.fixture
def target(tmp_path):
    return tmp_path / "home" / ".claude"


def _fail_for(monkeypatch, *names: str, once: bool = False):
    """``relocation._copy`` raises PermissionError for these file names (first time only with ``once``)."""
    real, seen = relocation._copy, set()

    def copy(src, dst):
        if Path(dst).name in names and not (once and str(dst) in seen):
            seen.add(str(dst))
            raise PermissionError(13, "in use by another process")
        return real(src, dst)
    monkeypatch.setattr(relocation, "_copy", copy)


def relocate(clone, target, failed=None):
    lines: list = []
    n = bootstrap.relocate(clone, target, emit=lambda *r: lines.append(r), failed=failed)
    return n, lines


def test_a_read_only_target_file_is_replaced(clone, target):
    old = _tree(target, {"hooks/a.py": "old a"})
    os.chmod(old / "hooks" / "a.py", stat.S_IREAD)
    failed: list = []
    relocate(clone, target, failed)
    assert (target / "hooks" / "a.py").read_text(encoding="utf-8") == "new a" and failed == []


def test_a_locked_file_is_retried_once_after_clearing_the_read_only_bit(clone, target, monkeypatch):
    _tree(target, {"hooks/a.py": "old a"})
    chmods: list = []
    real_chmod = os.chmod
    monkeypatch.setattr(relocation.os, "chmod", lambda p, m, **k: chmods.append((Path(p).name, m)) or real_chmod(p, m, **k))
    _fail_for(monkeypatch, "a.py", once=True)
    failed: list = []
    relocate(clone, target, failed)
    assert failed == [] and (target / "hooks" / "a.py").read_text(encoding="utf-8") == "new a"
    assert next(m for n, m in chmods if n == "a.py") == stat.S_IREAD | stat.S_IWRITE  # the bit cleared first


def test_a_persistent_failure_is_listed_not_swallowed_and_not_ok(clone, target, monkeypatch):
    _fail_for(monkeypatch, "a.py")
    failed: list = []
    n, lines = relocate(clone, target, failed)
    assert [f[0] for f in failed] == ["hooks/a.py"] and "in use" in failed[0][1]
    assert not (target / "hooks" / "a.py").exists() and n == len(FILES) - 1
    status = next(s for k, _, s in lines if k == "relocate")
    assert not status.startswith("OK") and "1 failed" in status
    assert bootstrap.fatal_failures(failed) == failed  # a bundle sentinel dir: the install cannot go on


def test_a_failure_outside_the_bundle_items_is_listed_but_not_fatal(clone, target, monkeypatch):
    _fail_for(monkeypatch, "note.md")
    failed: list = []
    relocate(clone, target, failed)
    assert [f[0] for f in failed] == ["docs/note.md"] and bootstrap.fatal_failures(failed) == []


def test_only_the_first_five_failures_are_printed(clone, target, monkeypatch, capsys):
    many = _tree(clone, {f"hooks/f{i}.py": "x" for i in range(7)})
    _fail_for(monkeypatch, *[f"f{i}.py" for i in range(7)])
    failed: list = []
    relocate(many, target, failed)
    out = capsys.readouterr().out
    assert len(failed) == 7 and out.count("hooks/f") == 5 and "2 more" in out


def test_main_fails_when_a_bundle_file_could_not_be_copied(clone, target, monkeypatch, capsys):
    _fail_for(monkeypatch, "install-ui.py")
    monkeypatch.setattr(bootstrap, "_SRC_ROOT", clone)
    monkeypatch.setattr(bootstrap, "canonical_target", lambda: target)
    monkeypatch.delenv(bootstrap._GUARD, raising=False)
    monkeypatch.setattr(bootstrap, "_run_headless", lambda ci: pytest.fail("must not continue"))
    assert bootstrap.main(["--ci"]) == 1
    assert "install-ui.py" in capsys.readouterr().out


def test_pre_install_copy_is_written_after_the_overwrite_succeeded(clone, target):
    _tree(target, {"CLAUDE.md": "mine"})  # first install: bundle items missing at the target
    relocate(clone, target)
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "new claude"
    assert (target / "CLAUDE.md.pre-install").read_text(encoding="utf-8") == "mine"


def test_no_pre_install_copy_for_a_file_that_was_not_replaced(clone, target, monkeypatch):
    _tree(target, {"CLAUDE.md": "mine"})
    _fail_for(monkeypatch, "CLAUDE.md")
    failed: list = []
    relocate(clone, target, failed)
    assert (target / "CLAUDE.md").read_text(encoding="utf-8") == "mine"
    assert not (target / "CLAUDE.md.pre-install").exists() and [f[0] for f in failed] == ["CLAUDE.md"]


def test_the_pre_install_copy_keeps_the_originals_permissions(clone, target):
    """SEC1B-08: the kept copy used to get the umask default; a read-only / 0600 original stays so."""
    mine = _tree(target, {"CLAUDE.md": "mine"}) / "CLAUDE.md"
    os.chmod(mine, stat.S_IREAD)
    want = stat.S_IMODE(mine.stat().st_mode)
    relocate(clone, target)
    keep = target / "CLAUDE.md.pre-install"
    assert keep.read_text(encoding="utf-8") == "mine" and stat.S_IMODE(keep.stat().st_mode) == want


def test_the_original_is_kept_before_it_is_overwritten_so_a_failed_overwrite_loses_nothing(clone, target, monkeypatch):
    mine = _tree(target, {"CLAUDE.md": "mine"}) / "CLAUDE.md"
    seen: list = []
    real = relocation._copy

    def copy(src, dst):
        if Path(dst).name == "CLAUDE.md":
            seen.append(sorted(p.name for p in target.glob("CLAUDE.md*")))  # what exists when the overwrite starts
        return real(src, dst)
    monkeypatch.setattr(relocation, "_copy", copy)
    relocate(clone, target)
    assert seen == [["CLAUDE.md", "CLAUDE.md.pre-install"]] and mine.read_text(encoding="utf-8") == "new claude"


@pytest.mark.parametrize("windows", [True, False])
def test_windows_copies_without_alternate_streams(clone, target, monkeypatch, windows):
    """Intent, not the call set: POSIX ``copy2`` calls the global ``copyfile`` itself (3.10 - 3.14), Windows
    3.12+ ``copy2`` never does. Windows must never reach ``copy2`` (NTFS streams); POSIX must."""
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)
    seen: list = []
    for name in ("copyfile", "copy2"):
        real = getattr(shutil, name)
        monkeypatch.setattr(shutil, name, lambda s, d, _r=real, _n=name, **k: seen.append(_n) or _r(s, d, **k))
    relocate(clone, target)
    assert ("copy2" in seen) is (not windows) and ("copyfile" in seen or not windows)


@pytest.mark.skipif(not plat.IS_WINDOWS, reason="NTFS alternate data streams")
def test_a_zone_identifier_stream_is_not_carried_into_the_target(clone, target):
    with open(str(clone / "hooks" / "a.py") + ":Zone.Identifier", "w", encoding="utf-8") as fh:
        fh.write("[ZoneTransfer]\nZoneId=3\n")
    relocate(clone, target)
    assert (target / "hooks" / "a.py").is_file() and not os.path.exists(str(target / "hooks" / "a.py") + ":Zone.Identifier")


def test_without_git_the_message_says_so_instead_of_blaming_the_clone(clone, target, monkeypatch, capsys):
    (clone / ".git").mkdir()
    monkeypatch.setattr(bootstrap, "_SRC_ROOT", clone)
    monkeypatch.setattr(bootstrap, "canonical_target", lambda: target)
    monkeypatch.delenv(bootstrap._GUARD, raising=False)
    monkeypatch.setattr(shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "relocate", lambda *a, **k: 0)
    monkeypatch.setattr(bootstrap, "_launch_ui", lambda: 0)
    monkeypatch.setattr(bootstrap, "_run_headless", lambda ci: 0)
    bootstrap.main([])
    out = capsys.readouterr().out
    assert "git not found — skipping git restore" in out and "uncommitted" not in out


# --- the end-of-run hint ---------------------------------------------------------------------- #
def test_windows_hint_is_a_new_terminal_with_no_export(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.delenv("CLAUDE_CODE_GIT_BASH_PATH", raising=False)
    hint = bootstrap._path_hint()
    assert "Open a new terminal" in hint and "claude, node, git, uv, gh" in hint and "export" not in hint
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", "/t/git/bin/bash.exe")
    assert "CLAUDE_CODE_GIT_BASH_PATH=/t/git/bin/bash.exe" in bootstrap._path_hint()


def test_posix_hint_is_unchanged(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    assert 'export PATH="$HOME/.local/bin:$PATH"' in bootstrap._path_hint()


def _headless(monkeypatch, capsys, *, windows: bool, sudo="sudo apt-get install -y iproute2") -> str:
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)
    todo = ostools.checklist(M, None if windows else sudo)
    res = {"rows": [], "success": True, "rounds": 1, "fails": [], "todo": todo}
    monkeypatch.setitem(sys.modules, "selfheal", SimpleNamespace(self_heal=lambda t, ci: res))
    assert bootstrap._run_headless(ci=False) == 0
    return capsys.readouterr().out


@pytest.mark.parametrize("ci,ok,head", [(True, True, "install (plan only): OK"), (True, False, "install (plan only): INCOMPLETE"),
                                        (False, True, "install: SUCCESS"), (False, False, "install: INCOMPLETE")])
def test_a_ci_run_says_it_planned_and_never_success(monkeypatch, capsys, ci, ok, head):  # A6v2-03
    res = {"rows": [], "success": ok, "rounds": 1, "fails": [] if ok else ["links"], "todo": []}
    monkeypatch.setitem(sys.modules, "selfheal", SimpleNamespace(self_heal=lambda t, ci: res))
    assert bootstrap._run_headless(ci=ci) == (0 if ok else 1)
    out = capsys.readouterr().out
    assert head in out and ("nothing was installed" in out) == ci
    assert ("SUCCESS" in out) == (ok and not ci)


def test_a_windows_install_prints_no_posix_text(monkeypatch, capsys):
    out = _headless(monkeypatch, capsys, windows=True)
    assert "export" not in out and "apt" not in out and "sudo" not in out
    assert out.count("Open a new terminal") == 1 and "gh auth login" in out


def test_a_linux_install_still_prints_the_apt_and_export_lines(monkeypatch, capsys):
    out = _headless(monkeypatch, capsys, windows=False)
    assert "apt-get install" in out and "export PATH" in out and "Open a new terminal (or" in out


def test_checklist_adds_the_new_terminal_step_only_on_windows(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert any("Open a new terminal" in ln for ln in ostools.checklist(M, None))
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    assert not any("new terminal" in ln for ln in ostools.checklist(M, None))

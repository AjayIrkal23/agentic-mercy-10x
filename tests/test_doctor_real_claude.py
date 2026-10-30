"""F3: the doctor runs the Claude Code CLI itself, never bin/claude (the oomguard launcher): through the
launcher `claude plugin test` got `--settings` in front of it and refused, and `claude --version` wrote a
launch-caps file that made the launch-caps row PASS."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import doctor_mods  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix", reason="shebang scripts as fake binaries")

LAUNCHER = "#!/usr/bin/env bash\n# agentic-mercy oomguard launcher: test copy\n"


def _exe(d: Path, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / "claude"
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


def test_real_claude_skips_the_launcher(tmp_path):
    wrap = _exe(tmp_path / "wrap", LAUNCHER)
    real = _exe(tmp_path / "real", "#!/bin/sh\necho 2.1.288\n")
    both = f"{wrap.parent}{os.pathsep}{real.parent}"
    assert doctor_mods.real_claude(environ={"PATH": both}) == str(real)
    assert doctor_mods.real_claude(environ={"PATH": str(real.parent)}) == str(real)
    assert doctor_mods.real_claude(environ={"PATH": str(wrap.parent)}) is None
    assert doctor_mods.real_claude(environ={"PATH": str(wrap.parent), "CLAUDE_REAL_BIN": str(real)}) == str(real)


def test_mods_runtime_runs_the_real_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_mods, "real_claude", lambda: "/opt/real/claude")
    (tmp_path / "mods" / "m").mkdir(parents=True)
    calls: list = []
    st, _ = doctor_mods.check_mods_runtime(tmp_path, ["m"], False,
                                           run=lambda argv, cwd=None: calls.append(argv) or (0, "ok"))
    assert calls[0][:3] == ["/opt/real/claude", "plugin", "test"] and st == "PASS"

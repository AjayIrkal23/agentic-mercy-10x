"""F8: a machine whose owner put LOCAL_SUDO_PASS in ~/.claude/.env gets the gitignored
scripts/sudo-askpass.sh (mode 700) from the tracked example; .env is the helper's only password source."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
import settings_install as SI  # noqa: E402

pytestmark = pytest.mark.skipif(os.name != "posix" or shutil.which("bash") is None, reason="POSIX helper")
EXAMPLE = ROOT / "scripts" / "sudo-askpass.example.sh"


def _target(tmp: Path, env_text: str | None) -> Path:
    (tmp / "scripts").mkdir()
    shutil.copy(EXAMPLE, tmp / "scripts" / "sudo-askpass.example.sh")
    if env_text is not None:
        (tmp / ".env").write_text(env_text, encoding="utf-8")
    return tmp


def test_seeded_mode_700_when_the_owner_opted_in(tmp_path):
    t = _target(tmp_path, "LOCAL_SUDO_PASS=example-only\n")
    rows: list = []
    assert SI.seed_askpass(t, lambda *r: rows.append(r))
    dst = t / "scripts" / "sudo-askpass.sh"
    assert stat.S_IMODE(dst.stat().st_mode) == 0o700 and dst.read_bytes() == EXAMPLE.read_bytes()
    assert "example-only" not in dst.read_text(encoding="utf-8") and any("mode 700" in r[2] for r in rows)


@pytest.mark.parametrize("env_text", [None, "", "OTHER=1\n", "LOCAL_SUDO_PASS=\n", "LOCAL_SUDO_PASS=''\n"])
def test_not_seeded_without_a_password_in_env(tmp_path, env_text):
    t = _target(tmp_path, env_text)
    assert not SI.seed_askpass(t, lambda *r: None) and not (t / "scripts" / "sudo-askpass.sh").exists()


def test_an_existing_helper_is_never_replaced(tmp_path):
    t = _target(tmp_path, "export LOCAL_SUDO_PASS=example-only\n")
    own = t / "scripts" / "sudo-askpass.sh"
    own.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    assert not SI.seed_askpass(t, lambda *r: None) and own.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_the_helper_reads_only_the_env_file(tmp_path):
    base = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path), "LOCAL_SUDO_PASS": "from-the-caller"}

    def run():
        return subprocess.run(["bash", str(EXAMPLE)], capture_output=True, text=True, env=base, timeout=20)
    cp = run()
    assert cp.returncode == 2 and cp.stdout == ""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".env").write_text("LOCAL_SUDO_PASS=example-only\n", encoding="utf-8")
    cp = run()
    assert cp.returncode == 0 and cp.stdout == "example-only\n"

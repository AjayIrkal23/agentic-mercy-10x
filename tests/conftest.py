"""Suite-wide isolation: hook telemetry goes to a temp dir, never the live one.

Same rule as hooks/tests/conftest.py (audit 2026-10-05 I-01): installer, doctor and
render tests spawn hooks that honour CLAUDE_HOOK_TELEMETRY_DIR.
"""
import os
import shutil
import tempfile

import pytest

_MY_DIRS: list = []


def _own_dir(var: str, prefix: str) -> None:
    # remember only the dirs this conftest created (a pre-set env var is the caller's)
    if var not in os.environ:
        d = tempfile.mkdtemp(prefix=prefix)
        _MY_DIRS.append(d)
        os.environ[var] = d


_own_dir("CLAUDE_HOOK_TELEMETRY_DIR", "claude-hook-telemetry-")
_own_dir("CLAUDE_HOOK_STATE_DIR", "claude-hook-state-")
# hooks/.state (gate evidence, index state) — audit J-02
_own_dir("CLAUDE_HOOK_DOTSTATE_DIR", "claude-hook-dotstate-")
# installer tests must never download node / claude / ollama or call apt (selfheal._base_tools)
os.environ.setdefault("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")


def pytest_sessionfinish(session, exitstatus):
    """A7-17: do not leave three temp dirs per run behind."""
    for d in _MY_DIRS:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def _restore_environ():
    """Installer code writes os.environ directly (bootstrap.main: CLAUDE_CONFIG_DIR and the
    relocation guard; selfheal.pin_config_dir). monkeypatch cannot undo a write it never
    recorded, so a leaked CLAUDE_CONFIG_DIR moved `_claude_dir()` for later hook tests."""
    saved = dict(os.environ)
    yield
    if dict(os.environ) != saved:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture
def symlink_ok(tmp_path):
    """Skip when this account cannot create symlinks (Windows without Developer Mode / admin)."""
    target = tmp_path / "symlink-probe-target"
    target.write_text("x", encoding="utf-8")
    try:
        os.symlink(target, tmp_path / "symlink-probe-link")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"cannot create symlinks here ({exc}); on Windows enable Developer Mode or run elevated")

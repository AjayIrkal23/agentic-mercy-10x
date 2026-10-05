"""Suite-wide isolation: hook telemetry goes to a temp dir, never the live one.

Scripts derive `hooks/.telemetry` and `telemetry/` from their own location, so a
sandbox HOME did not isolate them (audit 2026-10-05 I-01: ~70% of the production
dir was test residue). Every writer and reader honours CLAUDE_HOOK_TELEMETRY_DIR;
setting it here reaches every in-process import and every spawned hook.
"""
import os
import shutil
import tempfile

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


def pytest_sessionfinish(session, exitstatus):
    """A7-17: do not leave three temp dirs per run behind."""
    for d in _MY_DIRS:
        shutil.rmtree(d, ignore_errors=True)

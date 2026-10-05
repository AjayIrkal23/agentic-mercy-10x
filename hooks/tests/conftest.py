"""Suite-wide isolation: hook telemetry goes to a temp dir, never the live one.

Scripts derive `hooks/.telemetry` and `telemetry/` from their own location, so a
sandbox HOME did not isolate them (audit 2026-10-05 I-01: ~70% of the production
dir was test residue). Every writer and reader honours CLAUDE_HOOK_TELEMETRY_DIR;
setting it here reaches every in-process import and every spawned hook.
"""
import os
import tempfile

os.environ.setdefault("CLAUDE_HOOK_TELEMETRY_DIR", tempfile.mkdtemp(prefix="claude-hook-telemetry-"))
os.environ.setdefault("CLAUDE_HOOK_STATE_DIR", tempfile.mkdtemp(prefix="claude-hook-state-"))
# hooks/.state (gate evidence, index state) — audit J-02
os.environ.setdefault("CLAUDE_HOOK_DOTSTATE_DIR", tempfile.mkdtemp(prefix="claude-hook-dotstate-"))

"""Suite-wide isolation: hook telemetry goes to a temp dir, never the live one.

Same rule as hooks/tests/conftest.py (audit 2026-10-05 I-01): installer, doctor and
render tests spawn hooks that honour CLAUDE_HOOK_TELEMETRY_DIR.
"""
import os
import tempfile

os.environ.setdefault("CLAUDE_HOOK_TELEMETRY_DIR", tempfile.mkdtemp(prefix="claude-hook-telemetry-"))
os.environ.setdefault("CLAUDE_HOOK_STATE_DIR", tempfile.mkdtemp(prefix="claude-hook-state-"))
# hooks/.state (gate evidence, index state) — audit J-02
os.environ.setdefault("CLAUDE_HOOK_DOTSTATE_DIR", tempfile.mkdtemp(prefix="claude-hook-dotstate-"))
# installer tests must never download node / claude / ollama or call apt (selfheal._base_tools)
os.environ.setdefault("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")

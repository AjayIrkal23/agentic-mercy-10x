# `hooks/tools/` — local rules

Standalone hook utilities run by the dispatcher or the doctor, not per-tool links.

| File | Role |
|------|------|
| `link-doctor.py` | fires a synthetic event through every enabled dispatch link; asserts exit 0 + parseable output + telemetry (run by `installer/doctor.py`) |
| `state-cleanup.py` | session-start async exec: bounded retention purge of `telemetry/` and `state/` files |

- Both must never raise and never block a session; set `CLAUDE_HOOK_DOCTOR=1` when
  dry-firing links so disk-writing links no-op.
- Parent: [`../CLAUDE.md`](../CLAUDE.md)

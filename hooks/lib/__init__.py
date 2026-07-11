"""hooks/lib — shared stdlib-only foundation for the 100x workflow system.

Modules:
  platform       — the ONE sys.platform branching point (paths, exes, process control).
  repo_context   — the ONLY active-repo resolver (walk-up .git, RepoCtx key).
  hook_telemetry — O_APPEND jsonl fire-logger + debug dump.

Every P1/P3/P4/P6 deliverable imports from here. Pure Python 3 stdlib only:
no third-party deps, no hardcoded absolute paths, Windows+POSIX portable.
"""

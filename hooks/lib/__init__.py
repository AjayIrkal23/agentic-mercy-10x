"""hooks/lib — shared stdlib-only foundation for the 100x workflow system.

Modules:
  platform       — the ONE sys.platform branching point (paths, exes, process control).
  repo_context   — the ONLY active-repo resolver (walk-up .git, RepoCtx key).
  hook_telemetry — O_APPEND jsonl fire-logger + debug dump.
  skill_aliases  — alias -> canonical skill-name resolution (skill-aliases.json).
  code_files     — the one code-file classifier and anchored skip list.
  gate_state     — per-session gate JSON state: safe ids, paths, locked read-modify-write.
  turns          — turn-boundary helpers for Stop-time gates.
  memwatch_state — the OOM guard's shared state file paths and readers.
  gate_mode      — ask-or-advise: an ask downgrades to an advisory when nobody can answer.
  oomguard_config — the OOM guard's user overrides with defaults.
  plan_tier      — which Claude plan this machine runs on and what it allows.
  usage_guard    — steps subagents down while the 5-hour window is nearly used up.
  session_notices — one-line SessionStart notices.
  memory_gate    — Stop gate 7: a "remember this" prompt ends with a saved memory.
  persist_common — per-session dedup ledger and the CODEX append primitive.
  invoke_templates — prose for the /invoke skill family.
  model_mode     — per-project subagent model mode and the shared model resolver.
  workflow_script — script surgery for the workflow model guard.

Every P1/P3/P4/P6 deliverable imports from here. Pure Python 3 stdlib only:
no third-party deps, no hardcoded absolute paths, Windows+POSIX portable.
"""

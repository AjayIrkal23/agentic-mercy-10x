# Model routing (mechanism)

Three layers, one truth (`hooks/model-policy.json`):

1. `env.CLAUDE_CODE_SUBAGENT_MODEL=sonnet` — native *default only* (2.1.251+ semantics);
   an agent's `model:` and a per-call `model` win over it.
2. Agent frontmatter `model:` on every agent: `opus` for the judges (santa-reviewer,
   frontend-uiux-designer, planning-director, spec-architect, debug-detective);
   `sonnet` for every executor. `agents/team-lead.md` is the main session's team playbook
   (no frontmatter), not an agent.
3. `opus-guard` (PreToolUse `Agent`) sets `model` and the `[label]`. Precedence:
   **session flag > per-project mode > explicit `model` / `[label]` (pinned agents,
   escalation executors and fable only with the user's override phrase this turn) > agent
   pin > escalation > sonnet**. An ignored explicit model is named in the telemetry reason. Escalation lifts an executor (implementors, integrator, refactor)
   to Opus when the prompt reports a failed previous attempt, or when it names no
   plan/spec and the task classifies as size ≥ L and risk ≥ 2. So omit `model` on
   `Agent` calls unless honoring a user's model request. Every decision is logged to
   `hooks/.telemetry/<sid>.model-routing.jsonl`. It never touches `prompt` or `name`;
   the write protocol reaches subagents through a `SubagentStart` hook. Fable is never
   automatic.

Overrides: per-project `state/model-modes/<repo>` via `scripts/model-mode.py` or the
phrases "use opus for this project" / "back to normal" (prompt router). Global flags
`state/sonnet-only-mode` > `opus-only-mode` > `fable-only-mode` hit every project — never
for one repo.

Effort: per-agent `effort:` frontmatter is the only lever — xhigh santa, debug, uiux;
high implementors, integrator, refactor, test, audit, spec, plan, security;
medium docs-sync, deadcode, qa, memory-codex. `max` is banned
(`hooks/tests/test_model_policy_consistency.py`). Claude Code reads no subagent-effort
env var (`CLAUDE_CODE_SUBAGENT_EFFORT` does nothing), so built-ins (general-purpose,
Explore, Plan) run at Claude Code's own default.

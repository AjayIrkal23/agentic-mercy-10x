# Model routing (mechanism)

Three layers, one truth (`hooks/model-policy.json`):

1. `env.CLAUDE_CODE_SUBAGENT_MODEL=sonnet` — native *default only* (2.1.251+ semantics);
   an agent's `model:` and a per-call `model` win over it.
2. Agent frontmatter `model:` on every agent (`opus` for the implementor/design agents
   and `santa-reviewer`; `sonnet` otherwise).
3. `opus-guard` (PreToolUse `Agent`) aligns `[label]` ⇄ `model`. Precedence:
   **session flag > per-project mode > explicit `model` param > agent pin > `[label]` >
   sonnet**. It never touches `prompt` or `name`; the write protocol reaches subagents
   through a `SubagentStart` hook. Fable is never automatic.

Overrides: per-project `state/model-modes/<repo>` via `scripts/model-mode.py` or the
phrases "use opus for this project" / "back to normal" (prompt router). Global flags
`state/sonnet-only-mode` > `opus-only-mode` > `fable-only-mode` hit every project — never
for one repo.

Effort: `CLAUDE_CODE_SUBAGENT_EFFORT=high` default; per-agent `effort:` — xhigh
implementors, santa, debug, uiux; high audit, spec, plan, security, test, refactor,
integrator; medium docs-sync, deadcode, qa, memory-codex.

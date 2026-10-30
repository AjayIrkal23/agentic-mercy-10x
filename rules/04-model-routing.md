# Model routing (mechanism)

One truth: `hooks/model-policy.json`. The plan tier is detected at session start from the login
(`pro` / `max5` / `max20` / `api`; `state/plan-tier.json`) and picks a column; the agent's role picks the row.
Haiku 5.5 is the default worker (explore, docs, cleanup, verify everywhere; every executor on pro); Sonnet
executes on max5/max20; judges are Sonnet on pro and max5, Opus on max20. Escalation (retry marker, or no
plan marker with size >= L and risk >= 2) lifts executors one model within the ceiling: pro never Opus or
Fable; max5 Opus only when my turn says "use opus"; Fable only on max20 when I say "use fable".
Above 80 % of the 5-hour window every subagent steps down one model (`state/usage-guard.json`, `↓` in the
statusline) until the window resets or drops under 70 %. `opus-guard` (Agent), `workflow-model-guard`
(Workflow) and the generated `workflows/*.js` enforce it; the mercy mod caps `agent.spawn` when present.
My `/model`, my per-turn phrase and a per-project pin (`use opus for this project`, capped) always win.
Omit `model` on `Agent` calls. Full matrix, state files, telemetry: `docs/MODEL-ROUTING.md`.

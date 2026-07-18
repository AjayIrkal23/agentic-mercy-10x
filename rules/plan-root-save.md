# Plan file save locations (plan-root-save)

> Always-on rule, referenced by `workflow-orchestrator` and `planning-and-task-breakdown`.
> Restored 2026-07-18 after backup loss (content reconstructed from referencing skills).

Every approved plan is saved to BOTH locations, same kebab-case `<feature-name>` slug:

1. **Project root:** `plan-YYYY-MM-DD-<feature-name>.md` — visible entry point for the repo.
2. **Superpowers tree:** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` — canonical archive consumed by executing-plans / subagent-driven-development.

Rules:
- Date is the day the plan is approved, not started.
- The two files are the same content; root copy may be deleted after the plan ships, the `docs/superpowers/plans/` copy is permanent.
- Specs live separately under `docs/superpowers/specs/`; plans link to their spec.

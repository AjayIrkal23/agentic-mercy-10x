<!-- ecc:skills/config-gc, skills/automation-audit-ops, skills/workspace-surface-audit, agents/harness-optimizer.md, commands/harness-audit.md, scripts/harness-audit.js, scripts/lib/harness-audit-consumer.js @25278e7d -->
# Harness audit method (ECC graft)

## Scored categories (0–10 each)

hooks, skills, agents, rules/doctrine, MCP servers, memory, settings/permissions, docs.
Score each on: is it wired, is it used, is it correct, what does it cost (tokens, latency,
RAM). Report the score with the evidence line per category.

## Keep / merge / cut / fix

For every component: **keep** (used, correct), **merge** (duplicates another; name the
survivor), **cut** (unused or superseded), **fix** (used but wrong). Every verdict cites the
evidence (telemetry row, reference count, test).

## Soft-delete ladder

Never jump straight to delete: **disable** (config flag off) → **quarantine** (moved out of
the load path, still on disk) → **delete** after a clean observation window. Each rung is
reversible by the user.

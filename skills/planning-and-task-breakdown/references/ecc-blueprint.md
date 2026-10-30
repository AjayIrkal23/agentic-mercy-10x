<!-- ecc:skills/blueprint, commands/prp-plan.md @25278e7d -->
# SOURCE-cited plans and multi-PR graphs (ECC graft)

- **SOURCE-cited:** every task names the `file:symbol` it changes (or the new file it
  creates) and cites the evidence that the change belongs there; a task without a target is
  not ready.
- **Multi-PR dependency graph:** when a plan spans several PRs, list each PR with its tasks,
  what it depends on, and what it unblocks; independent PRs are marked so they can run in
  parallel; each PR is shippable on its own.

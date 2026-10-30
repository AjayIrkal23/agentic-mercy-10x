---
name: ecc-digest-github-coordination
description: ECC's GitHub-native epic coordination (claim, sync, validate, publish, review, unblock, decompose) driven by a marked block and coordination labels on epic issues; the reusable idea is a label state machine with a dry-run preview.
---
<!-- ecc-digest:github-coordination@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# GitHub coordination

## What it is
ECC coordinates multi-agent work on GitHub through epic issues. `scripts/github-coordination.js`, backed by `scripts/lib/github-coordination.js` and the `scripts/lib/github-coordination` modules (policy, parsing, gh API, state, actions, store), implements seven verbs: claim, sync, validate, publish, review, unblock and decompose. Each `commands/epic-*.md` file is a ten-line shim over one verb. An epic issue carries a marked `ecc-coordination` block in its body that holds the machine state, and labels in a `coordination:` namespace mirror it: available, claimed, ready, blocked, validated, review-requested, review-approved, review-changes-requested, published, synced. `config/github-native-coordination.json` holds the policy: one branch per epic (no task branches), validation and review required before publish. All GitHub I/O goes through the `gh` CLI, a `--dry-run` flag previews every change, and a local snapshot is kept in ECC's sql.js state store. `scripts/work-items.js` is the companion: a local table of work items from Linear, GitHub, handoffs or manual entry, with list, show, upsert, close, claim (recording whether the owner is an agent or a human) and a GitHub sync that maps issues and PRs and closes stale rows.

## The reusable idea
A tracker issue can be a small state machine that several agents share without a server. The state lives in two places that check each other: a fenced, machine-readable block in the issue body (the source of truth) and labels (the view humans and filters use). Every verb reads the block, checks the transition against a policy file, previews the edit in dry-run, then writes block and labels together through the CLI. Recording whether a claim came from an agent or a human makes later audits simple. The design needs no webhook and no extra service; `gh` is the only dependency.

## Why not adopted
It encodes ECC's own project process, and nothing in this workbench runs epic-level multi-agent work on GitHub. The existing `to-issues` and `triage` skills plus the GitHub MCP cover issue creation and triage; neither needs a label state machine today. The scripts also depend on the Node runtime and ECC's state store. If epic coordination is ever wanted, the block-plus-labels protocol above can be rebuilt as a short Python script over `gh`.

## Upstream paths
- `commands/epic-claim.md`
- `commands/epic-decompose.md`
- `commands/epic-publish.md`
- `commands/epic-review.md`
- `commands/epic-sync.md`
- `commands/epic-unblock.md`
- `commands/epic-validate.md`
- `config/github-native-coordination.json`
- `scripts/github-coordination.js`
- `scripts/lib/github-coordination`
- `scripts/lib/github-coordination.js`
- `scripts/work-items.js`

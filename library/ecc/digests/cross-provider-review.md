---
name: ecc-digest-cross-provider-review
description: ECC Astra review and the council multi-model skill, which send a diff or a decision draft to a second provider's CLI for an independent verdict; the reusable idea is a consent-gated second opinion with a pinned, sandboxed adapter and a PASS/FAIL exit code.
---
<!-- ecc-digest:cross-provider-review@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Cross-provider review

## What it is
`scripts/astra-review.js` with `scripts/lib/astra-review` sends a change to a model from another provider, through that provider's Codex CLI, for an independent review. The scope can be the uncommitted tree (default), a base ref, one commit, a file list or the files of a commit. Nothing leaves the machine until the caller passes an explicit consent flag (or sets the matching environment variable). The review returns PASS or FAIL with findings, the exit code is 0, 1 or 2 (error), and an optional fix mode lets the second model edit the tree. Timeouts run from 30 to 900 seconds. `commands/astra-review.md`, `docs/ASTRA-REVIEW-GUIDE.md` and the README section are the entry points. `skills/council-multi-model` is the decision-side twin: after the council skill's four voices produce a draft, it asks the second provider for one critique, through a sandboxed adapter that runs in a new empty temp dir, ignores the user's own config and rules, and pins the CLI to an exact version.

## The reusable idea
A second model only adds signal when it cannot see the first model's reasoning, so the reviewer gets the diff and the task, never the conversation. Make the egress explicit: a flag per run, named after the provider, with no default. Run the external CLI in an empty directory with config loading disabled and the version pinned, so a CLI update or a stray config file cannot change what is sent. Return a machine-readable verdict and a conventional exit code, so the review can sit in a script or a gate. Keep fix mode separate and off by default: a reviewer that edits is no longer independent.

## Why not adopted
The workbench's review lane is `santa-reviewer` (the Santa Method: breaker, simplifier and verifier passes with confirmed findings only) plus `doubt-driven-development`, both inside one provider. Sending code to another provider is a data-egress decision the user has not made, and it needs another CLI and login. The adapter's sandboxing and consent rules are worth reusing if a cross-provider lane is ever approved, as an optional lane that never runs automatically.

## Upstream paths
- `README.md#astra-review`
- `commands/astra-review.md`
- `docs/ASTRA-REVIEW-GUIDE.md`
- `scripts/astra-review.js`
- `scripts/lib/astra-review`
- `skills/council-multi-model`

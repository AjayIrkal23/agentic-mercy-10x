<!-- ecc:skills/intent-driven-development, skills/product-capability, agents/spec-miner.md, commands/plan-prd.md, docs/PLAN-PRD-PATTERN.md @25278e7d -->
# Intent, capability and phase files (ECC graft)

## Observable acceptance criteria

Every criterion names something a test or a person can observe: an input, an action and the
visible result ("submitting an empty email shows 'Email is required' under the field").
"Works well" or "is fast" is not a criterion until it has a number.

## Capability plan

Before features, list the capabilities the product needs (what a user can do), each with its
owner surface (FE / BE / infra), its dependencies and the criterion that proves it exists.
Features are then slices across capabilities.

## Phase-file pattern

`PRD.md` (why, who, criteria) → `PLAN.md` (ordered phases, dependencies) →
`phases/NN-<name>.md` (one file per phase: scope, tasks, exit check). Each phase file is
executable on its own; a phase is done when its exit check passes, not when its tasks are
ticked.

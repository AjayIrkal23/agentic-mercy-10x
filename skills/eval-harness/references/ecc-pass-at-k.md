<!-- ecc:skills/eval-harness, skills/agent-eval, agents/agent-evaluator.md, scripts/eval-harness.js, scripts/lib/eval-harness, examples/eval-harness, the-longform-guide.md#evals-pass-at-k @25278e7d -->
# pass@k, pass^k and eval receipts

## Two reliability metrics

- **pass@k** — "at least one of k attempts passes". Use it for capability: can the agent do
  this at all? Target pass@3 > 90 % before calling a capability shipped.
- **pass^k** — "all k attempts pass". Use it for critical paths (data writes, security
  gates, anything a user relies on every time). A flaky 2-of-3 is a fail here.
- Report both with k and the sample size; never a single run.

## Receipt format

An eval result is a receipt someone else can check offline:

- the capsule: prompt, model, settings, tool list, seed or run id;
- the artifact bytes (diff, file, transcript excerpt) with a content hash;
- named checks, each PASS/FAIL with the evidence line it read.

A reviewer re-runs the named checks against the stored bytes without re-running the model.

## What is not evidence

- A static warning (linter, schema check) is not containment evidence.
- A utility test that passes regardless of the agent's behavior is not promotion evidence.
- "It worked once in chat" is neither.

## Loop

1. Define the task set and the named checks first (they are the spec).
2. Run k attempts per task; record receipts.
3. Promote a prompt/skill change only when pass@k holds and pass^k does not regress.

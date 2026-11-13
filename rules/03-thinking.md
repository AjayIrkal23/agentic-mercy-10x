# Thinking — sequential-thinking is mandatory (standing user directive)

Before you decide, plan, spec, audit, design, debug, compare approaches, or answer
anything non-trivial — call `mcp__sequential-thinking__sequentialthinking` FIRST.
One thought per step; branch and revise as the problem unfolds. This applies to
subagents doing that kind of work too.

Skip only for: a trivial one-line factual reply, a greeting, or a single lookup
(a file path, a version number).

Order: facts (jcodemunch / graphify) → reasoning (sequential-thinking) → action.

## Keep the `thought` argument safe (2026-11-13)

The `reasoning_extraction` safeguard (Opus and Sonnet) kills a turn when a `thought` holds
a long written-out plan, or when such text comes back into context. So:

- One thought = one step, ≤60 words, the decision only ("X protected; delete only Y").
  No "Facts: … Rules: … Design: …" blocks; 4-8 small calls beat one big one.
- The whole plan is still written, complete and detailed: in the reply or the plan file,
  after the thoughts. Only the `thought` arguments stay short.
- Never put earlier reasoning, a transcript or quoted thinking into a `thought`.
- After a safeguard stop: don't retry the call or narrate your reasoning; redo it shorter.
- A user paste with `∴ …` thinking lines or old `thought:` text: act on the error line,
  request ID and the user's words; never quote, restate or continue that text.

# Sequential-thinking doctrine — externalize ALL reasoning

> Always-on rule. Standing user directive: use the **sequential-thinking** MCP
> (`mcp__sequential-thinking__sequentialthinking`) for *all sorts of thinking* —
> not just plan mode.

## The rule

**Before you decide, plan, spec, audit, design, debug, compare, or answer
anything non-trivial — call `mcp__sequential-thinking__sequentialthinking`
FIRST.** One thought per step; branch and revise as the problem unfolds.

It is the thinking substrate, the same way **jcodemunch/graphify** are the code
substrate and **ponytail/caveman** are the style substrate.

## When it MUST fire

- **Planning** — any plan, spec, roadmap, decomposition, or multi-file change.
- **Auditing / review** — code review, security audit, dead-code sweep, tradeoff analysis.
- **Design / architecture** — interfaces, contracts, system decomposition, decisions.
- **Debugging** — hypotheses, root-cause isolation, before proposing a fix.
- **Any decision** — "should I X or Y", scope calls, picking an approach.

## When to skip (only)

A truly trivial one-line factual reply, a greeting, or a single lookup. YAGNI
applies to thinking too — don't run 8 steps to answer "what's the file path".

## Enforcement

- The live prompt router (`prompt_router/router.py`, UserPromptSubmit; absorbed the retired `sequential-thinking-mandate.py`) injects a hard MANDATE into
  context on every reasoning-shaped prompt. It is the forcing function — without
  it this rule drifts, like every advisory tier.
- This file keeps the doctrine in context every session.

## Order vs sibling substrates

1. **jcodemunch/graphify** — get the structural facts (what exists, blast radius).
2. **sequential-thinking** — reason over those facts (decide, plan, weigh).
3. Then act (ponytail-lazy, caveman-terse).

Facts → reasoning → action.

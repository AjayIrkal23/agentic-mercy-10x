---
name: mcp-usage-standards
description: Use when MCP selection, evidence scope, or external verification strategy materially affects
  design, debugging, implementation, or repo analysis. Choose the right MCP and keep evidence retrieval
  disciplined Use to choose the right MCP, narrow the evidence scope, and avoid unnecessary tool usage.
disable-model-invocation: false
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 805
triggers:
  keywords:
  - affects
  - analysis
  - avoid
  - choose
  - debugging
  - design
  - disciplined
  - evidence
  - external
  - implementation
  - materially
  - mcp
  - narrow
  - repo
  - retrieval
  - right
  - scope
  - selection
  - standards
  - strategy
  - tool
  - unnecessary
  - usage
  - verification
  paths: []
  intents:
  - general
---
# MCP Usage Standards

## Overview

MCP routing for this machine is driven by **`~/.claude/settings.json`**. Load this skill when tool choice materially affects correctness, evidence, or verification — not for routine single-file edits with obvious local answers.

Canonical quick table: **`~/.claude/rules/user-mcp-inventory.md`**.

## Active MCP registry (`~/.claude/settings.json`)

| Server | Use when | Skip when |
| --- | --- | --- |
| **`context7`** | Official/current docs for libraries, frameworks, SDKs, APIs, CLIs, cloud APIs | Answer is purely in-repo; no external doc uncertainty |
| **`sequential-thinking`** | Complex decomposition, ambiguous tradeoffs, high-risk reasoning | Straightforward edits or shallow questions |
| **`fetch`** | Static HTML/markdown-ish pages; URLs where no JS interaction is needed | SPA state, clicks, auth flows, or rendered behavior required |
| **`memory`** | Durable stash/recall genuinely worth carrying across threads | Secrets, chatter, ephemeral task state |
| **`browser-tools-mcp`** | That server’s console/network/DevTools-oriented evidence is explicitly needed | Same check is cheaper via `fetch` or repo-only |
| **`playwright`** | Real browser automation: flows, clicks, accessibility snapshots / UI probes ([`@playwright/mcp`](https://www.npmjs.com/package/@playwright/mcp)) | Static fetch or local code read suffices |
| **`markdownify`** | Convert HTML/PDF/etc. → markdown for ingest (respect server path/env rules) | No conversion workflow |
| **`graphify`** | Query knowledge graph backed by **`graphify-out/graph.json`** | **`graph.json` missing** — build graph first (`graphify` / wiki); MCP will fail |

**Browser MCP triage:** `fetch` (static) → **`playwright`** (drive the page) → **`browser-tools-mcp`** when you need that toolchain’s diagnostics; don’t stack two browsers for one trivial question.

## Selection rules

1. Prefer **repo files**, project docs, `AGENTS.md` / linkage files before MCP for codebase questions.
2. Prefer **`context7`** over ad-hoc web answers for upstream library correctness.
3. Prefer **`fetch`** before **`playwright`** when HTML is effectively static.
4. Prefer **`playwright`** before ad-hoc shell `curl | grep` UI checks when deterministic browser actions matter.
5. Use **`memory`** sparingly — never secrets.
6. Use **`markdownify`** only when conversion is part of the task scope.
7. Use **`sequential-thinking`** only when reasoning cost justifies serialized steps.

## Non-negotiables

- Pick MCP intentionally; smallest tool wins.
- Minimum evidence retrieval; summarize what changed your mind.
- No secrets/tokens/credentials on the wire or in memory entries.
- If an MCP fails, change strategy once — state unverified assumptions.

## Workflow

1. Name what is unknown vs what local source should prove.
2. Choose one MCP tier (fetch vs playwright vs docs vs thinking).
3. Narrow the prompt before calling tools.
4. Record what evidence confirmed or ruled out.

## Next

See **`references/full-guide.md`** for per-server detail and appendix on **optional / not-installed** MCPs.

## Completion checklist

- Correct MCP tier chosen.
- No redundant browser/doc calls.
- No secrets leaked.
- Findings summarized.

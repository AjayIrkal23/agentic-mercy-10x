---
name: tool-and-doc-selection
description: Chooses the right source of truth (workspace files, local docs, installed doc tools, MCP integrations, or web search) and keeps evidence retrieval disciplined.
when_to_use: Use when deciding which docs or tools to consult for a task, before reaching for web search.
metadata:
  schema: 1
  category: docs
  surfaces:
  - docs
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 582
  triggers:
    keywords:
    - which docs
    - which tool
    - source of truth
    - where to look
    - web search
    - docs lookup
    - local docs
    paths: []
    intents:
    - docs
---
# Tool And Doc Selection

## Use When
- You need to decide whether local code, `jcodemunch`, local docs (`jdocmunch`), Context7, or web browsing is the right source.
- A task depends on current library or framework docs.
- You are about to use tools for evidence gathering or verification.

## Do Not Use
- Implementing application logic on its own.
- Re-stating general coding safety rules that already live elsewhere.
- Treating tools as mandatory when local repo truth is sufficient.

## Owns
- Source-of-truth precedence for repo work.
- Choosing `jcodemunch` first for indexed broad repo code structure or linkage, while using shell/file tools for exact paths, literal text, dirty or untracked files, stale indexes, direct verification reads, and execution output.
- Routing library and framework doc questions to external docs skills first.
- Avoiding stale or nonexistent tool references in local guidance.

## Does Not Own
- Product architecture or implementation policy.
- UI or backend coding standards.
- Agent or command authoring.

## Combine With
- Any skill that needs current docs or evidence.
- The Context7 MCP (`mcp__context7__resolve-library-id` → `query-docs`) for library, framework, SDK, API, and CLI questions.
- The memory MCP (`mcp__memory__add_observations`) when a recurring tool or source-selection pattern should become a durable preference.
- Web search only after local sources and docs tools are insufficient.

## Workflow
1. Prefer local code, `jcodemunch`, local docs, and repo manifests for repo truth; apply the `jcodemunch`-first rule from `~/.claude/rules/00-tool-precedence.md`.
2. Use Context7 for library and framework questions.
3. Use `jdocmunch` for indexed doc sets; `Read` a single doc file directly.
4. Use MCP or web tools only when they add evidence that local sources and `jcodemunch` cannot provide.
5. Record which source was authoritative when the choice matters.
6. If the same routing preference keeps repeating across sessions, record it in the memory MCP (`decision::` entity).
7. Avoid stale tool names or unnecessary tool usage.

## Output Contract
- The chosen source of truth and why it was selected.
- Any unresolved uncertainty that still requires verification.
- A short note when a docs skill or external tool was required.

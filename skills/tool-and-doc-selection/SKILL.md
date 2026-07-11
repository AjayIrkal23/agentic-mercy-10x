---
name: tool-and-doc-selection
description: Use when deciding which source of truth to consult among workspace files, local docs, installed
  docs tools, MCP integrations, or web search. Choose the right source of truth Use to choose the right
  local or external source for this task.
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
  - among
  - choose
  - consult
  - deciding
  - doc
  - docs
  - external
  - files
  - installed
  - integrations
  - local
  - mcp
  - right
  - search
  - selection
  - source
  - task
  - tool
  - tools
  - truth
  - web
  - workspace
  paths:
  - .claude/hooks/
  - .claude/rules/
  intents:
  - docs
---
# Tool And Doc Selection

## Use When
- You need to decide whether local code, `jcodemunch`, local docs, Deepvue MCP, Context7, or web browsing is the right source.
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
- External `find-docs`, `deepvue-docs`, and `context7-mcp` for library, framework, SDK, API, and CLI questions.
- `workflow-overlay-optimizer` when recurring tool or source-selection patterns should become durable personal routing preferences.
- Web search only after local sources and docs skills are insufficient.

## Workflow
1. Prefer local code, `jcodemunch`, local docs, and repo manifests for repo truth; apply the hybrid `jcodemunch`-first rule from `~/.codex/skill-routing-matrix.md`.
2. Use external docs skills for library and framework questions.
3. Use `deepvue-docs` for Deepvue questions and `context7-mcp` for other external docs when `find-docs` routes there.
4. Use MCP or web tools only when they add evidence that local sources and `jcodemunch` cannot provide.
5. Record which source was authoritative when the choice matters.
6. If the same routing preference keeps repeating across sessions, refresh it through `workflow-overlay-optimizer`.
7. Avoid stale tool names or unnecessary tool usage.

## Output Contract
- The chosen source of truth and why it was selected.
- Any unresolved uncertainty that still requires verification.
- A short note when a docs skill or external tool was required.

---
name: command-development
description: 'Create or update command definitions: frontmatter, arguments, and reusable command workflows.'
when_to_use: Use when adding or editing .claude/commands/ or turning a command into a skill.
paths:
- '**/.claude/commands/**'
- 'commands/**/*.md'
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 357
  triggers:
    keywords:
    - slash command
    - command definition
    - custom command
    - command arguments
    - command frontmatter
    paths: []
    intents:
    - general
---
# Command Development

## Use When
- Creating a new local command or updating an existing one.
- Defining command arguments, frontmatter, or command execution flow.
- Converting a repeated manual workflow into a reusable command.

## Do Not Use
- Designing autonomous agents.
- Implementing application code or business logic.
- Editing a normal skill instead of a command definition.

## Owns
- Command frontmatter shape and argument design.
- Command UX, file references, and execution flow.
- Reusable command patterns for repetitive operator workflows.

## Does Not Own
- Agent system prompts and agent routing.
- Product architecture or code standards.
- Library docs lookup policy.

## Combine With
- `tool-and-doc-selection` when the command depends on external tooling or docs.
- `workflow-orchestrator` when the command is only one step in a larger delivery flow.

## Workflow
1. Define the command's user-facing job in one sentence.
2. Keep arguments and frontmatter small, explicit, and predictable.
3. Prefer deterministic steps and file references over long prose.
4. Validate the command with an example invocation before treating it as done.
5. Reuse supporting references or examples when they exist instead of duplicating them inline.

## Output Contract
- A command definition with clear frontmatter and arguments.
- Example invocation or usage notes.
- Any supporting references that the command depends on.

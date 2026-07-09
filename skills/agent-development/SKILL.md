---
name: agent-development
description: Use when creating or revising reusable agent definitions, trigger text,
  or system prompts for autonomous helpers. Design reusable autonomous agent definitions
  Use to draft or revise an autonomous agent definition.
disable-model-invocation: true
---
# Agent Development

## Use When
- Creating a new local agent definition.
- Rewriting an existing agent prompt, trigger description, or agent metadata.
- Reviewing whether an autonomous helper should be an agent instead of a skill or command.

## Do Not Use
- Building normal skills or command workflows.
- Creating slash-command style helpers.
- Implementing product code or business logic.

## Owns
- Agent naming, scope, and trigger phrasing.
- Agent system-prompt shape and guardrails.
- Agent metadata quality for reliable routing.

## Does Not Own
- Command frontmatter and slash-command UX.
- General project architecture or feature implementation.
- Library-specific docs lookup policy.

## Combine With
- `workflow-orchestrator` for multi-agent delivery planning.
- External `skill-creator` when the task is really a skill design task.
- `tool-and-doc-selection` if the agent must rely on docs or repo tools.

## Workflow
1. Confirm the agent's job is autonomous and bounded.
2. Write a trigger-focused description that matches realistic user prompts.
3. Keep the system prompt narrow, opinionated, and outcome-based.
4. Point to supporting references or scripts when they exist instead of embedding long manuals.
5. Validate the agent against one or two realistic prompts.

## Output Contract
- A proposed or updated agent definition with clear trigger text.
- A short explanation of scope boundaries and non-goals.
- Any follow-up validation prompts needed to test the agent.

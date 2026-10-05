---
name: workflow-orchestrator
description: 'Coordination shell for multi-phase work: identifies touched surfaces and routes each phase to Architect, Code, or Debug mode with explicit ownership and quality gates.'
when_to_use: Use when work spans multiple phases, domains, or specialist roles.
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 783
  triggers:
    keywords:
    - orchestrate
    - orchestrator
    - multi-phase
    - multiple phases
    - coordinate agents
    - cross-surface
    - end to end
    - phase owners
    - sequencing
    paths: []
    intents:
    - general
---
# Workflow Orchestrator

## Overview

This is the coordination shell.

It does not assume a mixed frontend/backend plan by default. It identifies the touched surfaces, then routes each phase to the right mode and domain stack.

**Canonical orchestrator for this machine:** this skill is the single workflow router. Plan-vs-execution stack ordering lives in `references/stack-ordering.md`.

## Use When

- Work spans multiple phases.
- Multiple surfaces or roles are involved.
- Sequencing, delegation, or quality gates need to be explicit.

## Do Not Use

- Small isolated tasks that fit directly in architect, code, or debug.
- Pure implementation without coordination needs.

## Surface Selection Rule

Decide whether the work is:

- Backend-only
- Frontend-only
- Cross-surface
- Still unclear

Then assign phases using the matching baseline skills for each surface instead of assuming both sides always matter.

For frontend phases, load `frontend-standards-always-follow` first; add `frontend-design:frontend-design` (plugin) for new or redesigned visual surfaces, `vite-react-best-practices` for narrow React/Vite code work, and `expo-react-native` instead for React Native / Expo screens.
For backend phases, load `backend-standards-always-follow` and `service-layer-standards` together.

## Routing Rule

- Use `architect-system-design` for design, decomposition, and plan creation.
- Use `code-execution-standard` for known-scope implementation.
- Use `debug-investigation` when cause or failure source is still unknown.

Use `project-reference-linkage` for linked modules and shared contracts.
Use `mcp-usage-standards` when MCP selection or external verification affects the workflow.

## Workflow

1. Restate the objective and success criteria.
2. Identify touched surfaces and dependencies.
3. Break the work into phases.
4. Draw the phase flow as a fenced `mermaid` block (flowchart or state diagram) in the plan so phase boundaries, parallel work, and quality gates are visible at a glance; preview with the drawio MCP `open_drawio_mermaid` when it is connected.
5. Assign each phase to architect, code, or debug.
6. Mark what can run in parallel and what is blocked.
7. Define the minimum quality gates before completion.

## Output Contract

- Objective and success criteria.
- Touched surfaces.
- Ordered phases and mode assignment.
- Mermaid phase diagram (fenced `mermaid` block) embedded or linked.
- Dependencies, risks, and quality gates.
- Approval gate only when ambiguity or risk justifies it.
- **Plan file saved to both:** `plan-YYYY-MM-DD-<feature-name>.md` at project root AND `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` (see `~/.claude/rules/02-lifecycle.md` phase 1).

## References

- Use `references/full-guide.md` if you need the previous full strict guide.

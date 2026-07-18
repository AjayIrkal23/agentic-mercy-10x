---
name: workflow-orchestrator
description: "ALWAYS invoke when work spans multiple phases, domains, or specialist roles and needs explicit sequencing, ownership, and quality gates across Architect, Code, and Debug modes."
disable-model-invocation: false
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
  - agent
  - architect
  - break
  - choosing
  - code
  - complex
  - cursor
  - debug
  - domains
  - execution
  - explicit
  - first
  - frontend/backend
  - gates
  - implement
  - implementation
  - include
  - mandatory
  - mode
  - modes
  - multiple
  - need
  - needs
  - orchestrator
  - ordering
  - ownership
  - phases
  - plan
  - planning
  - quality
  - roles
  - route
  - routing
  - sequencing
  - skill
  - skills
  - spans
  - specialist
  - stacks
  - superpowers
  - triggers
  - work
  - workflow
  paths: []
  intents:
  - general
---
# Workflow Orchestrator

## Overview

This is the coordination shell.

It does not assume a mixed frontend/backend plan by default. It identifies the touched surfaces, then routes each phase to the right mode and domain stack.

**Canonical orchestrator for this machine:** Use this skill as the single master workflow router in Cursor. If your setup also ships a separate `agent-skills-orchestrator` skill (from the Everything Claude Code bundle), do not treat both as mandatory "first skill" in the same task unless you merge their content yourself. Prefer `plan-exec-stack-guide` for plan vs execution and Superpowers paths.

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

For frontend phases, select and load the matching Build Web Apps plugin skill when available before the local frontend baseline; use `build-web-apps:react-best-practices` for narrow React/Vite/UI/code work when no more specific plugin fits.
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
4. Render the phase flow with `claude-mermaid:mermaid-diagrams` (plugin path `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`) — flowchart or state diagram — so phase boundaries, parallel work, and quality gates are visible at a glance. Use `mermaid_preview` to iterate; `mermaid_save` when promoted into the plan/PRD/ADR.
5. Assign each phase to architect, code, or debug.
6. Mark what can run in parallel and what is blocked.
7. Define the minimum quality gates before completion.

## Output Contract

- Objective and success criteria.
- Touched surfaces.
- Ordered phases and mode assignment.
- Mermaid phase diagram (rendered via `claude-mermaid:mermaid-diagrams`) embedded or linked.
- Dependencies, risks, and quality gates.
- Approval gate only when ambiguity or risk justifies it.
- **Plan file saved to both:** `plan-YYYY-MM-DD-<feature-name>.md` at project root AND `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` (see `~/.claude/rules/plan-root-save.md`).

## References

- Use `references/full-guide.md` if you need the previous full strict guide.

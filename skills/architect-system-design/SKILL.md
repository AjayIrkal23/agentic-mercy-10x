---
name: architect-system-design
description: Use when the main task is design, decomposition, interface planning,
  or implementation planning before code changes begin. Create build-ready design
  and contract specs Use to produce a build-ready architecture spec.
disable-model-invocation: false
---
# Architect System Design

## Overview

This is the architecture shell.

It does not assume frontend and backend both matter. It classifies the touched surfaces first, then pulls in only the domain skills the design actually needs.

## Use When

- The main task is system design, decomposition, or interface planning.
- Contracts, boundaries, phases, or ownership are still being decided.
- The implementation path is not yet decision-complete.

## Do Not Use

- Straightforward implementation where scope is already known.
- Unknown failures that need debugging before design.
- Library documentation lookup by itself.

## Surface Selection Rule

Choose the touched surface first:

- Backend-only: load the mandatory Backend Core Compliance Set before design decisions: `backend-standards-always-follow`, `service-layer-standards`, `backend-api-standards`, `backend-error-handling`, and `backend-performance-standards`. Preserve `api-contract-standards` for envelope/contract work, `domain-scaffold-patterns` for new domain/feature skeleton planning, and `scaffold-standards` for concrete backend skeleton details.
- Frontend-only: select and load the matching Build Web Apps plugin skill when available, then load the mandatory Frontend Core Compliance Set: `build-web-apps:frontend-app-builder` for new/redesign/visual surfaces or `build-web-apps:react-best-practices` for React/Vite/UI/code planning, plus `frontend-standards-always-follow`, `frontend-structure-standards`, `frontend-response-handling`, `frontend-server-data-patterns`, `frontend-api-standards`, and `react-hooks-patterns`.
- Cross-surface: load the matching Build Web Apps plugin plus Frontend Core Compliance Set and Backend Core Compliance Set, then only the preserved add-ons required by the actual design.

Use `project-reference-linkage` when the design crosses shared contracts or linked modules.
Use `mcp-usage-standards` when external verification or MCP choice affects the design.
Use `dead-code-and-change-audit` if the design becomes a coding task or changes code.

## Workflow

1. Restate the problem, users, and success condition.
2. Identify the touched surfaces, load the matching Build Web Apps plugin for frontend surfaces, and load the Frontend Core Compliance Set or Backend Core Compliance Set required by those surfaces.
3. Extract requirements, constraints, and contract implications.
4. Define boundaries, interfaces, and key data flow.
5. Render the system design (boundaries, interfaces, data flow) as a Mermaid diagram via `claude-mermaid:mermaid-diagrams` (plugin path `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`). Use flowchart for module boundaries, sequence diagram for cross-service flows, state diagram for lifecycle work, ER diagram for new data models. Iterate with `mermaid_preview`; persist via `mermaid_save` into the design doc.
6. Call out risks, bottlenecks, and validation needs.
7. Produce an implementation-ready plan with phases and acceptance criteria.

## Output Contract

- Clear problem framing.
- Touched surfaces and loaded domain standards.
- Interface and boundary decisions.
- Mermaid system / sequence / ER diagram (rendered via `claude-mermaid:mermaid-diagrams`) embedded in the design doc.
- Risks, assumptions, and acceptance criteria.
- An implementation-ready phase plan.

## References

- Use `references/full-guide.md` if you need the previous full strict guide.

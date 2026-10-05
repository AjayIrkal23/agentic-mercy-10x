---
name: architect-system-design
description: 'Architecture shell: classify the touched surfaces, decompose the system, plan interfaces and implementation order before code changes.'
when_to_use: Use when the task is design, decomposition, interface planning, or an implementation plan that precedes coding.
metadata:
  schema: 1
  category: planning
  surfaces:
  - planning
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 858
  triggers:
    keywords:
    - system design
    - architecture
    - architect
    - decompose the system
    - decomposition
    - module boundaries
    - service boundaries
    - interface design
    - data flow
    - design doc
    - how should we architect
    paths: []
    intents:
    - planning
---
# Architect System Design

> Examples are Go-first; Node/TS/Fastify/Mongo variants in `references/node-stack.md`. Detect the repo's real stack before choosing a block.

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

- Backend-only: load the mandatory Backend Core Compliance Set before design decisions: `backend-standards-always-follow`, `service-layer-standards`, `backend-api-standards`, `backend-error-handling`, and `backend-performance-standards`. Preserve `api-contract-standards` for envelope/contract work, and `scaffold-standards` for new domain/feature skeleton planning and concrete backend skeleton details.
- Frontend-only: load the Frontend Core Compliance Set: `frontend-design:frontend-design` (plugin) for new/redesign/visual surfaces or `vite-react-best-practices` for React/Vite/UI/code planning (`expo-react-native` for React Native / Expo), plus `frontend-standards-always-follow`, `frontend-structure-standards`, `frontend-response-handling`, `frontend-server-data-patterns`, and `react-hooks-patterns`.
- Cross-surface: load the Frontend Core Compliance Set and Backend Core Compliance Set, then only the preserved add-ons required by the actual design.

Use `project-reference-linkage` when the design crosses shared contracts or linked modules.
Use `mcp-usage-standards` when external verification or MCP choice affects the design.
Use `dead-code-and-change-audit` if the design becomes a coding task or changes code.

## Workflow

1. Restate the problem, users, and success condition.
2. Identify the touched surfaces and load the Frontend Core Compliance Set or Backend Core Compliance Set required by those surfaces.
3. Extract requirements, constraints, and contract implications.
4. Define boundaries, interfaces, and key data flow.
5. Draw the system design (boundaries, interfaces, data flow) as a fenced `mermaid` block in the design doc. Use flowchart for module boundaries, sequence diagram for cross-service flows, state diagram for lifecycle work, ER diagram for new data models. Preview with the drawio MCP `open_drawio_mermaid` when it is connected.
6. Call out risks, bottlenecks, and validation needs.
7. Produce an implementation-ready plan with phases and acceptance criteria.

## Output Contract

- Clear problem framing.
- Touched surfaces and loaded domain standards.
- Interface and boundary decisions.
- Mermaid system / sequence / ER diagram (fenced `mermaid` block) embedded in the design doc.
- Risks, assumptions, and acceptance criteria.
- An implementation-ready phase plan.

## References

- Use `references/full-guide.md` if you need the previous full strict guide.

---
name: code-execution-standard
description: Use when scope and root cause are already understood and the task is implementing a safe, validated, known-scope change.
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 1040
  triggers:
    keywords:
    - implement the plan
    - execute the plan
    - implement this change
    - known-scope change
    - make the change
    - apply the fix
    - incrementally
    paths: []
    intents:
    - general
---
# Code Execution Standard

## Overview

This is the implementation shell.

It does not carry frontend and backend standards by default. It selects the touched surfaces first, then loads only the matching baseline skills and specialists.
Use this shell for implementation work in default chat as well as explicit code-mode execution. Do not wait for architect or plan wording before activating it.

## Use When

- The scope is known.
- The design is already clear enough to implement.
- The job is to make a safe change and verify it.

## Do Not Use

- Architecture-first work.
- Unknown failures that need root-cause analysis first.
- Documentation lookup by itself.

## Surface Selection Rule

Choose the touched surface first:

If the prompt is asking for a code change, treat it as implementation and activate this shell before editing, even when the prompt does not explicitly mention mode selection.

- Backend-only: load the mandatory Backend Core Compliance Set before editing: `backend-standards-always-follow`, `service-layer-standards`, `backend-api-standards`, `backend-error-handling`, and `backend-performance-standards`. Preserve `api-contract-standards` for envelope/contract work and `scaffold-standards` for new domain/feature skeletons.
- Frontend-only: load the Frontend Core Compliance Set: `frontend-design:frontend-design` (plugin) for new/redesign/visual surfaces or `vite-react-best-practices` for React/Vite/UI/code work (`expo-react-native` for React Native / Expo), plus `frontend-standards-always-follow`, `frontend-structure-standards`, `frontend-response-handling`, `frontend-server-data-patterns`, and `react-hooks-patterns`.
- Cross-surface: load the Frontend Core Compliance Set and Backend Core Compliance Set, then only the preserved add-ons required by the actual files and contracts being changed.

Use `project-reference-linkage` for linked modules and shared contracts.
Use `mcp-usage-standards` when external verification or repo-system truth must guide the implementation.
Use `dead-code-and-change-audit` for every coding task and every code change.
When the repo is indexed, use `jcodemunch` first for broad path discovery, symbol search, reference tracing, dependency graphs, context bundles, and blast-radius checks. Use shell/file tools immediately for exact paths, literal text, dirty or untracked files, generated or ignored files, stale or ambiguous indexes, small known scopes, direct verification reads, and command execution.

## Workflow

1. Confirm the touched surfaces and impacted layers, preferring `jcodemunch` for indexed broad repo discovery and shell/file tools for exact or verification lookups.
2. Load the Frontend Core Compliance Set for frontend work and the Backend Core Compliance Set for backend/server work.
3. Add `dead-code-and-change-audit` for code changes and only the other specialists required by the actual change.
4. Implement the smallest complete change that satisfies the request.
5. Verify tests, contracts, stale references, and user-visible behavior before closing.

## Non-Negotiables

- No guessing when the repo already shows a pattern.
- No unnecessary new abstractions.
- No contract drift without intent.
- No touched manually maintained source file may remain over 250 lines without an explicit blocker; split frontend/backend files according to the active surface standards before adding more behavior.
- No completion claims without verification.

## Output Contract

- Completed code changes or a blocked-path explanation.
- Touched surfaces and loaded standards.
- Validation results and known gaps.
- Assumptions that affected implementation.

## References

- Use `references/full-guide.md` if you need the previous full strict guide.
- Persistent routing friction or a skill that keeps failing to activate: report it (router keywords live in the skill's `metadata.triggers.keywords`), do not patch it ad hoc per prompt.

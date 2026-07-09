---
name: project-structure-map
description: Use when you need a fast map of layer boundaries and likely impacted
  files in an unfamiliar codebase before making changes. Map layer boundaries and
  likely impacted files Use to identify likely impacted files and layer boundaries
  for this codebase change.
disable-model-invocation: false
---
# Project Structure Map

## Use When
- Locating the current path or owner for a layer before editing.
- Mapping which files are likely impacted by a change.
- Verifying how major codebase layers connect.

## Do Not Use
- Defining implementation rules for a specific layer.
- Choosing API envelopes, error behavior, or styling direction.
- Driving orchestration, design, implementation, or debugging on its own.

## Owns
- Fast discovery of current codebase paths and layer boundaries.
- Dependency tracing between route, controller, service, schema, model, component, API, and store files.
- Quick impact-analysis checklists grounded in the host codebase.

## Does Not Own
- Business rules, contracts, or styling policy.
- File-size limits or performance heuristics.
- Tool-selection guidance.

## Combine With
- `repo-memory-sync` when repo memory exists already or should be refreshed after mapping.
- `jcodemunch-code-finder` when locating files, symbols, references, dependencies, or blast radius.
- Any implementation or debugging skill that needs a path map.
- Scaffolding guidance when you are creating new modules.
- Layer-specific frontend or backend standards once the impacted files are known.

## Workflow
1. If inside a repository and stored repo memory could help, load `repo-memory-sync` first.
2. Use `jcodemunch-code-finder` as the code-discovery companion. If the repo is indexed, start with `jcodemunch` file tree, symbol search, and reference tracing for broad entry-point discovery; use shell/file tools for exact paths, literal text, dirty or untracked files, stale indexes, direct verification reads, and execution output.
3. Read local docs, manifests, and nearby files to confirm the current codebase conventions.
4. Trace outward to the adjacent layers that can affect behavior.
5. Record the observed paths before creating new folders or files.
6. Treat this skill as a locator and impact tracer, not as a rule owner for other domains.

## Output Contract
- A short impacted-path map grounded in the current codebase.
- Any stale or conflicting repo-memory facts surfaced early.
- Any ambiguous path or ownership questions surfaced early.

## Mapping Checklist
- Entry points: routes, pages, commands, jobs, handlers, or controllers.
- Data flow: API clients, state modules, services, repositories, models, or queries.
- Validation and contracts: schemas, types, DTOs, serializers, or response envelopes.
- UI layers: screens, components, hooks, stores, styles, or design-system primitives.
- Cross-cutting code: configuration, tests, background tasks, logging, or shared utilities.

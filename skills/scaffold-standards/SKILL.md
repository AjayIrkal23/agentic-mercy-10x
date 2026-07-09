---
name: scaffold-standards
description: Use when scaffolding a new backend or full-stack domain, route/controller/service/schema
  skeleton, or standard list and CRUD feature structure. Define the standard domain
  and feature skeleton Use to define the standard backend or full-stack route, controller,
  service, schema, and feature skeleton.
disable-model-invocation: false
---
# Scaffold Standards

## Overview

This skill defines the standard skeleton for new domains and features.

Use it when consistency of file layout, naming, and build order matters more than one-off speed.

## Use When

- Creating a new backend domain.
- Adding a new route/controller/service/schema flow.
- Scaffolding a new full-stack CRUD or list feature.
- Defining the minimum skeleton before implementation starts.

## Backend Skeleton

```text
/routes/index.ts
/routes/{domain}/index.ts
/routes/{domain}/{action}.route.ts
/controllers/index.ts
/controllers/{domain}/index.ts
/controllers/{domain}/{action}.controller.ts
/controllers/{domain}/{feature}/{action}.controller.ts
/schemas/{domain}/{action}.schema.ts
/schemas/{domain}/{feature}/{action}.schema.ts
/schemas/{domain}/{feature}/index.ts
/types/{domain}/{name}.ts
/services/{domain}/{action}.service.ts
/services/{domain}/{feature}/index.ts
/services/{domain}/{feature}/{action}.service.ts
/services/{domain}/{feature}/shared.ts
/services/{domain}/{feature}/audit.ts
/services/{domain}/{feature}/reference.ts
/services/{domain}/{feature}/constraints.ts
/services/{domain}/{feature}/deleteGuards.service.ts
/services/{domain}/{feature}/lookupToken.service.ts
/services/{domain}/{feature}/mapping.ts
/services/{domain}/{feature}/normalization.ts
/services/{domain}/{feature}/snapshot.ts
/services/{domain}/{feature}/core.ts
/models/{domain}/{ModelName}.ts
/utils/{domain}/query.ts
/utils/{domain}/mapper.ts
```

Keep reusable backend types in `/types/{domain}/{name}.ts` instead of declaring them inline inside config, routes, controllers, services, or queue modules.

If the repo already uses controller-mirror feature folders, scaffold into that feature-folder pattern instead of forcing flat per-action service files.

Use the query helper and mapper files when the domain needs list/query logic or DTO conversion.

## Standard Action Set

Where applicable:

- `list`
- `getById`
- `create`
- `update`
- `delete`

## Contract Expectations

- Success responses follow the standard envelope.
- List features use paginated backend-driven query behavior.
- Errors follow the shared error envelope.

## Suggested Build Order

1. Lock the contract.
2. Add schema.
3. Add service.
4. Add controller and route.
5. Add helpers or mappers if needed.
6. Add frontend integration if the feature is full-stack.

## Naming Rules

- Folder names use kebab-case.
- Code identifiers use camelCase or PascalCase.
- Keep route/controller/service naming aligned across the stack.

## Combine With

- `api-contract-standards` for envelope and compatibility rules.
- `service-layer-standards` for boundary discipline.
- `backend-api-standards` for list/query semantics.

## References

- Use `references/full-guide.md` for the longer strict version with full-stack scaffolding details and extended examples.

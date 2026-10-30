<!-- ecc:rules/typescript, skills/coding-standards, skills/frontend-patterns @25278e7d -->
# TypeScript rules (ECC graft)

- **Explicit public types:** exported functions, hooks and components declare parameter and
  return types; inference is for locals.
- **No `any`:** use `unknown` and narrow; a justified escape hatch carries a comment.
- **Zod at boundaries:** parse API responses, form input, env and URL params with a schema;
  types flow from `z.infer`.
- **Narrow before use:** guard `null`/`undefined` and union members before access; no
  non-null `!` to silence the checker.
- **Discriminated unions over flags:** `{ status: "loading" } | { status: "ok"; data }`
  instead of `isLoading` + `data?` + `error?` that can disagree.

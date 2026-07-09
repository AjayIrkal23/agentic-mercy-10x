# Context7 Lookup Guide

## When to Use Context7

**MANDATORY for:**
- Any external library/framework mentioned in the task
- Any dependency in package.json, requirements.txt, go.mod, Cargo.toml
- Any API whose behavior you're unsure about
- Version-sensitive libraries (React, Next.js, Tailwind, Prisma, etc.)

**RECOMMENDED for:**
- Libraries you "think you know" — verify current version behavior
- New library installations
- Configuration changes
- Debugging library-related issues

## Two-Step Process

### Step 1: Resolve Library ID

```json
{
  "libraryName": "React",
  "query": "how to use useEffect cleanup function"
}
```

**Selection criteria:**
1. Name match (exact > partial)
2. Source reputation (High > Medium > Low)
3. Code snippet count (more = better)
4. Benchmark score (100 = highest)

**Common library IDs:**
- `/facebook/react`
- `/vercel/next.js`
- `/tailwindlabs/tailwindcss`
- `/prisma/prisma`
- `/fastify/fastify`
- `/supabase/supabase`

### Step 2: Query Documentation

```json
{
  "libraryId": "/facebook/react",
  "query": "useEffect cleanup function examples 2024"
}
```

**Query best practices:**
- Be specific: "React useEffect cleanup function examples" not "react hooks"
- Include version if known: "Next.js 14 app router middleware"
- Ask for patterns: "Express.js JWT authentication best practices"
- Ask for configuration: "Prisma schema many-to-many relationship"

## Decision Tree

```
Task mentions library?
    ├─ Yes → Is it in package.json?
    │   ├─ Yes → resolve-library-id → query-docs
    │   └─ No → resolve-library-id → query-docs (user may have missed it)
    └─ No → Check imports in relevant files
        ├─ External imports found → resolve-library-id → query-docs
        └─ No imports → Skip Context7
```

## Common Lookup Patterns

### React / Frontend
- `resolve-library-id("React", "useEffect patterns")`
- `query-docs("/facebook/react", "useEffect cleanup function")`
- `query-docs("/tailwindlabs/tailwindcss", "responsive grid layout")`

### Backend / Node.js
- `resolve-library-id("Fastify", "route validation")`
- `query-docs("/fastify/fastify", "hook lifecycle order")`
- `query-docs("/prisma/prisma", "relation queries with include")`

### Database
- `resolve-library-id("Prisma", "migration workflow")`
- `query-docs("/supabase/supabase", "RLS policy examples")`

## Skip Conditions

Skip Context7 ONLY when:
- Task uses pure standard library features (no npm/pip/go modules)
- Task is a file move or rename with no API usage
- You've already queried this library in the current session for the same API

---
name: agentation-react
description: 'Verifies, and restores when missing, the dev-only Agentation annotation overlay in a React web app: the agentation dependency, one wrapper component and its development-gated mount in the root app shell.'
when_to_use: Use when a repo's docs require Agentation ("use agentation-react"), before React web work in such a repo, or when a change touches the root app shell, package.json or the dev overlay wrapper.
metadata:
  schema: 1
  category: frontend
  surfaces:
  - frontend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - agentation
    - agentation-react
    - agentation overlay
    - agentation toolbar
    - annotation toolbar
    - AgentationOverlay
    - dev overlay
    intents:
    - VERIFY
---
# Agentation (React web)

Agentation is a development-only toolbar that lets a person annotate DOM elements in the
running web app so an agent gets exact targets. In repos that adopt it, it is tooling the
team depends on: **never remove it, never ship it to production, never move it into
feature components.**

The repo's own doc is the contract (in site-sync-vista:
`frontend_docs/18-agentation-react.md`). Read it first; it names the wrapper path, the
mount point and the endpoint. What follows is the generic check.

## 1. Check (read-only, no server)

```bash
grep -n '"agentation"' package.json                       # dependency present
git ls-files | grep -i 'AgentationOverlay'                # one wrapper component
grep -rn 'AgentationOverlay' src/App.tsx src/main.tsx 2>/dev/null   # mounted from the shell
```

Then read the mount and the wrapper and confirm:

| Check | Pass when |
|---|---|
| Dependency | `agentation` is in `package.json` (and the lockfile) |
| Single wrapper | exactly one wrapper (e.g. `src/components/dev/AgentationOverlay.tsx`) imports `agentation`; no feature file imports the package directly |
| Root mount | the root shell (`src/App.tsx` or `src/main.tsx`) renders the wrapper once |
| Dev-only | the render is gated on `import.meta.env.DEV` (Vite) or `process.env.NODE_ENV !== "production"`, so production builds drop it |
| Endpoint | the endpoint matches the repo doc; do not change it unless the task is about the tooling |

`grep -rn "from 'agentation'\|from \"agentation\"" src` lists every importer: more
than the wrapper is drift.

## 2. Restore (only when a check fails)

1. Missing dependency: add it with the repo's package manager (`npm i agentation`), never
   by editing the lockfile.
2. Missing wrapper: recreate it at the path the repo doc names: a small component that
   imports the toolbar from `agentation`, passes the documented endpoint, and returns
   `null` outside development.
3. Missing mount: render the wrapper once in the root shell, after the router/providers,
   behind the dev gate.
4. Extra direct imports: route them through the wrapper.

Keep the diff to those files. Record the restore in the repo's doc if it changed paths.

## 3. Verify without starting anything

Run the repo's own commands (site-sync-vista: `npm run lint`, `npm run test`,
`npm run build`). After the build, confirm the overlay is absent from production output:

```bash
grep -rl 'agentation' dist/ | head
```

No hits = the gate works. Hits mean the package is imported statically outside the gate
(Vite only drops code behind a compile-time `import.meta.env.DEV` branch or a dynamic
`import()` inside it); report that and fix it only if the task covers the tooling.

A live look at the toolbar is the user's step (they run the dev server); say so instead of
starting one.

## Scope

Web React surface only. React Native / Expo apps and servers do not mount Agentation
unless their own docs say so.

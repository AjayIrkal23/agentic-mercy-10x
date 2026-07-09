# Vite React Best Practices

Comprehensive guide for building production-ready React SPAs with Vite.

## Table of Contents
1. [Vite SPA Requirements](#vite-spa-requirements)
2. [React Core Best Practices](#react-core-best-practices)
3. [Anti-Patterns](#anti-patterns)
4. [Troubleshooting](#troubleshooting)

---

# Vite SPA Requirements

## Configure Static Host Rewrites for SPA Routing

Vite SPAs differ from Next.js in that they have no server-side routing logic. When a user navigates deeper than `/` (e.g., `/dashboard`), and hits "Refresh", the browser asks the server for `/dashboard`. Without a rewrite rule, the static host returns 404.

### Why it matters
Failing to configure rewrites is the #1 cause of "404 Not Found" errors on page refresh in SPAs. It breaks deep linking, sharing URLs, and user confidence.

### Incorrect
Deploying a Vite app to S3, Netlify, or Nginx without specific SPA configuration.

```nginx
# Nginx default (Incorrect for SPA)
location / {
  root /var/www/html;
  index index.html;
  # Returns 404 if file not found
}
```

### Correct
Configure the host to serve `index.html` for any unknown path, allowing the client-side React Router to handle the URL.

#### Nginx
```nginx
location / {
  try_files $uri $uri/ /index.html;
}
```

#### Netlify (`netlify.toml`)
```toml
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

#### Vercel (`vercel.json`)
```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

---

## Correct Caching Strategy for Vite Assets

Vite uses content-based hashing for built assets (e.g., `index.a1b2c3d4.js`). This allows for a very specific and efficient caching strategy.

### Why it matters
Incorrect caching leads to two major issues:
1. **Users see old code** after a deployment (if `index.html` is cached).
2. **Slow loading** (if hashed assets are not cached aggressively).

### Incorrect
Applying the same cache policy to all files.

```http
# Incorrect: Caching everything for a week
Cache-Control: public, max-age=604800
```

### Correct
Split your caching strategy into two categories:

#### 1. The Entry Point (`index.html`)
This file MUST NOT be cached, or cached for a very short time. It is the "pointer" to your versioned assets.

**Header:**
```http
Cache-Control: no-cache, no-store, must-revalidate
```

#### 2. Hashed Assets (`/assets/*.js`, `/assets/*.css`, images)
Since the filename changes whenever the content changes, these can be cached "forever".

**Header:**
```http
Cache-Control: public, max-age=31536000, immutable
```

---

## Environment Variables in Vite

Vite exposes environment variables on the `import.meta.env` object. Unlike server-side frameworks, all variables are embedded into the JavaScript bundle at build time.

### Why it matters
- **Security:** Accidental exposure of private keys (`DB_PASSWORD`) to the client.
- **Confusion:** Expecting variables to break at runtime if the environment changes (they are "baked in" at build time).

### Incorrect
Using `process.env` or non-prefixed variables.

```tsx
// Incorrect: Vite doesn't polyfill process.env by default
console.log(process.env.API_KEY);

// Incorrect: This variable will be undefined unless configured in `vite.config.ts`
console.log(import.meta.env.SECRET_KEY);
```

### Correct
Prefix public variables with `VITE_` and access via `import.meta.env`.

```env
# .env
VITE_API_URL=https://api.example.com
DB_PASSWORD=supersecret
```

```tsx
// App.tsx
// Correct: VITE_ prefix makes it accessible
const apiUrl = import.meta.env.VITE_API_URL;

// Correct: Private variable is undefined in the bundle
const dbPass = import.meta.env.DB_PASSWORD; // undefined
```

---

## Validate Production Builds Locally

The development server (`vite`) uses `esbuild` and serves unbundled files. The production build (`vite build`) uses Rollup and bundles files. This slight difference can hide bugs until deployment.

### Why it matters
Issues like case-sensitive file imports, missing public assets, or aggressive tree-shaking might not appear in Dev mode but will crash the Production build or runtime.

### Anti-Pattern
Pushing code to CI/CD immediately after verifying it works in `npm run dev`.

```bash
# Don't do this only
npm run dev
git commit -m "It works on my machine"
git push
```

### Correct Workflow
Always run a full build and preview cycle locally before pushing major changes.

```package.json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview"
  }
}
```

1. **Typecheck First:** Run `tsc --noEmit` to catch type errors.
2. **Build:** Run `vite build` to generate the `dist/` folder.
3. **Preview:** Run `vite preview` to spin up a local static server serving the contents of `dist/`.

---

# React Core Best Practices

## Route-Level Code Splitting

Load code only when it's needed. In a generic CRA or Vite app, the default behavior might bundle the entire application into a single large JS file if you reference components directly in your router.

### Why it matters
A massive initial bundle delays the "Time to Interactive" (TTI).

### Incorrect
Importing all page components at the top level of your router.

```tsx
import Dashboard from './pages/Dashboard';
import Settings from './pages/Settings';
```

### Correct
Use `React.lazy` and `Suspense` to split code by route.

```tsx
import { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));

function App() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Suspense>
  );
}
```

---

# Anti-Patterns

## Anti-Pattern: Importing from Dist

Never import files from the `dist/`, `build/`, or generated output folders of your libraries or your own project.

### Why it matters
- **Bundling double:** You might include the same library twice.
- **Optimization loss:** Pre-bundled code cannot be effectively tree-shaken.

### Incorrect
```tsx
import { Button } from 'expensive-library/dist/bundle.js';
```

### Correct
Import the source modules or the main package entry point.

```tsx
import { Button } from 'expensive-library';
```

---

# Troubleshooting Vite

## Common Issues

### 1. "Module is external" or "Cannot find module"
**Cause:** Deep imports from CommonJS libraries.
**Fix:** Add package to `optimizeDeps.include` in `vite.config.ts`.

### 2. HMR Not Working (Full Reload on Save)
**Cause:** Circular dependencies or Default Exports inconsistencies.
**Fix:** Check console for "circular dependency" warnings. Use named exports.

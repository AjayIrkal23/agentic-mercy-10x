# Environment Variables in Vite

Vite exposes environment variables on the `import.meta.env` object. Unlike server-side frameworks, all variables are embedded into the JavaScript bundle at build time.

## Why it matters
- **Security:** Accidental exposure of private keys (`DB_PASSWORD`) to the client.
- **Confusion:** Expecting variables to break at runtime if the environment changes (they are "baked in" at build time).

## Incorrect
Using `process.env` or non-prefixed variables.

```tsx
// Incorrect: Vite doesn't polyfill process.env by default
console.log(process.env.API_KEY);

// Incorrect: This variable will be undefined unless configured in `vite.config.ts`
console.log(import.meta.env.SECRET_KEY);
```

## Correct
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

### Type Safety (Recommended)
Create `src/vite-env.d.ts`:
```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_FEATURE_FLAG: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

# Common Vite Troubleshooting

Quick fixes for the most frequent issues encountered in Vite + React projects.

## 1. "Module is external" or "Cannot find module"
**Cause:** Deep imports from CommonJS libraries or missing exports in `package.json`.
**Fix:** Add valid ESM entry point or include in `optimizeDeps`.

```ts
// vite.config.ts
export default defineConfig({
  optimizeDeps: {
    include: ['broken-lib/dist/utils']
  }
})
```

## 2. HMR Not Working (Full Reload on Save)
**Cause:**
1. **Circular Dependency:** A imports B, B imports A. Check console warnings.
2. **Export Default vs Named:** React Fast Refresh prefers Named Exports or consistent exports.
3. **Case Sensitivity:** Importing `File.tsx` as `file.tsx` works on Mac but implies a new module ID.

## 3. Styles Missing in Production
**Cause:** Dynamic imports of CSS files that the bundler cannot trace statically.
**Fix:** Ensure CSS imports are static or part of the module graph.

## 4. 404 on Refresh
**Cause:** Missing client-side routing fallback.
**Fix:** Configure rewrites on your static host (see `vite-spa-rewrites.md`).

# Validate Production Builds Locally

The development server (`vite`) uses `esbuild` and serves unbundled files. The production build (`vite build`) uses Rollup and bundles files. This slight difference can hide bugs until deployment.

## Why it matters
Issues like case-sensitive file imports, missing public assets, or aggressive tree-shaking might not appear in Dev mode but will crash the Production build or runtime.

## Anti-Pattern
Pushing code to CI/CD immediately after verifying it works in `npm run dev`.

```bash
# Don't do this only
npm run dev
git commit -m "It works on my machine"
git push
```

## Correct Workflow
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

1. **Typecheck First:** Run `tsc --noEmit` to catch type errors (Vite builds ignore them by default).
2. **Build:** Run `vite build` to generate the `dist/` folder.
3. **Preview:** Run `vite preview` to spin up a local static server serving the contents of `dist/`.
4. **Verify behaviors:** Click around the preview app to ensure everything loads correctly.

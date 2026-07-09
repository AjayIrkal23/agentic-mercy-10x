<!-- dox:child v1 -->
# `assets/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

README illustration assets only — the WebP infographics embedded in the root
`README.md`. All AI-generated via Higgsfield (Nano Banana Pro), downscaled to
1600px-wide WebP so the clone stays lean. No source PNGs kept (converted, then deleted).
Nothing else belongs here — not app assets, not skill assets.

## Local conventions

- Format `.webp`, ≤ ~1600px wide, `ffmpeg -c:v libwebp -quality 90`; keep each file < ~200 KB.
- Kebab-case names matching the README section they illustrate (`hooks-lifecycle.webp`).
- Referenced from `../README.md` via relative `<img src="assets/...">` — never hot-linked CDN URLs (they expire).

## Key files

| File | Role |
|------|------|
| `hero.webp` | Top banner — orchestrated dev pipeline |
| `token-economics.webp` · `auto-index.webp` · `codebase-navigation.webp` | Intel / token-saving story |
| `superpowers-grid.webp` | The eight-superpowers overview |
| `standards-frontend/backend/scaffold/api-contract.webp` | Structure & standards |
| `skill-router.webp` · `invoke-team.webp` | Orchestration (router + /invoke chain) |
| `hooks-lifecycle.webp` · `hooks-gates.webp` | Hook enforcement |
| `uiux-antislop/stack-flow/designer-loop.webp` | Anti-slop UI/UX |
| `codebase-structure.webp` | Before/after structure |

## Gotchas / fragile spots

- AI-generated in-image text can garble — keep it to titles + short labels; put exhaustive/accurate
  detail in the README's Markdown tables, not the image.
- Some images carry a model-invented watermark/logo — cosmetic only.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
- Related: root `README.md` (the only consumer of these files)

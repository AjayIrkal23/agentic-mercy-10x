<!-- dox:child v1 -->
# `assets/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

The WebP plates embedded in the root `README.md`, one per feature section, and their
HTML sources in `src/`. Nothing else belongs here: not app assets, not skill assets.

Each plate is an HTML page (`src/<name>.html` + the shared `src/base.css`) rendered by
headless Chromium. Every label, count and terminal line in a plate is a real name or a
real output from this repo (router output, `scripts/statusline.py`, `installer/doctor.py`,
`hooks/dispatch.config.json` link ids). The only generated image is the hero background
`src/hero-bg.webp` (GPT Image 2.5 Sunburst on OpenArt, textless, 2026-10-06).

## Local conventions

- Re-render after a change: `python3 assets/src/render.py [name ...]` (2x screenshot →
  1600 px WebP, quality 90; keep each file < ~200 KB). Plate heights live in `HEIGHTS`.
- One design system for every plate: tokens in `src/base.css` (near-black, one accent
  `#d97757`, Geist + Geist Mono, cards 14 px, chips 8 px). No em dashes in plate text.
- Plate text states facts only. When a count changes (skills, links, MCP servers,
  doctor rows), edit the HTML and re-render; never replace a plate with AI-generated text
  (it invents labels: the old neon set showed hooks that never existed).
- Kebab-case names matching the README section (`hooks.webp`), referenced from
  `../README.md` via relative `<img src="assets/...">`, never hot-linked CDN URLs.

## Key files

| File | Role |
|------|------|
| `film.webp` | first thing in the README: a silent ~10 s loop cut from the launch film (release `launch-film-2026-10-06`), linked to the public GCS copy because GitHub plays no hot-linked `<video>`. Shots from the master at 2.0, 29.4, 42.4, 114.4, 130.4, 153.4 s (1.4 s each) and 209.6 s (2.2 s), 960x540, 12 fps, ffmpeg `libwebp_anim` q 62, orange "WATCH THE FILM · 3:34" pill top right (Geist Mono Bold). Keep it under ~1 MB |
| `hero.webp` | former top banner (name, pitch, real counts, install command); the film preview replaced it in the README on 2026-10-06, kept for reuse |
| `install.webp` | install flow + a real doctor run |
| `router.webp` | prompt router stages + real router output |
| `invoke.webp` | `/invoke` acts, agents, model pins, artifacts |
| `hooks.webp` | hook timeline with real dispatch link ids and types |
| `mercy.webp` | the mercy mod per session step, guard refusal, bridge |
| `deck.webp` | action band, mod status, real `statusline.py` output, `/pulse` views |
| `mcp.webp` | the 16 MCP servers grouped by job |
| `src/*.html`, `src/base.css` | plate sources |
| `src/hero-bg.webp` | hero background art (OpenArt) |
| `src/render.py` | renders plates (Chromium + ImageMagick or ffmpeg; Ubuntu and Windows) |

## Gotchas / fragile spots

- Fonts load from Google Fonts at render time: rendering needs the network, or the
  plates fall back to system fonts and the layout shifts.
- `render.py` finds Chromium on `PATH` or in the Playwright cache
  (`chromium_headless_shell-*`).

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
- Related: root `README.md` (the only consumer of these files)

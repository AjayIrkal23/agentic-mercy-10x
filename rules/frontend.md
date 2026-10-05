---
paths:
  - "**/*.{tsx,jsx,vue,svelte,astro,html}"
  - "**/*.{css,scss}"
  - "**/tailwind.config.*"
  - "**/components.json"
---
# Frontend (loads on FE files)

**React Native / Expo files** (an app with `app.json`/`app.config.*` and `react-native` in
its `package.json`) also match these globs, but the DOM, CSS, Tailwind, `motion/react`
and Higgsfield-web-asset rules below do not apply there: use `expo-react-native` and the
app's own `CLAUDE.md`.

**Baseline skills:** `frontend-standards-always-follow` + `frontend-structure-standards`
first; the rest (`react-hooks-patterns`, `frontend-response-handling`,
`frontend-server-data-patterns`, `tailwind-design-system`, `ui-styling`,
`webapp-testing`) surface by their own `paths:`. No client-side filtering of server
data; the API layer parses envelopes → typed data; types live in `src/types/<domain>/`.

**Visual authority (in order):** `design-taste-frontend` > plugin
`frontend-design:frontend-design` > `frontend-ui-engineering` §anti-AI.
Keyboard-accessible, mobile-first, semantic tokens ≥4.5:1, no emoji icons, no
"AI aesthetic" defaults.

**Motion:** React UI → `motion-dev` (`motion/react`); SVG draw/morph, timelines,
non-React → `animejs-motion` (v4 ESM). CSS-only hover/focus stays CSS.

**Scroll:** any scroll-driven / scrollytelling / pinned / parallax request → invoke
`nateherk-design:scroll-craft` (renamed from `scrollcraft` in 0.3.0) before writing
scroll code. scroll-craft owns the scroll
timeline and page grammar; its kie.ai asset path runs only with my explicit OK —
otherwise assets come from Higgsfield below.

**Assets — Higgsfield (`mcp__higgsfield__*`) is the default engine.** Placeholders,
gray boxes, `bg-gradient` stand-ins, stock/unsplash URLs, lorem-image services and
emoji-as-icon are a hard fail wherever Higgsfield can generate the real thing. When it
needs its one-time login (the router says so once per session), ask me once, batched with
any other login, use `mcp__higgsfield__authenticate`, and report the assets as pending
until then.

| Need | Tool | Default model (higgsfield skills 0.13) |
|---|---|---|
| hero / section image, texture, illustration, OG image, on-image text | `generate_image` | GPT Image 2.5 |
| logo, icon, vector-like mark | `generate_image` | Recraft V4.1 (`recraft_v4_1`, vector) |
| cartoon / illustrated character | `generate_image` | Nano Banana 2 (`nano_banana_flash`; `nano_banana_2` = Pro) |
| person / reference-consistent image | `generate_image` (+ `higgsfield-soul-id` for a trained face) | GPT Image 2.5 / Soul |
| background loop, product clip, image → motion | `generate_video` / `motion_control` | Seedance 2.5 (`seedance_2_5`, 4–30 s, ≤1080p; 4K → Seedance 2.0) |
| ad / UGC / product demo video | `generate_video` | Marketing Studio |
| interactive 3D element as a GLB | `generate_3d` | Multi-Image to 3D |
| UI sound, ambient bed, SFX, short music | `generate_audio` | Seed Audio 1.0 |
| enhance / new aspect / cutout | `upscale_image` · `upscale_video` · `outpaint_image` · `reframe` · `remove_background` | — |
| unsure which model fits | `models_explore(action:"recommend")` first | — |

Several independent assets → `generate_image_batch` / `generate_video_batch` → `jobs_wait`
(one `show_generation_by_ids`). Local input photo/video → `media_upload_widget` (never
paste into chat). Check `balance` before a batch. Skills: `higgsfield-generate`,
`higgsfield-product-photoshoot`, `higgsfield-marketplace-cards`, `higgsfield-brandkit`
(brand systems), `higgsfield-youtube-thumbnail`, `higgsfield-video-explainer`,
`higgsfield-websites` (greenfield full sites only).

**OpenArt** (`mcp__openart__*`) is the sanctioned secondary engine only when the
project's memory or `CLAUDE.md` says so.

**3D split:** a GLB asset → Higgsfield `generate_3d`; a procedural Three.js model coded
from a reference image → `img2threejs`; consuming a GLB in React → `threejs-r3f`.

**Reticle / browser guard:** never run `reticle init`; never start dev servers or open
browsers to verify — attach to the app I am already running (playwright MCP,
browser-tools when its extension is live). Otherwise verify with `npm run build`,
`lint`, and tests.

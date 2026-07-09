# Higgsfield — MANDATORY frontend asset engine

> Always-on rule. Standing user directive (2026-07-04): **every frontend UI/UX task
> sources its visual/motion/3D/audio ASSETS from Higgsfield.** The user holds an
> `ultimate` asset-generation subscription — bespoke generation is the default, not
> the exception. Placeholder boxes, `bg-gradient` fakes, unsplash/stock URLs, emoji
> "icons", and lorem-image services are BANNED where Higgsfield can generate the real
> thing. This is the asset layer *underneath* the UI/UX six-skill craft stack
> ([[ui-ux-playbook]]), not a replacement for it.

## The one rule

Building or polishing any frontend? **Any asset that is raster, video, 3D, or audio
comes from Higgsfield.** Arrangement, layout, tokens, typography, and DOM motion stay
with the craft stack (Impeccable / Taste / Huashu / UI-UX-Pro-Max / frontend-design).
Higgsfield supplies the *materials*; the craft stack *arranges* them.

## Capability → tool map (what MUST be generated, not faked)

| Frontend need | Higgsfield tool (connector `mcp__claude_ai_higgsfield__*`) | Model |
|---|---|---|
| Hero image, section imagery, background, texture, pattern | `generate_image` | GPT Image 2 |
| Character / person / reference-consistent image | `generate_image` (+ `higgsfield-soul-id` for a trained face) | Nano Banana 2/Pro |
| Illustration, spot graphic, bespoke icon, logo, OG image | `generate_image` | GPT Image 2 |
| Hero background loop, animated section, motion background, product clip | `generate_video` | Seedance 2.0 |
| Image → moving element (parallax plate, living hero) | `generate_video` / `motion_control` | — |
| Interactive / hero 3D element | `generate_3d` (image → GLB) | — |
| UI sound, ambient bed, SFX, short music | `generate_audio` | Seed Audio 1.0 |
| Enhance / 2K-4K an asset | `upscale_image` / `upscale_video` | — |
| Expand / uncrop for a new aspect | `outpaint_image` | — |
| Change a video's aspect for a breakpoint | `reframe` | — |
| Cutout / transparent PNG | `remove_background` | — |
| Ad / marketing creative, avatar, UGC | Marketing Studio via `generate_video` | — |
| Full bespoke site (greenfield only) | `higgsfield-websites` skill (own Cloudflare Worker template) | — |
| Unsure which model fits | `models_explore(action:'recommend')` FIRST | — |

Local input photo/video for a generation → `media_upload_widget` (never ask the user to
paste into chat; remote MCP can't read chat attachments). Check `balance` before a large
batch. Skills that route this: `higgsfield-generate`, `higgsfield-soul-id`,
`higgsfield-product-photoshoot`, `higgsfield-marketplace-cards`, `higgsfield-websites`.

## The boundary (be honest — don't fake capability)

Higgsfield does **not** write Framer Motion, CSS keyframes, SVG-in-JSX, or your React.
So:
- **DOM/component motion** (transitions, hover/press/focus, scroll reveal, layout
  animation) → stays code, owned by Taste-Skill / Impeccable `animate`. BUT any *media*
  it drives (the video in the hero, the texture in the parallax, the 3D in the canvas)
  is Higgsfield-generated, not a placeholder.
- **Layout, type, tokens, spacing, a11y** → craft stack, unchanged.
- **Raster/video/3D/audio pixels** → Higgsfield, always.

Rule of thumb: *if the deliverable would otherwise ship a gray box, a stock URL, a
CSS-only gradient standing in for real art, an emoji-as-icon, or a "TODO: add image"* —
that is exactly where Higgsfield is mandatory.

## When it fires

Any UI/UX/frontend trigger (see [[ui-ux-playbook]] Phase A intake). Concretely: new
component/page/landing/hero/dashboard, redesign/polish/restyle, "make it amazing",
theming, marketing pages, empty/error/loading states that want real art, and any prompt
naming image/illustration/icon/background/video/animation/3D/audio.

## Order within the UI/UX flow

1. **Intake + context** — craft stack (Impeccable `load-context`, Taste dials, product truth).
2. **Design direction** — craft stack (tokens, layout, type).
3. **Asset generation — HIGGSFIELD** — generate every raster/video/3D/audio asset the
   design calls for (`models_explore` → `generate_*` → `upscale`/`reframe`/`remove_background`).
4. **Assemble + motion** — craft stack arranges the Higgsfield assets; code-level motion
   references those assets.
5. **Verify** — Impeccable audit/critique/polish + Huashu `verify.py`; confirm no
   placeholder/stock asset survived (that is a hard fail of this rule).

## Enforcement

- `ui-ux-stack-orchestrator.py` injects a Higgsfield asset-layer line into the UI stack
  checklist on every UI-classified prompt (before-submit).
- `fullstack-skills-reminder.py` carries `higgsfield-generate` in `FRONTEND_SKILLS`.
- `frontend-uiux-designer` agent has the Higgsfield connector tools wired and an
  Asset-Generation phase in its workflow.
- This rule is imported into CLAUDE.md so the mandate stays in context every session.

Connector status check: `balance` (live = credits + plan returned). Deep playbook:
skill `higgsfield-generate`.

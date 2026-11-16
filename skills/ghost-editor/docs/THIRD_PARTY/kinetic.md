# Third-party sources: kinetic type (`textfx` beats)

File: `scripts/lib/kinetic.mjs`. No upstream code file was copied verbatim: the blocks were written fresh for the skill's
single-timeline GSAP contract. The table says which technique, constant or formula came from where. All sources are MIT or
Apache-2.0 (verified 2026-10-10 from each repo's LICENSE file and `gh api repos/<r> --jq .license.spdx_id`).

| repo | licence | what was taken (ideas, numbers, formulas) | used in |
|---|---|---|---|
| [heygen-com/hyperframes-launches](https://github.com/heygen-com/hyperframes-launches) (`HF-heygen-stripe/compositions/rotary.html`) | Apache-2.0 (NOTICE: Copyright HeyGen) | rotisserie drum geometry: words at `rotateX(-k*step) translateZ(R)`, axis pushed back by R, top/bottom mask gradient, width hugging the widest word, `rotationX` step ending on the spoken onset, no CSS filter on the 3D group | `drum` |
| heygen-com/hyperframes-launches (`variables-launch/compositions/scene-01.html`) | Apache-2.0 | word dial with visible waiting neighbours; staggered "waterfall" entry | `drum`, `spring` |
| heygen-com/hyperframes-launches (`claude-design-send-hyperframes-launch/compositions/s4-thesis.html`) | Apache-2.0 | character scramble: width-bounded glyph pool, `hash(step*31 + w*17 + i*7)` deterministic glyph choice, left-to-right resolve per word; `hash(i) = frac(sin(i*127.1)*43758.5453)` | `scramble` |
| heygen-com/hyperframes-launches (`heygen-apple-motion/02-bouncy-ui/index.html`, README) | Apache-2.0 | damped spring residual `A*e^(-2*pi*zeta*f*t)*cos(2*pi*f*sqrt(1-zeta^2)*t)` with zeta = 1/3 on separate position / shape / rotation channels; volume-conserving squash `sx = e^(q/2), sy = e^(-q/2)`; 2D flip fallback `scaleY = abs(cos theta)`; one ease family (`1 - 2^(-10p)` and its mirror) | `spring`, `flipstack`, `hook`, runtime `KT.spring/EO/EI` |
| [whaleyxbt/claude-motion](https://github.com/whaleyxbt/claude-motion) (`src/lib.ts`, `src/components/primitives.tsx`, `.claude/skills/motion-design`) | MIT, (c) 2026 whaleyxbt | mask primitive numbers (`translateY 118 %`, `rotate 5deg`, origin `0 100%`, padding/negative-margin trick); bezier curves `(0.16,1,0.3,1)`, `(0.6,0,0.9,0.35)`, `(0.65,0,0.35,1)`; line boil via `feTurbulence` + `feDisplacementMap` reseeded at 12 fps; reading-hold rule | `headline`, every mask line, runtime `KT.OUT/IN/INOUT`, `readingHold()` |
| [bangtutorial/bang-motion](https://github.com/bangtutorial/bang-motion) (`references/techniques.md`, `references/opener-konsep.md`) | MIT, (c) 2026 Bang Tutorial | `mark()` timing (mark draws 0.4-0.6 s after the words), the under / marker / box / strike emphasis forms, the giant-cropped-word pull-back opener, the dark text "pocket" under type over busy ground | `headline`, `hook`, `pocket()` |
| [iart-ai/tiktok-video-skills](https://github.com/iart-ai/tiktok-video-skills), [iart-ai/kinetic-typography-skills](https://github.com/iart-ai/kinetic-typography-skills) (packs of [iart-ai/motion-skills](https://github.com/iart-ai/motion-skills)) | MIT, (c) 2026 iart.ai | hook text on screen by frame 1 (no fade-up), footage punch-in as a spring, char/word stagger ranges | `hook`, `spring` |
| [latent-spaces/brag](https://github.com/latent-spaces/brag) (`skills/brag-slim/SKILL.md`, `references/step-2-plan.md`) | MIT, (c) 2026 Shunit Haviv Hakimi | reading floor ~0.3 s per word; no crossfade between busy layouts (stagger instead) | `readingHold()`, swap mode gap |

Fonts: the bundled OFL fonts in `templates/fonts` (Inter, Montserrat, Unbounded, JetBrains Mono). GSAP 3.14.2 is loaded the
same way build.mjs always has (GSAP standard "no charge" licence).

Not used: Remotion (claude-motion's runtime; company licence above a size threshold), three.js backgrounds from
bang-motion, the HyperFrames registry text blocks (Latin-only alphabets; Cyrillic-aware versions were written instead).

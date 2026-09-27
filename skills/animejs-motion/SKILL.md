---
name: animejs-motion
description: ALWAYS invoke for SVG animation (line-draw/morph), standalone timelines, and non-React or "sprinkle" motion — anime.js v4 is the engine for these. In React app UI, `motion-dev` (Motion) is PRIMARY for layout/exit/gestures/scroll; reach here for SVG (`svg.createDrawable`/`morphTo`/`createMotionPath`), imperative `createTimeline` sequences, `createDraggable`, and non-React pages. MUST use v4 ESM API (`import { animate } from 'animejs'`) — never v3 `anime({})`. Pull exact API from Context7 `/websites/animejs`. Not for React layout/exit animations (Motion), CSS-only hover/focus (native CSS), or asset pixels (Higgsfield).
---

# anime.js (v4) — SVG / timeline / standalone motion engine

**Standing directive:** anime.js v4 is the engine for **SVG animation, standalone timelines, and
non-React / "sprinkle" motion**. For **React app UI**, Motion ([[motion-dev]]) is PRIMARY
(layout, exit/`AnimatePresence`, gestures, scroll). Split routing: [[motion-engine-mandate]].
Reach here for: `svg.createDrawable`/`morphTo`/`createMotionPath`, imperative `createTimeline`
sequences, `createDraggable`, non-React pages. Not Framer Motion, not GSAP, not hand-rolled rAF.

## Where it sits in the stack

```
        DECIDES the motion   (should it move? easing? duration? physical or not?)
  → Motion / anime.js  IMPLEMENTS it        (Motion = React UI · anime.js = SVG/timeline/standalone)
    →   GATES it           (Block/Approve on the motion diff before ship)
```

Motion + anime.js are the motion counterpart to Higgsfield (asset pixels).
Emil/ own *whether and how* to move; the engines are *how you write it*.

## Docs — Context7 first, no local copy

For ANY non-trivial API detail, query **Context7 `/websites/animejs`** (mirror of
animejs.com/documentation, ~1,900 snippets). Do not guess v3 syntax from memory.
- `mcp__context7__query-docs('/websites/animejs', '<specific question>')`
- Human docs: https://animejs.com/documentation/getting-started
The cheat-sheet below covers the 80% common case so trivial motion needs no round-trip.

## v4 quick-ref (ESM named imports — NOT default `anime`)

```js
import {
  animate, createTimeline, createTimer, createAnimatable,
  stagger, onScroll, svg, utils, eases, spring,
  createScope, createDraggable,
} from 'animejs';

// core
animate('.box', { x: '10rem', opacity: [0, 1], ease: 'out(3)', duration: 400 });

// property keyframes (per-step ease/duration)
animate('.logo', { scale: [{ to: 1.25, ease: 'inOut(3)', duration: 200 },
                           { to: 1,    ease: spring({ bounce: .4 }) }] });

// timeline — .add(target, params, position)
createTimeline({ defaults: { ease: 'out(2)' } })
  .add('.a', { y: [20, 0], opacity: [0, 1] })
  .add('.b', { y: [20, 0], opacity: [0, 1] }, '-=150'); // overlap 150ms

// stagger a list
animate('.item', { y: [16, 0], opacity: [0, 1], delay: stagger(60, { from: 'first' }) });

// scroll-linked: pass onScroll() to autoplay
animate('.reveal', { opacity: [0, 1], y: [24, 0],
  autoplay: onScroll({ target: '.reveal', enter: 'bottom top', sync: 1 }) });

// SVG
animate(svg.createDrawable('.line'), { draw: ['0 0', '0 1'], duration: 1200 });
svg.morphTo('.to-shape');

// utils: select / set / random / cleanup
utils.set('.box', { opacity: 0 });
utils.$('.item');                 // scoped querySelectorAll
```

## v4 rules (the traps)

- **`ease`, not `easing`** (v3 → v4 rename). Strings: `'linear'`, `'in(2)'`, `'out(3)'`,
  `'inOut(4)'`, `'inOutQuad'`, `cubicBezier(...)`, `spring({ bounce, duration })`.
- **Named ESM imports.** `import { animate } from 'animejs'` — the v3 `import anime from 'animejs'; anime({...})` is gone.
- **React / any framework → `createScope`.** Wrap instances so unmount cleans up:
  ```js
  useEffect(() => {
    const scope = createScope({ root }).add(self => {
      animate('.logo', { rotate: 360, loop: true });
      self.add('bump', () => animate('.logo', { scale: [1, 1.1, 1] })); // callable via scope.methods.bump()
    });
    return () => scope.revert();   // <-- mandatory cleanup
  }, []);
  ```
- **Spring settling overrides `duration`** — with `ease: spring(...)`, drop the explicit `duration`.
- **Perf:** animate `transform`/`opacity` (compositor), avoid layout props (`top`/`width`/`margin`) in loops.

## Craft mandates (inherited — do not relitigate)

- **Motion default = no bounce** (). `spring({ bounce })`/overshoot ONLY for
  *gesture-released* motion the user physically imparted (drag-to-dismiss, flick, swipe →
  `createDraggable` + `releaseEase: spring(...)`). A card that merely fades in must not overshoot.
- **Respect `prefers-reduced-motion`** — gate/shorten motion:
  ```js
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) animate(/* ... */);
  ```
- Every motion that ships still passes the **``** gate (easing/duration/interruptibility/a11y).

## When NOT to use it

- Pure CSS hover/focus/active states → native CSS `transition`. Don't pull in JS.
- Asset pixels (images/video/3D/audio) → Higgsfield, not anime.js.

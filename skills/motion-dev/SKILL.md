---
name: motion-dev
description: "ALWAYS invoke for React UI motion — this is the PRIMARY motion engine for React app interfaces. Motion (motion.dev, the rebranded Framer Motion) owns declarative React motion — enter/exit transitions (`AnimatePresence`), layout & shared-element animations (`layout`/`layoutId`), gestures (`whileHover`/`whileTap`/`whileInView`/`drag`), and scroll-linked motion (`useScroll`). Pairs with `animejs-motion` (which owns SVG draw/morph, standalone timelines, non-React). Use the `motion` package + `motion/react` import — NOT the old `framer-motion`. Pull exact API from Context7 `/websites/motion_dev`. Not for SVG line-draw/morph or non-React (anime.js), CSS-only hover states (native CSS), or asset pixels (Higgsfield)."
---

# Motion (motion.dev) — PRIMARY React UI motion engine

**Standing directive:** Motion is the motion engine for **React app UI** in this user's stack.
It's the rebranded successor to Framer Motion (package `motion`, import `motion/react`).
It owns the things anime.js structurally can't do in React: **layout animations**, **exit
animations**, gesture props, and deep hook integration.

## Split with anime.js (one engine per job — see [[motion-engine-mandate]])

```
React UI motion            → Motion       ← layout, AnimatePresence exit, drag, whileHover, useScroll
SVG draw/morph, timelines,
  standalone / non-React    → anime.js v4  ← svg.createDrawable/morphTo, createTimeline, createDraggable
CSS hover/focus/active      → native CSS   (don't pull in JS)
asset pixels                → Higgsfield
```

Overlap (both do spring/stagger/scroll) resolves by **context**: writing React component motion → Motion; SVG/standalone sequence → anime.js.

## Docs — Context7 first, no local copy

Query **Context7 `/websites/motion_dev`** for any non-trivial API. Human docs: https://motion.dev/docs
- **AI Kit** (optional, official): a **Motion+** paid add-on (one-time, lifetime) — installs a
  `/motion` skill (handwritten animation rules), an **MCP server** (doc/example search, perf
  audits, a transition-curve editor), and can generate CSS springs with no import. In Cursor: `/moti`.
  It's the official "AI writes good Motion code" tooling; this skill is the free-standing guidance.

## Quick-ref (Motion v11+, `motion/react`)

```jsx
// npm i motion
import { motion, AnimatePresence, useScroll, useTransform, useAnimate, useReducedMotion } from "motion/react";

// declarative enter
<motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: .4, ease: "easeOut" }} />

// EXIT — the anime.js-can't: mount/unmount animation (needs a key on the child)
<AnimatePresence>
  {open && <motion.div key="panel" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />}
</AnimatePresence>

// LAYOUT — auto-animate position/size changes; layoutId = shared-element transition
<motion.div layout />
<motion.div layoutId="card" />

// gestures
<motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: .97 }} />
<motion.div whileInView={{ opacity: 1 }} viewport={{ once: true }} />
<motion.div drag dragConstraints={{ left: 0, right: 300 }} />

// variants + stagger children
const list = { show: { transition: { staggerChildren: .05 } } };
const item = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0 } };
<motion.ul variants={list} initial="hidden" animate="show">
  <motion.li variants={item} />
</motion.ul>

// spring (gesture-released only, per craft default)
transition={{ type: "spring", stiffness: 300, damping: 30 }}

// scroll-linked
const { scrollYProgress } = useScroll();
const y = useTransform(scrollYProgress, [0, 1], [0, -200]);

// imperative when you need it
const [scope, animate] = useAnimate();
animate(scope.current, { opacity: 1 });
```

## Rules (the traps)

- **Package is `motion`, import `motion/react`** — the old `framer-motion` package/import is legacy.
- **`AnimatePresence`** children must be direct `motion.*` with a stable **`key`**; it's what makes exit fire.
- **`layout`** does FLIP under the hood — animate `layout`, don't hand-animate `width`/`top`.
- **Reduced motion:** `const reduce = useReducedMotion();` → skip/shorten; or global `<MotionConfig reducedMotion="user">`.
- **No-bounce default** (): `ease: "easeOut"` for entrances; `type: "spring"` with bounce ONLY for gesture-released motion (drag/flick/swipe).

## When NOT to use it

- SVG line-draw/morph, standalone timeline, or non-React → `animejs-motion`.
- CSS hover/focus/active → native CSS `transition`.
- Image/video/3D/audio pixels → Higgsfield.
- Every motion that ships still passes the **``** gate.

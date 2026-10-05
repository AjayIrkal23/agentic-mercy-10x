---
name: kokonutui
description: On-demand KokonutUI block source - 100+ animated React/TS blocks on shadcn/ui, Tailwind v4 and Motion, pulled with the shadcn CLI and reconciled to the project's tokens.
when_to_use: Only when the user names KokonutUI / kokonut explicitly; never for a generic UI request (those stay with shadcn + design-taste-frontend).
metadata:
  category: frontend
  surfaces: [frontend]
  triggers:
    keywords: [kokonutui, kokonut, "kokonut ui", "@kokonutui"]
    intents: [implement, design]
---

# KokonutUI — on-demand block source (explicit mention only)

**Trigger rule:** use this skill **only** when the user names KokonutUI / kokonut / kokonut ui.
It is NOT part of the default frontend stack and must never fire on a generic UI prompt.
Generic component/page building stays with **shadcn** (component layer) + **`design-taste-frontend`** (design authority).

## What it is

100+ opinionated, animated React + TypeScript components, templates, and blocks (hero, pricing,
AI-chat, cards, buttons, backgrounds) built **on top of shadcn/ui + Tailwind v4 + Motion**. It is a
*block pack you pull from*, not a foundation — it extends your existing shadcn setup, it does not
replace it.

## It sits ON shadcn — literally

Installed through **shadcn's own CLI registry**, same `components.json`, same `cn()` util, same
Tailwind v4 `@theme`:

```bash
npx shadcn@latest init                                  # once, if no components.json
npx shadcn@latest add https://kokonutui.com/r/utils.json   # cn() util (clsx + tailwind-merge)
npx shadcn@latest add @kokonutui/<component>            # e.g. @kokonutui/particle-button
```

Requires **Tailwind v4** (`@import "tailwindcss"`). Many components use **Motion** — which is your
adopted React motion engine (`motion-dev`), so its animations fit the stack.

## GUARDRAIL — reconcile to the design authority before ship (non-negotiable)

KokonutUI leans trendy/gradient/animated. `design-taste-frontend` is the **design authority**.
A pulled component is a **starting point, not an endorsement**:
- Map its colors to the **`tailwind-design-system` `@theme` tokens** — never let it introduce a 2nd palette or the decorative gradients `design-taste-frontend` bans.
- Apply the **no-bounce default** from the `motion-dev` craft bar — strip overshoot/spring unless the motion is gesture-released.
- Any motion it ships still passes the **`motion-dev` craft bar** (easing, ≤300 ms UI, interruptible, reduced-motion, transform/opacity only).
- Cards/layout still obey the `design-taste-frontend` bans (cards must earn their place, no identical card grids).

If a KokonutUI block conflicts with `design-taste-frontend`, `design-taste-frontend` wins — adapt the block, don't ship it raw.

## Docs

Context7 **`/websites/kokonutui`** (or repo `/kokonut-labs/kokonutui`). Human: https://kokonutui.com

## When NOT to use it

- Any prompt that doesn't name KokonutUI → don't invoke (shadcn + `design-taste-frontend` own it).
- Base primitives / forms / accessible components → shadcn directly.
- Motion authoring → `motion-dev` / `animejs-motion`. Asset pixels → Higgsfield.

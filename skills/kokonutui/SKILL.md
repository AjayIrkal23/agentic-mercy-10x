---
name: kokonutui
description: Invoke ONLY when the user EXPLICITLY says "KokonutUI" / "kokonut" / "kokonut ui". ON-DEMAND block source — NOT a default, NOT auto-fired. Do NOT invoke for generic "build a component/page/dashboard" requests — those stay with shadcn + . KokonutUI is 100+ design-forward, animated React/TS components & blocks built ON shadcn/ui + Tailwind v4 + Motion, installed via the shadcn CLI registry (`npx shadcn@latest add @kokonutui/<name>`). When invoked, RECONCILE every pulled component to 's palette/tokens/motion defaults before ship — its trendy/gradient/overshoot aesthetic must never override the design authority. Docs via Context7 `/websites/kokonutui`.
---

# KokonutUI — on-demand block source (explicit mention only)

**Trigger rule:** use this skill **only** when the user names KokonutUI / kokonut / kokonut ui.
It is NOT part of the default frontend stack and must never fire on a generic UI prompt.
Generic component/page building stays with **shadcn** (component layer) + **** (authority).

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
adopted React motion engine ([[motion-dev]]), so its animations fit the stack.

## GUARDRAIL — reconcile to  before ship (non-negotiable)

KokonutUI leans trendy/gradient/animated.  is the **design authority** ([[ui-ux-playbook]]).
A pulled component is a **starting point, not an endorsement**:
- Map its colors to the **`tailwind-design-system` `@theme` tokens** — never let it introduce a 2nd palette or decorative gradients  bans.
- Apply 's **no-bounce default** — strip overshoot/spring unless the motion is gesture-released.
- Any motion it ships still passes the **``** gate.
- Cards/layout still obey  bans (cards must earn their place, no identical card grids).

If a KokonutUI block conflicts with ,  wins — adapt the block, don't ship it raw.

## Docs

Context7 **`/websites/kokonutui`** (or repo `/kokonut-labs/kokonutui`). Human: https://kokonutui.com

## When NOT to use it

- Any prompt that doesn't name KokonutUI → don't invoke (shadcn +  own it).
- Base primitives / forms / accessible components → shadcn directly.
- Motion authoring → `motion-dev` / `animejs-motion`. Asset pixels → Higgsfield.

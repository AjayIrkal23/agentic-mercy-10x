---
name: tailwind-design-system
description: Tailwind CSS v4 tokens, themes (`@theme`), utility conventions, and component primitives in a Tailwind-based frontend — the token layer beneath shadcn components.
when_to_use: Use when touching a CSS entry file, a tailwind/postcss config, components.json, or components/ui, and when defining or migrating design tokens, themes, or v3→v4 patterns.
paths:
  - "**/*.css"
  - "**/tailwind.config.*"
  - "**/postcss.config.*"
  - "**/components.json"
  - "**/components/ui/**"
metadata:
  schema: 1
  category: frontend
  surfaces: [frontend]
  platforms: [linux, darwin, windows]
  token-cost: 650
  triggers:
    keywords: [tailwind, tailwind v4, "@theme", tokens, design tokens, theme, dark mode, css variables, utilities, primitives, cva, components.json]
    paths: [.css, tailwind.config, postcss.config, components.json, /components/ui/]
    intents: [frontend, implement, design]
---
# Tailwind Design System

**Ownership split:** `shadcn` owns components (CLI, registry, `components/ui`); **this skill owns
tokens** — `@theme`, semantic roles, utility conventions; `ui-styling` is the theming / dark-mode
reference. Tailwind **v4 only** (CSS-first `@import "tailwindcss"` + `@theme`, no `tailwind.config.js`
unless the repo is still on v3).

## Use When
- A task changes Tailwind v4 tokens, themes, component primitives, or utility conventions.
- You are standardizing a Tailwind-based design system.
- You are migrating Tailwind v3 assumptions to v4 patterns.

## Do Not Use
- Choosing the visual direction of the interface.
- Structuring frontend modules or server-data flows.
- Applying exact library syntax without first checking current docs when uncertain.

## Owns
- Tailwind v4 token and theming patterns.
- Design-system implementation details for a Tailwind-based stack.
- Tailwind-specific component and utility conventions.

## Does Not Own
- Premium UI direction or aesthetic strategy.
- General frontend architecture.
- Non-Tailwind styling systems.

## Combine With
- `shadcn` for adding/fixing components; `ui-styling` for dark-mode and CSS-variable theming recipes.
- `frontend-ui-engineering` for visual direction and production-quality patterns.
- `frontend-structure-standards` for component boundaries.
- `tool-and-doc-selection` to route Tailwind/CVA/Radix questions to current docs.

## Workflow
1. Verify the project is using Tailwind v4 before applying v4-specific syntax.
2. Confirm whether existing tokens, utilities, theme packs, or component primitives already exist.
3. Organize theme work around semantic tokens for surfaces, text, borders, accents, and data-viz roles instead of hardcoded one-off values.
4. Keep design-system changes in shared, reusable layers instead of one-off screens.
5. Move advanced examples or migrations to references instead of bloating the skill body, and verify current library syntax through docs tools when the exact API matters.

## Output Contract
- The Tailwind v4 implementation pattern being applied.
- Any token, theme, or component-primitives changes.
- A note about docs verification when exact syntax is version-sensitive.

See `references/tailwind-v4-checklist.md` for the detailed implementation checklist.

## Theme Structure
- Define one clear theme contract before adding variants: background, surface, text, border, accent, muted, destructive, and chart or status roles.
- Keep named themes as data or token layers that can be swapped without rewriting component code.
- When adding a new theme, document the intended mood, core palette roles, and typography pairing instead of only listing hex values.
- Preserve accessibility and contrast requirements across light, dark, and branded variants.

# Icon Design Reference

AI-powered SVG icon generation using the active model. 15 styles, 12 categories, multi-size export.

## How icons are made

Write each SVG directly with the Write tool (there is no generator script). Decide per icon:
description, file name, style (table below), category, color (default `currentColor`),
display size (24) and viewBox (24). For variations write N files side by side; for several
sizes keep one viewBox and set `width`/`height` per export.

## Available Styles

| Style | Stroke | Fill | Best For |
|-------|--------|------|----------|
| outlined | 2px | none | UI interfaces, web apps |
| filled | 0 | solid | Mobile apps, nav bars |
| duotone | 0 | dual | Marketing, landing pages |
| thin | 1-1.5px | none | Luxury brands, editorial |
| bold | 3px | none | Headers, hero sections |
| rounded | 2px | none | Friendly apps, health |
| sharp | 2px | none | Tech, fintech, enterprise |
| flat | 0 | solid | Material design, Google-style |
| gradient | 0 | gradient | Modern brands, SaaS |
| glassmorphism | 1px | semi | Modern UI, overlays |
| pixel | 0 | solid | Gaming, retro |
| hand-drawn | varies | none | Artisan, creative |
| isometric | 1-2px | partial | Tech docs, infographics |
| glyph | 0 | solid | System UI, compact |
| animated-ready | 2px | varies | Interactive UI, onboarding |

## Icon Categories

| Category | Icons |
|----------|-------|
| navigation | arrows, menus, home, chevrons |
| action | edit, delete, save, download, upload |
| communication | email, chat, phone, notification |
| media | play, pause, volume, camera |
| file | document, folder, archive, cloud |
| user | person, group, profile, settings |
| commerce | cart, bag, wallet, credit card |
| data | chart, graph, analytics, dashboard |
| development | code, terminal, bug, git, API |
| social | heart, star, bookmark, trophy |
| weather | sun, moon, cloud, rain |
| map | pin, location, compass, globe |

## SVG Best Practices

- **ViewBox**: Use `0 0 24 24` (standard) or `0 0 16 16` (compact)
- **Colors**: Use `currentColor` for CSS inheritance, avoid hardcoded colors
- **Accessibility**: Always include `<title>` element
- **Optimization**: Minimal path nodes, no embedded fonts or raster images
- **Sizing**: Design at 24px, test at 16px and 48px for clarity
- **Stroke**: Use `stroke-linecap="round"` and `stroke-linejoin="round"` for outlined styles

## Model

- **active session model**: SVG is XML text — generated in-model, no image API (do NOT route to Higgsfield)
- Text-only output (SVG is XML text) — no image generation API needed
- Supports structured output for consistent SVG formatting

## Workflow

1. Describe the icon ("settings gear")
2. Choose a style (outlined)
3. Write the .svg file
4. Optionally write variations
5. Multi-size export by `width`/`height` (16, 24, 32, 48)

## Setup

No API key and no install needed — SVG icons are written directly as text.

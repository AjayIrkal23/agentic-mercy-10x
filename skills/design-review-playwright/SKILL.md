---
name: design-review-playwright
description: Live visual QA against design specs using Playwright screenshots (adapted from GStack /design-review)
---

# Design Review with Playwright

Visual QA comparing implementation against design specs.

## Steps

1. **Screenshot** the implementation: `mcp__playwright__browser_take_screenshot`
2. **Compare** against design spec (Figma URL, mockup, or DESIGN.md)
3. **Check** spacing, typography, colors, alignment
4. **Responsive** — screenshot at 320px, 768px, 1440px
5. **Interactive states** — hover, focus, active, disabled
6. **Dark mode** if applicable

## Checklist

- [ ] Layout matches spec
- [ ] Typography (font, size, weight, line-height)
- [ ] Colors match design tokens
- [ ] Spacing follows 4/8dp rhythm
- [ ] Interactive states present
- [ ] Responsive at all breakpoints
- [ ] Accessibility (contrast, labels, keyboard)

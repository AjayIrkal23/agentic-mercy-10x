---
name: qa-playwright
description: "ALWAYS invoke for a systematic QA testing loop using Playwright MCP (adapted from GStack /qa)."
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 237
triggers:
  keywords:
  - adapted
  - gstack
  - loop
  - mcp
  - playwright
  - systematic
  - testing
  paths: []
  intents:
  - general
---
# QA with Playwright

Systematic QA loop: test → find bugs → fix → retest → commit.

## Steps

1. **Start dev server** if not running (`npm run dev` or `make run`)
2. **Navigate** to the feature: `mcp__playwright__browser_navigate`
3. **Snapshot** the page: `mcp__playwright__browser_snapshot`
4. **Test golden path** — click through primary user flow
5. **Test edge cases** — empty states, error states, boundary inputs
6. **Test responsive** — resize to 320px, 768px, 1440px: `mcp__playwright__browser_resize`
7. **Check console** for errors: `mcp__playwright__browser_console_messages`
8. **Screenshot** evidence: `mcp__playwright__browser_take_screenshot`

## Fix Loop

For each bug found:
1. Document: what happened vs expected
2. Fix the code
3. Retest the specific scenario
4. Screenshot the fix
5. Continue testing

## Completion

- All golden paths work
- No console errors
- Responsive at 3 breakpoints
- Screenshots captured as evidence

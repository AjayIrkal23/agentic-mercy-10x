---
name: canary-playwright
description: Post-deploy canary monitoring using Playwright MCP (adapted from GStack /canary)
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 170
triggers:
  keywords:
  - adapted
  - canary
  - gstack
  - mcp
  - monitoring
  - playwright
  - post-deploy
  paths: []
  intents:
  - general
---
# Canary Monitoring

Post-deploy health checks using Playwright.

## Steps

1. **Navigate** to production/staging URL: `mcp__playwright__browser_navigate`
2. **Health check** — verify page loads, no error screens
3. **Auth flow** — login if applicable, verify session works
4. **Critical paths** — test 2-3 most important user flows
5. **API health** — check network requests for errors: `mcp__playwright__browser_network_requests`
6. **Console** — check for new errors: `mcp__playwright__browser_console_messages`
7. **Screenshot** final state: `mcp__playwright__browser_take_screenshot`

## Report

Output: PASS/FAIL with evidence (screenshots, console errors, failed requests).

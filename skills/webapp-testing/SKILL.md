---
name: webapp-testing
description: Use when validating a local web UI in a browser with Playwright, capturing screenshots, or
  inspecting console and network behavior. Validate local web UIs with browser automation Use to reproduce
  or validate a local web UI with Playwright.
disable-model-invocation: true
schema: 1
category: testing
surfaces:
- backend
- frontend
platforms:
- linux
- darwin
- windows
token-cost: 554
triggers:
  keywords:
  - automation
  - behavior
  - browser
  - capturing
  - console
  - inspecting
  - local
  - network
  - playwright
  - reproduce
  - screenshots
  - testing
  - uis
  - validate
  - validating
  - web
  - webapp
  paths:
  - .spec.
  - .test.
  - __tests__
  - _test.ts
  - _test.tsx
  intents:
  - testing
---
# Webapp Testing

## Use When
- Reproducing frontend issues in a real browser.
- Validating local UI flows with Playwright.
- Capturing screenshots, console output, network observations, or rendered DOM state.

## Do Not Use
- Looking up Playwright or browser API syntax without docs verification.
- Replacing `debug-investigation` when the overall root cause is still unknown.
- Owning frontend architecture, styling direction, or backend contracts.

## Owns
- Browser-based UI reproduction and validation workflow.
- Safe local server lifecycle management for automation runs.
- Reconnaissance patterns for screenshots, console logs, network events, and DOM inspection.

## Does Not Own
- The source of truth for Playwright or library APIs.
- Product debugging strategy outside browser evidence gathering.
- Implementation policy for app code changes.

## Combine With
- `debug-investigation` when browser evidence is one part of a broader bug investigation.
- `code-execution-standard` when the task includes fixing the issue after reproducing it.
- `tool-and-doc-selection` when exact Playwright, browser, or test-runner syntax matters.

## Workflow
1. Confirm the workspace or environment already has the browser automation runtime you plan to use, then run `python3 scripts/with_server.py --help` before using the helper.
2. Start only the local services you need, and prefer explicit readiness checks such as `--ready-url`, locator waits, or app-specific assertions over blanket `networkidle`.
3. Keep Playwright scripts focused on browser actions and assertions while the helper owns startup and teardown.
4. Save screenshots and logs to workspace-safe temp locations such as `/tmp` or a task-specific scratch folder inside the current workspace.
5. Route Playwright or browser-automation API questions through `tool-and-doc-selection` and the docs skills instead of treating this skill as API documentation.

## Output Contract
- The local URLs or servers that were exercised and how readiness was verified.
- The browser evidence captured: screenshot paths, console output, network observations, or assertions.
- Any follow-up handoff to `debug-investigation`, `code-execution-standard`, or docs skills.

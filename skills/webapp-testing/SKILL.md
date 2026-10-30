---
name: webapp-testing
description: "End-to-end testing of a web app in a real browser — driving flows with Playwright, asserting UI, and capturing console/network/performance evidence and screenshots against real runtime data."
when_to_use: Use when writing or running .spec files, an e2e/ suite, or a Playwright config, or when a UI flow must be verified in a real browser.
paths:
  - "**/*.spec.{ts,tsx}"
  - "**/e2e/**"
  - "**/playwright.config.*"
metadata:
  schema: 1
  category: testing
  surfaces: [frontend, backend]
  platforms: [linux, darwin, windows]
  token-cost: 600
  triggers:
    keywords: [playwright, e2e, end-to-end, browser test, spec, screenshot, console errors, network requests, devtools, webapp testing, ui flow]
    paths: [.spec., .test., __tests__, /e2e/, playwright.config]
    intents: [testing]
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
1. Attach to the app the user is already running (standing rule: never start dev servers yourself). `scripts/with_server.py` exists for the one case where the user explicitly asks for an automated run that starts and stops its own server; a subagent never calls it.
2. Confirm the browser automation runtime you plan to use is already installed, and prefer explicit readiness checks such as `--ready-url`, locator waits, or app-specific assertions over blanket `networkidle`.
3. Keep Playwright scripts focused on browser actions and assertions; startup and teardown belong to the user (or to the helper, when the user asked for it).
4. Save screenshots and logs to workspace-safe temp locations such as `/tmp` or a task-specific scratch folder inside the current workspace.
5. Route Playwright or browser-automation API questions through `tool-and-doc-selection` and the docs skills instead of treating this skill as API documentation.

## Output Contract
- The local URLs or servers that were exercised and how readiness was verified.
- The browser evidence captured: screenshot paths, console output, network observations, or assertions.
- Any follow-up handoff to `debug-investigation`, `code-execution-standard`, or docs skills.

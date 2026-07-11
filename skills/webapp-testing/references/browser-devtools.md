# Browser testing with DevTools (MCP-backed)

> Absorbed into `webapp-testing`. This method now drives the **installed** `playwright` and `browser-tools` MCP servers, not the uninstalled chrome-devtools MCP.

## Runtime inspection loop
1. Navigate + snapshot: `mcp__playwright__browser_navigate`, `mcp__playwright__browser_snapshot`.
2. Console + network evidence: `mcp__browser-tools-mcp__getConsoleErrors`, `getNetworkErrors`, `getNetworkLogs`.
3. DOM + interaction: `mcp__playwright__browser_click/type/fill_form`, then re-snapshot to assert the change.
4. Visual proof: `mcp__playwright__browser_take_screenshot`.
5. Audits: `mcp__browser-tools-mcp__runAccessibilityAudit`, `runPerformanceAudit`, `runBestPracticesAudit`.

Capture DOM, console errors, network requests, performance, and visual output with real runtime data. The legacy chrome-devtools-MCP steps require an uninstalled server and are intentionally not used here.

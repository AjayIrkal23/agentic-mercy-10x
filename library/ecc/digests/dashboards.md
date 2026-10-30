---
name: ecc-digest-dashboards
description: ECC's inventory dashboards, a loopback web catalogue and a Tkinter GUI over ECC's own agents, skills, commands, MCP servers, rules and hooks; the reusable idea is a loopback-only bind enforced in code, with SSH port forwarding for remote viewing.
---
<!-- ecc-digest:dashboards@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Dashboards

## What it is
ECC ships two viewers for its own catalogue. `scripts/dashboard-web.js` (about 1,100 lines, most of it inline HTML and CSS) is a Node HTTP server on port 3456 that lists ECC's agents, skills, commands, MCP servers, rules and hooks with search and translations, and opens a browser when it starts. It binds to loopback only: a host override that is not a loopback address makes it throw at startup, it has no authentication by design, and its docs explain SSH port forwarding for viewing it from another machine. `ecc_dashboard.py` is a Tkinter desktop GUI over the same inventory, with a settings tab and an "open terminal" action; `scripts/lib/ecc_dashboard_runtime.py` holds its runtime helpers. The README's dashboard section introduces both, launched through npm scripts. The study note marks the web dashboard as not read line by line and the Tk GUI as thin.

## The reusable idea
For any local tool that serves a page: enforce the loopback bind in code rather than in documentation, and fail at startup when someone points it elsewhere; a page with no authentication is only safe when nothing but the local user can reach it. Pair that with a Host and Origin check (see the Plan Canvas digest) to stop DNS rebinding. When remote viewing is needed, document SSH port forwarding instead of adding a login form. Everything else here is an inventory viewer, which a static generated page does as well.

## Why not adopted
They catalogue ECC's own components, not the workbench's. The workbench already has `scripts/mcp_inventory.py`, the generated skills index and the doctor report for its inventory, and the library's own `INDEX.json` is the catalogue of what was vendored. Both viewers start a server or a GUI and open a browser, which the workbench rules forbid the agent to do on its own; the web one also needs the Node runtime and the GUI needs Tk.

## Upstream paths
- `README.md#dashboard-gui`
- `ecc_dashboard.py`
- `scripts/dashboard-web.js`
- `scripts/lib/ecc_dashboard_runtime.py`

---
name: ecc-digest-mcp-catalogue
description: ECC's MCP server catalogue (about 30 server entries with launch commands, env placeholders and descriptions) and its one-default-connector policy; the reusable idea is that a skill wrapping a CLI beats a default MCP, and every launcher must pin a version.
---
<!-- ecc-digest:mcp-catalogue@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# MCP catalogue

## What it is
`mcp-configs/mcp-servers.json` is a catalogue of MCP servers that ECC's installer copies to a target for a human to pick from; nothing in it is enabled automatically. Each entry has a command, arguments, optional environment placeholders and a description. At the vendored commit it lists around 30 servers, among them browser automation services, ClickHouse, several Cloudflare servers, CodeScene, Confluence, Jira, Context7, ECC's own memory vault, Exa and parallel web search, fal.ai, a filesystem server, Firecrawl, GitHub, Playwright, Railway and a few memory services. Most launchers are package-runner commands without a version, and secrets are placeholders like a "your token here" string. The README describes the policy around it: ECC ships one default connector, retired six former defaults after an audit, and offers an environment variable to disable listed servers.

## The reusable idea
Two policies are worth adopting as review rules. First, prefer a skill that wraps an existing CLI over a default MCP server: the CLI costs no context until the skill is used, while every enabled server puts its tool schemas into each session. Second, pin every launcher to an exact version (or a digest) and never ship a real credential in a catalogue; an unpinned package runner fetches whatever the registry serves at each session start, which is a supply-chain risk. A catalogue is fine as documentation as long as it is never installed verbatim.

## Why not adopted
The workbench manages its MCP roster through `installer/manifest.json`, the doctor's MCP roster check and `scripts/mcp_inventory.py`, and already runs most of the useful servers (GitHub, Playwright, Context7, memory, Firecrawl and others). Copying ECC's catalogue would bring unpinned launchers, which `scripts/validate_imports.py` flags as class V. The file is not vendored; this digest records the policy.

## Upstream paths
- `mcp-configs`

---
name: ecc-digest-agentshield
description: ECC AgentShield, an external scanner for agent configuration (CLAUDE.md, settings, MCP configs, hooks, agents, skills) with static rules, secret patterns and a grade; the reusable idea is treating the agent's own config as attack surface and scanning it read-only.
---
<!-- ecc-digest:agentshield@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# AgentShield

## What it is
AgentShield is a separate npm package from its own GitHub organisation; ECC wraps it. The `skills/security-scan` skill and `commands/security-scan.md` run it against an agent setup: CLAUDE.md files, settings, MCP server configs, hooks, agent definitions and skills. Per the security guide's AgentShield section (marked marketing-heavy and unverified by the study note), it applies about 100 static rules, checks 14 secret patterns, grades the setup from A to F, exits 2 on a critical finding, and has an optional mode that runs three model roles (attacker, defender, auditor) over the config. A fix mode rewrites the config. The README says there is no audited version pin, and the wrapper launches the package through npx.

## The reusable idea
An agent's configuration is code that runs with the user's privileges: hooks execute shell commands, MCP servers get network and file access, and skills and CLAUDE.md text steer the model. Scan it like code. The checks that matter: hook commands that fetch and execute remote content, MCP launchers without a pinned version, permissions that allow broad shell or network access, secrets pasted into settings or env blocks, and instruction files that tell the model to skip confirmation. Run the scan read-only and report; changing config should stay a human decision. Exit codes make it usable as a CI gate.

## Why not adopted
The scanner is an unpinned third-party package, its fix mode edits config without asking, and the user wants a question before changes. The workbench covers the same ground with code it controls: the doctor's settings-safety and MCP roster checks (`installer/doctor.py`), jcodemunch's agent-config audit, semgrep scans of security-sensitive files, `scripts/validate_imports.py` (unpinned launchers, secrets, personal paths) and the go-live secrets scan in `scripts/golive.py`. The checklist above is kept as reference for extending those checks.

## Upstream paths
- `commands/security-scan.md`
- `skills/security-scan`
- `the-security-guide.md#agentshield`

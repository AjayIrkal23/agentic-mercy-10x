---
name: ecc-digest-security-guide
description: ECC's security guide and tooling (threat model for agent setups, separate identities, supply-chain IOC scanner, advisory feeds, an opt-in third-party monitor); the reusable idea is the lethal-trifecta threat model and scoped, short-lived credentials per agent.
---
<!-- ecc-digest:security-guide@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Security guide

## What it is
`SECURITY.md` is ECC's disclosure policy and `docs/security` holds its security notes. The substance is in `the-security-guide.md`. Its threat model section names the lethal trifecta: an agent that holds private data, reads untrusted content and can talk to the outside world can be steered by prompt injection into leaking that data. It lists the attack surfaces of a coding agent (messages and attachments, PR and issue text, MCP servers, skills, persistent memory) and recaps known Claude Code issues (hooks running before trust was granted, a base-URL override that leaked credentials, MCP auto-approval). The separate-identities section argues for one scoped, short-lived token per agent or job instead of a shared personal token, so a compromised session can only reach what its token allows. The tooling side: `scripts/ci/scan-supply-chain-iocs.js` (about 850 lines) scans manifests, lockfiles, AI-tool configs and installed packages for known indicators of compromise, and `scripts/ci/supply-chain-advisory-sources.js` builds a refreshable report from advisory feeds over the network. `scripts/hooks/insaits-security-wrapper.js` and `insaits-security-monitor.py` bridge an opt-in third-party SDK that claims local detection of credential exposure and prompt injection; they are not registered by default.

## The reusable idea
Use the trifecta as a review question for every new tool or MCP server: does this session now combine private data, untrusted input and an outbound channel? If yes, remove one leg (no network, no secrets in the environment, or no untrusted input) rather than trusting a filter. Give each automated job its own narrowly scoped, expiring credential. Scan what the agent loads (skills, hooks, MCP configs, lockfiles) for known-bad indicators in CI, not only application code. The minimum-bar checklist in the guide ends with the gaps worth closing: egress deny for untrusted repos, a sandbox for code you did not write, and a kill switch for runaway sessions.

## Why not adopted
The workbench already has semgrep scans on security-sensitive files, `hooks/dangerous-bash-gate.py`, the import hygiene validator (`scripts/validate_imports.py`, whose secret patterns and sanitisation rules came from this guide) and the two-layer go-live secrets scan in `scripts/golive.py`. The IOC scanner and advisory feeds are Node scripts with network fetches, and the InsAIts monitor depends on an unverified third-party package; both stay out. The guide's ideas are kept here as reference.

## Upstream paths
- `SECURITY.md`
- `docs/security`
- `scripts/ci/scan-supply-chain-iocs.js`
- `scripts/ci/supply-chain-advisory-sources.js`
- `scripts/hooks/insaits-security-monitor.py`
- `scripts/hooks/insaits-security-wrapper.js`
- `the-security-guide.md#separate-identities`
- `the-security-guide.md#threat-model`

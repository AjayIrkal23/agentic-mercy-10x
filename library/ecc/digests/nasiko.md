---
name: ecc-digest-nasiko
description: ECC's lifecycle bridge for the experimental Nasiko CLI (status, consent-gated install and ownership-checked uninstall of a pinned release); the reusable idea is a safe template for adding any third-party binary with pinned digests and no latest.
---
<!-- ecc-digest:nasiko@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Nasiko

## What it is
Nasiko is an experimental external CLI that ECC can install and manage. `scripts/nasiko.js` exposes three verbs through the ECC command: `status --json` (read-only), `install --version <pinned> --dry-run` followed by the same command with `--yes`, and `uninstall --yes`. `scripts/lib/nasiko-release.js` knows the pinned release (v0.1.0 per the study note, which did not verify the pin), downloads the asset and checks its digest before extracting anything. The `skills/nasiko-control-plane` skill tells the agent how to drive these verbs, and its `agents/openai.yaml` file is display metadata (a name and a default prompt) for another vendor's UI, not an agent definition.

## The reusable idea
The lifecycle rules are a good template for any CLI a workbench installs on the user's behalf:
- status is always read-only and machine-readable, so the agent can check state without side effects;
- install takes an exact version, never `latest`, and verifies a pinned digest before extraction;
- install shows a dry run first and acts only with an explicit consent flag;
- the binary goes to a known managed location; the installer never searches PATH to decide what to touch and never runs a vendor bootstrap script;
- uninstall removes the binary only when the ledger says the installer placed it, so a user's own copy is never deleted;
- telemetry is opt-in and separate from install;
- any validation failure stops the run and is reported as a failure, never as partial success.

## Why not adopted
Nasiko itself has no use in this workbench. The pattern is already followed by `installer/` (pinned versions and SHA-256 checks in `installer/manifest.json`, downloads through `installer/safe_fetch.py`, the gitleaks install in `installer/basetools.py`), so the digest stays as a reference for the next tool added that way.

## Upstream paths
- `scripts/lib/nasiko-release.js`
- `scripts/nasiko.js`
- `skills/nasiko-control-plane`
- `skills/nasiko-control-plane/agents/openai.yaml`

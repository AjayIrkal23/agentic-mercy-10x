---
name: ecc-digest-install-system
description: ECC's installer and plugin packaging (profiles, modules, targets, install-state ledger, doctor/repair/uninstall); the reusable idea is an ownership ledger that never overwrites or deletes a file the installer did not place.
---
<!-- ecc-digest:install-system@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Install system

## What it is
ECC ships its content through a Node installer. `install.sh` and `install.ps1` are thin wrappers that run `scripts/install-apply.js`, which accepts a profile (`minimal`, `core`, `developer`, `security`, `research`, `full`), explicit modules, `--with`/`--without` component ids, `--dry-run` and `--json`. `scripts/install-plan.js` resolves a profile to modules to file operations without writing anything, and `scripts/install-guided.js` is the interactive front end. The engine under `scripts/lib/install` (about 7k lines per the study note) normalises the request, builds the plan and applies it through 16 harness adapters in `scripts/lib/install-targets`. The catalogue lives in `manifests/` (`install-modules.json` with 41 modules, `install-components.json` with about 130 user-facing ids, `install-profiles.json` with the profiles, plus `install-assets`). Every applied file is recorded in an install-state JSON per target (`scripts/lib/install-state.js`, mirrored into a SQLite store by `install-state-store-sync.js`), and `scripts/doctor.js`, `scripts/repair.js` and `scripts/uninstall.js` all read that ledger. The alternative route is the Claude plugin (`.claude-plugin`, `plugins`, `scripts/setup.js`, `scripts/lib/claude-plugin-setup.js`), which declares the whole skills and commands directories. `scripts/auto-update.js`, `scripts/catalog.js`, `scripts/list-installed.js` and the `skills/configure-ecc` skill sit on top.

## The reusable idea
Two mechanisms are worth rebuilding. First, the ownership guard plus ledger: before writing, the installer checks whether the destination exists and is recorded as its own; an unrecorded file is skipped with a warning, never overwritten or claimed. On removal it deletes only files that are in the ledger and whose digest still matches what it wrote, so a file the user edited survives an upgrade. Drift is then a simple report: ledger entries that are missing on disk or whose digest changed. Second, hook consent (`scripts/lib/install/hook-consent.js`): any plan that would install automatic hooks needs an explicit flag, and the installer lists the capability groups those hooks hold (source writes, command rewrites, LLM egress from transcripts, MCP network activity, permission gates) before asking. Smaller ideas: a pid lockfile with stale detection around settings merges, and `scripts/lib/path-safety.js`, which refuses writes that escape the trusted root through `..` or a symlink.

## Why not adopted
The workbench already installs itself through `installer/` (`render.py`, `doctor.py`, `selfheal`) from one git checkout, and the daily self-heal covers repair. Running ECC's installer against this tree would add `rules/ecc/`, flat skills and a second hook runtime that doubles `hooks/dispatch.py`; the Node runtime and 16 targets for other harnesses bring nothing to a single-harness setup, and the full profile would put about 311 skill descriptions into every session. The ledger idea is noted for a future `--check` drift report; the content itself is reachable through `library/` at zero always-on cost.

## Upstream paths
- `.claude-plugin`
- `README.md#claude-plugin`
- `README.md#install-system`
- `commands/auto-update.md`
- `commands/project-init.md`
- `docs/SELECTIVE-INSTALL-ARCHITECTURE.md`
- `install.ps1`
- `install.sh`
- `manifests`
- `manifests/install-assets`
- `manifests/install-components.json`
- `manifests/install-modules.json`
- `manifests/install-profiles.json`
- `plugins`
- `scripts/auto-update.js`
- `scripts/catalog.js`
- `scripts/doctor.js`
- `scripts/install-apply.js`
- `scripts/install-guided.js`
- `scripts/install-plan.js`
- `scripts/lib/claude-dry-run-sandbox.js`
- `scripts/lib/claude-plugin-setup.js`
- `scripts/lib/claude-scope-migration.js`
- `scripts/lib/install`
- `scripts/lib/install-executor.js`
- `scripts/lib/install-lifecycle.js`
- `scripts/lib/install-manifests.js`
- `scripts/lib/install-state-store-sync.js`
- `scripts/lib/install-state.js`
- `scripts/lib/install-targets`
- `scripts/lib/install/hook-consent.js`
- `scripts/lib/missing-dependency.js`
- `scripts/lib/path-safety.js`
- `scripts/lib/resolve-ecc-root.js`
- `scripts/list-installed.js`
- `scripts/repair.js`
- `scripts/setup.js`
- `scripts/uninstall.js`
- `skills/configure-ecc`

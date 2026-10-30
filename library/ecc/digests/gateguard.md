---
name: ecc-digest-gateguard
description: ECC GateGuard, a fact-forcing hook that denies the first edit of each file until the model answers a checklist; the reusable idea is a sensitive-target list (auth, payments, migrations, workflows, keys) that always asks before a write.
---
<!-- ecc-digest:gateguard@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# GateGuard

## What it is
GateGuard is ECC's write and shell gate. The hook `gateguard-fact-force.js` (about 2.6k lines, outside this digest's id list) runs on Edit, Write, MultiEdit, NotebookEdit, Bash and PowerShell. The first edit of each file in a session is denied with a checklist chosen by the target's class (instruction file, test, prose, config, code): who imports it, what public API changes, which call sites move, whether a duplicate already exists, what data schema is touched, and a quote of the user's instruction. After the model answers in prose and retries, the file key is recorded and the edit passes. Destructive shell commands and, in the standard profile, the first routine shell command of a session are gated the same way. The work is split across `scripts/lib/gateguard-*.js`: `target-class` classifies the path, `turn-scan` reads the transcript, `search-evidence` and `search-filters` give credit when a prior Read or Grep already covered the file, `change-profile`, `code-lexer` and `file-context` size the change, `readonly-shell` recognises harmless commands, `state` keeps the per-session record and `metrics` counts denials. `scripts/gateguard-report.js` summarises the metrics, `scripts/dev/gateguard-eval.js` and `gateguard-latency.js` are its evaluation and timing harnesses, and `docs/gateguard` holds the design notes.

## The reusable idea
The thesis in the source is that a model answers "are you sure" with yes, so the gate should demand facts instead of confirmation. The study note's verdict is that the real value is the investigation the question triggers, not the prose answer, which the model can invent. Two pieces are worth keeping. A sensitive-target list: paths under auth, security, payment, migrations, CI workflow files, `.env` files and key material always trigger the gate, whatever the importer count says. And prior-search credit: when the transcript already shows a read or search that covered the target, the gate stays quiet, so it adds friction only where nothing was checked.

## Why not adopted
The workbench covers the same ground with cheaper mechanisms: `hooks/gateguard-write-gate.py` (same name, different mechanism: a real importer scan and an ask prompt), `hooks/dangerous-bash-gate.py` for destructive commands, the jcodemunch read gate, and `check_edit_safe` / `get_blast_radius` before shared edits, all run through `hooks/dispatch.py`. Porting GateGuard means a Node runtime and about 6k lines of dependent libraries for a ritual whose evidence is model-written prose. The per-file deny costs a round trip for every new file, and the first-command-per-session deny works against the autonomy rule. The sensitive-target list is the one idea to fold into the existing write gate.

## Upstream paths
- `README.md#gateguard-and-ioc-scanner`
- `docs/gateguard`
- `scripts/dev`
- `scripts/dev/gateguard-eval.js`
- `scripts/dev/gateguard-latency.js`
- `scripts/gateguard-report.js`
- `scripts/lib/gateguard-change-profile.js`
- `scripts/lib/gateguard-code-lexer.js`
- `scripts/lib/gateguard-file-context.js`
- `scripts/lib/gateguard-metrics.js`
- `scripts/lib/gateguard-readonly-shell.js`
- `scripts/lib/gateguard-search-evidence.js`
- `scripts/lib/gateguard-search-filters.js`
- `scripts/lib/gateguard-state.js`
- `scripts/lib/gateguard-target-class.js`
- `scripts/lib/gateguard-turn-scan.js`

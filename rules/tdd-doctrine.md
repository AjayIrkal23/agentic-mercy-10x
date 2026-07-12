# TDD Doctrine — three layers, one discipline

> Always-on rule. Fuses the TDD **skills** with the **tdd-guard** write-time
> enforcer (auto-initialized, warn mode) and the **completion gates** into one
> system. Each layer covers a failure the others can't.

## The three layers

| Layer | Owns | Mechanism |
|-------|------|-----------|
| **1. KNOW-HOW** (skills) | *How* to do TDD well | `test-driven-development`, `tdd`, `golang-testing` (table-driven Go), `webapp-testing` — red→green→refactor mechanics |
| **2. ENFORCEMENT** (tdd-guard, **warn mode**) | *Flagging* test-skipping at write-time | PreToolUse hook (`tdd_guard_launcher.py` → `tdd-guard-gate.py`) flags impl-without-failing-test, over-implementation, and behavior-adding refactors as a **non-blocking advisory**. Auto-initialized per project. |
| **3. VERIFICATION** (gates) | *Proving* it passes at the end | `verification-loop`, `hard-completion-gate`, Karpathy "write the failing test, then make it pass" |

Skill = how. Guard = flag. Gate = verify.

## Warn mode (does NOT pause you)

`tdd-guard-gate.py` runs the real `tdd-guard` but **downgrades every block to an
advisory** — the agent sees `⚠️ TDD GUARD (advisory …)` and **proceeds**. It also
**scopes to the project**: edits to files OUTSIDE the active project root (e.g.
`~/.claude` infra) are never evaluated.

**Instruction for the agent:** a `⚠️ TDD GUARD` advisory is a directive, not noise.
On seeing one for real product code, STOP, write the failing test first
(`golang-testing` / `test-driven-development` skill), `make tdd`, then implement.
Do not ignore it just because it no longer blocks.

To make a project HARD-block instead of warn: route its launcher to `tdd-guard`
directly (remove the gate) — not recommended globally.

## Auto-init (you never hand-write a config)

`tdd-guard-init-guard.py` runs at SessionStart and on UserPromptSubmit (through the
`dispatch.py` session-start and user-prompt-submit chains) — exactly like the
jcodemunch/graphify index guards. It:

1. Detects stacks (go.mod → go; vitest/jest in package.json → js; pytest → py).
2. Writes `<project>/.claude/tdd-guard/data/config.json` with `guardEnabled` +
   `ignorePatterns` scoped to test-bearing code (exempts non-code, generated,
   vendor, mocks, migrations, cmd, test files, and sub-packages with no runner).
3. **DORMANT** (`guardEnabled:false`) until a real test runner exists; auto-flips
   ON when one appears.
4. **Keeps it updated**: re-fingerprints structure each session; regenerates only
   when files/folders changed, else silent.

**Ownership:** a config is auto-managed iff the sidecar `.autoinit.json`
(`autoManaged:true`) exists. A hand-written config with no sidecar is never
touched. Delete the sidecar to take manual control; set `guardEnabled:false` to
pause (auto re-enables on next structural change unless the sidecar is removed).

## Global install, per-project activation

The `tdd-guard` binary + the launcher are wired globally in `~/.claude`, but the
launcher is **gated**: it runs tdd-guard only when the repo has a config
(`guardEnabled` not false). Every other repo → instant allow, zero token cost.

## The loop in an active project (GO_UDP backend)

1. **RED** — write the failing test first (`golang-testing` skill: table-driven `_test.go`).
2. `cd UDP_PLATFORM/server && make tdd` → `go test -json | tdd-guard-go` writes `test.json` (red/green state).
3. **GREEN** — implement; the advisory clears once a failing test exists.
4. `make tdd` → green.
5. **REFACTOR** — `make lint` (golangci-lint) enforces the refactor phase.

GO_UDP scope: `server/internal/**` Go logic. Exempt: `client/**` (no suite yet),
cmd/generated/mocks/migrations, `*_test.go`, non-code.

## Frontend

`client/**` is exempt until a Vitest + Testing Library suite + `tdd-guard-vitest`
reporter exist; the auto-init flips it on automatically once `vitest` is in its
`package.json`.

Related: skills `test-driven-development`, `tdd`, `golang-testing`,
`webapp-testing`, `verification-loop`, `tdd-auto-init`; rule `tdd-autoinit.md`.

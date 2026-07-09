---
name: tdd-auto-init
description: Operate and customize the auto-initialized tdd-guard TDD system. Use when setting up TDD enforcement in a new repo, when tdd-guard isn't activating (or is firing where it shouldn't), when adding a test stack (Go/Vitest/Jest/pytest) and wiring its reporter, when a TDD advisory appears, or when pausing/forcing/troubleshooting tdd-guard. tdd-guard auto-initializes per project (like the jcodemunch/graphify index guards), runs in non-blocking WARN mode, and self-maintains its config as files/folders change — this skill is how you drive, scope, and debug that.
disable-model-invocation: false
---

# tdd-guard Auto-Init

tdd-guard is installed globally, **auto-initialized per project**, runs in
**warn mode** (advisory, never pauses), and **self-updates** as the repo changes.
You normally do nothing. This skill is for the cases where you do.

Authoritative model: rules `tdd-doctrine.md` + `tdd-autoinit.md`.

## Mental model (30 seconds)

- A repo becomes **active** when `.claude/tdd-guard/data/config.json` exists with
  `guardEnabled` not false. The init guard writes it automatically on session start
  / first prompt when it detects a test stack.
- On every Write/Edit, `tdd-guard-gate.py` runs tdd-guard, **downgrades any block to
  a `⚠️ TDD GUARD` advisory**, and **ignores files outside the project root**.
- A `⚠️ TDD GUARD` advisory is a directive: write the failing test first, then implement.

## Common tasks

**A TDD advisory appeared while I was coding.**
Don't ignore it. Invoke `golang-testing` (or `test-driven-development`), write the
failing test for that exact behavior, refresh state (`make tdd` for Go), then implement.

**Set up TDD in a brand-new repo.** Nothing to do — open it and prompt; the guard
auto-inits. It stays DORMANT until a test runner exists (go.mod, or vitest/jest in
package.json, or pytest), then auto-enables. To get red/green signal, wire the
reporter for that stack (below).

**Wire a reporter (required for the guard to see red/green):**
- Go: `go install github.com/nizos/tdd-guard/reporters/go/cmd/tdd-guard-go@latest`;
  run tests as `go test -json ./... 2>&1 | tdd-guard-go -project-root <abs-root>`
  (add a `make tdd` target).
- Vitest/Jest: `npm i -D tdd-guard-vitest` (or `-jest`) and register the reporter in
  the test config; then remove that surface from `ignorePatterns` (auto-init flips it
  on once `vitest`/`jest` is a dependency).
- pytest: `pip install tdd-guard-pytest`; configure the plugin.

**tdd-guard is firing where it shouldn't (wrong files).** It only validates files
INSIDE the project root and not matching `ignorePatterns`. Add a glob to
`ignorePatterns` in the repo's `config.json` (minimatch; patterns REPLACE defaults,
so keep the existing ones). If you hand-edit, also delete `.autoinit.json` to take
manual ownership (else the next structural change regenerates it).

**Pause enforcement for a repo.** Set `"guardEnabled": false` in its `config.json`.
(Auto re-enables on the next structural change unless you also delete `.autoinit.json`.)

**Force a fresh re-detect.** Delete the repo's `config.json` and trigger a prompt (or
start a new session). The guard regenerates a scoped config + sidecar.

**Make a repo HARD-block instead of warn** (maximum rigor, accept the pause): point its
launcher entry at `tdd-guard` directly instead of `tdd-guard-gate.py`. Not recommended
globally — warn mode + honoring advisories is the default robust posture.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No advisory ever appears | Repo DORMANT (no test runner) or no reporter wired → no red/green. Wire the reporter. |
| Advisory on non-app files | Add a glob to `ignorePatterns`; delete `.autoinit.json` to keep your edit. |
| Guard active in a repo you don't want | `guardEnabled:false` + delete `.autoinit.json`. |
| Validation feels slow | It's an SDK (Sonnet) call per in-scope edit. Lower to haiku via `TDD_GUARD_MODEL_VERSION` (less reliable) or exempt more paths. |

Reporters/config files live in `<project>/.claude/tdd-guard/data/`. Transient files
(`test.json`, `todos.json`, …) are gitignored; `config.json` + `.autoinit.json` are committed.

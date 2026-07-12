# tdd-guard Auto-Init — operational rule

> Always-on. The companion to `tdd-doctrine.md`: that file is the *why*; this is
> the *what-runs-when*. tdd-guard is auto-initialized and self-maintaining per
> project, like the jcodemunch/graphify index guards — you never hand-create a
> config.

## What runs, when

| Hook | Event | Mode | Does |
|------|-------|------|------|
| `tdd-guard-init-guard.py` | SessionStart (via the `dispatch.py` session-start chain) | `session` | full scan; (re)write config if structure fingerprint changed, else silent |
| `tdd-guard-init-guard.py` | UserPromptSubmit (via the `dispatch.py` user-prompt-submit chain) | `prompt` | if config missing → init; else no-op (cheap) |
| `tdd_guard_launcher.py` → `tdd-guard-gate.py` | PreToolUse `Write\|Edit\|MultiEdit\|TodoWrite` (dispatch pre-tool-use link) | — | runs tdd-guard in **warn mode**, scoped to the project; downgrades blocks to advisories; skips files outside the project root |

## Auto-detection → config

- **go.mod** present → Go enforced (`go test`). **vitest/jest** in a package.json
  → that JS surface enforced. **pytest** in pyproject/setup.cfg → Python enforced.
- `guardEnabled = (any runner found)`. No runner yet → **DORMANT** (`false`);
  auto-flips ON when a runner appears.
- `ignorePatterns` exempt: non-code, generated (`*.gen.go`,`*.pb.go`), vendor,
  node_modules, dist/build, mocks, migrations, **cmd**, test files themselves,
  and any sub-package with no unit-test runner (e.g. a Vitest-less frontend).
- Files **outside** the project root are never evaluated (the gate skips them).

## Ownership (never clobbers your hand edits)

- Auto-managed iff sidecar `.claude/tdd-guard/data/.autoinit.json` has
  `autoManaged:true` (+ a structure `fingerprint`).
- Config present but **no sidecar** → treated as MANUAL → the guard never rewrites it.
- **Take manual control:** delete `.autoinit.json`.
- **Pause a repo:** set `"guardEnabled": false` in its config (auto re-enables on the
  next structural change unless you also delete the sidecar).

## Files (committed vs ignored)

- Committed: `config.json`, `.autoinit.json` (so auto-management survives clones).
- Gitignored: `test.json`, `todos.json`, `modifications.json`, `lint.json` (transient).

## Force a refresh / new stack

- Force re-eval now: delete `config.json` then trigger any prompt (prompt-mode re-inits),
  or just start a new session (session-mode regenerates on fingerprint change).
- New stack needs a **reporter** for red/green state: Go `tdd-guard-go` (`make tdd`);
  JS `tdd-guard-vitest`/`-jest`; Python `tdd-guard-pytest`. Wire it once per stack.

See: skill `tdd-auto-init`, rule `tdd-doctrine.md`.

# Lifecycle (phases 0–7)

0. **Orient** — jcodemunch first; graphify when a graph exists; root `CLAUDE.md` → the
   target dir's `CLAUDE.md` (+ `CODEX.md`). Unclear spec → `ASSUMPTIONS I'M MAKING:`.
1. **Plan** (>2 files or a new domain) — 3–5 sharpening questions, vertical slices, a
   "Not doing" list, approval before code; save `plan-YYYY-MM-DD-<slug>.md` at the repo
   root. Non-interactive (`/invoke`, subagents): no approval stop.
2. **Implement** — TDD (`test-driven-development`): failing test → minimal code →
   refactor. Touch only what was asked; never rename fields or keys unasked.
3. **Surface rules** — `rules/frontend.md` / `rules/backend.md` load with their files.
4. **Dead-code audit of YOUR diff** (`dead-code-and-change-audit`); pre-existing dead code:
   report, never drive-by delete.
5. **Lint / format / tests / security** — from the package root; semgrep on auth, input
   or API changes.
6. **Review** — Santa Method (`santa-reviewer`) for 3+ changed files; confirmed findings
   only. Could the change be half as long?
7. **Docs** — repo docs, then the local `CLAUDE.md` of every changed dir (`dox-doc-tree`).
   ADR only when hard to reverse + surprising + a real trade-off.

`/invoke <acts...> [-- task]`: one specialist per act, closers after code-mutating acts,
artifacts in `.claude/runs/<ts>-<slug>/`; a router WORKFLOW line → run that saved workflow.

## Stop gates (`hard-completion-gate`)

Gate 2 docs (only with `server_docs/` / `frontend_docs/`), Gate 3 security (semgrep),
Gate 4 Santa (3+ files), Gate 5 dead-code (3+ files). Each Stop gate blocks at most once
per human turn: satisfy it or state why it does not apply. `blocking-doc-enforcer` blocks
`git commit` without doc updates when the repo has doc trees.

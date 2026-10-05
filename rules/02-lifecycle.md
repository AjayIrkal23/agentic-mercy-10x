# Lifecycle (phases 0–7)

One line each. FE/BE specifics load by path; skill bodies load on demand.

0. **Orient** — jcodemunch first (`assemble_task_context` / `get_repo_map`); graphify
   when a graph exists; read the repo's root `CLAUDE.md` → the target dir's `CLAUDE.md`,
   and `CODEX.md` if present. Surface `ASSUMPTIONS I'M MAKING:` when the spec is unclear.
1. **Plan** (anything >2 files or a new domain) — interactive: 3–5 sharpening questions,
   vertical slices, a "Not doing" list, approval before code. Save
   `plan-YYYY-MM-DD-<slug>.md` at the repo root and in `docs/superpowers/plans/`.
   Non-interactive (`/invoke`, subagents): plan artifact, no approval stop. Skills:
   `workflow-orchestrator` → `plan-mode-gate` → `superpowers:writing-plans` /
   `architect-system-design`.
2. **Implement** — TDD: failing test → minimal code → refactor
   (`test-driven-development`; Go: `golang-testing`). Touch only what was asked; never
   rename existing fields or keys unasked; the simplest thing that works.
3. **Surface rules** — `rules/frontend.md` / `rules/backend.md` load when their files are
   touched; the write-time reminder adds the canonical FE/BE skill set.
4. **Dead-code audit of YOUR diff** — `dead-code-and-change-audit`: orphaned imports,
   exports, routes, state you introduced. Pre-existing dead code: report, never
   drive-by delete.
5. **Lint / format / tests / security** — run from the package root;
   `mcp__semgrep__semgrep_scan` when auth, input handling, or API files changed.
6. **Review** — Santa Method (`santa-reviewer` agent, or `/invoke review`) for 3+
   changed files: BREAKER + SIMPLIFIER + VERIFIER, confirmed findings only. Karpathy
   check: could the change be half as long? does every line trace to the request?
7. **Docs** — `update-docs` for repo docs, then the local `CLAUDE.md` of every directory
   you changed (`dox-doc-tree`). ADR only when hard to reverse + surprising + a real
   trade-off.

## `/invoke`

`/invoke <acts...> [-- task]` runs one specialist per act in canonical order: audit spec
plan debug test impl refactor design clean security review docs verify. Closers (clean,
review, docs, verify; security when sensitive paths changed) run after code-mutating acts
and never duplicate an explicit act.
Artifacts land in `.claude/runs/<ts>-<slug>/`. Models come from `hooks/model-policy.json`.

## Stop gates (`hard-completion-gate`)

Gate 2 docs (hard, only when the repo has `server_docs/` / `frontend_docs/`), Gate 3
security (semgrep on security-sensitive files), Gate 4 Santa (3+ files), Gate 5
dead-code (3+ files). Each Stop gate (this one, `invoke-suite-gate`, the mercy verify
gate) blocks at most once per human turn: satisfy it or state why it does not apply,
then it passes. `blocking-doc-enforcer` blocks `git commit` without doc
updates when the repo has doc trees.

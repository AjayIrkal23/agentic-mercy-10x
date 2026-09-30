# Agents — routing, models, teams

Subagent definitions live here as `<name>.md` (YAML frontmatter + body). Claude Code
loads them natively; `/invoke <acts>` (skill `invoke`) dispatches them per act, and the
prompt router suggests one per prompt. 18 agents: 17 specialists + `team-lead`.

## Routing table

| Agent | Act / trigger | Model | Effort | Writes | Preload |
|---|---|---|---|---|---|
| `audit-specialist` | AUDIT — tech-debt, hotspots, dead code, repo health | sonnet | high | report only | 3 |
| `spec-architect` | SPEC — requirements, typed contracts, Not-Doing | opus | high | report only | 3 |
| `planning-director` | PLAN — dependency-ordered tasks, complete code per step | opus | high | report only | 4 |
| `debug-detective` | DEBUG — unknown-cause failures; ROOTCAUSE.md | opus | xhigh | instrumentation + 1-file fix | 4 |
| `test-author` | TEST — failing tests first (RED) | sonnet | high | test files | 3 |
| `implementation-engineer` | IMPL fallback — infra, scripts, hooks, ambiguous surface | sonnet ↑ | high | code | 8 |
| `backend-implementor-specialist` | IMPL backend — contract-first; publishes CONTRACT | sonnet ↑ | high | code | 13 |
| `frontend-implementor-specialist` | IMPL frontend — builds against CONTRACT; Higgsfield assets | sonnet ↑ | high | code | 13 |
| `integrator-specialist` | IMPL mixed closer — parity diff, wiring fixes, E2E proof | sonnet ↑ | high | small wiring fixes | 4 |
| `refactor-specialist` | REFACTOR — behavior-preserving, in its own worktree | sonnet ↑ | high | code (worktree) | 4 |
| `frontend-uiux-designer` | DESIGN — any "how it looks/feels" task; anti-slop + assets | opus | xhigh | code + assets | 9 |
| `deadcode-reaper` | CLEAN — removes only what this diff orphaned | sonnet | medium | removals + lint | 3 |
| `security-sentinel` | SECURITY — semgrep + OWASP; PASS/BLOCK (Gate 3) | sonnet | high | report only | 2 |
| `santa-reviewer` | REVIEW — BREAKER/SIMPLIFIER/VERIFIER (Gate 4) | opus | xhigh | report only | 2 |
| `docs-sync-agent` | DOCS — diff → docs ledger, dox tree, ADR test (Gate 2) | sonnet | medium | docs only, background | 2 |
| `qa-verifier` | VERIFY — evidence before assertions | sonnet | medium | report only | 2 |
| `memory-codex` | manual — append one dated CODEX.md entry | sonnet | medium | CODEX.md only | 0 |
| `team-lead` | teams — fullstack BE↔FE contract handoff, requested squads | opus | high | run.json only | 2 |

↑ = escalates to Opus on a failed previous attempt or large unplanned work (`escalation`
in `hooks/model-policy.json`).

Canonical `/invoke` order: audit spec plan debug test impl refactor design clean security
review docs verify. Closers (clean, security, review, docs, verify) run only after
code-mutating acts.

## Plain delegation vs teams

- **Plain delegation (default):** `Agent(subagent_type, description: "…")` with **no
  `model`** (opus-guard sets it and the `[label]`) and **no `name`**. The agent file's `model`, `effort`, `tools`,
  `disallowedTools`, `skills`, `memory`, `mcpServers` all apply.
- **Team (deliberate):** only when teammates must message each other — fullstack
  `/invoke impl` (impl-be publishes the CONTRACT → SendMessage → impl-fe builds →
  integrator diffs and bounces by name) or a parallel squad the user asks for. Passing
  `name` launches a *teammate*, which honours `tools`/`model` but **not** `skills:` or
  `mcpServers`; the lead tells each teammate its two baseline skills to `Skill()` first
  and registers `expected_artifacts` in `run.json` so the `TeammateIdle` gate keeps it
  working until the artifact exists. Pattern: `team-lead.md`.

## Model and effort

- Sonnet 5.5 executes, Opus 5.5 judges. Default subagent model is Sonnet
  (`env.CLAUDE_CODE_SUBAGENT_MODEL=sonnet`); every agent file pins its own `model:`
  (opus for the 6 judges: santa, uiux, plan, spec, debug, team-lead) so routing holds
  even if hooks fail. `opus-guard` sets `model` + `[label]` and escalates executors;
  precedence lives in `rules/04-model-routing.md`, pins in `hooks/model-policy.json`.
- Effort comes only from each agent's `effort:` (xhigh santa/debug/uiux; high executors
  and the other judges; medium docs/clean/qa/memory). `max` is banned. Claude Code reads
  no subagent-effort env var, so built-ins run at its own default.
- Fable is never automatic — only when the user asks for it on that turn.

## Skill preload (`skills:`)

Each agent's `skills:` list is preloaded in full at start (no manual `Read` of
SKILL.md files; canonical names only, aliases collapsed, ≤13). Bodies say
"Preloaded skills (frontmatter `skills:`); use `Skill(...)` for anything else."
Path-bound FE/BE standards also surface natively when matching files are read.
`hooks/gen-agent-skill-blocks.py` holds the table: run it to rewrite every agent's
`skills:` line, `--check` exits 1 on any drift (installer verify, WP-13). It also
prints `drift:` when a preloaded skill is unknown to the routing config.

## Least privilege

Read-only roles (`audit-specialist`, `spec-architect`, `planning-director`,
`santa-reviewer`, `security-sentinel`, `qa-verifier`) carry
`disallowedTools: Edit, NotebookEdit, Agent` — `Write` stays for their single report.
Every specialist disallows `Agent` (no recursive fan-out). `memory-codex` has an
explicit `tools:` allowlist. `memory: user` on santa/security/audit/debug keeps
false-positive lists, noise triage, metric snapshots, and killed hypotheses across runs.

## Removed (2026-09-27)

Four `figma-*` agents (need a Figma MCP that is not available on this Linux setup),
three `vercel-*` agents (never used, stale model ids), and all `*.bak*` files. No agent
depends on them; git history keeps the bodies.

# Agents — routing, models, teams

Subagent definitions live here as `<name>.md` (YAML frontmatter + body). Claude Code
loads them natively; `/invoke <acts>` (skill `invoke`) dispatches them per act, and the
prompt router suggests one per prompt. 17 agents, plus `team-lead.md`: the team playbook the
MAIN session follows (no frontmatter, so it is not a spawnable agent).
Frontmatter carries `maxTurns` on every agent and `omitClaudeMd: true` only on memory-codex
(the SubagentStart hook gives it a dox read line instead). Since 2026-10-31 (audit C-06)
qa-verifier and deadcode-reaper load `CLAUDE.md`, and no agent sets `autoCompactWindow`
(they inherit the session's window). Descriptions stay at or under 1,200 chars with one example
each (`tests/test_agent_frontmatter.py`).

## Routing table

| Agent | Act / trigger | Model | Effort | maxTurns | Writes | Preload |
|---|---|---|---|---|---|---|
| `audit-specialist` | AUDIT — tech-debt, hotspots, dead code, repo health | opus | high | 60 | report only | 3 |
| `spec-architect` | SPEC — requirements, typed contracts, Not-Doing | opus | high | 60 | report only | 3 |
| `planning-director` | PLAN — dependency-ordered tasks, complete code per step | opus | high | 60 | report only | 4 |
| `debug-detective` | DEBUG — unknown-cause failures; ROOTCAUSE.md | opus | xhigh | 80 | instrumentation + 1-file fix | 3 |
| `test-author` | TEST — failing tests first (RED) | opus | high | 40 | test files | 2 |
| `implementation-engineer` | IMPL fallback — infra, scripts, hooks, ambiguous surface | opus | high | 60 | code | 7 |
| `backend-implementor-specialist` | IMPL backend — contract-first; publishes CONTRACT | opus | high | 60 | code | 8 |
| `frontend-implementor-specialist` | IMPL frontend — builds against CONTRACT; Higgsfield assets | opus | high | 60 | code | 9 |
| `integrator-specialist` | IMPL mixed closer — parity diff, wiring fixes, E2E proof on a running app | opus | high | 40 | small wiring fixes | 4 |
| `refactor-specialist` | REFACTOR — behavior-preserving, in the main working tree | opus | high | 40 | code | 4 |
| `frontend-uiux-designer` | DESIGN — any "how it looks/feels" task; anti-slop + assets | opus | xhigh | 60 | code + assets | 3 |
| `deadcode-reaper` | CLEAN — removes only what this diff orphaned | sonnet | medium | 30 | removals + lint | 3 |
| `security-sentinel` | SECURITY — semgrep + OWASP; PASS/BLOCK (Gate 3) | opus | high | 50 | report only | 2 |
| `santa-reviewer` | REVIEW — BREAKER/SIMPLIFIER/VERIFIER (Gate 4) | opus | xhigh | 80 | report only | 2 |
| `docs-sync-agent` | DOCS — diff → docs ledger, dox tree, ADR test (Gate 2) | sonnet | medium | 30 | docs only, background | 2 |
| `qa-verifier` | VERIFY — evidence before assertions | opus | medium | 60 | report only | 2 |
| `memory-codex` | manual — append one dated CODEX.md entry | sonnet | medium | 10 | CODEX.md only | 0 |

Model = `tiers.max20` in `hooks/model-policy.json` (since 2026-10-31: Sonnet floor, Opus for
executors, tests and verify); other plan tiers below. On pro/max5/api executors escalate one
tier on a failed previous attempt or large unplanned work (`escalate` in the tier block). Caps are the `turn_caps.agents` table of `hooks/model-policy.json`
(frontmatter must equal it; every agentType a saved workflow calls must meet
`turn_caps.schema_floor[role]`). The SubagentStart block tells each agent its cap and its
deliver-by turn (cap minus `report_reserve`, 6); report-writing agents follow the
Turn budget section of their body: artifact created early, appended as results are
confirmed, finalized COMPLETE or `INCOMPLETE: <uncovered>` before the reserve, then
StructuredOutput / the final message.

Canonical `/invoke` order: audit spec plan debug test impl refactor design clean security
review docs verify. Closers (clean, security, review, docs, verify) run only after
code-mutating acts.

## Plan tiers

Truth is `model-policy.json` `tiers` (R3.3); details in `docs/MODEL-ROUTING.md`.

| Role | pro | max5 / api | max20 |
|---|---|---|---|
| explore / docs / cleanup | haiku | haiku | sonnet |
| verify | haiku | haiku | opus |
| test | haiku; sonnet on escalation | sonnet | opus |
| impl | haiku; sonnet on escalation | sonnet (haiku with a plan marker and size <= M) | opus |
| integrate / security | haiku; sonnet on escalation | sonnet | opus |
| judges | sonnet | sonnet; opus only with the user's phrase that turn | opus |
| main session | sonnet | sonnet | opus |
| ceiling | sonnet | opus, by request | fable, by request only |
| `fallbackModel` | haiku | haiku | sonnet, haiku |

Usage guard: above 80 % of the five-hour limit, executors step down one tier and judges
sit one tier above them.

## Plain delegation vs teams

- **Plain delegation (default):** `Agent(subagent_type, description: "…")` with **no
  `model`** (opus-guard sets it and the `[label]`) and **no `name`**. The agent file's `model`, `effort`, `tools`,
  `disallowedTools`, `skills`, `memory`, `mcpServers`, `maxTurns` all apply.
- **Team (deliberate):** only when teammates must message each other — fullstack
  `/invoke impl` (impl-be publishes the CONTRACT → SendMessage → impl-fe builds →
  integrator diffs and bounces by name) or a parallel squad the user asks for. The MAIN
  session is the lead (a subagent cannot spawn teammates). Passing `name` launches a
  *teammate*, which honours `tools`/`model` but **not** `skills:` or `mcpServers`; the
  lead tells each teammate its two baseline skills to `Skill()` first and registers
  `expected_artifacts` in `run.json` so the `TeammateIdle` gate keeps it working until
  the artifact exists. No teams → the same agents run sequentially. Playbook:
  `team-lead.md`; the one `run.json` schema lives in `skills/invoke/SKILL.md` §2.

## Model and effort

- Haiku is the default worker; the tier picks the rest. Every agent file pins its own
  `model:` (the max20 column) so routing holds even if hooks fail; `opus-guard` sets
  `model` + `[label]` per tier, escalates executors and caps every result at the tier's
  ceiling. An explicit `model` moves a judge or an executor only when the user's own turn
  names the model. Precedence lives in `rules/04-model-routing.md`, the matrix in
  `hooks/model-policy.json`.
- Effort comes only from each agent's `effort:` (xhigh santa/debug/uiux; high executors
  and the other judges; medium docs/clean/qa/memory). `max` is banned. Claude Code reads
  no subagent-effort env var, so built-ins run at its own default.
- Fable is never automatic — only when the user asks for it on that turn.

## Skill preload (`skills:`)

Each agent's `skills:` list is preloaded in full at start (no manual `Read` of
SKILL.md files; canonical names only, aliases collapsed, ≤13). It holds only what every
spawn needs; stack- and task-specific skills load on demand with `Skill()`, and
`hooks/tests/test_agents_wp5.py` caps the weight per spawn (20k tokens, uiux 45k since it
preloads the design trio `impeccable`, `ui-ux-pro-max`, `hallmark`, which its pipeline T1-T7 runs
on every task, 2026-11-03). Bodies say
"Preloaded skills (frontmatter `skills:`); use `Skill(...)` for anything else."
Path-bound FE/BE standards also surface natively when matching files are read.
A `paths:`-scoped skill in `skills:` is silently NOT preloaded (Claude Code lists it only
after a matching file is read), so the generator also writes a `<!-- path-skills -->`
block into the body naming those SKILL.md files to Read first.
`hooks/gen-agent-skill-blocks.py` holds the table: run it to rewrite every agent's
`skills:` line and path-skills block, `--check` exits 1 on any drift (installer verify,
WP-13). It also prints `drift:` when a preloaded skill is unknown to the routing config.
Boilerplate (write protocol, no commits, no servers, MCP-first) is not restated per body:
it comes from the SubagentStart block. The 250-line cap is a body rule: each executor's
OUTPUT CONTRACT (refactor-specialist: its hard constraints) states it; BE/FE implementors
also get it from the preloaded `*-standards-always-follow` skills.

## Act pipelines (automatic tool calls, 2026-11-03)

Every act agent carries one `## <act> pipeline (automatic, every task)` table: ordered steps
(`P1..Pn`; the designer's `T1..T7`), each an exact MCP call, `Skill("…")`, `Read ~/.claude/skills/…`
or vendored script, run by the agent itself on every task. The artifact gets `## Pipeline`: each
call and its result, or `P<n> skipped: <reason>` (no running app, no files of that kind, a runtime
missing; nothing is installed to make a step run). Interactive skills are adapted where they sit:
`grill-with-docs` is answered from code and docs, `finding-duplicate-functions` runs without
subagents. `hooks/pipeline-evidence-gate.py` (SubagentStop) keeps an act agent working once when its
run.json artifact lacks `## Pipeline`; `hooks/tests/test_act_pipelines.py` checks every table names
tools that exist. Change a pipeline in the agent body; the test keeps the shape.

## Least privilege

Read-only roles (`audit-specialist`, `spec-architect`, `planning-director`,
`santa-reviewer`, `security-sentinel`, `qa-verifier`) carry
`disallowedTools: Edit, NotebookEdit, Agent` — `Write` stays for their single report.
Every specialist disallows `Agent` (no recursive fan-out). `memory-codex` has an
explicit `tools:` allowlist. `memory: local` on santa/security/audit/debug keeps
false-positive lists, noise triage, metric snapshots, and killed hypotheses per repo
(`.claude/agent-memory-local/`, never committed: debug-detective adds the `.gitignore`
line with Edit when missing; santa/security/audit cannot edit, so they check it and
report `memory not gitignored` in their artifact instead of writing), so one
stack's "safe" never mutes a real finding in another. Scoping (ECC subagent-scoping):
one job per agent, the narrowest tool list that does it, a turn cap, and a single
artifact as the hand-off.

## ECC equivalents

ECC (@25278e7d) agents that merged into a local agent instead of landing as a second one:

| ECC agent | local agent | what came across |
|---|---|---|
| `architect` | `spec-architect` | duplicate role |
| `planner` | `planning-director` | duplicate role |
| `doc-updater` | `docs-sync-agent` | duplicate role |
| `e2e-runner` | `qa-verifier` | duplicate role |
| `refactor-cleaner` | `deadcode-reaper` | duplicate role |
| `security-reviewer` | `security-sentinel` | duplicate role |
| `tdd-guide` | `test-author` | duplicate role |
| `code-reviewer` (+ review-pr, rules/common/code-review) | `santa-reviewer` | pre-report gate, confidence floor, severity table, false-positive list |
| `build-error-resolver` (+ build-fix) | `implementation-engineer` | build-resolver discipline |
| `team-agent-orchestration` / `parallel-execution-optimizer` | `team-lead.md` | delegation completion contract, cascade |
| `subagent-scoping` (the-shortform-guide) | this README | Least privilege paragraph |

## Removed (2026-09-27)

Four `figma-*` agents (need a Figma MCP that is not available on this Linux setup),
three `vercel-*` agents (never used, stale model ids), and all `*.bak*` files. No agent
depends on them; git history keeps the bodies.

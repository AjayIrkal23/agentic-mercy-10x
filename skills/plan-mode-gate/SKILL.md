---
name: plan-mode-gate
description: Mandatory pre-flight gate for ALL planning and implementation work. Enforces superpowers
  discipline, jcodemunch codebase analysis, sequential thinking decomposition, and Context7 documentation
  lookup before any code changes. Use before EnterPlanMode, before writing any plan, and before direct
  implementation. This skill governs both Plan Mode and Code Mode.
version: 1.0.0
schema: 1
category: planning
surfaces:
- planning
platforms:
- linux
- darwin
- windows
token-cost: 2898
triggers:
  keywords:
  - analysis
  - both
  - changes
  - code
  - codebase
  - context7
  - decomposition
  - direct
  - discipline
  - documentation
  - enforces
  - enterplanmode
  - gate
  - governs
  - implementation
  - jcodemunch
  - lookup
  - mandatory
  - mode
  - plan
  - planning
  - pre-flight
  - sequential
  - skill
  - superpowers
  - thinking
  - work
  - writing
  paths: []
  intents:
  - planning
license: MIT
metadata:
  author: rohithambar
  tags:
  - planning
  - implementation
  - gate
  - superpowers
  - jcodemunch
  - context7
  - sequential-thinking
---
# Plan Mode & Code Mode Gate

<RIGID-SKILL>
This is a **rigid skill**. Follow it exactly. Do not adapt away from the discipline.
Skipping any gate produces incomplete plans, incorrect implementations, and wasted effort.
</RIGID-SKILL>

## Cursor adaptation (local port)

- **Canonical first router:** read **`workflow-orchestrator`** before this gate so lifecycle routing stays single-source.
- **jcodemunch / blast-radius:** MANDATORY-first for all code work per `~/.claude/rules/codebase-intel-first.md` — run the jcodemunch symbol index + graphify graph BEFORE reading/grepping. Use the MCP tools (plan_turn / assemble_task_context / get_blast_radius), then Superpowers discipline.
- **Automation:** a **`sessionStart`** hook injects a short reminder via **`~/.claude/hooks/session-plan-gate-hint.py`**. For manual JSON from the repo root: `node ~/.claude/skills/plan-mode-gate/scripts/plan-mode-check.js`. Optional post-edit reminder (not wired to Cursor **`preToolUse`** by default): `node ~/.claude/skills/plan-mode-gate/scripts/code-mode-check.js`.

## Purpose

Every task — whether planned or implemented directly — requires proper context gathering, problem decomposition, and skill discipline. This gate ensures you:
1. Consult ALL relevant skills before acting
2. Understand the codebase end-to-end before planning
3. Decompose complex problems before solving
4. Verify external library assumptions before using them

## When to Apply

**MUST apply when:**
- `EnterPlanMode` is about to be called
- User asks to "create", "build", "implement", "fix", "refactor", "add", "modify", "optimize", "polish"
- Any task touching >2 files
- Any task involving external libraries or frameworks
- Any task requiring understanding existing code patterns
- Any bug fix or debugging session

**ALSO apply when:**
- User asks a question that requires codebase exploration
- User requests code review or audit
- User asks "how should I..." about architecture or design

**SKIP only when:**
- Pure conversation with no action (answering a conceptual question)
- Administrative tasks (checking status, listing files)
- Reading a single known file with no analysis required

When in doubt: **APPLY**.

## Universal Pre-Flight Gate

Before ANY planning or implementation, announce:

```text
PLAN_GATE: superpowers=[pass|skip:<reason>] jcodemunch=[pass|skip:<reason>] sequential=[pass|skip:<reason>] context7=[pass|skip:<reason>] mutation=open|blocked
```

You may NOT proceed to `mutation=open` until all required gates pass.

---

## Gate 1: Superpowers Discipline (`using-superpowers`)

**ALWAYS PASS FIRST.**

Before exploring, planning, or implementing:

1. **Read `using-superpowers` skill** to refresh discipline
2. **Scan user request for skill triggers:**
   - "design", "UI", "UX", "component", "page" → `frontend-design-gate`, `ui-ux-pro-max`, `impeccable`
   - "test", "tdd", "coverage" → `tdd-workflow`, `test-driven-development`
   - "bug", "fix", "error", "failure" → `systematic-debugging`
   - "plan", "architecture", "design doc" → `brainstorming`, `writing-plans`
   - "refactor", "clean up" → `refactoring-patterns`, `code-review`
   - "deploy", "CI/CD" → `deployment-patterns`
   - "security", "auth", "XSS" → `security-review`
3. **Invoke ALL matching skills BEFORE any action**
4. **Process skills first** (brainstorming, debugging, writing-plans), then domain skills

**Skip only if:** The task is a single-file read with no implementation.

---

## Gate 2: Codebase Intelligence (jcodemunch)

**REQUIRED when repo is indexed or indexable.**

Before planning or implementing:

1. **Check if repo is indexed:**
   - Run `list_repos` or `resolve_repo(path=<cwd>)`
   - If not indexed → `index_folder(path=<cwd>)`

2. **Get planning context:**
   - Run `plan_turn(query=<user task>)` → get confidence + recommended symbols/files
   - Run `assemble_task_context(task=<user task>)` → auto-extract best-fit context
   - Run `get_repo_health` → understand codebase state (hotspots, dead code, complexity)

3. **If modifying existing code:**
   - Run `get_blast_radius(symbol=<target symbol>)` → find all affected files
   - Run `get_impact_preview(symbol_id=<target symbol>)` → understand downstream effects

4. **Document findings in your plan or reasoning**

**Skip only if:** The task creates a brand-new file with zero interaction with existing code.

---

## Gate 3: Problem Decomposition (`sequentialthinking`)

**REQUIRED for tasks with:**
- >3 subsystems or components
- >5 files touched
- Unclear requirements
- Architecture decisions needed
- Complex debugging scenarios

Use `sequentialthinking` tool:
- **Minimum thoughts:** 5
- **Maximum thoughts:** Scale to complexity (up to 20 for very complex tasks)
- **Must include:** Hypothesis generation + verification
- **Must include:** Branching or revision if initial hypothesis fails
- **Output:** Clear decomposition into independent sub-tasks

**When to use:**
- New feature with multiple moving parts
- Refactoring that crosses module boundaries
- Bug with unclear root cause
- Performance optimization requiring trade-off analysis
- Integration with external systems

**Skip only if:** The task is a trivial, isolated change (e.g., fix a typo, change a constant, add a single prop).

---

## Gate 4: Documentation Lookup (Context7)

**REQUIRED when task involves external libraries or frameworks.**

Before using any external library API:

1. **Identify libraries** from:
   - `package.json` dependencies
   - Import statements in relevant files
   - User mentions of specific libraries

2. **Resolve library IDs:**
   - Run `resolve-library-id(libraryName=<name>, query=<task>)`
   - Select best match based on source reputation and benchmark score

3. **Query documentation:**
   - Run `query-docs(libraryId=<id>, query=<specific question>)`
   - Query for: API patterns, configuration options, examples, best practices
   - Query for: version-specific behavior (check if API changed)

4. **Document findings** in your plan or reasoning

**Skip only if:** The task uses only standard language features with no external libraries.

---

## Plan Mode Workflow (EnterPlanMode → ExitPlanMode)

When `EnterPlanMode` is called, follow this exact sequence:

### Step 1: Universal Pre-Flight Gates
Complete Gates 1–4 above. Announce PLAN_GATE status.

### Step 2: Brainstorming (if creative work)
If the task involves creating NEW features, components, UI, or behavior:
- **Invoke `brainstorming` skill**
- Explore project context first
- Ask clarifying questions ONE AT A TIME
- Propose 2-3 approaches with trade-offs
- Present design sections and get user approval
- Write design doc to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- **HARD GATE:** Do NOT proceed to planning until user approves design

### Step 3: Systematic Debugging (if bug fix)
If the task involves fixing a bug or unexpected behavior:
- **Invoke `systematic-debugging` skill**
- Complete Phase 1: Root Cause Investigation BEFORE proposing fixes
- Reproduce consistently, check recent changes, gather evidence
- **HARD GATE:** Do NOT propose fixes until root cause is identified

### Step 4: Plan Writing (`writing-plans`)
Only after all gates pass and design is approved:
- **Invoke `writing-plans` skill**
- Map file structure before defining tasks
- Each step = one action (2-5 minutes)
- Exact file paths, complete code, exact commands
- No placeholders ("TBD", "implement later", "add validation")
- Self-review: spec coverage, placeholder scan, type consistency
- **Visualize the plan**: invoke `claude-mermaid:mermaid-diagrams` (plugin) to render the phase flow and dependency graph with `mermaid_preview`. Embed the diagram (or its `mermaid_save` path) into the plan file before exiting plan mode. Required for any plan with >2 phases or cross-surface dependencies.
- Save plan to **two locations** (both are mandatory):
  1. **Project root (primary):** `plan-YYYY-MM-DD-<feature-name>.md` at the repo/project root (e.g., `plan-2026-05-15-feature-name.md`) — committed with the project
  2. **Docs directory (secondary):** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` — existing convention, kept as archive copy
  - Use the same `<feature-name>` slug in both paths (kebab-case, 2–5 words)

### Step 5: Execution Handoff
- Offer execution choice: subagent-driven vs inline
- If subagent-driven → `subagent-driven-development`
- If inline → `executing-plans`
- If multi-phase → reference `strategic-compact` for compaction points

### Step 6: ExitPlanMode
- Present plan to user
- Wait for approval before executing

---

## Code Mode Workflow (Direct Implementation)

When user asks for direct implementation (no EnterPlanMode):

### Step 1: Universal Pre-Flight Gates
Complete Gates 1–4 above. Announce PLAN_GATE status.

### Step 2: Skill-Specific Execution
Follow the skills identified in Gate 1:
- Frontend work → `frontend-design-gate` + design skills
- Backend work → `backend-patterns` + relevant domain skills
- Bug fix → `systematic-debugging` (root cause first)
- Testing → `tdd-workflow` or `test-driven-development`

### Step 3: Tracking
- Use `TodoWrite` to track progress
- Run verifications after each step
- Stop when blocked, don't guess

### Step 4: Completion
- Run `verification-before-completion` or `verification-loop`
- Use `finishing-a-development-branch` if applicable

---

## Anti-Patterns (STOP — You Are Rationalizing)

| Thought | Reality |
|---------|---------|
| "I'll explore first, then check skills" | Skills tell you HOW to explore. Check first. |
| "This repo is small, I don't need jcodemunch" | Even small repos have hidden dependencies. Index and query. |
| "I know this library already" | Context7 has the latest docs. Verify assumptions. |
| "Sequential thinking is too slow" | Shallow thinking produces broken plans. Spend time upfront. |
| "The user is in a hurry, skip planning" | Rushed plans guarantee rework. Gates exist to prevent this. |
| "I already brainstormed in my head" | Brainstorming skill has structured design doc requirements. Use it. |
| "jcodemunch tools are extra tokens" | Understanding codebase saves more tokens than fixing wrong assumptions. |
| "I'll just read the main file quickly" | `assemble_task_context` gives you the BEST context, not just the obvious files. |
| "Context7 is overkill for React" | React hooks behavior changes between versions. Verify. |
| "This is a simple question, no gate needed" | Questions about code require codebase context. Run the gate. |

---

## Skill Priority During Planning

When multiple skills apply, use this order:

1. **plan-mode-gate** (this skill) — Always first
2. **using-superpowers** — Skill discipline
3. **Process skills** — How to approach (brainstorming, systematic-debugging, writing-plans)
4. **`claude-mermaid:mermaid-diagrams`** (plugin) — Visualize the plan. Render the phase / dependency / architecture diagram for any plan that touches multiple surfaces or >2 phases. Plugin path: `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`.
5. **Domain skills** — What to build (frontend-design-gate, backend-patterns, tdd-workflow)
6. **Execution skills** — How to execute (executing-plans, subagent-driven-development)
7. **Finishing skills** — How to complete (finishing-a-development-branch, verification-before-completion)

## Integration with frontend-design-gate

If the task involves frontend/UI work:
1. Complete `plan-mode-gate` first (this skill)
2. Then follow `frontend-design-gate` for design-specific workflow
3. The two gates are complementary: `plan-mode-gate` ensures proper planning process; `frontend-design-gate` ensures proper design skills

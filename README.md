<div align="center">

# ⚡ agentic-mercy-10x

### The agentic-dev environment that refuses to vibe-code.

*One `git clone` turns a stock Claude Code install into a disciplined engineering team that **plans before it codes, routes work to the right specialist, enforces standards at write-time, and proves it's done before it says so.***

<br/>

<img src="assets/hero.webp" alt="agentic-mercy-10x — an orchestrated AI development pipeline turning raw code into verified software" width="100%">

<br/><br/>

![Skills](https://img.shields.io/badge/skills-200%2B-6E56CF?style=for-the-badge)
![Hooks](https://img.shields.io/badge/hooks-70%2B-0EA5E9?style=for-the-badge)
![Commands](https://img.shields.io/badge/%2Finvoke_commands-139-F59E0B?style=for-the-badge)
![Specialists](https://img.shields.io/badge/specialist_agents-9-EC4899?style=for-the-badge)

![Built for Claude Code](https://img.shields.io/badge/built_for-Claude_Code-D97757?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Ubuntu%20%C2%B7%20Windows-E95420?style=flat-square)
![One-command install](https://img.shields.io/badge/install-one_command-22C55E?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-000000?style=flat-square)

<br/>

**[The Problem](#-the-problem-nobody-fixed) · [On Enter](#-what-actually-happens-when-you-hit-enter) · [One Prompt's Journey](#-the-journey-of-a-single-prompt) · [8 Superpowers](#-eight-superpowers-200-skills) · [Token Economy](#-the-token-economy) · [Structured Forever](#-your-codebase-stays-structured--forever) · [Install](#-install)**

</div>

---

## 🩸 The problem nobody fixed

AI coding agents are brilliant and **undisciplined**. Left alone, the same failures repeat on every task:

<div align="center">

| 😖 Stock agent | ⚡ agentic-mercy-10x |
|---|---|
| Forgets your standards halfway through | **Injects the right standard on every write** |
| Reads whole files, burns tokens, still misses the caller | **Symbol index + dependency graph answer in one call** |
| Codes first, understands never | **Gate: no code until it has a plan** |
| "Done!" — it wasn't tested | **Runs the real flow, captures real output** |
| Leaves dead code and rotted docs behind | **Sweeps orphans + syncs docs, every time** |
| Ships the SQL-injection you didn't see | **Semgrep + OWASP gate says BLOCK** |
| Burns premium-model $ on a one-line fix | **Routes each subagent to the cheapest capable model** |

</div>

> [!WARNING]
> **This is opinionated on purpose.** The hooks enforce *real* gates — TDD advisories, a per-directory documentation tree, dead-code sweeps, security scans, skill-routing, and model-routing. It will nudge (and sometimes block) you toward one way of working. That is the whole point. Skim [What the hooks enforce](#-what-the-hooks-enforce) before installing so nothing surprises you.

---

## 🎬 What actually happens when you hit Enter

Every task runs the same disciplined spine — **understand → build → auto-close → prove** — with gates that don't let sloppiness through. This is the full lifecycle, from the moment you open a project to the moment the agent is *allowed* to say "done":

```mermaid
flowchart TD
    A(["🖥️  cd project && claude"]):::start --> S0

    subgraph S0["①  SESSION START · hooks fire before you type a word"]
      B["🧠 Symbol index + dep-graph refreshed<br/>🗂️ Memory + CODEX working-log loaded<br/>📚 dox doc-tree root verified<br/>🧾 Skill manifest primed · ponytail + caveman on"]:::hook
    end

    S0 --> P(["⌨️  Your prompt"]):::start

    subgraph S1["②  UNDERSTAND"]
      AU["🔬 <b>AUDIT</b><br/>hotspots · coupling · churn · dead code<br/><i>cited findings, never vibes</i>"]:::agent
      SP["📐 <b>SPEC</b><br/>typed contracts · acceptance criteria<br/><i>+ an explicit Not-Doing list</i>"]:::agent
      PL["🗺️ <b>PLAN</b><br/>dependency-ordered · exact file paths<br/><i>a TDD cycle per task</i>"]:::agent
    end

    P --> AU --> SP --> PL

    subgraph S2["③  BUILD"]
      IM["⚙️ <b>IMPLEMENT</b><br/>task-by-task · test-first · atomic commits"]:::agent
      DB["🐞 <b>DEBUG</b><br/>reproduce → demonstrate root cause → minimal fix"]:::agent
    end

    PL --> IM
    IM -->|"tests red / bug"| DB
    DB -->|"root cause + fix"| IM

    subgraph S3["④  AUTO-CLOSE · runs every time, no exceptions"]
      CL["🧹 <b>CLEAN</b><br/>removes only what <i>this</i> diff orphaned"]:::agent
      DX["📖 <b>DOCS</b><br/>syncs docs + the per-dir CLAUDE.md tree"]:::agent
      VF["✅ <b>VERIFY</b><br/>runs the real flow · captures real output"]:::agent
    end

    IM --> CL --> DX --> VF

    subgraph GATES["🚧  STOP-GATES · the session cannot end until…"]
      G["Docs synced ✔   Security scanned ✔   Review passed ✔"]:::gate
    end

    VF --> G --> DONE(["🎉  Done — with evidence, not assertions"]):::done

    classDef start fill:#6E56CF,stroke:#4B3B9C,color:#fff,font-weight:bold
    classDef hook fill:#0EA5E9,stroke:#0369A1,color:#fff
    classDef agent fill:#1E293B,stroke:#6E56CF,color:#E2E8F0
    classDef gate fill:#F59E0B,stroke:#B45309,color:#1E293B,font-weight:bold
    classDef done fill:#22C55E,stroke:#15803D,color:#052e16,font-weight:bold
```

**The magic:** you don't invoke those stages by hand. The command name composes them — `/invoke-audit-spec-plan-impl-clean` runs the whole spine; `/invoke-debug` runs one act. **139 commands, generated from a single config**, cover every combination you'd ever want.

---

## 🧭 The journey of a single prompt

Zoom into *one* prompt. Here is literally every checkpoint it passes — from the shell to the final answer — and the invisible hook layer working the whole time so you don't have to:

```mermaid
sequenceDiagram
    autonumber
    participant You
    participant CC as Claude Code
    participant Hooks as Hook Layer
    participant Mesh as Agent Mesh

    You->>CC: cd project && claude
    CC->>Hooks: SessionStart
    Hooks-->>Mesh: index fresh · memory loaded · dox checked · ponytail+caveman armed
    Note over Hooks,Mesh: 🩹 kills "cold-start amnesia" — the agent boots knowing your codebase

    You->>CC: "add bulk CSV import"
    CC->>Hooks: UserPromptSubmit
    Hooks-->>Mesh: sequential-thinking mandate · intel-first · skill reminders
    Note over Hooks,Mesh: 🩹 kills "leap before you look" — reasoning is forced to the surface

    Mesh->>Hooks: EnterPlanMode
    Hooks-->>Mesh: PLAN_GATE — jcodemunch + context7 + decomposition required
    Note over Hooks,Mesh: 🩹 kills "code-first" — no mutation without a checked plan

    Mesh->>Hooks: Write / Edit  (PreToolUse)
    Hooks-->>Mesh: model routing · dox gate · TDD guard · fe/be skills injected
    Note over Hooks,Mesh: 🩹 kills "forgot the standard" + "premium-model waste"

    Hooks->>Hooks: PostToolUse — dead-code audit · doc enforcer · dox scaffold
    Note over Hooks: 🩹 kills "rot accumulates silently"

    Mesh->>CC: "done"
    CC->>Hooks: Stop
    Hooks-->>You: gates → docs ✔ · security ✔ · review ✔ · then allowed to finish
    Note over Hooks,You: 🩹 kills "it's done (it wasn't)"
```

Nothing above is something you have to remember. **The hooks remember for you.**

---

## 🦸 Eight superpowers, 200+ skills

Every skill in this workspace exists to give a developer one of eight superpowers. This is the full roster — **not a teaser, the actual inventory** — of what 10x's your day:

<div align="center">
<img src="assets/superpowers-grid.webp" alt="Eight developer superpowers: Analyze, Organize, Execute, Test, Secure, Learn, Create, Design" width="100%">
</div>

<br/>

### 🔬 ① ANALYZE — see the whole codebase in one call

> *The agent stops reading files blindly and starts querying a pre-built index. This is where the token savings come from.*

| Skill / tool | What it 10x's |
|---|---|
| `codebase-intel-first` | Doctrine: build a structural model **before** reading a single line |
| `jcodemunch-token-saver` | Symbol index — find a function, its callers, its blast radius in **one call**, not 20 file reads |
| `graphify` | Dependency graph — "who depends on X?", "how do A and B connect?" answered instantly |
| `project-structure-map` | Instant layer-boundary + impacted-files map for an unfamiliar repo |
| `project-reference-linkage` | The cross-module wiring map (component ↔ hook ↔ api ↔ controller ↔ route ↔ schema ↔ slice) |
| `iterative-retrieval` | Progressively refine context instead of dumping the whole tree |
| `lean-ctx` | Compressed I/O · 10 read modes · re-reads a file in **~13 tokens** |
| `caveman` | Output compression — **~75% fewer tokens**, full technical accuracy |
| `mcp-usage-standards` · `tool-and-doc-selection` | Pick the right source of truth, skip the wasteful search |

### 🗂️ ② ORGANIZE — a codebase that stays clean forever

> *Structure is enforced, not hoped for. New code lands in the right place with the right shape, every time.*

| Skill | What it 10x's |
|---|---|
| `frontend-structure-standards` · `frontend-standards-always-follow` | Domain-first folders, type ownership, 250-line file ceiling |
| `backend-standards-always-follow` · `service-layer-standards` · `backend-api-standards` | Route → controller → service → schema boundaries that never blur |
| `scaffold-standards` · `domain-scaffold-patterns` | New domain? Get the exact file tree before any logic is written |
| `api-contract-standards` · `api-and-interface-design` | Stable envelopes + typed contracts across the FE/BE seam |
| `architect-system-design` | Build-ready decomposition specs for new systems |
| `golang-patterns` · `react-hooks-patterns` · `postgres-patterns` · `vite-react-best-practices` · `tailwind-design-system` | Idiomatic, per-stack patterns baked in |
| `dead-code-and-change-audit` | Continuous hygiene — no orphaned imports, stale refs, or half-refactors survive |
| `code-simplification` · `improve-codebase-architecture` · `ponytail:ponytail-audit` | Actively shrink complexity instead of accreting it |

### 🗺️ ③ EXECUTE — never vibe-code again

> *No mutation without a plan. Reasoning is externalized, scope is questioned, work is sliced.*

| Skill | What it 10x's |
|---|---|
| `plan-mode-gate` · `workflow-orchestrator` · `plan-exec-stack-guide` | Hard pre-flight: no code until there's a checked plan |
| `spec-driven-development` · `planning-and-task-breakdown` · `writing-plans` | Turn a vague idea into ordered, testable tasks |
| `source-driven-development` | Every decision grounded in official docs, not stale memory |
| `sequential-thinking` (doctrine) | Externalize **all** reasoning — plan, audit, debug, decide |
| `ponytail` | The laziest solution that actually works — kills over-engineering at the source |
| `doubt-driven-development` | Adversarial self-review before a confident answer stands |
| `incremental-implementation` · `subagent-driven-development` · `dispatching-parallel-agents` · `using-git-worktrees` | Ship in safe slices, fan out independent work |

### 🧪 ④ TEST — prove it works, don't claim it

> *Evidence before assertions. Tests come first; "done" is earned, not announced.*

| Skill | What it 10x's |
|---|---|
| `test-driven-development` · `tdd` · `golang-testing` | Red → green → refactor; table-driven Go tests |
| `webapp-testing` · `browser-testing-with-devtools` | Real-browser DOM, console, network, and visual checks |
| `verification-loop` · `verification-before-completion` · `eval-harness` | A finish line you have to actually cross |
| `code-review-and-quality` · `frontend-code-review` · `backend-code-review` | Multi-axis review before merge |
| `systematic-debugging` · `debug-investigation` · `diagnose` | Reproduce → root cause → minimal fix (no fix before cause) |
| `fix-lint-format` | Green CI before you commit |

### 🛡️ ⑤ SECURE — ship without holes

> *Auth, input, and API changes get scanned automatically — a BLOCK verdict stops the session.*

| Skill / agent | What it 10x's |
|---|---|
| `owasp-security` · `security-and-hardening` | OWASP Top 10 (2025), ASVS, LLM/agentic threats baked into review |
| `security-sentinel` (agent) | Semgrep + OWASP pass on the diff → **BLOCK / PASS** |
| `backend-error-handling` | Safe logging, redaction, client-safe error mapping |

### 📖 ⑥ LEARN — never forget, never re-derive

> *Cross-session memory + a documentation tree that can't fall out of date.*

| Skill / system | What it 10x's |
|---|---|
| `memory` (MCP) + memory protocol | Patterns, decisions, and fragile-area gotchas persist across sessions |
| `dox-doc-tree` | A `CLAUDE.md` + `AGENTS.md` in **every** directory — read root→target before editing |
| `update-docs` · `documentation-and-adrs` | Docs + ADRs synced to the change, Gate-enforced |
| `CODEX.md` | A living working-decision log the whole team can read |
| `codebase-start-point-guide` | Deterministic onboarding flow into any repo |

### 🎼 ⑦ CREATE — a whole team of specialists in a box

> *Nine specialist agents + 139 `/invoke` commands + forensic X-ray vision over your git history.*

| Skill / agent | What it 10x's |
|---|---|
| 9 `/invoke` specialists + 139 commands | Audit · spec · plan · implement · debug · clean · docs · verify — composed on demand |
| `forensic-hotspot-finder` · `forensic-change-coupling` | Which files cause the most bugs; what secretly changes together |
| `forensic-complexity-trends` · `forensic-debt-quantification` | Is quality improving? What does the debt cost in **dollars**? |
| `tech-debt-audit` | Whole-repo, file-cited debt report with severity + effort |
| `workflow-orchestrator` | Routes multi-surface work across Architect / Code / Debug modes |

### 🎨 ⑧ DESIGN — UI that doesn't look AI-generated

> *A six-skill anti-slop design stack on top of a real asset-generation engine — the images in this very README were generated by it.*

| Skill / engine | What it 10x's |
|---|---|
| `impeccable` · `taste-skill` · `ui-ux-pro-max` · `huashu-design` | Anti-slop craft: tokens, typography, hierarchy, motion |
| `frontend-ui-engineering` · `design-extract` · `frontend-design` | Production UIs; extract a design system from any live URL |
| **Higgsfield** asset engine | Bespoke image / video / 3D / audio — real assets, never placeholders |

---

## 🧠 Always-fresh code intelligence

Every superpower above rests on one foundation: the agent **never works blind**. The moment a session starts, a guard checks that the repo's **symbol index** (jcodemunch) and **dependency graph** (graphify) are fresh — and silently re-indexes only what changed. No manual step, no stale map.

<div align="center">
<img src="assets/auto-index.webp" alt="Source code auto-scanned into a symbol index and a dependency graph, re-indexed automatically at session start" width="100%">
</div>

<br/>

| Layer | What it builds | What the agent asks it |
|---|---|---|
| **Symbol index** (`jcodemunch`) | Every function, class, type, caller, and reference — pre-parsed | *"Where is `X`? Who calls it? What's the blast radius if I change it?"* |
| **Dependency graph** (`graphify`) | The whole module wiring as a queryable graph | *"Who depends on `X`? How do `A` and `B` connect? What are the god-nodes?"* |
| **Freshness guards** (hooks) | A SessionStart check that re-indexes only the delta | *nothing — it just stays current, automatically* |

**Why it matters:** a stock agent re-derives structure with grep on *every* task and still misses cross-module edges. Here it's a one-call lookup against an always-current map — which is exactly where the token savings below come from.

---

## 🧭 The agent always knows where to look

Point a stock agent at an unfamiliar repo and it wanders — opening files, guessing, backtracking. This workspace gives it a **GPS**: `codebase-start-point-guide` sets the entry point, and `project-reference-linkage` + `project-structure-map` trace the exact vertical slice a change touches, so it walks straight to the right files and skips the rest.

<div align="center">
<img src="assets/codebase-navigation.webp" alt="An AI agent following a highlighted route from a start point straight to the exact target files, guided by project linkages" width="100%">
</div>

<br/>

The linkage map keeps the full slice traceable end to end — touch one node and the agent already knows every other node in the chain:

```mermaid
flowchart LR
    C["🧩 component"]:::fe --> H["🪝 hook"]:::fe --> A["🌐 api client"]:::fe
    A --> RT["🛣️ route"]:::be --> CT["🎛️ controller"]:::be --> SV["⚙️ service"]:::be
    SV --> SC["📐 schema"]:::be --> MD["🗄️ model"]:::be
    H -.->|"UI state"| ST["🗃️ store / slice"]:::fe

    classDef fe fill:#0EA5E9,stroke:#0369A1,color:#fff
    classDef be fill:#6E56CF,stroke:#4B3B9C,color:#fff
```

- `codebase-start-point-guide` — the deterministic "where do I begin" flow for any repo.
- `project-structure-map` — instant layer boundaries + likely-impacted files.
- `project-reference-linkage` — the cross-module wiring above, so nothing downstream is missed.

---

## 💰 The token economy

Here is the part that pays for itself. A stock agent answers a question by **reading files** — it grep-scans, opens a dozen, and drowns its own context. This workspace answers the same question by **querying a pre-built symbol index and dependency graph**, then compresses everything that flows through. The result is dramatic:

<div align="center">
<img src="assets/token-economics.webp" alt="Reading the entire codebase vs a surgical symbol lookup — 95% less token volume, 75% less processing" width="100%">
</div>

```mermaid
xychart-beta
    title "Tokens spent per task — stock agent vs agentic-mercy-10x (illustrative)"
    x-axis ["Find callers", "Grok a module", "Re-read a file", "Explain change"]
    y-axis "Tokens" 0 --> 80000
    bar [45000, 80000, 3000, 1200]
    bar [1500, 6000, 13, 300]
```

<div align="center"><i>Left/back bar = stock agent · front bar = this workspace. Illustrative estimates from each skill's stated savings.</i></div>

<br/>

| Everyday task | 🐌 Stock agent | ⚡ agentic-mercy-10x | Saved |
|---|---:|---:|---:|
| "Who calls `processPayment`?" | grep + read ~15 files ≈ **45k tok** | `find_references` ≈ **1.5k tok** | **~97%** |
| "Understand this module before editing" | read the whole dir ≈ **80k tok** | `assemble_task_context` ≈ **6k tok** | **~92%** |
| "Re-read a file after an edit" | full re-read ≈ **3k tok** | `lean-ctx` diff ≈ **13 tok** | **~99%** |
| "Explain the change you made" *(output)* | verbose prose ≈ **1.2k tok** | `caveman` ≈ **300 tok** | **~75%** |

**Fewer tokens is not just cheaper — it's *smarter*.** Every token you *don't* waste on a blind file dump is a token of context left for actual reasoning. This is why the workspace stays sharp on large repos where a naive agent chokes.

> Numbers above are illustrative estimates drawn from each skill's own stated savings (`jcodemunch-token-saver` ≈ 95% on retrieval, `caveman` ≈ 75% on output, `lean-ctx` ≈ 13-token re-reads). Your mileage varies with repo size — the *shape* of the win does not.

---

## 🗂️ Your codebase stays structured — forever

Left unattended, an AI agent turns any codebase into spaghetti — files wherever, types inline, dead code everywhere. This workspace makes structure **non-optional**: every new domain lands in a known shape, every layer boundary is enforced, and the cross-module wiring is mapped before anything is touched.

<div align="center">
<img src="assets/codebase-structure.webp" alt="Before: tangled spaghetti code. After: clean domain-organized architecture" width="100%">
</div>

<br/>

### The standards, made visual

Four always-on skill sets decide *where every file goes and what shape it takes* — so the structure above is what you get by default, not what you hope for:

<table>
<tr>
<td width="50%"><img src="assets/standards-frontend.webp" alt="Frontend standards — domain-first folders, type ownership, 250-line file ceiling"><br/><b>Frontend</b> — <code>frontend-structure-standards</code> · <code>frontend-standards-always-follow</code>: domain-first folders, central type ownership, a hard 250-line file ceiling.</td>
<td width="50%"><img src="assets/standards-backend.webp" alt="Backend layering — route, controller, service, schema, model"><br/><b>Backend</b> — <code>backend-standards-always-follow</code> · <code>service-layer-standards</code> · <code>backend-api-standards</code>: route → controller → service → schema → model boundaries that never blur.</td>
</tr>
<tr>
<td width="50%"><img src="assets/scaffold-standards.webp" alt="Scaffold standards — a new domain materializes the exact file tree"><br/><b>Scaffold</b> — <code>scaffold-standards</code> · <code>domain-scaffold-patterns</code>: a new domain emits its exact file tree, validated against real Fastify/TS, FastAPI/Python, and Go/chi codebases.</td>
<td width="50%"><img src="assets/api-contract.webp" alt="API contract bridging frontend and backend with a typed stable envelope"><br/><b>Contract</b> — <code>api-contract-standards</code> · <code>api-and-interface-design</code>: one typed, stable envelope across the FE/BE seam — no parallel shapes.</td>
</tr>
</table>

Three enforcement layers keep it that way, permanently:

- **At scaffold time** — `scaffold-standards` + `domain-scaffold-patterns` emit the exact file tree (validated against real production codebases: Fastify/TS, FastAPI/Python, Go/chi).
- **At write time** — structure skills are injected on every edit; the 250-line file ceiling and layer boundaries are checked.
- **At close time** — `dead-code-and-change-audit` sweeps orphans and the `dox` tree drops a `CLAUDE.md` into any directory you touched.

---

## 🛡️ Every step kills a real problem

This is the part that matters. Each layer of the workspace exists to permanently retire one failure mode of agentic development:

<div align="center">

| The agent used to… | …now it *structurally can't*, because | Layer |
|---|---|---|
| 🧠 Forget your standards mid-task | **200+ skills injected path-ranked on every write** (`fe_*` / `be_*` routing) | Enforcement |
| 🔦 Read whole files & burn tokens | **`codebase-intel-first`** steers to a symbol index + dep graph; **lean-ctx** compresses I/O | Doctrine + MCP |
| 🏃 Code before understanding | **plan-mode gate** + **spec-before-code** | Enforcement + Specialists |
| 🧪 Skip tests | **TDD guard** flags implementation written before a failing test | Enforcement |
| ☠️ Leave dead code behind | **`deadcode-reaper`** removes only what *your* diff orphaned — delete-safe | Specialists |
| 📉 Let docs rot | **dox tree** + **`docs-sync-agent`** update every directory you touch | Enforcement + Specialists |
| 🕳️ Ship security holes | **`security-sentinel`** — semgrep + OWASP → **BLOCK / PASS** | Specialists |
| 🤥 Lie about "done" | **`qa-verifier`** — real run, real output, **evidence-before-assertion** | Specialists |
| 💸 Burn premium-model $ on trivial work | **model routing** → cheapest capable model per subagent | Enforcement |
| 🎈 Over-engineer & bloat | **ponytail** — the laziest solution that actually works | Doctrine |
| 📜 Drown you in prose | **caveman** — ~75% fewer tokens, full technical accuracy | Doctrine |
| 🔁 Re-derive structure every session | **jcodemunch index + graphify graph** kept fresh by guards | MCP + Enforcement |
| 🌫️ Reason invisibly | **sequential-thinking mandate** externalizes every non-trivial decision | Doctrine |
| 🫥 Forget across sessions | **memory MCP** + **CODEX.md** working log | Doctrine + MCP |

</div>

---

## 🎼 One command, a whole team

Type `/invoke-audit-spec-plan-impl-design` and a **whole cross-functional team wakes up in order** — an auditor, an architect, a planner, an engineer, a designer — each a clean-context specialist, each handing its artifact to the next. And you often don't even type it: a plain-English prompt like *"fix this bug and clean up"* is **auto-classified by keywords** and the matching chain fires on its own.

<div align="center">
<img src="assets/invoke-team.webp" alt="One /invoke command igniting a chain of specialist agents — audit, spec, plan, implement, design, clean, docs, verify — also auto-triggered by keywords" width="100%">
</div>

<br/>

Under the hood, every one of the 139 commands runs the same **three acts**. That uniformity is why they compose so cleanly:

```mermaid
flowchart LR
    subgraph ACT1["🎬 ACT 1 · INTEL"]
      direction TB
      I["Symbol index<br/>+ dependency graph<br/>➜ a codebase brief"]:::a1
    end
    subgraph ACT2["🎬 ACT 2 · DISPATCH"]
      direction TB
      D["audit · spec · plan<br/>impl · debug · design<br/>➜ in dependency order"]:::a2
    end
    subgraph ACT3["🎬 ACT 3 · AUTO-CLOSE"]
      direction TB
      C["clean · docs · verify<br/>➜ then stop-gates"]:::a3
    end
    I ==> D ==> C

    classDef a1 fill:#0EA5E9,stroke:#0369A1,color:#fff
    classDef a2 fill:#6E56CF,stroke:#4B3B9C,color:#fff
    classDef a3 fill:#22C55E,stroke:#15803D,color:#052e16
```

```
ACT 1  Intel      → build a codebase brief (symbol index + dependency graph)
ACT 2  Dispatch   → hand the brief to one or more specialist agents, in order
ACT 3  Auto-close → dead-code sweep · doc sync · verification · stop-gates
```

Pick the acts you need and the command name writes itself: `/invoke-spec-plan-impl`, `/invoke-audit-debug-clean`, `/invoke-plan-impl-design`, … **139 in total, generated deterministically from one config file.**

---

## 🧭 The dynamic skill router

How does the right skill or specialist show up at the right moment, without you asking? A **dynamic router** sits between your prompt and the work. It classifies intent, ranks skills by the file paths you're touching, injects only what's relevant, and — over time — **tunes its own weights** based on what actually helped.

<div align="center">
<img src="assets/skill-router.webp" alt="A prompt entering a routing hub that fans out to only the relevant skills and specialist agents, with self-tuning weights" width="100%">
</div>

<br/>

| Piece | What it does |
|---|---|
| **Keyword auto-dispatch** | A prompt's intent maps to an `/invoke` category and fires the matching specialist chain — no command typed |
| **Path-ranked injection** | Editing a `.tsx`? You get `fe_*` skills. A Go service? `be_*` skills. Only the relevant standards load |
| **Session skill manifest** | Batches the skills you *haven't* read yet, so nothing mandatory is silently skipped |
| **Self-tuning weights** | A weight-updater learns which skills actually helped and re-ranks future routing |
| **One source of truth** | Every route, model, and command composition lives in `autonomous-skill-router.config.json` — edit it, regenerate, done |

**This is the brain of the workspace** — the reason 200+ skills, 9 specialists, and 139 commands feel like *one* system instead of a menu you have to memorize.

---

## 🤖 Specialist corps

Nine first-class specialists, each owning exactly one act of the pipeline. Clean context, sharp scope, no jack-of-all-trades mush:

<div align="center">

| Agent | Act | Owns |
|-------|----------|------|
| 🔬 `audit-specialist` | **AUDIT** | Forensic hotspots, coupling/churn, dead code, repo-health — cited findings. |
| 📐 `spec-architect` | **SPEC** | Requirements → typed contracts, acceptance criteria, an explicit Not-Doing list. |
| 🗺️ `planning-director` | **PLAN** | Spec → dependency-ordered, file-pathed, per-task-TDD plan. |
| ⚙️ `implementation-engineer` | **IMPLEMENT** | Executes the plan task-by-task with TDD *(runs on Opus by directive)*. |
| 🐞 `debug-detective` | **DEBUG** | Reproduce → demonstrate root cause → minimal fix. *No fix before cause.* |
| 🧹 `deadcode-reaper` | **CLEANUP** | Removes only what *this* session's diff orphaned; delete-safe. |
| 🕵️ `security-sentinel` | **SECURITY** | Semgrep + OWASP pass on the diff → BLOCK/PASS verdict. |
| 📖 `docs-sync-agent` | **DOCS** | Syncs docs + the per-directory `CLAUDE.md` tree to the change. |
| ✅ `qa-verifier` | **VERIFY** | Runs the real flow and captures real output — evidence before "done". |

</div>

`frontend-uiux-designer` owns all visual/UX work via a six-skill design stack. Dozens of GSD, Figma, and Vercel helper agents round out the roster.

---

## 🏛️ Five layers, one discipline

```mermaid
flowchart TD
    L1["🧭 <b>DOCTRINE</b> — CLAUDE.md + rules/<br/><i>always-in-context operating rules</i>"]:::l1
    L2["🎨 <b>CRAFT</b> — 200+ skills<br/><i>how to do the work well</i>"]:::l2
    L3["🛡️ <b>ENFORCEMENT</b> — 70+ hooks<br/><i>makes the doctrine real at write-time</i>"]:::l3
    L4["🤖 <b>SPECIALISTS</b> — agent mesh<br/><i>one expert per act</i>"]:::l4
    L5["🎼 <b>ORCHESTRATION</b> — 139 /invoke commands<br/><i>composes specialists into the 3-act flow</i>"]:::l5
    L1 --> L2 --> L3 --> L4 --> L5

    classDef l1 fill:#4B3B9C,stroke:#312566,color:#fff
    classDef l2 fill:#6E56CF,stroke:#4B3B9C,color:#fff
    classDef l3 fill:#0EA5E9,stroke:#0369A1,color:#fff
    classDef l4 fill:#EC4899,stroke:#9D174D,color:#fff
    classDef l5 fill:#F59E0B,stroke:#B45309,color:#1E293B
```

| Layer | Path | Role |
|-------|------|------|
| **1 · Doctrine** | `CLAUDE.md`, `rules/` | Always-in-context operating rules — model routing, skill protocol, TDD/dox/codebase-intel doctrine. |
| **2 · Craft** | `skills/` | 200+ skills the agent invokes to *do the work well* (standards, testing, security, design, forensics). |
| **3 · Enforcement** | `hooks/` | 70+ hooks that make the doctrine real — skill injection, index guards, write gates, model guards, stop-gates. |
| **4 · Specialists** | `agents/` | A specialist agent mesh (the `/invoke` corps + a UI/UX designer + GSD/Figma/Vercel helpers). |
| **5 · Orchestration** | `commands/` | 139 `/invoke-*` commands composing the specialists into the 3-act flow. |

---

## 🚧 70+ hooks across the lifecycle

Skills are *advice*. **Hooks are the enforcement.** They fire at five points in every session — SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop — and they are the reason the discipline actually holds instead of drifting the moment the agent gets busy.

<div align="center">
<img src="assets/hooks-lifecycle.webp" alt="70+ hooks firing across five lifecycle phases: session start, prompt, pre-write, post-write, stop" width="100%">
</div>

<br/>

Some of them don't just advise — they **gate**. A risky change runs a gauntlet before it's allowed through, and a session can't even *end* until the closing gates pass:

<div align="center">
<img src="assets/hooks-gates.webp" alt="A code change passing through a gauntlet of gates: model, intel, TDD, dox, security, review" width="100%">
</div>

<br/>

| Phase | What the hooks do | A few of them |
|---|---|---|
| **① SessionStart** | Boot knowing the codebase | `jcodemunch-index-guard` · `graphify-index-guard` · `memory-load-on-start` · `dox-tree-guard` · `tdd-guard-init-guard` |
| **② UserPromptSubmit** | Shape the request before work | `sequential-thinking-mandate` · `codebase-intel-router` · `autonomous-skill-router` · `ui-ux-stack-orchestrator` |
| **③ PreToolUse** | Gate & route every action | `opus-guard` · `workflow-model-guard` · `jcodemunch-enforce` · `dox-write-gate` · `tdd-guard-gate` · `security-scan-gate` · `skill_router` · `ponytail-caveman-guard` |
| **④ PostToolUse** | Clean up after every write | `post-write-aggregator` · `desloppify-cleanup` · `doc-update-enforcer` · `dox-child-scaffold` · `security-semgrep-tracker` |
| **⑤ Stop** | Prove it's done, then learn | `hard-completion-gate` · `invoke-suite-gate` · `santa-method-writer` · `session-learning-extractor` · `session-memory-writer` |

<details>
<summary><b>Every hook, by phase</b> (click to expand the full roster)</summary>

- **SessionStart** — `session-start-aggregator` · `session-lifecycle` · `jcodemunch-index-guard` · `graphify-index-guard` · `memory-load-on-start` · `memory-bootstrap-guard` · `dox-tree-guard` · `tdd-guard-init-guard` · `session-plan-gate-hint` · `discovery-skills-reminder`
- **UserPromptSubmit** — `sequential-thinking-mandate` · `codebase-intel-router` · `token-stack-prompt-reminder` · `ui-ux-stack-orchestrator` · `autonomous-skill-router`
- **PreToolUse** — `opus-guard` · `workflow-model-guard` · `model-router` · `force-sonnet-subagent` · `jcodemunch-enforce` · `graphify-enforce` · `graphify-context-hint` · `dox-write-gate` · `gateguard-write-gate` · `bash-write-gate` · `dangerous-bash-gate` · `tdd-guard-gate` · `security-scan-gate` · `first-write-skill-gate` · `fullstack-skills-reminder` · `skill_router` · `ponytail-caveman-guard` · `tool_compat`
- **PostToolUse** — `post-write-aggregator` · `desloppify-cleanup` · `doc-update-enforcer` · `blocking-doc-enforcer` · `documentation_lifecycle_hook` · `dox-child-scaffold` · `security-semgrep-tracker` · `skill-invocation-tracker`
- **Stop** — `hard-completion-gate` · `invoke-suite-gate` · `invoke-suite-manifest` · `suite_push` · `santa-method-writer` · `session-learning-extractor` · `session-memory-writer` · `codex-capture` · `skill-effectiveness-report` · `skill-router-weight-updater` · `weekly-retro-trigger` · `watch-daemon-session-end`
- **Engines & generators** — `dox_engine` · `gen-invoke-commands` · `_watch_refcount`

</details>

---

## 📖 A self-documenting codebase

One of those hooks deserves its own spotlight. The **dox tree** guarantees every directory in every repo carries a `CLAUDE.md` (+ `AGENTS.md`) — and the moment you create a new folder, a hook **auto-scaffolds** its doc. Before editing, the agent reads root → target, so it always inherits the local rules of the exact place it's working.

<div align="center">
<img src="assets/dox-tree.webp" alt="A self-documenting codebase — a doc in every folder, auto-scaffolded into new folders, read root to target" width="100%">
</div>

<br/>

- **A doc in every folder** — local conventions live next to the code they govern.
- **Auto-scaffold on new folders** — write into an undocumented dir and its `CLAUDE.md` appears, root index re-synced.
- **Read root → target** — the agent walks the doc chain before it edits, so it never violates a local rule it didn't know existed.

---

## 🎨 UI that never looks AI-generated

Most AI writes **slop UI** — templated cards, the same purple gradient, zero intention. This workspace refuses. A six-skill anti-slop design stack — on top of the **Higgsfield** asset engine that generated *every image in this README* — turns a brief into interfaces that look deliberately crafted.

<div align="center">
<img src="assets/uiux-antislop.webp" alt="AI slop vs crafted UI — a dramatic before and after" width="100%">
</div>

<br/>

The design work runs as its own pipeline — real design systems in, screenshot-verified UI out:

<table>
<tr>
<td width="50%"><img src="assets/uiux-stack-flow.webp" alt="The anti-slop design stack pipeline feeding a finished UI"><br/><b>The stack</b> — <code>impeccable</code> · <code>taste-skill</code> · <code>ui-ux-pro-max</code> · <code>huashu-design</code> · <code>frontend-ui-engineering</code> · <code>design-extract</code>, fed by Higgsfield-generated assets.</td>
<td width="50%"><img src="assets/uiux-designer-loop.webp" alt="The UI/UX designer loop — 3 variations, self-critique, screenshot proof"><br/><b>The loop</b> — the <code>frontend-uiux-designer</code> agent explores <b>3 variations</b>, runs a <b>self-critique</b> pass, then captures <b>screenshot proof</b> at real breakpoints before presenting.</td>
</tr>
</table>

---

## 🚀 Install

> [!NOTE]
> **Release: the 100x overhaul (v2.0).** The workbench is now a single-truth,
> cross-platform system. Highlights: a **unified prompt router** with a
> never-miss **trigger floor** (one subprocess per prompt instead of ~15, with a
> verbatim superset of every legacy keyword/path/intent rule proven by a
> zero-miss shadow harness); a single **`model-policy.json`** truth
> (sonnet default · opus for UI + heavy work · fable only on request) plus the
> subagent model-guard crash fix; an **active-repo-only, event-driven index
> lifecycle** with **zero background daemons**; **8 event dispatchers** where
> every original hook survives as its own isolated, individually-toggleable
> module; provenance-aware **skill consolidation** (128 upstream-locked skills
> kept byte-identical and hash-verified, 24 merges each preserving the old name
> as a routing alias, **139 commands collapsed to 20** with all historic names
> still resolving); and a **Windows + Ubuntu `install.py`** with a two-OS CI
> matrix. The full verification report and change list ship in the release notes.

**One command**, on Ubuntu/macOS **or** Windows. `install.py` is a stdlib-only
bootstrap (Python ≥ 3.10), OS auto-detected, idempotent, and non-destructive.

**Ubuntu / macOS**

```bash
git clone https://github.com/AjayIrkal23/agentic-mercy-10x ~/.claude && python3 ~/.claude/install.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/AjayIrkal23/agentic-mercy-10x $env:USERPROFILE\.claude ; py -3 $env:USERPROFILE\.claude\install.py
```

`install.py` runs, in order: **detect** OS/python/node/git → idempotent **deps** →
register the **MCP servers** → **materialize** skills (copy or NTFS junction,
never a symlink) → **render** `settings.json` from its tracked template → **build
+ validate** the skills catalog (R9 trigger-floor + R10 upstream-intactness) →
run **doctor**.

```bash
python install.py doctor     # health + trigger-surface + model-routing verifier
python install.py update     # git pull --ff-only → deps → re-render → rebuild → doctor
```

Flags: `--dry-run` (print planned actions, mutate nothing) · `--ci` (skip
networked steps). Requires `git` + `python3` (≥ 3.10); optional `node`/`bun`,
`gh`, `uv`. Every path resolves through `hooks/lib/platform.py` — **no hardcoded
usernames or drive letters**, so it works for any user on either OS.

> [!TIP]
> Want a lighter footprint? Everything is à-la-carte. Prune `settings.json` and any hooks you don't want — the system fails *open* where it matters, so removing a gate degrades gracefully instead of breaking.

---

## 🧩 What's NOT included

By design, the repo excludes anything that is a secret, a session artifact, personal data, or re-installable from elsewhere:

- **Secrets** — `.credentials.json`, API keys, tokens, and `~/.claude.json` (your MCP config) are never committed. `settings.json` references env vars (e.g. `${GITHUB_TOKEN}`) instead.
- **Sessions & personal data** — `projects/`, `history.jsonl`, `sessions/`, `file-history/`, `todos/`, shell snapshots, and per-machine state.
- **Re-installable externals** — the plugin cache/marketplaces, `skills/gstack/`, `ast-grep-mcp/`, and the GSD (`get-shit-done/`) system. The installer + notes fetch these.
- **Machine-specific manifests** — plugin install-paths and index-guard project roots, which are regenerated per machine.

After install, finish the setup:

1. **Plugins** — add the 5 marketplaces (`anthropics/claude-plugins-official`, `veelenga/claude-mermaid`, `obra/superpowers-marketplace`, `forrestchang/andrej-karpathy-skills`, `DietrichGebert/ponytail`) and `claude plugin install` the ones you want (superpowers, ponytail, karpathy-skills, mermaid, frontend-design, context7, supabase, firecrawl, playwright, clickhouse, LSPs, …).
2. **MCP servers** — the hooks expect `jcodemunch`, `graphify`, `lean-ctx`, `memory`, `sequential-thinking`, and `context7` configured in your own `~/.claude.json`. `settings.json` also references `ast-grep`, `semgrep`, `playwright`, and others — trim what you don't use.
3. **Secrets** — export your own tokens; nothing is shipped.

---

## 🛠️ Customization

This workspace is meant to be forked and tuned:

- **`hooks/autonomous-skill-router.config.json`** — the source of truth for the `/invoke` suite: which skills each category loads and how the acts compose. The **model** each category runs on lives in **`hooks/model-policy.json`** (single model truth). Edit these, not the generated command files.
- **`hooks/gen-invoke-commands.py`** — regenerates the **20** `/invoke` command files (one parametric `/invoke <acts…>` + single-act delegators, aliases, and utilities) from that config (`python3 hooks/gen-invoke-commands.py`). All 139 historic command names still resolve — file or router translator — and `--emit-combos` re-expands the 120 combo files in seconds. The output is deterministic.
- **`skills/.provenance.json`** — tracks every skill's upstream source and version, so you can see what's authored-here vs. vendored, and update accordingly.
- **`settings.json`** — the hook wiring, MCP servers, model, and permissions. `rules/` + `CLAUDE.md` hold the always-on doctrine.

---

## 🚧 What the hooks enforce

So there are no surprises — the workspace ships opinionated gates. The notable ones:

- **Skill routing** — path-ranked skills are injected on writes; a session skill manifest batches what you haven't read.
- **Codebase-intel-first** — blind source reads are steered toward the `jcodemunch` symbol index + `graphify` dependency graph.
- **TDD guard** (warn mode) — flags implementation written before a failing test. Advisory, not blocking, but treated as a directive.
- **dox documentation tree** — every git repo gets a `CLAUDE.md` + `AGENTS.md` in every directory; code writes are gated until a root `CLAUDE.md` exists.
- **Model routing** — subagents default to the cheapest capable model unless explicitly escalated.
- **Stop-gates** — docs sync, security scan (when auth files change), and a review pass before a session is allowed to end.

All hooks fail *open* where it matters, but they will change how the agent behaves. If you want a lighter setup, prune `settings.json` and the `hooks/` you don't want.

---

## 🙏 Credits

This workspace stands on excellent third-party skills. **Each keeps its own upstream license** — see each project for terms. Huge thanks to their authors:

| Skill / suite | Upstream |
|---------------|----------|
| Impeccable (UI/UX craft) | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) |
| Huashu Design (花叔) | [alchaincyf/huashu-design](https://github.com/alchaincyf/huashu-design) |
| UI/UX Pro Max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) |
| Taste-Skill (anti-slop frontend) | [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) |
| gstack (ship/QA/browse/design suite) | [garrytan/gstack](https://github.com/garrytan/gstack) |
| Superpowers | [obra/superpowers-marketplace](https://github.com/obra/superpowers-marketplace) |
| Ponytail (anti-over-engineering) | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) |
| Karpathy Guidelines | [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) |
| ast-grep MCP | [ast-grep/ast-grep-mcp](https://github.com/ast-grep/ast-grep-mcp) |

Frontend design assets are generated with Higgsfield; GSD (`get-shit-done`) supplies the `gsd-*` command system. `skills/.provenance.json` records the exact source and pinned version of every vendored skill.

---

## 📄 License

The workspace's own authored content (hooks, agents, commands, rules, self-authored skills, and this documentation) is **MIT-licensed** — see [LICENSE](LICENSE). © 2026 Ajay Irkal.

**Third-party skills under `skills/` retain their own upstream licenses** (see the Credits table). MIT applies to the original work in this repository, not to vendored code.

<div align="center">
<br/>

**If your agent has ever vibe-coded you into a corner — this is the way out.**

⭐ *Star it, fork it, bend it to your taste.*

</div>

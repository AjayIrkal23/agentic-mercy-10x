<!-- ecc:README.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
<p align="center">
  <img src="assets/hero.png" alt="ECC - the agent harness operating system" width="100%" />
</p>

<p align="center">
  <a href="https://www.star-history.com/affaan-m/ecc">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/badge?repo=affaan-m/ECC&type=trending&theme=dark" />
      <img src="https://api.star-history.com/badge?repo=affaan-m/ECC&type=trending" alt="GitHub Trending Repository of the Day" height="46" />
    </picture>
  </a>
  <a href="https://www.star-history.com/affaan-m/ecc">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/badge?repo=affaan-m/ECC&type=rank&theme=dark" />
      <img src="https://api.star-history.com/badge?repo=affaan-m/ECC&type=rank" alt="Star History Global Rank" height="46" />
    </picture>
  </a>
</p>

<p align="center">
  <strong>Language:</strong>
  <a href="README.md">English</a> |
  <a href="docs/ar/README.md">العربية</a> |
  <a href="docs/pt-BR/README.md">Português (Brasil)</a> |
  <a href="README.zh-CN.md">简体中文</a> |
  <a href="docs/zh-TW/README.md">繁體中文</a> |
  <a href="docs/ja-JP/README.md">日本語</a> |
  <a href="docs/ko-KR/README.md">한국어</a> |
  <a href="docs/tr/README.md">Türkçe</a> |
  <a href="docs/ru/README.md">Русский</a> |
  <a href="docs/vi-VN/README.md">Tiếng Việt</a> |
  <a href="docs/th/README.md">ไทย</a> |
  <a href="docs/de-DE/README.md">Deutsch</a> |
  <a href="docs/es/README.md">Español</a> |
  <a href="docs/uk-UA/README.md">Українська</a> |
  <a href="docs/pl/README.md">Polski</a> |
  <a href="docs/bn/README.md">বাংলা</a>
</p>

<p align="center">
  <a href="https://discord.gg/36yGMHGFbR"><img src="https://img.shields.io/discord/1496644400590094540?logo=discord&logoColor=white&label=Discord&color=5865F2" alt="Discord" /></a>
  <a href="https://ecc.tools"><img src="https://img.shields.io/badge/Website-ecc.tools-E07856?logo=googlechrome&logoColor=white" alt="Website" /></a>
  <a href="https://github.com/apps/ecc-tools"><img src="https://img.shields.io/badge/GitHub%20App-ECC%20Tools-181717?logo=github&logoColor=white" alt="GitHub App" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license" /></a>
</p>

<p align="center">
  <a href="https://github.com/affaan-m/ECC"><img src="https://img.shields.io/github/stars/affaan-m/ECC?style=flat" alt="GitHub stars" /></a>
  <a href="https://github.com/affaan-m/ECC/forks"><img src="https://img.shields.io/github/forks/affaan-m/ECC?style=flat" alt="GitHub forks" /></a>
  <a href="https://github.com/affaan-m/ECC/graphs/contributors"><img src="https://img.shields.io/github/contributors/affaan-m/ECC?style=flat" alt="Contributors" /></a>
  <a href="https://github.com/marketplace/ecc-tools"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ecc.tools%2Fbadge%2Finstalls&logo=github" alt="GitHub App installs" /></a>
</p>

<p align="center">
  <a href="https://www.npmjs.com/package/ecc-universal"><img src="https://img.shields.io/npm/dw/ecc-universal?label=ecc-universal&logo=npm" alt="ecc-universal npm downloads" /></a>
  <a href="https://www.npmjs.com/package/ecc-agentshield"><img src="https://img.shields.io/npm/dw/ecc-agentshield?label=ecc-agentshield&logo=npm" alt="ecc-agentshield npm downloads" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/-Shell-4EAA25?logo=gnu-bash&logoColor=white" alt="Shell" />
  <img src="https://img.shields.io/badge/-TypeScript-3178C6?logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/-Python-3776AB?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/-Go-00ADD8?logo=go&logoColor=white" alt="Go" />
  <img src="https://img.shields.io/badge/-Java-ED8B00?logo=openjdk&logoColor=white" alt="Java" />
  <img src="https://img.shields.io/badge/-Perl-39457E?logo=perl&logoColor=white" alt="Perl" />
  <img src="https://img.shields.io/badge/-Markdown-000000?logo=markdown&logoColor=white" alt="Markdown" />
</p>

> [!WARNING]
> **Official sources only.** Install ECC only from verified channels: the GitHub repository [github.com/affaan-m/ECC](https://github.com/affaan-m/ECC), the npm packages [`ecc-universal`](https://www.npmjs.com/package/ecc-universal) and [`ecc-agentshield`](https://www.npmjs.com/package/ecc-agentshield), the [GitHub App](https://github.com/apps/ecc-tools), the plugin slug `ecc@ecc`, and the project website [ecc.tools](https://ecc.tools). Third-party re-uploads and unofficial mirrors are not maintained or reviewed by the project and may contain malware.

## Self-Hosted Models and Custom Endpoints

ECC works through each harness's normal configuration, so you can use an official provider, a compatible custom API endpoint or model gateway, or a self-hosted model without changing ECC's workflows.

For Claude Code, ECC does not hardcode Anthropic-hosted transport settings. Minimal gateway example:

```bash
export ANTHROPIC_BASE_URL=https://your-gateway.example.com
export ANTHROPIC_AUTH_TOKEN=your-token
claude
```

If your gateway remaps model names, configure that in Claude Code rather than in ECC. ECC's hooks, skills, commands, and rules are model-provider agnostic once the `claude` CLI is already working. See Anthropic's [LLM gateway documentation](https://docs.anthropic.com/en/docs/claude-code/llm-gateway) and [model configuration documentation](https://docs.anthropic.com/en/docs/claude-code/model-config).

Run or self-host any open-source model behind that gateway using separate compute and serving setup. If you need GPU capacity, [Itô](https://compute.itomarkets.com) is ECC's preferred compute sponsor; any GPU provider works. The sponsorship link is passive: it does not invoke an RFQ, reserve capacity, provision compute, or configure serving. Separately, `ecc ito find` invokes the explicitly configured canonical Itô CLI and submits a live authenticated RFQ; it does not reserve capacity. Managed inference through Itô is not live yet.

### Self-host Kimi with ECC + Itô compute

The Kimi Code harness and the model-serving layer are separate. ECC configures the agent harness; you bring an API endpoint ([get a Kimi API key](https://platform.kimi.ai?aff=ecc)) or self-host an open-weight Kimi model on your own GPU capacity. This adapter is verified against Kimi Code 0.31.x (`@moonshot-ai/kimi-code`):

<table aria-label="Local Kimi model path" width="100%">
<tr>
<td width="33%" align="center">
  <a href="https://compute.itomarkets.com">
    <picture><source media="(prefers-color-scheme: light)" srcset="assets/images/sponsors/ito-transparent-light.png" /><img src="assets/images/sponsors/ito-transparent.png" width="92" alt="Itô Markets" /></picture><br />
    <strong>1. Get GPU capacity</strong>
  </a><br />
  <sub>Use Itô or any GPU provider.</sub>
</td>
<td width="33%" align="center">
  <a href="https://www.moonshot.ai">
    <picture><source media="(prefers-color-scheme: dark)" srcset="assets/images/sponsors/moonshot-dark.png" /><img src="assets/images/sponsors/moonshot.png" width="126" alt="Moonshot AI - Kimi" /></picture><br />
    <strong>2. Serve Kimi</strong>
  </a><br />
  <sub>Expose the chosen checkpoint through a compatible endpoint.</sub>
</td>
<td width="33%" align="center">
  <a href=".kimi/README.md">
    <img src="assets/images/community/ecc-tools-mark.svg" height="52" alt="ECC Tools" /><br />
    <strong>3. Run Kimi Code with ECC</strong>
  </a><br />
  <sub>Install project instructions and skills, then start Kimi Code.</sub>
</td>
</tr>
</table>

Configure the endpoint with Kimi Code's <a href="https://moonshotai.github.io/kimi-cli/en/configuration/providers.html">official provider guide</a>, then install ECC:

```bash
bash ./install.sh --target kimi --profile minimal
node scripts/ecc.js doctor --target kimi
kimi
```

Kimi Code discovers the installed `.kimi-code/AGENTS.md` instructions and `.kimi-code/skills/` workflows natively; project-level `.agents/skills/` is also an official discovery location. ECC safely merges project MCP entries into `.kimi-code/mcp.json` and does not change the user-level `~/.kimi-code/config.toml`. Kimi Code supports native hooks, but ECC's current managed-project adapter does not configure them, so this installer does not offer Kimi hook profiles. The installer dry-run and regression suite verify that every managed Kimi write stays inside the project-local `.kimi-code/` root.

### Itô compute CLI bridge

`ecc ito` delegates to the separately installed canonical Itô client; ECC does not maintain a second API client. `ecc ito login [--no-browser]` performs device authorization, opens the Itô verification page by default, and persists a device token in macOS Keychain; `--no-browser` suppresses the page handoff. ECC itself does no browser automation. `ecc ito auth` is validation-only and rejects `--no-browser`. The available operations are `ecc ito login`, `ecc ito auth`, `ecc ito find`, `ecc ito status`, and the separately gated `ecc ito evals`. The matching MCP tools remain `ito_auth`, `ito_find`, and `ito_status`; `ito_auth` validates existing credentials and node qualification is CLI-only.

The `ito-compute-cli` package is currently unpublished. Build it locally from the Itô runtime repo (private while the desk hardens; design partners get access) under `cli/ito-compute-cli`, run `npm ci` and `npm run check`, then set `ECC_ITO_CLI_EXECUTABLE` to that build's absolute `dist/bin/ito.js` path. Login never inherits `ITO_API_KEY`; auth, find, and status forward `ITO_API_KEY` directly when configured, and `ITO_AUTH_MODE=legacy` is not required. `ecc ito logout` revokes the current device credential and retains its local copy if remote revocation cannot be confirmed. Device tokens use macOS Keychain by default; explicit file fallback must retain owner-only directory/file permissions. ECC does not discover this credential-bearing client through `PATH`. See the [`ito-compute` skill](skills/ito-compute/SKILL.md) for the full RFQ authority and MCP setup contract.

`find` submits a live authenticated RFQ. It does not reserve capacity. `evals` requires both `ITO_ENABLE_SIXTYTWO_LIVE=1` and `--live-sixtytwo`, a separately installed `sixtytwo-cli==0.3.33`, an explicit node list, and an existing absolute configuration directory. It cannot rent, launch, recover, repair, or purchase. ECC exposes no quote lock, purchase, workload, or inference path, and it never replaces a missing client or failed live call with a local result.

## What's Inside

```text
ECC/
|-- agents/           # 71 specialized subagents for delegation
|-- skills/           # 311 reusable workflows loaded on demand
|-- commands/         # 97 maintained slash-command shims
|-- rules/            # opt-in common and language standards
|-- hooks/            # runtime automation and enforcement
|-- scripts/          # install, repair, sync, orchestration, and checks
|-- .claude-plugin/   # Claude Code marketplace manifest
|-- .codex/           # Codex reference configuration and agent roles
|-- .opencode/        # OpenCode plugin, commands, and instructions
|-- .cursor/          # Cursor rules and hook adapter
|-- docs/             # public setup, architecture, and operating guides
```

The root is the source of truth. Platform adapters package or map these same workflows instead of maintaining separate copies.

<details>
<summary><strong>Annotated component catalog</strong></summary>

```
ECC/
|-- .claude-plugin/   # Plugin and marketplace manifests
|   |-- plugin.json         # Plugin metadata and component paths
|   |-- marketplace.json    # Marketplace catalog for /plugin marketplace add
|
|-- agents/           # 71 specialized subagents for delegation
|   |-- planner.md           # Feature implementation planning
|   |-- architect.md         # System design decisions
|   |-- tdd-guide.md         # Test-driven development
|   |-- code-reviewer.md     # Quality and security review
|   |-- security-reviewer.md # Vulnerability analysis
|   |-- build-error-resolver.md
|   |-- e2e-runner.md        # Playwright E2E testing
|   |-- refactor-cleaner.md  # Dead code cleanup
|   |-- doc-updater.md       # Documentation sync
|   |-- docs-lookup.md       # Documentation/API lookup
|   |-- chief-of-staff.md    # Communication triage and drafts
|   |-- loop-operator.md     # Autonomous loop execution
|   |-- harness-optimizer.md # Harness config tuning
|   |-- cpp-reviewer.md      # C++ code review
|   |-- cpp-build-resolver.md # C++ build error resolution
|   |-- fsharp-reviewer.md   # F# functional code review
|   |-- go-reviewer.md       # Go code review
|   |-- go-build-resolver.md # Go build error resolution
|   |-- python-reviewer.md   # Python code review
|   |-- database-reviewer.md # Database/Supabase review
|   |-- typescript-reviewer.md # TypeScript/JavaScript code review
|   |-- java-reviewer.md     # Java/Spring Boot code review
|   |-- java-build-resolver.md # Java/Maven/Gradle build errors
|   |-- kotlin-reviewer.md   # Kotlin/Android/KMP code review
|   |-- kotlin-build-resolver.md # Kotlin/Gradle build errors
|   |-- harmonyos-app-resolver.md # HarmonyOS/ArkTS app development
|   |-- ruby-reviewer.md     # Ruby/Rails code review
|   |-- rust-reviewer.md     # Rust code review
|   |-- rust-build-resolver.md # Rust build error resolution
|   |-- pytorch-build-resolver.md # PyTorch/CUDA training errors
|   |-- mle-reviewer.md      # Production ML pipeline, eval, serving, and monitoring review
|
|-- skills/           # Workflow definitions and domain knowledge
|   |-- coding-standards/           # Language best practices
|   |-- clickhouse-io/              # ClickHouse analytics, queries, data engineering
|   |-- backend-patterns/           # API, database, caching patterns
|   |-- frontend-patterns/          # React, Next.js patterns
|   |-- frontend-slides/            # HTML slide decks and PPTX-to-web presentation workflows
|   |-- article-writing/            # Long-form writing in a supplied voice without generic AI tone
|   |-- content-engine/             # Multi-platform social content and repurposing workflows
|   |-- market-research/            # Source-attributed market, competitor, and investor research
|   |-- osint-investigation/        # OSINT methodology: competing hypotheses, falsification, visual and evidence verification
|   |-- investor-materials/         # Pitch decks, one-pagers, memos, and financial models
|   |-- investor-outreach/          # Personalized fundraising outreach and follow-up
|   |-- continuous-learning/        # Legacy v1 Stop-hook pattern extraction
|   |-- continuous-learning-v2/     # Instinct-based learning with confidence scoring
|   |-- iterative-retrieval/        # Progressive context refinement for subagents
|   |-- strategic-compact/          # Manual compaction suggestions (Longform Guide)
|   |-- tdd-workflow/               # TDD methodology
|   |-- security-review/            # Security checklist
|   |-- eval-harness/               # Verification loop evaluation (Longform Guide)
|   |-- verification-loop/          # Continuous verification (Longform Guide)
|   |-- videodb/                    # Video and audio: ingest, search, edit, generate, stream
|   |-- golang-patterns/            # Go idioms and best practices
|   |-- golang-testing/             # Go testing patterns, TDD, benchmarks
|   |-- cpp-coding-standards/       # C++ coding standards from C++ Core Guidelines
|   |-- cpp-testing/                # C++ testing with GoogleTest, CMake/CTest
|   |-- django-patterns/            # Django patterns, models, views
|   |-- django-security/            # Django security best practices
|   |-- django-tdd/                 # Django TDD workflow
|   |-- django-verification/        # Django verification loops
|   |-- laravel-patterns/           # Laravel architecture patterns
|   |-- laravel-security/           # Laravel security best practices
|   |-- laravel-tdd/                # Laravel TDD workflow
|   |-- laravel-verification/       # Laravel verification loops
|   |-- python-patterns/            # Python idioms and best practices
|   |-- python-testing/             # Python testing with pytest
|   |-- quarkus-patterns/           # Java Quarkus patterns
|   |-- quarkus-security/           # Quarkus security
|   |-- quarkus-tdd/                # Quarkus TDD
|   |-- quarkus-verification/       # Quarkus verification
|   |-- rails-patterns/             # Rails architecture patterns
|   |-- springboot-patterns/        # Java Spring Boot patterns
|   |-- springboot-security/        # Spring Boot security
|   |-- springboot-tdd/             # Spring Boot TDD
|   |-- springboot-verification/    # Spring Boot verification
|   |-- configure-ecc/              # Interactive installation wizard
|   |-- security-scan/              # AgentShield security auditor integration
|   |-- java-coding-standards/      # Java coding standards
|   |-- jpa-patterns/               # JPA/Hibernate patterns
|   |-- postgres-patterns/          # PostgreSQL optimization patterns
|   |-- nutrient-document-processing/ # Document processing with Nutrient API
|   |-- database-migrations/        # Migration patterns (Prisma, Drizzle, Django, Go)
|   |-- api-design/                 # REST API design, pagination, error responses
|   |-- deployment-patterns/        # CI/CD, Docker, health checks, rollbacks
|   |-- docker-patterns/            # Docker Compose, networking, volumes, container security
|   |-- e2e-testing/                # Playwright E2E patterns and Page Object Model
|   |-- content-hash-cache-pattern/ # SHA-256 content hash caching for file processing
|   |-- cost-aware-llm-pipeline/    # LLM cost optimization, model routing, budget tracking
|   |-- regex-vs-llm-structured-text/ # Decision framework: regex vs LLM for text parsing
|   |-- swift-actor-persistence/    # Thread-safe Swift data persistence with actors
|   |-- swift-protocol-di-testing/  # Protocol-based DI for testable Swift code
|   |-- search-first/               # Research-before-coding workflow
|   |-- skill-stocktake/            # Audit skills and commands for quality
|   |-- liquid-glass-design/        # iOS 26 Liquid Glass design system
|   |-- foundation-models-on-device/ # Apple on-device LLM with FoundationModels
|   |-- swift-concurrency-6-2/      # Swift 6.2 Approachable Concurrency
|   |-- mle-workflow/               # Production ML data contracts, evals, deployment, monitoring
|   |-- perl-patterns/              # Modern Perl 5.36+ idioms and best practices
|   |-- perl-security/              # Perl security patterns, taint mode, safe I/O
|   |-- perl-testing/               # Perl TDD with Test2::V0, prove, Devel::Cover
|   |-- autonomous-loops/           # Autonomous loop patterns: sequential pipelines, PR loops, DAG orchestration
|   |-- plankton-code-quality/      # Write-time code quality enforcement with Plankton hooks
|   |-- codehealth-mcp/             # Optional CodeScene Code Health MCP skill (opt-in)
|   |-- docs/examples/project-guidelines-template.md  # Template for project-specific skills
|
|-- commands/         # Maintained slash-entry compatibility; prefer skills/
|   |-- plan.md             # /plan - Implementation planning
|   |-- code-review.md      # /code-review - Quality review
|   |-- build-fix.md        # /build-fix - Fix build errors
|   |-- refactor-clean.md   # /refactor-clean - Dead code removal
|   |-- quality-gate.md     # /quality-gate - Verification gate
|   |-- learn.md            # /learn - Extract patterns mid-session (Longform Guide)
|   |-- learn-eval.md       # /learn-eval - Extract, evaluate, and save patterns
|   |-- checkpoint.md       # /checkpoint - Save verification state (Longform Guide)
|   |-- setup-pm.md         # /setup-pm - Configure package manager
|   |-- go-review.md        # /go-review - Go code review
|   |-- go-test.md          # /go-test - Go TDD workflow
|   |-- go-build.md         # /go-build - Fix Go build errors
|   |-- skill-create.md     # /skill-create - Generate skills from git history
|   |-- instinct-status.md  # /instinct-status - View learned instincts
|   |-- instinct-import.md  # /instinct-import - Import instincts
|   |-- instinct-export.md  # /instinct-export - Export instincts
|   |-- evolve.md           # /evolve - Cluster instincts into skills
|   |-- prune.md            # /prune - Delete expired pending instincts
|   |-- pm2.md              # /pm2 - PM2 service lifecycle management
|   |-- multi-plan.md       # /multi-plan - Multi-agent task decomposition
|   |-- multi-execute.md    # /multi-execute - Orchestrated multi-agent workflows
|   |-- multi-backend.md    # /multi-backend - Backend multi-service orchestration
|   |-- multi-frontend.md   # /multi-frontend - Frontend multi-service orchestration
|   |-- multi-workflow.md   # /multi-workflow - General multi-service workflows
|   |-- sessions.md         # /sessions - Session history management
|   |-- test-coverage.md    # /test-coverage - Test coverage analysis
|   |-- update-docs.md      # /update-docs - Update documentation
|   |-- update-codemaps.md  # /update-codemaps - Update codemaps
|   |-- python-review.md    # /python-review - Python code review
|-- legacy-command-shims/   # Opt-in archive for retired shims such as /tdd and /eval
|   |-- tdd.md              # /tdd - Prefer the tdd-workflow skill
|   |-- e2e.md              # /e2e - Prefer the e2e-testing skill
|   |-- eval.md             # /eval - Prefer the eval-harness skill
|   |-- verify.md           # /verify - Prefer the verification-loop skill
|   |-- orchestrate.md      # /orchestrate - Prefer dmux-workflows or multi-workflow
|
|-- rules/            # Always-follow guidelines (copy to ~/.claude/rules/ecc/)
|   |-- README.md            # Structure overview and installation guide
|   |-- common/              # Language-agnostic principles
|   |   |-- coding-style.md    # Immutability, file organization
|   |   |-- git-workflow.md    # Commit format, PR process
|   |   |-- testing.md         # TDD, 80% coverage requirement
|   |   |-- performance.md     # Model selection, context management
|   |   |-- patterns.md        # Design patterns, skeleton projects
|   |   |-- hooks.md           # Hook architecture, TodoWrite
|   |   |-- agents.md          # When to delegate to subagents
|   |   |-- security.md        # Mandatory security checks
|   |-- typescript/          # TypeScript/JavaScript specific
|   |-- python/              # Python specific
|   |-- golang/              # Go specific
|   |-- swift/               # Swift specific
|   |-- php/                 # PHP specific
|   |-- arkts/               # HarmonyOS / ArkTS specific
|
|-- hooks/            # Trigger-based automations
|   |-- README.md                 # Hook documentation, recipes, and customization guide
|   |-- hooks.json                # All hooks config (PreToolUse, PostToolUse, Stop, etc.)
|   |-- memory-persistence/       # Session lifecycle hooks (Longform Guide)
|   |-- strategic-compact/        # Compaction suggestions (Longform Guide)
|
|-- scripts/          # Cross-platform Node.js scripts
|   |-- lib/                     # Shared utilities
|   |   |-- utils.js             # Cross-platform file/path/system utilities
|   |   |-- package-manager.js   # Package manager detection and selection
|   |-- hooks/                   # Hook implementations
|   |   |-- session-start.js     # Load context on session start
|   |   |-- session-end.js       # Save state on session end
|   |   |-- pre-compact.js       # Pre-compaction state saving
|   |   |-- suggest-compact.js   # Strategic compaction suggestions
|   |   |-- evaluate-session.js  # Extract patterns from sessions
|   |-- setup-package-manager.js # Interactive PM setup
|
|-- tests/            # Test suite
|   |-- lib/                     # Library tests
|   |-- hooks/                   # Hook tests
|   |-- run-all.js               # Run all tests
|
|-- contexts/         # Dynamic system prompt injection contexts (Longform Guide)
|   |-- dev.md              # Development mode context
|   |-- review.md           # Code review mode context
|   |-- research.md         # Research/exploration mode context
|
|-- examples/         # Example configurations and sessions
|   |-- CLAUDE.md             # Example project-level config
|   |-- user-CLAUDE.md        # Example user-level config
|   |-- saas-nextjs-CLAUDE.md   # Real-world SaaS (Next.js + Supabase + Stripe)
|   |-- go-microservice-CLAUDE.md # Real-world Go microservice (gRPC + PostgreSQL)
|   |-- django-api-CLAUDE.md      # Real-world Django REST API (DRF + Celery)
|   |-- laravel-api-CLAUDE.md     # Real-world Laravel API (PostgreSQL + Redis)
|   |-- rust-api-CLAUDE.md        # Real-world Rust API (Axum + SQLx + PostgreSQL)
|
|-- mcp-configs/      # MCP server configurations
|   |-- mcp-servers.json    # GitHub, Supabase, Vercel, Railway, etc.
|
|-- ecc_dashboard.py  # Desktop GUI dashboard (Tkinter)
|
|-- marketplace.json  # Self-hosted marketplace config (for /plugin marketplace add)
```
</details>

<details>
<summary><strong>Dashboard GUI</strong></summary>

Launch the desktop dashboard to visually explore ECC components:

```bash
npm run dashboard
# or
python3 ./ecc_dashboard.py
```

**Features:**
- Tabbed interface: Agents, Skills, Commands, Rules, Settings
- Dark/Light theme toggle
- Font customization (family and size)
- Project logo in header and taskbar
- Search and filter across all components
</details>

## Key Concepts

<details>
<summary><strong>Agents, skills, hooks, and rules explained</strong></summary>

### Agents

Subagents handle delegated tasks with limited scope. Example:

```markdown
---
name: code-reviewer
description: Reviews code for quality, security, and maintainability
tools: Read, Grep, Glob, Bash
model: opus
---

You are a senior code reviewer...
```

### Skills

Skills are the primary workflow surface. They can be invoked directly, suggested automatically, and reused by agents. ECC still ships maintained `commands/` during migration, while retired short-name shims live under `legacy-command-shims/` for explicit opt-in only. New workflow development should land in `skills/` first.

```markdown
# TDD Workflow

1. Define interfaces first
2. Write failing tests (RED)
3. Implement minimal code (GREEN)
4. Refactor (IMPROVE)
5. Verify 80%+ coverage
```

### Hooks

Hooks fire on tool events. Example: warn about console.log:

```json
{
  "matcher": "tool == \"Edit\" && tool_input.file_path matches \"\\\\.(ts|tsx|js|jsx)$\"",
  "hooks": [{
    "type": "command",
    "command": "#!/bin/bash\ngrep -n 'console\\.log' \"$file_path\" && echo '[Hook] Remove console.log' >&2"
  }]
}
```

### Rules

Rules are always-follow guidelines, organized into `common/` (language-agnostic) + language-specific directories:

```
rules/
  common/          # Universal principles (always install)
  typescript/      # TS/JS specific patterns and tools
  python/          # Python specific patterns and tools
  golang/          # Go specific patterns and tools
  swift/           # Swift specific patterns and tools
  php/             # PHP specific patterns and tools
  arkts/           # HarmonyOS / ArkTS patterns and constraints
```

See [`rules/README.md`](rules/README.md) for installation and structure details.
</details>

## Guides

This repo is the raw code. The guides explain everything.

<table aria-label="ECC guides" width="100%">
<tr>
<td width="33%" align="center">
<a href="./the-shortform-guide.md">
<img src="assets/images/guides/shorthand-guide.png" width="213" height="120" alt="The Shorthand Guide to ECC" /><br />
<strong>The Shorthand Guide</strong>
</a>
<br /><sub>Setup, foundations, and day-one use. <b>Read this first.</b> (<a href="https://x.com/affaan/status/2012378465664745795">thread</a>)</sub>
</td>
<td width="33%" align="center">
<a href="./the-longform-guide.md">
<img src="assets/images/guides/longform-guide.png" width="213" height="120" alt="The Longform Guide to ECC" /><br />
<strong>The Longform Guide</strong>
</a>
<br /><sub>Context economics, memory, evals, and parallel agents. (<a href="https://x.com/affaan/status/2014040193557471352">thread</a>)</sub>
</td>
<td width="33%" align="center">
<a href="./the-security-guide.md">
<img src="assets/images/guides/security-guide.png" width="213" height="120" alt="The Security Guide to ECC" /><br />
<strong>The Security Guide</strong>
</a>
<br /><sub>Prompt injection, hooks, MCP, and AgentShield. (<a href="https://x.com/affaan/status/2033263813387223421">thread</a>)</sub>
</td>
</tr>
</table>

| Topic | What You'll Learn |
|-------|-------------------|
| Token Optimization | Model selection, system prompt slimming, background processes |
| Memory Persistence | Hooks that save/load context across sessions automatically |
| Continuous Learning | Auto-extract patterns from sessions into reusable skills |
| Verification Loops | Checkpoint vs continuous evals, grader types, pass@k metrics |
| Parallelization | Git worktrees, cascade method, when to scale instances |
| Subagent Orchestration | The context problem, iterative retrieval pattern |

[Commands Quick Reference](./COMMANDS-QUICK-REF.md) | [Manual Adaptation Guide](docs/MANUAL-ADAPTATION-GUIDE.md) | [Astra Review Guide](docs/ASTRA-REVIEW-GUIDE.md) | [Troubleshooting FAQ](./TROUBLESHOOTING.md) | [Roadmap](docs/ROADMAP.md)

## Token Optimization

Agent usage can be expensive if you don't manage token consumption. These settings significantly reduce costs without sacrificing quality. Full guide: [docs/token-optimization.md](docs/token-optimization.md).

<details>
<summary><strong>Recommended settings</strong></summary>

Add to `~/.claude/settings.json`:

```json
{
  "model": "sonnet",
  "env": {
    "CLAUDE_CODE_EFFORT_LEVEL": "medium",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50",
    "CLAUDE_CODE_SUBAGENT_MODEL": "haiku"
  }
}
```

The effort setting requires a model that supports effort controls. On Amazon Bedrock,
Google Cloud's Agent Platform, and Microsoft Foundry, the `sonnet` alias currently
resolves to Sonnet 4.5, which does not support effort controls. Select an effort-capable
model available from your provider, or omit `CLAUDE_CODE_EFFORT_LEVEL`.

| Setting | Default | Recommended | Impact |
|---------|---------|-------------|--------|
| `model` | opus | **sonnet** | ~60% cost reduction; handles 80%+ of coding tasks |
| `CLAUDE_CODE_EFFORT_LEVEL` | Model-dependent | **medium**, if supported | Controls adaptive reasoning depth on models that support effort controls; lower effort trades reasoning depth for latency and cost |
| `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` | 95 | **50** | Compacts earlier, better quality in long sessions |
| `ECC_CONTEXT_MONITOR_COST_WARNINGS` | on | **off for subscription users** | Suppresses agent-facing API-rate estimate warnings while keeping context/scope/loop warnings |

For fixed-budget models, `MAX_THINKING_TOKENS` controls the thinking budget. On Opus 4.6 or Sonnet 4.6, also set `CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING=1` to use that mode. A positive token value does not cap adaptive reasoning; see the [performance rule](rules/common/performance.md#extended-thinking--plan-mode).

Switch to Opus only when you need deep architectural reasoning:
```
/model opus
```
</details>

<details>
<summary><strong>Daily workflow commands</strong></summary>

| Command | When to Use |
|---------|-------------|
| `/model sonnet` | Default for most tasks |
| `/model opus` | Complex architecture, debugging, deep reasoning |
| `/clear` | Between unrelated tasks (free, instant reset) |
| `/compact` | At logical task breakpoints (research done, milestone complete) |
| `/cost` | Monitor token spending during session |

If you use a subscription and the context monitor's API-rate estimates are not useful, set `ECC_CONTEXT_MONITOR_COST_WARNINGS=off`. This only suppresses the agent-facing cost warnings; it does not disable context exhaustion, scope, or loop warnings.
</details>

<details>
<summary><strong>Strategic compaction</strong></summary>

The `strategic-compact` skill suggests `/compact` at logical breakpoints instead of relying on auto-compaction at 95% context. See `skills/strategic-compact/SKILL.md` for the full decision guide.

**When to compact:**
- After research/exploration, before implementation
- After completing a milestone, before starting the next
- After debugging, before continuing feature work
- After a failed approach, before trying a new one

**When NOT to compact:**
- Mid-implementation (you'll lose variable names, file paths, partial state)
</details>

<details>
<summary><strong>Context window management</strong></summary>

**Critical:** Don't enable all MCPs at once. Each MCP tool description consumes tokens from your 200k window, potentially reducing it to ~70k.

- Keep under 10 MCPs enabled per project
- Keep under 80 tools active
- Use `/mcp` to disable unused Claude Code MCP servers; those runtime choices persist in `~/.claude.json`
- Use `ECC_DISABLED_MCPS` only to filter ECC-generated MCP configs during install/sync flows
- If context is getting heavy, run `/context-budget` and remove rules you do not need

**Agent teams cost warning:** Agent Teams spawns multiple context windows. Each teammate consumes tokens independently. Only use for tasks where parallelism provides clear value (multi-module work, parallel reviews). For simple sequential tasks, subagents are more token-efficient.
</details>

## Security

Install ECC only from official sources:

- GitHub repository: <https://github.com/affaan-m/ECC>
- Claude Code plugin: `ecc@ecc`
- npm packages: [`ecc-universal`](https://www.npmjs.com/package/ecc-universal) and [`ecc-agentshield`](https://www.npmjs.com/package/ecc-agentshield)
- GitHub App: <https://github.com/apps/ecc-tools>
- Website: <https://ecc.tools>

Scan a project with an already installed, reviewed AgentShield binary (see [runner provenance](#agentshield-runner-provenance)):

```bash
agentshield scan --path .
```

- **Report a vulnerability.** Use the private process in [SECURITY.md](SECURITY.md) (GitHub private vulnerability reporting). Please do not open public issues for security reports.
- **Built-in guardrails.** GateGuard gates destructive shell commands (including `rm`, force/path `git checkout`, and destructive `find -exec`) before they run; the supply-chain IOC scanner runs in CI; and AgentShield audits your own agent, hook, MCP, permission, and secret surfaces (`/security-scan`).

<details>
<summary><strong>Hooks, MCP servers, and context controls</strong></summary>

Hooks can run shell commands, MCP servers can hold credentials, and project instructions can enter an agent's context. Treat all three as executable configuration.

Do not copy raw `hooks/hooks.json` into `~/.claude/settings.json` after a plugin install. Modern Claude Code versions load plugin hooks automatically, and a second copy can make them fire twice.

Use `/mcp` for Claude Code runtime disables; Claude Code persists those choices in `~/.claude.json`.

`ECC_DISABLED_MCPS` is an ECC install/sync filter, not a live Claude Code toggle.

If context is getting heavy, run `/context-budget`, remove rules you do not need, and disable unused MCP servers. See the [token optimization guide](docs/token-optimization.md).
</details>

Security references:

- [Security policy](SECURITY.md)
- [Security guide](./the-security-guide.md)
- [MCP connector policy](docs/MCP-CONNECTOR-POLICY.md)
- [Supply-chain incident response](docs/security/supply-chain-incident-response.md)

## Ecosystem Tools

<details>
<summary><strong>Skill Creator: generate skills from your git history</strong></summary>

Two ways to generate skills from your repository:

### Option A: Local Analysis (Built-in)

Use the `/skill-create` command for local analysis without external services:

```bash
/skill-create                    # Analyze current repo
/skill-create --instincts        # Also generate instincts for continuous-learning-v2
```

This analyzes your git history locally and generates SKILL.md files.

### Option B: GitHub App (Advanced)

For advanced features (10k+ commits, auto-PRs, team sharing):

[Install ECC Tools GitHub App](https://github.com/apps/ecc-tools) | [ecc.tools](https://ecc.tools)

```bash
# Comment on any issue:
/ecc-tools analyze
```

Both options create:
- **SKILL.md files**: Ready-to-use skills for the active harness
- **Instinct collections**: For continuous-learning-v2
- **Pattern extraction**: Learns from your commit history
</details>

<details>
<summary><strong>AgentShield: security auditor for agent configs</strong></summary>

> Built at the Claude Code Hackathon (Cerebral Valley x Anthropic, Feb 2026). 1282 tests, 98% coverage, 102 static analysis rules.

Scan your agent configuration for vulnerabilities, misconfigurations, and injection risks.

<a id="agentshield-runner-provenance"></a>
**Runner provenance:** these commands require an already installed, reviewed AgentShield binary from `ecc-agentshield`. The [official package](https://www.npmjs.com/package/ecc-agentshield) documents the `agentshield` CLI. Record the selected release, reviewed source and verified package integrity in your installation record. Registry publication alone does not establish an audit; ECC does not supply an audited AgentShield pin here. Do not substitute an unversioned one-shot download. `/security-scan` is workflow guidance and has the same runner prerequisite.

```bash
# Scan only the intended project directory
agentshield scan --path .

# Auto-fix safe issues
agentshield scan --path . --fix

# Deep analysis with three Opus 4.6 agents
agentshield scan --path . --opus --stream

# Generate secure config from scratch
agentshield init
```

**What it scans:** CLAUDE.md, settings.json, MCP configs, hooks, agent definitions, and skills across 5 categories: secrets detection (14 patterns), permission auditing, hook injection analysis, MCP server risk profiling, and agent config review.

**The `--opus` flag** runs three Claude Opus 4.6 agents in a red-team/blue-team/auditor pipeline. The attacker finds exploit chains, the defender evaluates protections, and the auditor synthesizes both into a prioritized risk assessment. Adversarial reasoning, not just pattern matching.

**Output formats:** Terminal (color-graded A-F), JSON (CI pipelines), Markdown, HTML. Exit code 2 on critical findings for build gates.

Use `/security-scan` in Claude Code to run it, or add to CI with the [GitHub Action](https://github.com/affaan-m/agentshield).

[GitHub](https://github.com/affaan-m/agentshield) | [npm](https://www.npmjs.com/package/ecc-agentshield)
</details>

<details>
<summary><strong>Continuous Learning v2: instincts</strong></summary>

The instinct-based learning system automatically learns your patterns:

```bash
/instinct-status        # Show learned instincts with confidence
/instinct-import <file> # Import instincts from others
/instinct-export        # Export your instincts for sharing
/evolve                 # Cluster related instincts into skills
```

See `skills/continuous-learning-v2/` for full documentation. Keep `continuous-learning/` only when you explicitly want the legacy v1 Stop-hook learned-skill flow.
</details>

## Troubleshooting

<details>
<summary><strong>ECC appears twice or hooks fire twice</strong></summary>

The usual cause is installing the Claude plugin and then running `./install.sh --profile full` on top of it.

1. Remove the Claude Code plugin install.
2. Run `node scripts/ecc.js uninstall --dry-run` from the ECC checkout.
3. Remove extra rule folders you manually copied and no longer want.
4. Reinstall once, using one path.

For hook-specific checks, see the [hooks README](hooks/README.md).
</details>

<details>
<summary><strong>My hooks aren't working / "Duplicate hooks file" errors</strong></summary>

**Do NOT add a `"hooks"` field to `.claude-plugin/plugin.json`.** Claude Code v2.1+ automatically loads `hooks/hooks.json` from installed plugins. Explicitly declaring it causes duplicate detection errors. See [#29](https://github.com/affaan-m/ECC/issues/29), [#52](https://github.com/affaan-m/ECC/issues/52), [#103](https://github.com/affaan-m/ECC/issues/103).
</details>

<details>
<summary><strong>Codex marketplace installs but skills do not load</strong></summary>

Run the cache check from an ECC checkout:

```bash
node scripts/codex/check-plugin-cache.js
```

If it reports unresolved parent references, refresh the native cache with `codex plugin marketplace upgrade ecc`, run `codex plugin add ecc@ecc` again, and restart Codex. Registration in `codex plugin list` confirms the marketplace entry, while the cache check verifies that the installed manifest can resolve its skills, MCP configuration, and assets. Use `bash scripts/sync-ecc-to-codex.sh` only when you intentionally need the legacy copied-configuration compatibility path.
</details>

More answers: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) covers memory, hooks, installation, performance, and common error messages. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) tracks workarounds for open Claude Code bugs.

## Background

I've been using Claude Code since the experimental rollout. Won the Anthropic x Forum Ventures hackathon in Sep 2025 with [@DRodriguezFX](https://x.com/DRodriguezFX), built [zenith.chat](https://zenith.chat) entirely with agentic workflows.

These configs are battle-tested across multiple production applications.

---
name: ecc-digest-agents-roster
description: ECC's AGENTS.md, the cross-harness instruction file listing ECC's agent roster, core principles, orchestration, security, style, testing and git guidance; the reusable idea is a single roster table of agent, purpose and when to use it.
---
<!-- ecc-digest:agents-roster@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Agents roster

## What it is
`AGENTS.md` is ECC's top-level instruction file for harnesses that read that name. It opens with a product line (version 2.2.3 at the vendored commit, with counts of agents, skills and commands that the study note says disagree with other ECC files) and five core principles: agent-first delegation, test-driven work with an 80 percent coverage target, security first, immutability, and planning before execution. The main body is a roster table with one row per agent: name, purpose and when to use it (planner, architect, TDD guide, code reviewer, security reviewer, build-error resolver, end-to-end runner, refactor cleaner, doc updater, and one reviewer or build resolver per language). Later sections cover agent orchestration, security guidelines, coding style, testing requirements, the development workflow, a workflow surface policy, git workflow, architecture patterns, performance, project structure and success metrics. The same five principles are repeated in other ECC files.

## The reusable idea
The roster table is the useful format: three columns (agent, purpose, when to use) let a model pick a delegate without opening every agent file, and the "when" column is phrased as a trigger ("after writing or modifying code", "when the build fails") rather than a description. A roster also makes gaps and overlaps visible: two rows with the same trigger mean one agent is redundant.

## Why not adopted
The workbench has its own roster and rules: `agents/README.md`, the agent frontmatter, `agents/team-lead.md` for team playbooks and the model policy in `hooks/model-policy.json`, plus the always-on doctrine in CLAUDE.md and `rules/`. Loading a second instruction file would add always-on tokens and conflicting guidance (for example ECC's immutability rule and coverage target are not workbench rules). The vendored ECC agents that have value are in `library/ecc/agents/`, where the router surfaces the language reviewers in the review lane.

## Upstream paths
- `AGENTS.md`

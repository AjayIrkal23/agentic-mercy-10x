# Model routing — Fable-first specialists (supersedes "/invoke-impl on Opus")

> Always-on. Standing user directive (2026-07-18): **"use fable for everything"** —
> all substantive specialist work runs on **Fable**. This file superseded the older
> /invoke-impl-on-Opus carve-out on 2026-07-18 (backup: `.bak-20260718`).

## Rule

- **Fable-pinned agents** (via `model-policy.json → agent_pins.fable`, enforced by
  `opus-guard.py`): `frontend-uiux-designer`, `implementation-engineer`,
  `backend-implementor-specialist`, `frontend-implementor-specialist`,
  `integrator-specialist`. A `[sonnet]`/`[opus]` label on these is auto-corrected to
  `[fable]`.
- **Fable-pinned /invoke acts** (via `invoke_categories`): IMPLEMENT, REVIEW, AUDIT,
  SPEC, PLAN, DEBUG, DESIGN, DOCS, VERIFY — rendered into the generated `/invoke`
  command by `gen-invoke-commands.py`.
- **Sonnet remains** for cheap read-only helpers: `Explore`, `claude-code-guide`,
  lint/docs lookups. Don't burn Fable on a file search.
- **Implementor routing (Option A, 2026-07-18):** IMPLEMENT surface routing sends
  frontend→`frontend-implementor-specialist`, backend→`backend-implementor-specialist`
  (contract-first, emits `IMPL-REPORT-BE.md ## CONTRACT`), mixed→BE→FE→
  `integrator-specialist` (parity diff + E2E evidence), everything else→
  `implementation-engineer` (general). Source: `autonomous-skill-router.config.json
  → categories.IMPLEMENT.surface_routing`.

## To change

Edit `hooks/model-policy.json` (`agent_pins`, `invoke_categories`) and re-run
`python3 ~/.claude/hooks/gen-invoke-commands.py`. Session overrides still win:
`state/sonnet-only-mode` > `opus-only-mode` > `fable-only-mode`.

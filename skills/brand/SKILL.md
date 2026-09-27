---
name: brand
argument-hint: "[update|review|create] [args]"
metadata:
  author: claudekit
  version: "1.0.0"
description: "ALWAYS invoke for brand voice, visual identity, messaging frameworks, and brand consistency — tone of voice, branded content, marketing copy, style guides, and brand-compliance review of existing assets."
keywords:
  - brand voice
  - tone of voice
  - brand identity
  - visual identity
  - messaging
  - messaging framework
  - brand guidelines
  - style guide
  - brand consistency
  - brand compliance
  - branded content
  - marketing copy
  - tagline
  - positioning
  - brand assets
surfaces:
  - frontend
intents:
  - DESIGN
---

> **ASSET GENERATION — HIGGSFIELD, NOT GEMINI (standing user directive, overrides this skill).**
> This skill's upstream image paths call the Gemini / Imagen / Nano-Banana APIs and expect
> `HIGGSFIELD_MCP (no key needed)` plus the `higgsfield-generate` / `higgsfield-generate` skills. **None of those are configured
> here.** Every raster, video, 3D, or audio asset MUST instead be generated through Higgsfield
> (`mcp__higgsfield__generate_image` / `generate_video` / `generate_3d` / `generate_audio`, skill
> `higgsfield-generate`). Use this skill for its *art direction, specs, styles, and layout
> reasoning*; hand the actual pixel generation to Higgsfield. See
> `~/.claude/rules/higgsfield-frontend-mandate.md`.

# Brand

Brand identity, voice, messaging, asset management, and consistency frameworks.

## When to Use

- Brand voice definition and content tone guidance
- Visual identity standards and style guide development
- Messaging framework creation
- Brand consistency review and audit
- Asset organization, naming, and approval
- Color palette management and typography specs

## Quick Start

**Inject brand context into prompts:**
```bash
node scripts/inject-brand-context.cjs
node scripts/inject-brand-context.cjs --json
```

**Validate an asset:**
```bash
node scripts/validate-asset.cjs <asset-path>
```

**Extract/compare colors:**
```bash
node scripts/extract-colors.cjs --palette
node scripts/extract-colors.cjs <image-path>
```

## Brand Sync Workflow

```bash
# 1. Edit docs/brand-guidelines.md (or use /brand update)
# 2. Sync to design tokens
node scripts/sync-brand-to-tokens.cjs
# 3. Verify
node scripts/inject-brand-context.cjs --json | head -20
```

**Files synced:**
- `docs/brand-guidelines.md` → Source of truth
- `assets/design-tokens.json` → Token definitions
- `assets/design-tokens.css` → CSS variables

## Subcommands

| Subcommand | Description | Reference |
|------------|-------------|-----------|
| `update` | Update brand identity and sync to all design systems | `references/update.md` |

## References

| Topic | File |
|-------|------|
| Voice Framework | `references/voice-framework.md` |
| Visual Identity | `references/visual-identity.md` |
| Messaging | `references/messaging-framework.md` |
| Consistency | `references/consistency-checklist.md` |
| Guidelines Template | `references/brand-guideline-template.md` |
| Asset Organization | `references/asset-organization.md` |
| Color Management | `references/color-palette-management.md` |
| Typography | `references/typography-specifications.md` |
| Logo Usage | `references/logo-usage-rules.md` |
| Approval Checklist | `references/approval-checklist.md` |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/inject-brand-context.cjs` | Extract brand context for prompt injection |
| `scripts/sync-brand-to-tokens.cjs` | Sync brand-guidelines.md → design-tokens.json/css |
| `scripts/validate-asset.cjs` | Validate asset naming, size, format |
| `scripts/extract-colors.cjs` | Extract and compare colors against palette |

## Templates

| Template | Purpose |
|----------|---------|
| `templates/brand-guidelines-starter.md` | Complete starter template for new brands |

## Routing

1. Parse subcommand from `$ARGUMENTS` (first word)
2. Load corresponding `references/{subcommand}.md`
3. Execute with remaining arguments

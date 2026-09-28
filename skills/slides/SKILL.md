---
name: slides
argument-hint: "[topic] [slide-count]"
description: "HTML slide decks: Chart.js data slides, design-token-driven layouts, responsive slide structure, copywriting formulas, and slide strategy. For .pptx files use anthropic-skills:pptx instead."
when_to_use: Use when the deliverable is an HTML presentation; route .pptx/.potx requests to anthropic-skills:pptx and Artifact decks to the Slides artifact type.
metadata:
  author: claudekit
  version: "1.0.0"
  category: design
  surfaces: [frontend]
  triggers:
    keywords: [slide, slides, slide deck, deck, presentation, pitch deck, html presentation, chart.js, data slide, slide layout, speaker notes]
    intents: [design]
---

# Slides

Strategic HTML presentation design with data visualization.

## When to Use

- Marketing presentations and pitch decks
- Data-driven slides with Chart.js
- Strategic slide design with layout patterns
- Copywriting-optimized presentation content

## Subcommands

| Subcommand | Description | Reference |
|------------|-------------|-----------|
| `create` | Create strategic presentation slides | `references/create.md` |

## References (Knowledge Base)

| Topic | File |
|-------|------|
| Layout Patterns | `references/layout-patterns.md` |
| HTML Template | `references/html-template.md` |
| Copywriting Formulas | `references/copywriting-formulas.md` |
| Slide Strategies | `references/slide-strategies.md` |

## Routing

1. Parse subcommand from `$ARGUMENTS` (first word)
2. Load corresponding `references/{subcommand}.md`
3. Execute with remaining arguments

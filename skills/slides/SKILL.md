---
name: slides
argument-hint: "[topic] [slide-count]"
metadata:
  author: claudekit
  version: "1.0.0"
description: "ALWAYS invoke when creating HTML presentations or slide decks — Chart.js data slides, design-token-driven layouts, responsive slide structure, copywriting formulas, and contextual slide strategy."
keywords:
  - slide
  - slides
  - slide deck
  - deck
  - presentation
  - pitch deck
  - keynote
  - powerpoint alternative
  - html presentation
  - chart.js
  - data slide
  - slide layout
  - speaker notes
surfaces:
  - frontend
intents:
  - DESIGN
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

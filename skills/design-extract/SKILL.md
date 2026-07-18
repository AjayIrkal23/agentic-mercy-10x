---
name: design-extract
description: "ALWAYS invoke when a reference URL is available to extract complete design systems from live websites — tokens, Tailwind config, typography, colors, and component anatomy. Commands: /extract, /grade, /battle, /remix, /pack, /theme-swap, /brand, /pair."
---

# Extract Design Language

Extract the complete design language from any website URL. Generates 8 output files covering colors, typography, spacing, shadows, components, breakpoints, animations, and accessibility.

## Prerequisites

Ensure `designlang` is available. Install if needed:

```bash
npm install -g designlang
```

Or use npx (no install required):

```bash
npx designlang <url>
```

## Process

1. **Run the extraction** on the provided URL:

```bash
npx designlang <url> --screenshots
```

For multi-page crawling: `npx designlang <url> --depth 3 --screenshots`
For dark mode: `npx designlang <url> --dark --screenshots`

2. **Read the generated markdown file** to understand the design:

```bash
cat design-extract-output/*-design-language.md
```

3. **Present key findings** to the user:
   - Primary color palette with hex codes
   - Font families in use
   - Spacing system (base unit if detected)
   - WCAG accessibility score
   - Component patterns found
   - Notable design decisions (shadows, radii, etc.)

4. **Offer next steps:**
   - Copy `*-tailwind.config.js` into their project
   - Import `*-variables.css` into their stylesheet
   - Paste `*-shadcn-theme.css` into globals.css for shadcn/ui users
   - Import `*-theme.js` for React/CSS-in-JS projects
   - Import `*-figma-variables.json` into Figma for designer handoff
   - Open `*-preview.html` in a browser for a visual overview
   - Use the markdown file as context for AI-assisted development

## Output Files (8)

| File | Purpose |
|------|---------|
| `*-design-language.md` | AI-optimized markdown — the full design system for LLMs |
| `*-preview.html` | Visual HTML report with swatches, type scale, shadows, a11y |
| `*-design-tokens.json` | W3C Design Tokens format |
| `*-tailwind.config.js` | Ready-to-use Tailwind CSS theme |
| `*-variables.css` | CSS custom properties |
| `*-figma-variables.json` | Figma Variables import format |
| `*-theme.js` | React/CSS-in-JS theme object |
| `*-shadcn-theme.css` | shadcn/ui theme CSS variables |

## CLI Commands

### Core Extraction
- `designlang <url>` — Colors, typography, spacing, shadows, radii, CSS vars, breakpoints, animations, components
- `designlang apply <url>` — Auto-detect framework and write tokens to your project
- `designlang clone <url>` — Generate a working Next.js starter with extracted design

### Grading & Comparison
- `designlang grade <url>` — Shareable HTML Design Report Card — letter grade, 8 dimensions, evidence, strengths + fixes
- `designlang battle <urlA> <urlB>` — Head-to-head graded battle card with verdict, dimension table, palette comparison

### Design Transformation
- `designlang remix <url> --as <vocab>` — Restyle the audited page in another vocabulary (brutalist / swiss / art-deco / cyberpunk / soft-ui / editorial)
- `designlang theme-swap <url> --primary <hex>` — Recolour the extracted design around a new brand primary
- `designlang pair <urlA> <urlB>` — Fuse two designs across 7 axes (colours/type/spacing/shape/motion/voice/components)

### Documentation & Analysis
- `designlang brand <url>` — Full editorial brand-guidelines document (13 chapters)
- `designlang pack <url>` — Bundle every output into one polished design-system directory
- `designlang drift <url> --tokens <file>` — Check local tokens for drift against a live site
- `designlang visual-diff <before> <after>` — Side-by-side HTML diff of two URLs

### MCP Server
- `designlang mcp` — Launch stdio MCP server for Cursor / Claude Code / agent integration

## Claude Code Slash Commands

Inside Claude Code sessions (via plugin):
- `/extract <url>` — Full extraction output
- `/grade <url>` — Design Report Card
- `/battle <urlA> <urlB>` — Comparative analysis
- `/remix <url> --as <vocab>` — Style transformation
- `/pack <url>` — Bundled design system
- `/theme-swap <url> --primary <hex>` — Recolour around a new brand primary
- `/brand <url>` — Full editorial brand-guidelines document
- `/pair <urlA> <urlB>` — Fuse two designs

## Additional Commands

- **Compare two sites:** `npx designlang diff <urlA> <urlB>`
- **View history:** `npx designlang history <url>`

## Options

| Flag | Description |
|------|-------------|
| `--out <dir>` | Output directory (default: `./design-extract-output`) |
| `--dark` | Also extract dark mode color scheme |
| `--depth <n>` | Crawl N internal pages for site-wide extraction |
| `--screenshots` | Capture component screenshots (buttons, cards, nav) |
| `--wait <ms>` | Wait time after page load for SPAs |
| `--framework <type>` | Generate only specific theme (`react` or `shadcn`) |

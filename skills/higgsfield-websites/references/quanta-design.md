# Skill: Quanta Design

**Higgsfield-SDK apps only.** Use Quanta ONLY for app surfaces that integrate the
Higgsfield fnf SDK — generation consoles and fnf-backed tools (image/video
generation, media upload, profile, workspace, credits, generation feed/history) —
for layout, styling, fonts, buttons, components, responsive composition,
empty/loading/error states, and premium polish.

**Do not use for anything that does not call the Higgsfield SDK** — marketing/
landing pages, portfolios, brochure/creative sites, and general SaaS/dashboards/
tools build from their template recipe with custom Tailwind/CSS, not
`@higgsfield/quanta/*` components or q-prefixed semantic utilities.

The visual direction comes from the template recipe the agent picked (its palette,
type, accent, mood) — Quanta is the IMPLEMENTATION layer for the fnf app chrome,
not a second design system. Take palette / type / accent / mood from the recipe
and execute the surface with Quanta tokens and components; the craft skill for
these Higgsfield-SDK surfaces (`references/minimalist-ui.md`) still governs HOW to
execute it well.

Before coding, read `app/packages/quanta/ai/AGENTS.md`. That package guide is the
canonical Quanta API/token reference. This skill explains how this template must
compose Quanta into generated fnf-SDK app UIs.

## Template Wiring

Quanta is already wired through `app/src/styles.css`.

Keep these pieces:

- `@import "@higgsfield/quanta/tailwind.css";`
  - This single Tailwind entry imports Quanta primitives, theme variables,
    typography, z-index, border-width, and q-* component utilities.
- `@source "../packages/quanta/src";`
  - Required because Quanta is vendored in `app/packages/`; Tailwind must scan
    component source so literal class strings are generated.
- `@theme { --spacing: 0.25rem; }`
  - Restores native Tailwind spacing for generated app layout.
- `@theme inline { ... }`
  - Maps shadcn-style semantic aliases to Quanta variables so legacy scaffold
    pieces still render while new UI uses Quanta.
- `bootstrapScript()` in `app/src/routes/__root.tsx`
  - Keeps persisted theme/brand from flashing on first paint.

Do not remove or duplicate these imports. Do not import Quanta CSS again inside
individual components.

## Current Spacing And Token Rules

This is the rule agents must remember:

- **App layout spacing is native Tailwind:** `p-4`, `px-6`, `gap-3`, `mt-6`,
  `h-10`, `w-80`, `min-h-dvh`.
- **Quanta semantic styling is q-prefixed:** `bg-q-background-primary`,
  `text-q-body-md-regular`, `border-q-border-subtle`, `z-q-modal`.
- **Old numeric spacing classes are wrong for app layout:** do not write
  `p-400`, `px-400`, `gap-200`, `mt-300`.
- **Do not use raw q-spacing vars in app code:** avoid `p-q-400` unless you are
  intentionally maintaining Quanta internals. Generated app screens should use
  native spacing.

Good:

```tsx
<main className="min-h-dvh bg-q-background-primary p-4 text-q-text-primary tablet:p-6">
  <section className="grid gap-4 desktop:grid-cols-[280px_1fr]">
    ...
  </section>
</main>
```

Bad:

```tsx
<main className="bg-background-primary px-400 py-300 text-sm font-medium">
  ...
</main>
```

## Component Priority

Use Quanta components before legacy `app/src/components/ui/*`, before direct Radix,
and before third-party equivalents.

| Need | Use |
|---|---|
| Actions and links | `Button` from `@higgsfield/quanta/button` |
| Top navigation | `NavigationMenu` from `@higgsfield/quanta/navigation-menu` |
| Text fields | `Input` from `@higgsfield/quanta/input` |
| Multi-line text / prompts | `Textarea` from `@higgsfield/quanta/textarea` |
| Binary settings | `Switch`, `Checkbox`, `Toggle` |
| Exclusive choices | `RadioGroup`, `RadioLabel` |
| Segmented modes/views | `Tabs` |
| Menus/model pickers | `Dropdown` |
| Command palette/search actions | `Command` from `@higgsfield/quanta/cmdk` |
| Dialog/editor/confirm | `Modal` |
| Edge sheet/mobile panel | `Vault` |
| Toasts | `Toaster`, `toast` from `@higgsfield/quanta/sonner` |
| Progress/loading | `Progress` |
| Metadata/status | `Badge`, `Tag`, `Dot`, `Kbd`, `Avatar`, `Divider` |

Legacy shadcn-style components may remain for scaffold compatibility, but new
client UI should not start there. Also do not import `cmdk`, `sonner`, or
`vaul` directly for new UI; Quanta already wraps those interaction patterns with
the correct visual system.

## Core Imports

```tsx
import { Button } from '@higgsfield/quanta/button'
import { Input } from '@higgsfield/quanta/input'
import { Textarea } from '@higgsfield/quanta/textarea'
import { NavigationMenu } from '@higgsfield/quanta/navigation-menu'
import { Tabs } from '@higgsfield/quanta/tabs'
import { Dropdown } from '@higgsfield/quanta/dropdown'
import { Modal } from '@higgsfield/quanta/modal'
import { Vault } from '@higgsfield/quanta/vault'
import { Toaster, toast } from '@higgsfield/quanta/sonner'
```

Mount one `<Toaster />` near the root shell before calling `toast.*`.

## Premium App Layout Rules

Generated app UIs must look designed, not like raw low-level layouts.

1. **Start with the product surface.** If the task is a notes app, editor,
   dashboard, generator, gallery, CRM, or workspace, make that actual interface
   the first screen.
2. **Use a stable shell.** Prefer `min-h-dvh bg-q-background-primary
   text-q-text-primary`, a header/top bar when actions exist, and scroll regions
   with `min-h-0 overflow-auto`.
3. **Use meaningful regions.** Most product tools need a sidebar/list, a main
   work area, and optionally an inspector/action rail.
4. **Give regions enough space.** Start with `p-4 tablet:p-6 desktop:p-8`,
   `gap-4 tablet:gap-6`, and tighten only for dense tables/toolbars.
5. **Constrain text and panels.** Use `min-w-0`, `truncate`, `max-w-*`,
   `grid-cols-*`, and `minmax(0,1fr)` patterns so content never overlaps.
6. **Make state visible.** Selected rows, hover states, focus states, empty
   states, loading states, and errors should be designed surfaces, not bare text.
7. **Avoid card soup.** Do not put cards inside cards inside cards. Use shells,
   sidebars, bands, lists, workspaces, and repeated item cards only where they
   are semantically useful.
8. **Use icons for tools.** Icon-only buttons need `iconOnly` and an accessible
   label. Do not write text labels into tiny square controls.
9. **Keep palettes balanced.** Quanta already provides dark surfaces and brand
   accents. Avoid one-note purple/blue gradients, random blur blobs, and raw
   decorative shapes.

## Layout Recipes

### App shell

```tsx
<div className="min-h-dvh bg-q-background-primary text-q-text-primary">
  <header className="flex h-14 items-center justify-between border-b border-q-border-subtle px-4 tablet:px-6">
    <h1 className="text-q-title-md-semi-bold">Workspace</h1>
    <Button size="sm">Create</Button>
  </header>
  <main className="grid min-h-[calc(100dvh-3.5rem)] grid-cols-1 desktop:grid-cols-[280px_minmax(0,1fr)]">
    <aside className="min-h-0 border-r border-q-border-subtle p-4">...</aside>
    <section className="min-h-0 overflow-auto p-4 tablet:p-6">...</section>
  </main>
</div>
```

### Split editor/tool

Use this for notes, editors, media generators, project feeds, and dashboards.

```tsx
<main className="grid min-h-dvh grid-cols-1 bg-q-background-primary text-q-text-primary desktop:grid-cols-[320px_minmax(0,1fr)_360px]">
  <aside className="min-h-0 overflow-auto border-r border-q-border-subtle p-4">...</aside>
  <section className="min-h-0 overflow-auto p-6">...</section>
  <aside className="min-h-0 overflow-auto border-l border-q-border-subtle p-4">...</aside>
</main>
```

Collapse sidebars behind `Tabs`, `Dropdown`, or `Vault` on smaller screens when
space is tight.

### Form panel

```tsx
<section className="mx-auto grid w-full max-w-3xl gap-5 p-4 tablet:p-6">
  <div className="grid gap-2">
    <h1 className="text-q-title-lg-semi-bold">Generate image</h1>
    <p className="text-q-body-md-regular text-q-text-secondary">Tune the prompt and settings.</p>
  </div>
  <div className="grid gap-4 rounded-lg border border-q-border-subtle bg-q-background-secondary p-4">
    <Textarea label="Prompt" rows={5} />
    <Button>Generate</Button>
  </div>
</section>
```

Use cards for real grouped content, not as a wrapper around every section.

## Typography Rules

Use Quanta composite typography utilities. Do not make the whole app
`text-sm font-medium`.

| Use | Utility |
|---|---|
| App page title / hero in a tool surface | `text-q-headline-sm-semi-bold` or `text-q-headline-md-semi-bold` |
| Large in-app display (generator headline) | `text-q-display-lg-bold` or `text-q-display-md-bold` |
| Section title | `text-q-title-md-semi-bold` |
| Item title | `text-q-title-sm-semi-bold` or `text-q-label-lg-semi-bold` |
| Body | `text-q-body-md-regular` |
| Meta/help | `text-q-body-sm-regular` or `text-q-caption-sm-medium` |
| Code/ids | `text-q-mono-sm-regular` |

Color text with semantic utilities:

- Primary: `text-q-text-primary`
- Supporting: `text-q-text-secondary`
- Low emphasis: `text-q-text-tertiary`
- Disabled: `text-q-text-disabled`
- On brand/inverse surfaces: `text-q-text-inverse`

## Button Rules

Use `@higgsfield/quanta/button`.

```tsx
import { Button } from '@higgsfield/quanta/button'
```

- Main page action: `variant="primary" size="md"`.
- Supporting action: `secondary` or `outline`.
- Toolbar/low-emphasis action: `tertiary` or `ghost`.
- Destructive action: `danger` or `dangerSoft`.
- Soft brand emphasis: `brandSoft`.
- Dense toolbars use `size="sm"` or `size="xs"`.
- Icon-only buttons must pass `iconOnly`, fixed dimensions from the component,
  and an accessible label.

## State Rules

Every generated app UI should have credible states:

- Loading: `Progress`, skeleton-like surfaces, or disabled controls.
- Empty: a centered or region-local empty state with a title, supporting text,
  and a relevant action.
- Error: a styled message with retry/action; do not dump raw stack traces.
- Disabled/unavailable: disabled controls plus short explanation when needed.
- Selected/current: visible selected state independent of hover.

## Debugging Missing Styles

When styles look missing or spacing collapses:

1. Check `app/src/styles.css` still imports `@higgsfield/quanta/tailwind.css`.
2. Check `@source "../packages/quanta/src";` is present.
3. Check `@theme { --spacing: 0.25rem; }` is still present after the Quanta
   import to restore normal Tailwind layout spacing in generated app UIs.
4. Check the app uses native spacing (`p-4`, `gap-2`) and q-prefixed semantic
   utilities (`bg-q-*`, `text-q-*`).
5. Check imports are from Quanta subpaths like `@higgsfield/quanta/button`.
6. Check `app/packages/quanta/package.json` still depends on `@base-ui/react`.

Run a quick stale-spacing scan when layouts look wrong:

```bash
rg 'px-400|p-400|py-300|mt-300|gap-200' app/src skills app/packages/quanta/ai
```

Fix any hits in app/source code to native spacing (`px-4`, `py-3`, `mt-3`,
`gap-2`). It is fine for docs to mention old classes only inside bad examples.

## Anti-Patterns

- Raw palette classes like `bg-red-500`, `text-zinc-400`.
- Invented `q-*` utilities like `bg-q-card-primary`.
- Old spacing token classes: `p-400`, `px-400`, `gap-200`, `mt-300`.
- Raw q-spacing in app code: `p-q-400`, unless maintaining Quanta internals.
- Arbitrary text sizes such as `text-[13px]`.
- Splitting Quanta typography into `text-xl font-semibold`.
- Floating loose text/actions on the canvas without a shell or region.
- Hover-only selected states.
- Empty/loading/error states as bare text.
- Direct `cmdk`, `sonner`, `vaul`, Radix, or Base UI usage for new app UI when
  Quanta already provides the pattern.

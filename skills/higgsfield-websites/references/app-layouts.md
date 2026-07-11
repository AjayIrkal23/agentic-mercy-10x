# app-layouts — the standard Higgsfield app layouts (`type: "app"` builds ONLY)

A `type: "app"` product must look and feel like a Higgsfield product. Instead of
inventing app chrome from scratch, START from one of the four standard layouts
below — they mirror how Higgsfield's own products are laid out, and each
one ships as a READY SCAFFOLD in the template under **`app/src/layouts/`** (read
`app/src/layouts/AGENTS.md`). Copy the closest scaffold into your route and
adapt it: the scaffolds are prop-driven (data, handlers, and slot nodes all
arrive via props) and each file's header comment carries its exact fnf-react
wiring recipe. **If the user asks for a different layout, build what they ask
for** — the standard layouts are the default, not a cage (a custom layout is
still built with Quanta components + `q-` tokens).

Every layout is composed from Quanta (`references/quanta-design.md`,
`app/packages/quanta/ai/AGENTS.md` for the canonical API) and must be a real
end-to-end app per `references/fnf-sdk.md`: Higgsfield auth
(`references/auth.md`), server-side generation submit + poll, results rendered
with `higgsfield-generation-card.tsx`, and the app's own product state in D1
(saved/favorited, collections, presets, history).

## Choosing a layout

| Product shape | Layout | Scaffold file |
|---|---|---|
| Multi-asset creative workspace: prompt → many generations, browse/organize output | **Marketing studio** | `app/src/layouts/marketing-studio-layout.tsx` |
| Guided flow with a fixed sequence of choices ending in one result | **Stepper** | `app/src/layouts/stepper-layout.tsx` |
| One transform, minimal inputs (e.g. swap a face, restyle one photo) | **Simple app** | `app/src/layouts/app-form.tsx` |
| Enhance/convert ONE uploaded asset with a couple of options | **Upscaler** | `app/src/layouts/upscaler-layout.tsx` |
| Turn source media into short-form clips with presets + a session library | **Shorts studio** | `app/src/layouts/shorts-studio-layout.tsx` |
| Anything else the user describes | Custom — compose it from Quanta, keep the anatomy rules below | — |

## 1. Marketing studio — the workspace

The full creative-tool layout, mirroring Higgsfield's Marketing Studio
(higgsfield.ai/marketing-studio/product). Scaffold:
`app/src/layouts/marketing-studio-layout.tsx`.

- **Left rail** — Quanta `Sidebar` (`@higgsfield/quanta/sidebar`): logo/title in
  the header, nav rows for the app's surfaces (Create, Library/History,
  Collections, Settings). Collapsible.
- **Gallery** — a controls row (feed filters, view controls — slot) above a
  responsive grid of generation results (`higgsfield-generation-card.tsx`;
  real empty state copy; skeleton `loader` while polling).
- **Docked floating form** — the signature region: a bottom-centered, floating
  rounded panel OVER the gallery built from **`PromptBox`**
  (`@higgsfield/quanta/prompt-box`): `PromptBox.Attachments` (reference/upload
  chips row), `PromptBox.Input` (auto-grows, Enter submits; placeholder like
  "Describe the image you want to create..."), settings CHIPS in
  `PromptBox.Toolbar` (batch size, quality, aspect ratio, brand-kit picks —
  chips, not full-width selects), and cost + `PromptBox.Counter` +
  `PromptBox.Submit` in `PromptBox.Actions`. Use PromptBox for the prompt
  surface in EVERY layout that takes a prompt — never hand-roll it.
- Product state in D1: every generation the user keeps, plus
  collections/projects.

## 2. Stepper — the staged flow

A staged pipeline for products where each step's ACTION produces the next
step's content, mirroring Higgsfield's Shots app (higgsfield.ai/apps/shots).
Scaffold: `app/src/layouts/stepper-layout.tsx`. This is NOT a Back/Continue
wizard:

- A step indicator across the top — numbered circles + labels (e.g. "Upload" →
  "Grid" → "Upscale"), thin dividers between them; the active step is full
  opacity, others dimmed. Steps already visited are clickable (back-jumping is
  allowed); unvisited forward steps are locked.
- A full-height STAGE renders the active step's content (upload card → result
  grid → final output).
- A step-scoped ACTIONS ROW under the stage carries that step's controls + its
  primary action (e.g. aspect-ratio `Select` + a `marketingPrimary` "Generate"
  button; the final step swaps to secondary "Start new" / "Go to library"
  actions). Completing the action is what advances the flow — there is no
  generic Continue button.
- Persist the flow state so a refresh doesn't lose progress (D1 or route state).

## 3. Simple app — the one-shot tool (faceswap-style)

A single screen, no navigation: two or three inputs and one primary action.
The scaffold here is **`AppForm`** (`app/src/layouts/app-form.tsx`) — the form
from Higgsfield's own face-swap app (higgsfield.ai/apps/face-swap). It is ONLY
the form; you compose the page around it.

- `AppForm` anatomy: input-fields slot → optional mode toggle + settings rows →
  submit row (optional accessory + one full-width `marketingPrimary` Button —
  the accent generate CTA — with the credit cost) → quiet helper line
  ("You have N free generations left").
- Inputs, face-swap style: two upload cards side by side on desktop
  (`flex flex-col gap-3 md:flex-row`, each `flex-1`), labelled like the real
  app — "Target Image" ("Upload the photo with face to replace") and
  "Your Photo" ("Upload the face you want to insert").
- Page composition is yours: the face-swap app pairs the form with a title block and a
  large preview panel (square on desktop) that shows demo media until the
  result replaces it — a good default; results carry download / try again /
  save actions.
- History strip (the user's previous runs, from D1) under the tool — optional
  but recommended.

## 4. Upscaler — the single-asset enhancer

One asset in, an enhanced asset out, mirroring Higgsfield's Upscale tool
(higgsfield.ai/upscale). Scaffold: `app/src/layouts/upscaler-layout.tsx`.

- **Media stage** (left, the wide column): empty = a dashed-border upload card
  with an optional before/after example, a bold uppercase title ("Upscale"), a
  muted line like "Upload your images or videos to enhance their resolution
  and quality.", and an upload Button; with media = the asset full-bleed, with
  overlay slots for progress/failure and a toolbar (compare toggle +
  download/save/delete actions) once done.
- **Settings panel** (right, ~21rem, appears once media is loaded): a header
  with the tool name + a ghost "Reset", scrollable settings (model `Select`,
  scale-factor toggle group, an "Advanced settings" collapsible), and a STICKY
  full-width `marketingPrimary` submit with the credit cost.
- Result: a before/after compare (slider where feasible), then download + save.
- Recent enhancements from D1 below.

## 5. Shorts studio — presets + session library

Source media in, short-form clips out, mirroring Higgsfield's Shorts Studio
(higgsfield.ai/shorts-studio). Scaffold: `app/src/layouts/shorts-studio-layout.tsx`
(two exports).

- **`ShortsStudioLayout`** — the tabbed studio shell: Quanta `Tabs` with e.g.
  "Presets" / "History" / "How it works", a per-tab controls slot on the right
  of the tab row (search on Presets; a "Liked" filter on History), and the
  active tab's content below: a preset-card grid (preview + name + a "Create
  custom preset" card), a sessions grid (cover + generating/failed status
  badge + like/download actions), or guide copy.
- **`ShortsStudioForm`** — the creation form card: fields slot (a preset
  picker card with a "Change" action, a media upload field with constraints
  copy like max duration/size, an "Output ratio:" Vertical/Landscape toggle),
  then a footer with an optional hint line and a tall full-width
  `marketingPrimary` "Generate" button carrying the credit cost.

## Anatomy rules (all layouts, incl. custom)

- The GENERATE action always uses Button `variant="marketingPrimary"` (the
  accent CTA every Higgsfield product uses); plain `primary` is for ordinary
  actions and navigation. `PromptBox.Submit` already defaults to it.
- Quanta components before custom markup: `Button`, `Input`, `Textarea`,
  `Dropdown`, `Select`, `Modal`, `Tabs`, `Sidebar`, `Avatar`, `Badge`,
  `Tooltip`, `sonner` toasts, `loader`. Spacing = native Tailwind (`p-4`,
  `gap-3`); semantics = `q-` utilities (`bg-q-background-primary`,
  `text-q-body-md-regular`).
- The signed-out state, auth guards, `/api/user`, cost preview, submit/poll
  routes, and D1 persistence are MANDATORY — see the checklist in
  `references/fnf-sdk.md`.
- Generation results always render through `higgsfield-generation-card.tsx`,
  never a bare `<img>`.
- Polish per `references/minimalist-ui.md`: real empty/loading/error states,
  keyboard focus states, responsive down to mobile.

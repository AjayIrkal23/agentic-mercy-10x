# Skill: SEO Meta Tags

The `__root.tsx` template ships with placeholder meta (`<App Title>`, generic description). This skill ensures those placeholders NEVER reach production. Every deploy must have real, keyword-targeted meta tags.

## Global Meta in `__root.tsx`

Set these in the root route's `head()` function. They apply site-wide and are overridden per-route where needed.

```tsx
export const Route = createRootRouteWithContext()({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'Acme Studio — Creative Agency for Bold Brands' },
      { name: 'description', content: 'Acme Studio builds brand identities, websites, and campaigns that stand out. Based in NYC, working worldwide.' },
      { name: 'author', content: 'Acme Studio' },
      { name: 'theme-color', content: '#0A0A0A' },
      { name: 'robots', content: 'index, follow, max-image-preview:large' },
      { property: 'og:type', content: 'website' },
      { property: 'og:site_name', content: 'Acme Studio' },
      { property: 'og:locale', content: 'en_US' },
      { name: 'twitter:card', content: 'summary_large_image' },
    ],
  }),
  // ...
});
```

## Per-Route Meta in Page `head()`

Each page route overrides title, description, and OG tags. This goes in the route definition, not the component.

```tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/services')({
  head: () => ({
    meta: [
      { title: 'Services — Acme Studio' },
      { name: 'description', content: 'Brand identity, web design, and digital campaigns. See what Acme Studio can build for you.' },
      { property: 'og:title', content: 'Services — Acme Studio' },
      { property: 'og:description', content: 'Brand identity, web design, and digital campaigns.' },
      { property: 'og:url', content: 'https://acme-studio.higgsfield.app/services' },
      { property: 'og:image', content: 'https://acme-studio.higgsfield.app/og-services.png' },
      { name: 'twitter:title', content: 'Services — Acme Studio' },
      { name: 'twitter:description', content: 'Brand identity, web design, and digital campaigns.' },
    ],
    links: [
      { rel: 'canonical', href: 'https://acme-studio.higgsfield.app/services' },
    ],
  }),
  component: ServicesPage,
});
```

## Title Formula

- **Homepage:** `[Brand] — [Tagline]` → `Acme Studio — Creative Agency for Bold Brands`
- **Subpages:** `[Page] — [Brand]` → `Services — Acme Studio`

Keep titles under 60 characters. The brand always appears.

## Description Rules

- 150-160 characters max. Google truncates beyond that.
- Primary keyword in the first 100 characters.
- Write for humans — it shows in search result snippets.
- Derive from intake: the user's stated purpose/service IS the description seed.

## Canonical URL Pattern

All Higgsfield apps follow: `https://<slug>.higgsfield.app/<path>`

- Homepage: `https://acme-studio.higgsfield.app`
- Subpage: `https://acme-studio.higgsfield.app/services`
- No trailing slash. No query params. No fragments.

## Robots Directive

| Page type | `robots` value |
|---|---|
| Public pages (homepage, services, about, blog) | `index, follow, max-image-preview:large` |
| Auth pages, admin, dashboard | `noindex, nofollow` |
| Legal (privacy, terms) | `index, nofollow` |

Set the default in `__root.tsx`. Override per-route for protected pages.

## Deriving Values from Intake

Map user input directly:

| Intake field | Meta target |
|---|---|
| Brand / business name | `title` (brand part), `og:site_name`, `author` |
| Purpose / tagline | `title` (tagline part), homepage `description` |
| Primary service / product | Subpage `description` seed |
| Brand color | `theme-color` |
| Logo / hero image | `og:image` |

## Page metadata file (`app/src/app-meta.json`) + cover video

`app/src/app-meta.json` is the machine-editable page-metadata file the template
reads at BUILD time for the global head, and the marketplace syncs onto the
website's feed/listing card on every deploy. Its keys:

```jsonc
{
  "og_title":       "…",   // browser <title> + og:title
  "og_description": "…",   // meta description + og:description
  "og_image_url":   "…",   // og:image + twitter:image (the feed card cover)
  "favicon_url":    "…",   // <link rel="icon">
  "og_video_url":   "…"    // og:video — the COVER VIDEO (feed cards play it on hover)
}
```

Fill the four text/image keys with real values before any production deploy or
publish (URLs: absolute https, or a root-relative path to a file in
`app/public/` — it is resolved against the site's own host).

**Cover video (`og_video_url`).** The animated counterpart of the cover image —
the Higgsfield feed plays it on the website's card. It is OPTIONAL and costs
credits to produce, so:

1. **ASK THE USER FIRST.** Offer it when publishing ("want a short cover video
   for the feed card?"); never generate one unprompted.
2. If yes: generate a SHORT seamless loop (3-6s, no cuts, loop-friendly motion)
   of the site's hero visual with the Higgsfield video tools (the video-loop
   recipe in `references/asset-system.md` / `references/wow-maker.md` applies).
3. Put the result where the card can load it: download it into `app/public/`
   (e.g. `app/public/cover-video.mp4`) and set
   `"og_video_url": "/cover-video.mp4"`, or use the generation result's hosted
   https URL directly.
4. Commit + deploy — the metadata (and the feed card) update on the next
   deploy, like every other `app-meta.json` change.

## Pitfalls

1. **Duplicate titles across routes.** Every page needs a unique `title` and `description`. Copy-paste from root is the #1 SEO mistake.
2. **Missing `og:image`.** Social shares without an image get 80% less engagement. Use a 1200x630 image minimum. If no custom OG image exists, use the hero or logo on a colored background.
3. **Placeholder text in production.** Search `__root.tsx` for `App Title`, `MyApp`, or `Lorem` before every deploy. Automated check: the build should grep for these.
4. **Description too short or generic.** "Welcome to our website" is not a description. It must describe what the user gets.
5. **Canonical mismatch.** The canonical URL in `head()` must exactly match the deployed URL. Wrong canonical = Google ignores the page.

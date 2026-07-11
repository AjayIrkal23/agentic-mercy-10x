# Skill: SEO Technical Foundations

Technical SEO infrastructure that every Higgsfield website needs. This skill covers the server routes, headers, and performance patterns that search engines require before they'll properly index a site.

## robots.txt Server Route

Create `app/src/routes/robots.txt.ts`:

```ts
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/robots')({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const origin = new URL(request.url).origin;
        const body = [
          'User-agent: *',
          'Allow: /',
          '',
          `Sitemap: ${origin}/sitemap.xml`,
        ].join('\n');

        return new Response(body, {
          status: 200,
          headers: { 'Content-Type': 'text/plain' },
        });
      },
    },
  },
});
```

The file path is `robots.txt.ts` — TanStack Start maps the `.txt` extension to serve at `/robots.txt`. Origin is derived from the request so it works in both preview and production.

## sitemap.xml Server Route

Create `app/src/routes/sitemap.xml.ts`:

### Single-page site (landing page)

```ts
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/sitemap')({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const origin = new URL(request.url).origin;
        const today = new Date().toISOString().split('T')[0];

        const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>${origin}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>`;

        return new Response(xml, {
          status: 200,
          headers: { 'Content-Type': 'application/xml' },
        });
      },
    },
  },
});
```

### Multi-page site

```ts
import { createFileRoute } from '@tanstack/react-router';

const ROUTES = [
  { path: '/', priority: '1.0', changefreq: 'weekly' },
  { path: '/services', priority: '0.8', changefreq: 'monthly' },
  { path: '/about', priority: '0.6', changefreq: 'monthly' },
  { path: '/contact', priority: '0.6', changefreq: 'monthly' },
  { path: '/blog', priority: '0.7', changefreq: 'weekly' },
];

export const Route = createFileRoute('/sitemap')({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const origin = new URL(request.url).origin;
        const today = new Date().toISOString().split('T')[0];

        const urls = ROUTES.map(
          (r) => `  <url>
    <loc>${origin}${r.path === '/' ? '' : r.path}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${r.changefreq}</changefreq>
    <priority>${r.priority}</priority>
  </url>`
        ).join('\n');

        const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>`;

        return new Response(xml, {
          status: 200,
          headers: { 'Content-Type': 'application/xml' },
        });
      },
    },
  },
});
```

Update the `ROUTES` array when adding pages. Keep paths in sync with actual route files.

## Security Headers in server.ts

Security headers (CSP, HSTS, etc.) are not defined here — they have one
canonical owner: `applySecurityHeaders()` in
`app/src/lib/security-headers.server.ts`. Import it in `app/src/server.ts` and
wrap every response (including redirects and error responses):

```ts
import { applySecurityHeaders } from './lib/security-headers.server';

export default {
  async fetch(request: Request, env: any) {
    try {
      const response = await handler.fetch(request, env);
      return applySecurityHeaders(response);
    } catch (error) {
      return applySecurityHeaders(new Response('Internal Server Error', { status: 500 }));
    }
  },
};
```

Do not define a second header function in this file. For the full rules
(framing/CSP rationale, what to keep, what never to set), see
`references/security-worker-hardening.md`.

## Trailing Slash Normalization

Add this at the top of the fetch handler in `app/src/server.ts`, before the `handler.fetch` call. Duplicate URLs (with and without trailing slash) split link equity.

```ts
const url = new URL(request.url);
if (url.pathname !== '/' && url.pathname.endsWith('/')) {
  url.pathname = url.pathname.slice(0, -1);
  return Response.redirect(url.toString(), 301);
}
```

## Canonical URLs

Every page route's `head()` must include a canonical link. This is the single source-of-truth URL for that page.

```ts
export const Route = createFileRoute('/about')({
  head: () => ({
    links: [
      { rel: 'canonical', href: 'https://acme-studio.higgsfield.app/about' },
    ],
    meta: [
      { title: 'About — Acme Studio' },
      // ... other meta
    ],
  }),
  component: AboutPage,
});
```

Pattern: `https://<slug>.higgsfield.app/<path>` — no trailing slash, no query params.

## Performance Hints in `__root.tsx`

Add preconnect hints in the root route's `head()` for any external resources. Google Fonts is the most common:

```tsx
head: () => ({
  links: [
    { rel: 'preconnect', href: 'https://fonts.googleapis.com' },
    { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossOrigin: 'anonymous' },
    { rel: 'dns-prefetch', href: 'https://fonts.googleapis.com' },
  ],
  meta: [
    // ... meta tags from seo-meta-tags skill
  ],
}),
```

Place `preconnect` before any stylesheet links. This shaves 100-300ms off font loading, which directly impacts Largest Contentful Paint (LCP).

## Cloudflare Edge Advantage

Higgsfield websites deploy as Cloudflare Workers with SSR. This means:

- **SSR at 300+ edge locations** — the HTML is rendered close to the user, not at a single origin. TTFB under 100ms globally.
- **No hydration delay for crawlers** — search engine bots get fully rendered HTML on first request. No "render budget" concerns.
- **Automatic HTTPS** — Cloudflare handles TLS. No certificate management needed.
- **HTTP/2 and HTTP/3** — enabled by default on Cloudflare. Parallel resource loading with zero config.

This is a structural SEO advantage over client-rendered SPAs. Don't undermine it by adding client-side-only rendering patterns — keep data fetching in `loader()` and critical content in the initial SSR response.

## Pitfalls

1. **Forgetting to update the sitemap ROUTES array.** Every new page route needs a corresponding sitemap entry. Dead sitemap URLs actively hurt crawl efficiency.
2. **CSP blocking inline styles from the design system.** The default CSP includes `'unsafe-inline'` for styles. If you tighten it, test that Tailwind/CSS-in-JS still works.
3. **robots.txt blocking staging assets.** The route derives origin from the request URL, so preview and production get correct sitemaps automatically. Don't hardcode URLs.
4. **Missing canonical on dynamic routes.** Routes with params (`/blog/$slug`) must build the canonical URL from the param value, not use a static string.
5. **Trailing slash redirect loops.** The normalization redirect must be the FIRST check in `fetch()`, before `handler.fetch`. Placing it after can cause double-processing or loops with Cloudflare's own redirects.

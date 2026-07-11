# Skill: SEO Schema Markup

Load this skill for any website build with a public face. Structured data (JSON-LD) is how search engines understand what a page *is* — without it, rich results are off the table.

## Schema Type Decision Matrix

| Site type | Schema types to apply |
|---|---|
| Agency / studio / company | `Organization` + `ProfessionalService` + `WebSite` |
| Product / e-commerce | `Product` + `Organization` + `WebSite` |
| SaaS / app | `SoftwareApplication` + `Organization` + `WebSite` |
| Local business | `LocalBusiness` + `WebSite` |
| Blog / content site | `Article` or `BlogPosting` + `WebSite` |
| Any site | `WebSite` (always include) |
| Page has FAQ section | Add `FAQPage` to the above |

## Reusable Component

Create `app/src/components/StructuredData.tsx`:

```tsx
export function StructuredData({ json }: { json: string }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: json }}
    />
  );
}
```

SSR-safe. No client JS needed. The `json` prop is a pre-stringified JSON-LD object.

## Usage Pattern

1. Define schema objects as module-level constants — `JSON.stringify` runs once at import time, not per render.
2. Place `<StructuredData>` at the top of the page JSX, before any visible content.

```tsx
import { StructuredData } from '~/components/StructuredData';

const ORG_SCHEMA = JSON.stringify({
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Acme Studio',
  url: 'https://acme-studio.higgsfield.app',
  logo: 'https://acme-studio.higgsfield.app/logo.png',
});

export function HomePage() {
  return (
    <>
      <StructuredData json={ORG_SCHEMA} />
      {/* visible content */}
    </>
  );
}
```

## Required Fields Per Schema Type

### Organization

| Field | Value |
|---|---|
| `@type` | `"Organization"` |
| `name` | Brand name |
| `url` | Canonical site URL |
| `logo` | Absolute URL to logo image |
| `sameAs` | Array of social profile URLs (optional but recommended) |

### WebSite

| Field | Value |
|---|---|
| `@type` | `"WebSite"` |
| `name` | Site name |
| `url` | Canonical homepage URL |
| `potentialAction` | `SearchAction` with `query-input` (if site has search) |

### ProfessionalService

| Field | Value |
|---|---|
| `@type` | `"ProfessionalService"` |
| `name` | Business name |
| `url` | Canonical URL |
| `description` | One-sentence service description |
| `areaServed` | Geographic area or `"Worldwide"` |
| `serviceType` | Primary service category |
| `priceRange` | e.g. `"$$"` or `"$$$"` |

### SoftwareApplication

| Field | Value |
|---|---|
| `@type` | `"SoftwareApplication"` |
| `name` | App name |
| `url` | Canonical URL |
| `applicationCategory` | e.g. `"BusinessApplication"` |
| `operatingSystem` | `"Web"` for web apps |
| `offers` | `{ "@type": "Offer", "price": "0", "priceCurrency": "USD" }` |

### Product

| Field | Value |
|---|---|
| `@type` | `"Product"` |
| `name` | Product name |
| `description` | Short product description |
| `image` | Product image URL |
| `offers` | `Offer` with `price`, `priceCurrency`, `availability` |

### FAQPage

| Field | Value |
|---|---|
| `@type` | `"FAQPage"` |
| `mainEntity` | Array of `{ "@type": "Question", "name": "...", "acceptedAnswer": { "@type": "Answer", "text": "..." } }` |

## Complete Example: Agency Site

This goes in the homepage component. All three schemas in one `@graph`:

```tsx
const SCHEMA = JSON.stringify({
  '@context': 'https://schema.org',
  '@graph': [
    {
      '@type': 'Organization',
      '@id': 'https://acme-studio.higgsfield.app/#org',
      name: 'Acme Studio',
      url: 'https://acme-studio.higgsfield.app',
      logo: 'https://acme-studio.higgsfield.app/logo.png',
      sameAs: [
        'https://twitter.com/acmestudio',
        'https://linkedin.com/company/acmestudio',
      ],
    },
    {
      '@type': 'WebSite',
      '@id': 'https://acme-studio.higgsfield.app/#website',
      name: 'Acme Studio',
      url: 'https://acme-studio.higgsfield.app',
      publisher: { '@id': 'https://acme-studio.higgsfield.app/#org' },
    },
    {
      '@type': 'ProfessionalService',
      '@id': 'https://acme-studio.higgsfield.app/#service',
      name: 'Acme Studio',
      url: 'https://acme-studio.higgsfield.app',
      description: 'Full-service creative agency specializing in brand identity and web design.',
      areaServed: 'Worldwide',
      serviceType: 'Creative Agency',
      priceRange: '$$$',
      provider: { '@id': 'https://acme-studio.higgsfield.app/#org' },
    },
  ],
});
```

## Pitfalls

1. **No relative URLs.** Every `url`, `logo`, `image` field must be an absolute `https://` URL. Schema validators reject relative paths silently.
2. **Don't duplicate schemas.** Use `@graph` to bundle multiple types in one `<script>` tag. Multiple `<script type="application/ld+json">` blocks are valid but harder to maintain.
3. **Match visible content.** Schema `name`/`description` must match what the user sees on the page. Google penalizes mismatches.
4. **Test with Google Rich Results Test** (https://search.google.com/test/rich-results) before shipping. Schema syntax errors are invisible to users but block rich results.
5. **Keep schemas on the pages they describe.** Organization schema goes on the homepage. Product schema goes on the product page. Don't dump everything on every page.

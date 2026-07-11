# Skill: Entity Optimizer

## What It Is

Entity optimization establishes the site's primary entity (business, person, product) as a distinct node in knowledge graphs used by Google, Bing, and AI search engines. The goal is unambiguous machine identification — when an AI engine mentions your entity, it should pull the correct name, description, and links.

## Entity Data Model

Collect these fields during the business intake (the `seo-schema-markup` skill handles the base schema; this skill enriches it):

| Field          | Example                                      | Required |
|----------------|----------------------------------------------|----------|
| name           | Acme Corp                                    | Yes      |
| description    | Automated invoicing for logistics companies  | Yes      |
| url            | https://acmecorp.com                         | Yes      |
| logo           | https://acmecorp.com/logo.png                | Yes      |
| sameAs[]       | [LinkedIn URL, Instagram URL, ...]           | Yes      |
| foundingDate   | 2019-03-15                                   | If known |
| industry       | Financial Technology                         | If known |
| areaServed     | North America, Europe                        | If known |

## sameAs Strategy

`sameAs` tells search engines which external profiles belong to this entity. Include URLs from:

- **LinkedIn** — company page URL (e.g. `https://linkedin.com/company/acmecorp`)
- **Instagram** — `https://instagram.com/acmecorp`
- **X (Twitter)** — `https://x.com/acmecorp`
- **GitHub** — `https://github.com/acmecorp` (if applicable)
- **Crunchbase** — `https://crunchbase.com/organization/acmecorp` (if listed)
- **Wikidata** — `https://wikidata.org/wiki/Q12345` (if an entry exists)

During intake, ask the client for all active social/professional profiles. Verify each URL resolves (don't include dead links). Order from highest authority to lowest. Only include profiles the entity actually controls.

## Consistent NAP

Name, Address, and Phone must be identical across:

1. **JSON-LD structured data** — the Organization schema on the page
2. **Visible page content** — the footer or contact section
3. **External listings** — Google Business Profile, Yelp, LinkedIn, etc.

Even minor differences ("St." vs "Street", "+1 555" vs "555") fragment the entity in knowledge graphs. Pick one canonical format and enforce it everywhere. If the business has no physical address, omit `address` entirely rather than using a fake or partial one.

## Multi-Entity @graph Pattern

When a page represents multiple entities (the company, its founder, and its product), use the `@graph` array to define them in a single JSON-LD block with cross-references:

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://acmecorp.com/#org",
      "name": "Acme Corp",
      "url": "https://acmecorp.com",
      "logo": "https://acmecorp.com/logo.png",
      "founder": { "@id": "https://acmecorp.com/#founder" },
      "sameAs": [
        "https://linkedin.com/company/acmecorp",
        "https://instagram.com/acmecorp"
      ]
    },
    {
      "@type": "Person",
      "@id": "https://acmecorp.com/#founder",
      "name": "Jane Smith",
      "jobTitle": "CEO & Founder",
      "worksFor": { "@id": "https://acmecorp.com/#org" },
      "sameAs": ["https://linkedin.com/in/janesmith"]
    },
    {
      "@type": "SoftwareApplication",
      "@id": "https://acmecorp.com/#product",
      "name": "Acme Invoicing",
      "applicationCategory": "BusinessApplication",
      "offers": {
        "@type": "Offer",
        "price": "99",
        "priceCurrency": "USD"
      },
      "provider": { "@id": "https://acmecorp.com/#org" }
    }
  ]
}
```

Key rules: each entity gets a unique `@id` (use URL fragments like `/#org`, `/#founder`). Cross-reference via `{ "@id": "..." }` rather than nesting the full object. This lets search engines build a connected graph rather than treating each entity as isolated.

## Implementation

Use the `StructuredData` component from the `seo-schema-markup` skill. Build the JSON-LD string at module level with all entity fields populated, then pass it as the `json` prop:

```tsx
import { StructuredData } from '~/components/StructuredData';

const entityJson = JSON.stringify({
  "@context": "https://schema.org",
  "@graph": [ /* entities as above */ ]
});

export default function Page() {
  return (
    <>
      <StructuredData json={entityJson} />
      {/* visible page content */}
    </>
  );
}
```

The visible page content must reflect every claim in the schema — name, description, address, founding date. Don't put data in JSON-LD that visitors can't see.

## Pitfalls

1. **Dead sameAs links** — Including social URLs that 404 or redirect to a login wall. Verify every URL before adding it to the schema.
2. **NAP fragmentation** — Using "Acme Corp" in schema but "Acme Corporation" in the footer. Pick one canonical name.
3. **Missing @id cross-references** — Defining Organization and Person in the same @graph but not linking them via `founder`/`worksFor`. Without links, search engines treat them as unrelated.
4. **Over-claiming sameAs** — Listing profiles the entity doesn't own (e.g. a Wikipedia article about a different "Acme"). Every sameAs URL must be a profile controlled by or specifically about this entity.
5. **Invisible schema data** — Putting industry, areaServed, or founding date in JSON-LD without showing it anywhere on the page. Search engines increasingly penalize schema that has no visible counterpart.

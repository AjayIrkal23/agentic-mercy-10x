# Skill: GEO Content Optimizer

## What is GEO

Generative Engine Optimization (GEO) is the practice of structuring website content so AI-powered search engines (ChatGPT, Perplexity, Gemini, Copilot) can extract, cite, and surface it in generated answers. Traditional SEO gets you ranked; GEO gets you quoted.

## 7 Principles

### 1. Direct Answer Structure

Lead every section with the answer, not a buildup. AI engines extract the first sentence that resolves the query — if your answer is buried in paragraph three, it won't be selected. Write the topic sentence as a standalone factual statement, then add supporting detail below. Pattern: "X is Y. It works by Z. This matters because W."

### 2. Entity Clarity

Name and type the primary entity within the first 100 words of the page. "Acme Corp is a B2B SaaS company that provides automated invoicing for mid-market logistics firms." This gives AI engines the subject, category, and scope immediately. Avoid opening with generic statements like "Welcome to our website" or "In today's fast-paced world."

### 3. Factual Specificity

Replace vague claims with concrete, verifiable data points. AI engines prefer citable facts over marketing language. "Trusted by many clients" → "Used by 200+ logistics companies across 14 countries since 2019." "Industry-leading uptime" → "99.97% uptime over the trailing 12 months, verified by StatusPage." Every stat should be something you can back up if challenged.

### 4. Schema-Content Alignment

The JSON-LD structured data must reflect what's visible on the page — not aspirational content, not a different description, not extra services not mentioned in the copy. If the Organization schema says `"description": "AI-powered invoicing platform"`, those words must appear in the visible hero or about section. AI engines cross-reference schema against page text; mismatches reduce trust signals.

### 5. FAQ Sections

Add a FAQ section with direct question-and-answer pairs. Each answer should be 1-3 sentences — long enough to be useful, short enough to be extractable. Wrap in FAQPage schema.

Component pattern:

```tsx
function FAQ({ items }: { items: { q: string; a: string }[] }) {
  return (
    <section>
      <h2>Frequently Asked Questions</h2>
      {items.map((item, i) => (
        <details key={i}>
          <summary>{item.q}</summary>
          <p>{item.a}</p>
        </details>
      ))}
    </section>
  );
}
```

Matching FAQPage schema (add to the page's JSON-LD):

```json
{
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "What does Acme Corp do?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Acme Corp provides automated invoicing software for mid-market logistics companies, handling billing, compliance, and payment reconciliation."
      }
    }
  ]
}
```

### 6. Citation-Friendly Headings

Write H2 and H3 headings that match the queries people (and AI) actually ask. Not "Our Approach" but "How Acme Corp Automates Invoice Processing." Not "Features" but "Key Features of Acme Invoicing Software." The heading should be a valid search query on its own. AI engines use headings as section identifiers when constructing citations — a descriptive heading increases the chance your section gets attributed.

### 7. Topical Authority

Demonstrate depth through internal linking, consistent entity naming, and expertise signals. Link related sections to each other (e.g. the pricing page links to the features page with descriptive anchor text). Use the exact same entity name everywhere — don't alternate between "Acme", "Acme Corp", "ACME Corporation", and "our company." Include an expertise section (team credentials, years in operation, certifications) to strengthen E-E-A-T signals that AI engines evaluate.

---

## Before / After Example

**Before (vague, buried answer):**
```
Welcome to Acme Corp. We've been in business for years and pride
ourselves on excellent service. Our innovative platform helps
companies manage their finances. Many organizations trust us.
Contact us to learn more about what we can do for you.
```

**After (GEO-optimized):**
```
Acme Corp is an automated invoicing platform for mid-market
logistics companies, processing over 2M invoices annually across
14 countries. Founded in 2019, the platform reduces manual billing
time by 73% through AI-powered line-item matching and compliance
checks. Acme serves 200+ customers including DHL Freight and Kuehne+Nagel.
```

---

## Pitfalls

1. **Keyword stuffing for AI** — Repeating the same phrase unnaturally hoping AI will pick it up. AI engines detect and penalize this the same way traditional search does.
2. **Schema without matching content** — Adding FAQPage schema for questions never shown on the page. This is structured-data spam and triggers trust penalties.
3. **Walls of text with no structure** — AI engines rely on headings, lists, and paragraphs to segment content. A 2000-word block with no subheadings is effectively invisible to extraction.
4. **Answering questions indirectly** — "Contact us for pricing" instead of showing actual pricing. AI engines skip sections that don't contain an answer.
5. **Inconsistent entity naming** — Switching between "Acme Corp", "Acme", "the company", and "we" makes it harder for AI to build a coherent entity profile. Pick one primary name and use it consistently, especially in headings and first sentences.

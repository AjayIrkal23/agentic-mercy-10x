# Skill: SEO On-Page Audit

## When to Run

Run this audit after building any website and before running `higgsfield website deploy <website_id> --env preview`. It is the SEO quality gate. Do not deploy until every FAIL is resolved. The audit is self-contained — read the project source files directly, no external tools or browser needed.

## Audit Procedure

Read every route/page component in `app/src/routes/`. For each file, evaluate the 10 checks below. Collect results, print the summary table, fix any FAILs, then re-run until clean.

---

### 1. Heading Hierarchy

Verify exactly one `<h1>` per page. Sections use `<h2>`, subsections `<h3>`, etc. No skipped levels (e.g. `<h1>` followed by `<h3>` with no `<h2>`). The `<h1>` must contain or closely match the page's primary keyword.

FAIL if: multiple `<h1>` tags, zero `<h1>` tags, or any skipped heading level.

### 2. Image Alt Text

Every `<img>` element must have a non-empty `alt` attribute. For AI-generated images, derive `alt` from the generation prompt (e.g. prompt "modern office interior" → `alt="Modern office interior"`). Decorative images use `alt=""` with `role="presentation"`.

FAIL if: any `<img>` lacks `alt`. WARN if: `alt` is generic like "image" or "photo".

### 3. Link Text Quality

Anchor text must describe the destination. Flag any `<a>` whose visible text is "click here", "read more", "learn more", "here", or "link". Replace with descriptive text that makes sense out of context.

FAIL if: any non-descriptive anchor text found.

### 4. Content-to-Code Ratio

Scan each page component for visible text content vs. JS/markup overhead. A page should have at least 200 words of visible text (excluding nav/footer boilerplate). Flag pages that are mostly animations, images, or interactive JS with minimal readable text.

WARN if: visible text is under 200 words. FAIL if: under 50 words.

### 5. Keyword Alignment

Identify the page's primary keyword (from the business intake or page purpose). Verify it appears in: the `<title>` tag, the `<h1>`, the first paragraph of body text, and the `<meta name="description">` content. Phrasing can vary but the core term must be present.

FAIL if: keyword missing from title or H1. WARN if: missing from first paragraph or meta description.

### 6. Mobile Readability

Check CSS/Tailwind classes for: no `font-size` below 16px on body text (12px acceptable only for captions/labels), `line-height` at least 1.5 on paragraphs, sufficient color contrast (no light gray on white). Verify the viewport meta tag is present.

FAIL if: viewport meta missing. WARN if: body text under 16px or line-height under 1.4.

### 7. Keyboard Navigation

All interactive elements (`<button>`, `<a>`, `<input>`, custom clickable `<div>`s) must be keyboard-focusable. Any `<div>` or `<span>` with an `onClick` must also have `role="button"`, `tabIndex={0}`, and a keyboard handler. Check for visible focus indicators (no `outline-none` without a replacement).

FAIL if: clickable element lacks keyboard support. WARN if: `outline-none` used without custom focus style.

### 8. Fragment Integrity

Find all `href="#..."` links in the page. For each fragment identifier, verify a matching `id` exists in the rendered DOM of the same page. Check both static IDs and dynamically generated ones (section slugs, etc.).

FAIL if: any fragment link points to a non-existent ID.

### 9. Form Accessibility

Every `<input>`, `<select>`, and `<textarea>` must have an associated `<label>` (via `htmlFor`/`id` pairing) or an `aria-label`/`aria-labelledby`. Required fields must have the `required` attribute or `aria-required="true"`. Error messages must be linked via `aria-describedby`.

FAIL if: any input lacks a label. WARN if: required fields not marked.

### 10. Social Preview

Verify `<meta property="og:title">`, `<meta property="og:description">`, and `<meta property="og:image">` exist. The `og:image` must be an absolute URL (starts with `https://`), not a relative path. Also check for `<meta name="twitter:card">`.

FAIL if: `og:image` missing or relative. WARN if: `og:title` or `og:description` missing.

---

## Output Format

After scanning, print this table to the build log:

```
┌─────────────────────────┬────────┬──────────────────────────────────┐
│ Check                   │ Status │ Detail                           │
├─────────────────────────┼────────┼──────────────────────────────────┤
│ Heading hierarchy       │ PASS   │                                  │
│ Image alt text          │ FAIL   │ 2 images missing alt in Hero.tsx │
│ Link text quality       │ PASS   │                                  │
│ Content-to-code ratio   │ WARN   │ 120 words on /pricing            │
│ Keyword alignment       │ PASS   │                                  │
│ Mobile readability      │ PASS   │                                  │
│ Keyboard navigation     │ PASS   │                                  │
│ Fragment integrity      │ FAIL   │ #team target missing             │
│ Form accessibility      │ PASS   │                                  │
│ Social preview          │ PASS   │                                  │
├─────────────────────────┼────────┼──────────────────────────────────┤
│ RESULT                  │ BLOCK  │ 2 FAIL — fix before deploy       │
└─────────────────────────┴────────┴──────────────────────────────────┘
```

Status values: **PASS** (good), **WARN** (acceptable, note for improvement), **FAIL** (must fix before deploy).

## Fix-and-Recheck Loop

1. For each FAIL, open the source file and apply the fix directly.
2. After fixing all FAILs, re-run the full 10-item audit from the top.
3. Repeat until the table shows zero FAILs.
4. WARNs are acceptable for deploy but should be noted in the deploy summary.
5. Only after a clean pass (zero FAILs), proceed to `higgsfield website deploy <website_id> --env preview`.

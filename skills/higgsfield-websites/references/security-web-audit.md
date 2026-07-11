# Skill: Web Security Audit

## When to Load

After building any website, before `higgsfield website deploy <website_id> --env preview`. Run alongside `references/seo-audit.md` as the security half of the pre-deploy quality gate. This audit applies to every site -- brochure, website, dashboard -- because even static sites can have XSS or misconfiguration.

---

## Precedent Rules

Internalize these before auditing. They prevent false positives that waste time and erode trust in the audit.

1. **React JSX auto-escapes by default.** `<p>{userInput}</p>` is safe. Do NOT flag normal JSX text interpolation `{variable}` as XSS. React escapes all string values rendered in JSX.

2. **`dangerouslySetInnerHTML` IS a real risk.** Flag it unless the content is a hardcoded string literal or sanitized through DOMPurify / a known sanitizer. "It comes from our CMS" is not a defense without sanitization.

3. **Environment variables are trusted input.** Do not flag `process.env.X` or `env.VARIABLE` as tainted user input. These are set at build/deploy time by the platform.

4. **UUIDs are unguessable.** Do not flag UUID-based resource access (`/api/items/550e8400-e29b-...`) as IDOR. UUIDs have 122 bits of entropy -- brute force is infeasible.

5. **Test files are excluded.** Skip `*.test.ts`, `*.test.tsx`, `__tests__/`, `*.spec.ts`, `*.spec.tsx`. Test code does not ship to production.

6. **Example/template files are excluded.** Skip `.example`, `.sample`, `.template` files. They are not deployed.

7. **Dev-only config is excluded.** Skip `Dockerfile`, `docker-compose.yml`, `.devcontainer/`, and local development config that does not deploy to Workers.

8. **Missing HTTPS is not a finding.** Cloudflare enforces HTTPS at the edge for all `*.higgsfield.app` domains. Do not flag HTTP links to the website's own domain.

---

## OWASP Top 10 Checklist

### A01: Broken Access Control

Check every `createServerFn` that reads or writes user data. It must verify authentication before accessing data.

```ts
// FAIL -- no auth check
const getUserNotes = createServerFn({ method: 'GET' })
  .handler(async ({ data }) => {
    return db.prepare('SELECT * FROM notes WHERE user_id = ?').bind(data.userId).all();
  });

// PASS -- auth check before data access
const getUserNotes = createServerFn({ method: 'GET' })
  .handler(async ({ data, request }) => {
    const session = await getSession(request);
    if (!session?.userId) throw new Error('Unauthorized');
    return db.prepare('SELECT * FROM notes WHERE user_id = ?').bind(session.userId).all();
  });
```

Also check: API routes under `app/src/routes/api/` must verify auth. Page loaders returning private data must check session. Never rely on client-side route guards alone.

### A02: Cryptographic Failures

- No hardcoded secrets in source (grep for `sk-`, `ghp_`, `Bearer `, long base64 strings)
- No `Math.random()` for security-relevant values (IDs, tokens, nonces)
- No sensitive data (passwords, tokens, PII) in the client bundle -- check props passed from loaders to components
- Cross-reference with `references/security-worker-hardening.md` rules 2, 3, 4

### A03: Injection

**SQL Injection (D1):** Every D1 query must use parameterized binding.

```ts
// FAIL -- string concatenation
db.prepare(`SELECT * FROM users WHERE name = '${name}'`).all();

// PASS -- parameterized
db.prepare('SELECT * FROM users WHERE name = ?').bind(name).all();
```

**XSS:** Flag `dangerouslySetInnerHTML` with non-static content. Flag `href={userInput}` without protocol validation (see React-Specific Checks below).

**Command Injection:** Flag any use of `eval()`, `new Function()`, or template literal construction of executable code in server functions.

### A04: Insecure Design

Check for fail-open defaults on security-critical paths:

- `|| 'default'` fallback on secrets or auth tokens -- should crash, not fall back
- Missing rate limiting on public-facing API routes (POST endpoints, form submissions)
- Admin functionality accessible without role checks
- Password/auth flows without brute-force protection

If the website has no auth or sensitive operations, mark as N/A.

### A05: Security Misconfiguration

- Missing security headers -- check for `applySecurityHeaders()` or equivalent in `server.ts` (cross-ref worker-hardening rule 8)
- Overly permissive CORS (`Access-Control-Allow-Origin: *`)
- Debug info in production responses (`stack`, `trace`, internal paths in error bodies)
- Source maps served in production (`*.map` files accessible)
- Default credentials or placeholder secrets in committed config

### A06: Vulnerable Components

```bash
# Run in the app directory
bun audit 2>/dev/null || npm audit 2>/dev/null || echo "No audit tool available"
```

Check `package.json` for:
- Dependencies with known CVEs
- Unmaintained packages (no updates in 2+ years for security-relevant deps)
- Unnecessary dependencies that expand attack surface

If no audit tool is available, manually check critical deps (auth libraries, crypto, parsers) against known vulnerability databases.

### A07: Authentication Failures

Skip if site has no auth. If auth is present, check:

- Session fixation: session ID must rotate after login
- CSRF: state-changing server functions (POST/PUT/DELETE) must verify origin or use CSRF tokens. TanStack Start server functions include origin checking by default -- verify it's not disabled.
- Session expiry: sessions must have a `Max-Age` or `Expires`. Infinite sessions are a finding.
- Password storage: if the website stores passwords, they must be hashed (bcrypt, scrypt, argon2). Never stored in plain text in D1.

### A08: Data Integrity Failures

Skip if site has no file uploads or external data processing. If present, check:

- File upload MIME type validation (don't trust `Content-Type` header alone; check magic bytes for critical uploads)
- File size limits enforced server-side (Workers have 100 MB request body limit but the website should enforce lower)
- Filename sanitization for R2 keys (strip path traversal: `../`, null bytes, control characters)
- External data (webhooks, API responses) validated before storage

### A09: Logging Failures

Flag `console.log` / `console.error` that prints:
- Passwords or password hashes
- API keys, tokens, secrets
- Full request bodies on auth endpoints
- Full database rows containing PII

Check that error responses to clients do not contain:
- Stack traces (`at Object.<anonymous>`, file paths)
- Internal hostnames or IP addresses
- Database error messages with schema details

### A10: SSRF

Skip if no server functions make outbound HTTP requests. If present, check:

```ts
// FAIL -- fetches arbitrary user-supplied URL
const proxyFetch = createServerFn({ method: 'POST' })
  .handler(async ({ data }) => {
    const res = await fetch(data.url); // user controls destination
    return res.json();
  });

// PASS -- allowlisted domains
const ALLOWED_HOSTS = ['api.example.com', 'cdn.example.com'];
const proxyFetch = createServerFn({ method: 'POST' })
  .handler(async ({ data }) => {
    const url = new URL(data.url);
    if (!ALLOWED_HOSTS.includes(url.hostname)) throw new Error('Blocked');
    const res = await fetch(url.toString());
    return res.json();
  });
```

Also check for: internal network access (`localhost`, `127.0.0.1`, `10.*`, `192.168.*`, `169.254.169.254` -- the metadata endpoint).

---

## Insecure Defaults Check

Scan the codebase for these fail-open patterns:

### Fail-Open Patterns

```ts
// BAD -- falls back to a default secret instead of crashing
const secret = env.SECRET_KEY || 'default-secret-key';
const jwtSecret = process.env.JWT_SECRET ?? 'changeme';

// BAD -- verification defaults to disabled
const verifySignature = options.verify ?? true; // should be ?? false or mandatory

// BAD -- empty catch swallows auth/crypto errors
try { await verifyToken(token); } catch {} // attacker wins on any error
```

### Dangerous Zero/Null/Empty Defaults

- `timeout: 0` -- may mean "no timeout" (infinite wait, DoS vector)
- `maxRetries: Infinity` -- retry storm
- Empty string accepted as password or API key
- Missing validation on optional fields that have security implications (e.g., `role` field defaults to `'admin'` if missing)

### The 5 Rationalizations to Reject

When reviewing code, reject these justifications for insecure defaults:

1. **"It's just for dev"** -- dev config ships to production more often than anyone admits.
2. **"Prod config overrides it"** -- if it doesn't, the fallback is the live value.
3. **"We'll fix it later"** -- later never comes; the default becomes the permanent value.
4. **"It's documented"** -- nobody reads documentation; the default is the behavior.
5. **"Nobody would do that"** -- attackers do exactly that.

---

## React-Specific Checks

### `dangerouslySetInnerHTML`

```ts
// FAIL -- unsanitized user content
<div dangerouslySetInnerHTML={{ __html: userComment }} />

// PASS -- hardcoded content
<div dangerouslySetInnerHTML={{ __html: '<strong>Welcome</strong>' }} />

// PASS -- sanitized
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(userComment) }} />
```

### `href` with User Input

```ts
// FAIL -- javascript: protocol injection
<a href={userUrl}>Click</a>

// PASS -- protocol validation
function safeHref(url: string): string {
  if (url.startsWith('/') || url.startsWith('#') || url.startsWith('https://')) return url;
  return '#';
}
<a href={safeHref(userUrl)}>Click</a>
```

### `<iframe>` with User Input

```ts
// FAIL -- no sandbox
<iframe src={userUrl} />

// PASS -- sandboxed
<iframe src={userUrl} sandbox="allow-scripts allow-same-origin" />
```

### Client-Side State

- Never store tokens, secrets, or API keys in `localStorage`, `sessionStorage`, or React state
- Auth tokens belong in `HttpOnly` cookies, not JavaScript-accessible storage
- If the website uses `zustand`, `jotai`, or React context for auth state, verify the token source is a server function, not client storage

### `eval()` / `new Function()`

Flag any occurrence in application code. Acceptable only in build tooling (`vite.config.ts`, bundler plugins) which does not execute at runtime.

---

## Output Format

Present audit results as a table. One row per check. Same format as `references/seo-audit.md`.

```
## Security Audit Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | A01 Broken Access Control | PASS | All 4 server functions verify session |
| 2 | A02 Cryptographic Failures | PASS | No hardcoded secrets found |
| 3 | A03 Injection | WARN | `dangerouslySetInnerHTML` in BlogPost.tsx -- verify content is sanitized |
| 4 | A04 Insecure Design | N/A | No auth or sensitive operations |
| 5 | A05 Security Misconfiguration | FAIL | Missing security headers in server.ts |
| 6 | A06 Vulnerable Components | PASS | `bun audit` reports 0 vulnerabilities |
| 7 | A07 Authentication Failures | N/A | No auth |
| 8 | A08 Data Integrity Failures | N/A | No file uploads |
| 9 | A09 Logging Failures | PASS | No sensitive data in console output |
| 10 | A10 SSRF | N/A | No outbound fetches from server functions |
| 11 | Insecure Defaults | PASS | No fail-open patterns found |
| 12 | React-Specific | WARN | 1 `dangerouslySetInnerHTML` usage |

**Summary: 5 PASS, 2 WARN, 1 FAIL, 4 N/A**
```

Status values:
- **PASS** -- check passed, no issues
- **FAIL** -- security issue found, must fix before deploy
- **WARN** -- potential issue, needs manual review
- **N/A** -- check does not apply to this site

Any FAIL blocks deploy. WARN items are noted in the deploy message for the user to review.

---

## Pitfalls

1. **Don't flag React JSX interpolation as XSS.** `{variable}` in JSX is auto-escaped. Only `dangerouslySetInnerHTML` and `href`/`src` attributes with user input are real XSS vectors in React.

2. **Don't flag `fetch()` in server functions as SSRF unless the URL comes from user input.** Server functions that fetch hardcoded API endpoints (e.g., `fetch('https://api.stripe.com/...')`) are not SSRF.

3. **Don't audit `node_modules/`.** Dependency code is checked by `bun audit` / `npm audit`, not by manual code review. Focus on application code in `app/src/`.

4. **Don't confuse build-time env vars with runtime secrets.** `VITE_*` env vars are intentionally public (bundled into client code). Only flag non-`VITE_` env vars that appear in client-reachable code.

5. **Don't flag missing rate limiting on static/SSR pages.** Rate limiting is relevant for API routes and form-handling server functions, not for page loads. Cloudflare's DDoS protection handles volumetric attacks at the edge.

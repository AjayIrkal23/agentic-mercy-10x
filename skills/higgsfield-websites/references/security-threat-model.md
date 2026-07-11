# Skill: Threat Model

## When to Load

Only when the site has auth, user data, or storage bindings. Load when ANY of these conditions is true:

- `references/auth.md` is loaded for this build
- `app.manifest.json` contains `"db": true`, `"r2": true`, or `"kv": true`
- The website has `createServerFn` calls that write or mutate data
- The website has `/api/user`, `__auth`, or session-related routes

**Skip** for static landing pages, portfolios, brochure sites, and websites with no user-submitted data.

### Detection

```ts
// Check app.manifest.json
const manifest = JSON.parse(fs.readFileSync('app.manifest.json', 'utf-8'));
const hasStorage = manifest.db || manifest.r2 || manifest.kv;

// Check for auth routes
// Grep for: /api/user, __auth, createServerFn with .bind() or INSERT/UPDATE/DELETE
```

---

## Trust Boundaries

Map these boundaries for every website with data. Each boundary is a point where input trust level changes.

### Browser → Worker (untrusted → trusted)

All data crossing this boundary is attacker-controlled:
- URL path and query parameters
- Request headers (including cookies, but cookies are tamper-resistant if `HttpOnly`)
- Form submissions and JSON request bodies
- File uploads

Every `createServerFn`, page loader, and API route handler sits on this boundary. Inputs must be validated.

### Worker → D1/R2/KV (trusted → trusted)

Both run in the same Cloudflare environment. The channel is trusted, but SQL injection is still possible if queries use string concatenation instead of parameterized `.bind()`. R2 key construction from user input can cause path traversal.

### Worker → External API (trusted → semi-trusted)

Outbound `fetch()` from server functions. Risks:
- SSRF if the URL comes from user input
- Response injection if the external API is compromised
- Secret leakage if auth headers are sent to the wrong host

Validate outbound URLs. Validate response shapes before trusting them.

### Worker → fnf.internal (trusted → trusted)

The platform's internal API. Auth is injected by the platform -- website code does not handle fnf tokens. Still validate response shapes; a malformed response should not crash the website or expose internal state.

### Auth Routes → Public Routes (access control boundary)

Routes that require authentication vs. routes that are public. Map which is which. Every protected route must verify session before rendering or returning data. A missing check on one route is the most common access control bug.

---

## Entry Point Inventory

Enumerate every entry point before analyzing threats. Build this list by scanning the codebase.

### Page Routes (`app/src/routes/**`)

For each route file, record:
- Path pattern (e.g., `/dashboard`, `/settings/$userId`)
- Auth required: yes/no
- Data loaded: what server functions or loaders run
- Writable: does the page submit forms or call mutation server functions

### Server Functions (`createServerFn`)

For each server function, record:
- Name and location
- HTTP method (GET/POST)
- Input shape (what data it accepts from the client)
- Data accessed (which D1 tables, R2 buckets, KV namespaces)
- Auth check: present/absent

### API Routes (`app/src/routes/api/**`)

For each API route, record:
- Path and HTTP methods handled
- Auth check: present/absent
- Input sources (body, query params, path params)
- Response data (what it returns, any sensitive fields)

### File Upload Surfaces

- R2 write operations (where file data comes from, size limits, type validation)
- Form file inputs (which pages accept file uploads)
- Filename/key construction (is user input used in R2 keys?)

### Webhook/Callback Endpoints

- External services that call back into the website (payment processors, OAuth providers, etc.)
- Signature verification on incoming webhooks
- Idempotency handling (replayed webhooks should not duplicate side effects)

---

## Asset Classification

| Asset | Location | Sensitivity | Protection |
|-------|----------|-------------|------------|
| User credentials (passwords) | D1 | Critical | Hashed (bcrypt/argon2), never logged, never returned to client |
| Session tokens | Cookie | Critical | `HttpOnly; Secure; SameSite=Strict`, rotated on login |
| PII (email, name, etc.) | D1 | High | Access-controlled by user ID, not in client bundle |
| Uploaded files | R2 | Medium-High | Access-controlled, validated MIME/size, sanitized filenames |
| Application data (posts, etc.) | D1 | Medium | Access-controlled per ownership or visibility settings |
| R2 objects (public assets) | R2 | Low | Public by design, no sensitive content |
| KV cache entries | KV | Low-Medium | May contain derived data; TTL-bounded; no secrets as values |
| API keys (external services) | Cloudflare Secrets | Critical | Never in code, injected via `env`, never logged |

---

## Attacker Model

### Anonymous Internet User

**Capabilities:**
- Reach all public routes and API endpoints
- Submit arbitrary form data, JSON bodies, file uploads
- Craft malicious URLs (XSS payloads in query params, path traversal)
- Replay and tamper with requests (no CSRF token = no protection on state changes)
- Enumerate routes and server functions by observing client JavaScript

**Goals:** Access other users' data, inject content, abuse server resources, exfiltrate secrets.

### Authenticated User

**Capabilities:**
- Everything anonymous users can do, plus valid session
- Access own data and attempt to access other users' data (IDOR)
- Attempt privilege escalation (modify role claims, access admin routes)
- Abuse rate-unlimited endpoints (spam, resource exhaustion)

**Goals:** Read/modify other users' data, escalate to admin, abuse platform resources.

### What Attackers CANNOT Do

These are platform guarantees -- do not model threats against them:

- **Access Worker internals at runtime.** V8 isolates provide memory isolation between requests and between Workers. An attacker cannot read another request's memory.
- **Intercept Worker-to-binding traffic.** D1, R2, KV communication happens in-process or over Cloudflare's internal network. There is no network path for an attacker to intercept.
- **Read Cloudflare Secrets.** Secrets are injected at deploy time into the Worker's `env` object. They are not in the code, not in the git repo, and not accessible via any API the attacker can reach.
- **Bypass Cloudflare edge security.** HTTPS termination, DDoS mitigation, and bot management happen before traffic reaches the Worker.

---

## Common Threat Patterns for the Stack

### 1. IDOR via Predictable Resource IDs

**Attack:** User changes `/api/notes/123` to `/api/notes/124` to read another user's note. Sequential integer IDs are trivially enumerable.

**Mitigation:** Always filter by authenticated user ID in D1 queries.

```ts
// VULNERABLE
db.prepare('SELECT * FROM notes WHERE id = ?').bind(noteId).first();

// SAFE
db.prepare('SELECT * FROM notes WHERE id = ? AND user_id = ?').bind(noteId, session.userId).first();
```

Using UUIDs as IDs adds defense-in-depth but does NOT replace access control checks.

### 2. Server Function Input Manipulation

**Attack:** Client sends unexpected shape to `createServerFn` -- extra fields, wrong types, oversized strings, negative numbers, SQL fragments.

**Mitigation:** Validate every input field before processing.

```ts
import { z } from 'zod';

const CreateNoteSchema = z.object({
  title: z.string().min(1).max(200),
  body: z.string().max(10000),
});

const createNote = createServerFn({ method: 'POST' })
  .validator((data: unknown) => CreateNoteSchema.parse(data))
  .handler(async ({ data, request }) => {
    const session = await getSession(request);
    if (!session) throw new Error('Unauthorized');
    await db.prepare('INSERT INTO notes (id, user_id, title, body) VALUES (?, ?, ?, ?)')
      .bind(crypto.randomUUID(), session.userId, data.title, data.body).run();
  });
```

### 3. Cross-Tenant Data Leak (Shared D1)

**Attack:** Preview and production deployments may share the same D1 database. Test data created during preview could leak into production, or production data could be modified via preview.

**Mitigation:**
- Never use real user data in preview/testing
- If isolation is critical, use `env.HF_ENV` to scope queries: `WHERE env = ?`
- Prefer separate D1 databases for preview and production when the platform supports it

### 4. Privilege Escalation via Client State

**Attack:** Client stores `role: 'admin'` in localStorage or sends `{ role: 'admin' }` in a server function call. Server trusts the client-provided role.

**Mitigation:** Never trust client-sent roles, permissions, or user IDs for authorization decisions.

```ts
// VULNERABLE -- role from client
const { role } = data;
if (role === 'admin') return getAdminData();

// SAFE -- role from server session
const session = await getSession(request);
const user = await db.prepare('SELECT role FROM users WHERE id = ?').bind(session.userId).first();
if (user?.role === 'admin') return getAdminData();
```

### 5. SSRF via Server Function

**Attack:** Server function accepts a URL from the client and fetches it. Attacker provides `http://169.254.169.254/latest/meta-data/` (cloud metadata), `http://localhost:8787/internal-api`, or internal network addresses.

**Mitigation:**

```ts
const ALLOWED_HOSTS = new Set(['api.example.com', 'cdn.example.com']);

function validateUrl(input: string): URL {
  const url = new URL(input);
  if (!['https:'].includes(url.protocol)) throw new Error('HTTPS only');
  if (!ALLOWED_HOSTS.has(url.hostname)) throw new Error('Host not allowed');
  // Block private IPs
  if (/^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.)/.test(url.hostname)) {
    throw new Error('Private IP blocked');
  }
  return url;
}
```

### 6. Webhook Replay / Forgery

**Attack:** Attacker sends forged webhook payloads to callback endpoints, or replays legitimate webhooks to duplicate side effects (double payment credits, duplicate notifications).

**Mitigation:**
- Verify webhook signatures using `crypto.subtle.timingSafeEqual()` (see worker-hardening rule 4)
- Track processed webhook IDs in D1/KV to enforce idempotency
- Reject webhooks with timestamps older than 5 minutes

---

## Output

Present threat model findings inline in chat as a summary table. Do not write to a file.

```
## Threat Model Summary

| # | Threat | Severity | Likelihood | Impact | Mitigation Status |
|---|--------|----------|------------|--------|-------------------|
| 1 | IDOR on /api/notes/:id | High | High | User data leak | MITIGATED -- queries filter by user_id |
| 2 | Server function input manipulation | Medium | High | Data corruption | OPEN -- no validation on createNote |
| 3 | SSRF via /api/proxy | High | Medium | Internal network access | MITIGATED -- allowlist in place |
| 4 | Privilege escalation | Critical | Low | Full admin access | MITIGATED -- role derived from DB |
| 5 | Webhook replay | Medium | Medium | Duplicate transactions | OPEN -- no idempotency check |

**Open items: 2 | Mitigated: 3 | Total attack surface: 5 entry points, 3 server functions, 1 webhook**
```

Severity scale: Critical > High > Medium > Low. Base severity on worst-case impact. Likelihood accounts for how easy the attack is to execute (High = no special tools needed, just a browser).

---

## Pitfalls

1. **Don't threat-model brochure sites.** A static landing page with no auth, no database, and no user input has no meaningful attack surface beyond XSS (covered by web-audit). Skip threat modeling for these.

2. **Don't assume D1 is multi-tenant by default.** Each website gets its own D1 database. Cross-tenant risk exists only between preview/production of the same website sharing a database, not between different websites.

3. **Don't model attacks against Cloudflare infrastructure.** V8 isolate escapes, edge network compromises, and Cloudflare-internal attacks are outside the website's threat model. The platform is the trust boundary.

4. **Don't confuse authentication with authorization.** A user being logged in (authenticated) does not mean they can access any resource (authorized). IDOR is an authorization bug, not an authentication bug. Check both.

5. **Don't skip the entry point inventory.** Jumping straight to threat patterns without enumerating entry points misses the routes and server functions unique to the website. The inventory is the foundation; patterns are applied against it.

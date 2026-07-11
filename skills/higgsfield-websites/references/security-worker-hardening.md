# Skill: Worker Security Hardening

## When to Load

Every website build. These are hard constraints of the Cloudflare Workers runtime, not optional best practices. Violating them causes data leaks, request cross-contamination, or runtime crashes. Load unconditionally alongside the build skill.

---

## Hard Rules

### 1. No Global Mutable State

Module-level variables persist across requests in the same V8 isolate. A `let` at module scope is shared by every concurrent request hitting that isolate.

```ts
// BAD -- leaks between requests
let currentUser: User | null = null;

export default {
  async fetch(request: Request) {
    currentUser = await getUser(request); // overwrites for ALL concurrent requests
    return handleRequest();
  }
};
```

```ts
// GOOD -- request-scoped data flows through params
export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext) {
    const user = await getUser(request);
    return handleRequest(user, env);
  }
};
```

Module-level `const` for static config (strings, frozen objects) is fine. Any `let` or mutable object at module scope is a bug. React context resets per SSR render and is safe for per-request data.

### 2. Cryptographic Randomness Only

`Math.random()` is not a CSPRNG. In Workers, its output may be predictable across requests in the same isolate.

```ts
// BAD
const sessionId = `sess_${Math.random().toString(36)}`;

// GOOD
const sessionId = crypto.randomUUID();

// GOOD -- for raw bytes (tokens, nonces)
const token = new Uint8Array(32);
crypto.getRandomValues(token);
```

`Math.random()` is acceptable only in client-side UI code (animations, layout jitter). Flag any server-side usage.

### 3. No Hardcoded Secrets

Never put API keys, tokens, passwords, or connection strings in source code or `wrangler.jsonc`.

```ts
// BAD
const API_KEY = "sk-proj-abc123...";

// GOOD -- store it with: higgsfield website secrets set <website_id> --name API_KEY --value <value>
// Access SERVER-SIDE via bindings().API_KEY (add it to AppEnv in bindings.server.ts)
```

In the Supercomputer builder, the platform injects secrets via the outbound Worker. Website code accesses them through `env` bindings at runtime. Secrets never appear in the git repo.

### 4. Timing-Safe Secret Comparison

String `===` leaks secret length via timing side-channels. Use `crypto.subtle.timingSafeEqual()` for any secret, token, or API key comparison.

```ts
async function safeCompare(a: string, b: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const aBuf = encoder.encode(a);
  const bBuf = encoder.encode(b);
  if (aBuf.byteLength !== bBuf.byteLength) return false;
  return crypto.subtle.timingSafeEqual(aBuf, bBuf);
}

// Usage in a webhook handler
const signature = request.headers.get('X-Webhook-Signature') ?? '';
if (!(await safeCompare(signature, env.WEBHOOK_SECRET))) {
  return new Response('Forbidden', { status: 403 });
}
```

### 5. Stream Large Payloads

Workers have a 128 MB memory limit. `await response.text()` or `await response.json()` buffers the entire body into memory. On unbounded external responses this causes OOM crashes.

```ts
// BAD -- buffers entire response
const data = await fetch(externalUrl).then(r => r.text());

// GOOD -- stream through
const upstream = await fetch(externalUrl);
return new Response(upstream.body, {
  headers: { 'Content-Type': upstream.headers.get('Content-Type') ?? 'application/octet-stream' },
});
```

For JSON processing of large payloads, use streaming JSON parsers or paginate the upstream API. Only call `.json()` when you control the response size (e.g., your own D1 queries).

### 6. Handle Every Promise

Every `Promise` must be `await`ed, `return`ed, or passed to `ctx.waitUntil()`. Floating promises silently swallow errors, may execute after the response is sent, and can leak data into subsequent requests.

```ts
// BAD -- fire-and-forget
logAnalytics(event); // returns Promise, nobody awaits it

// GOOD -- defer non-critical work
ctx.waitUntil(logAnalytics(event));

// GOOD -- critical work
await saveToDatabase(record);
```

### 7. No `passThroughOnException()`

This Cloudflare API forwards the original request to origin when the Worker throws, bypassing all security logic (auth checks, rate limiting, header injection).

```ts
// BAD -- security bypass on any error
export default {
  async fetch(request, env, ctx) {
    ctx.passThroughOnException();
    return handleRequest(request, env);
  }
};

// GOOD -- explicit error handling
export default {
  async fetch(request, env, ctx) {
    try {
      return await handleRequest(request, env);
    } catch (err) {
      console.error('Worker error:', err);
      return new Response('Internal Server Error', { status: 500 });
    }
  }
};
```

### 8. Security Headers on Every Response

Security headers are owned by a single canonical helper:
`app/src/lib/security-headers.server.ts`. Import `applySecurityHeaders()` in
`app/src/server.ts` and wrap every response leaving the Worker — including
redirects and error responses. Do not hand-roll a second header function.

The canonical helper is the drop-in `app/src/lib/security-headers.server.ts`:

```ts
export function applySecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  // Framing: the Supercomputer Design-mode inspector + preview render this app
  // inside an iframe from a higgsfield.app origin (cross-origin to the app's own
  // subdomain). `X-Frame-Options` has no cross-origin allowlist, so SAMEORIGIN/
  // DENY would blank the preview. We deliberately DO NOT set X-Frame-Options and
  // control framing via the CSP `frame-ancestors` allowlist below. Reviewer:
  // confirm/tighten the editor origin for your deployment.
  headers.set(
    'Content-Security-Policy',
    "default-src 'self'; " +
      "script-src 'self' 'unsafe-inline'; " +
      "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
      "font-src 'self' https://fonts.gstatic.com; " +
      "img-src 'self' data: https:; media-src 'self' https:; " +
      "connect-src 'self' https:; " +
      "frame-ancestors 'self' https://*.higgsfield.app https://higgsfield.app " +
      "https://*.higgsfield.ai https://fnf-dev.anwar-695.workers.dev " +
      "https://feat-apps-marketplace-tools-fnf-dev.anwar-695.workers.dev; " +
      "base-uri 'self'; form-action 'self'",
  );
  headers.set('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload');
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  headers.set('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  headers.set('X-XSS-Protection', '0');
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
```

Adjust CSP directives per website needs (e.g., add specific CDN origins), but keep
`X-Content-Type-Options` and keep `frame-ancestors` as the editor allowlist.
**Never set `X-Frame-Options`** — it has no cross-origin allowlist, so
`DENY`/`SAMEORIGIN` would blank the Supercomputer Design-mode/preview iframe,
which loads the website from a cross-origin `higgsfield.app` host. Framing is
controlled exclusively by the CSP `frame-ancestors` allowlist: it permits the
Supercomputer hosts while still blocking arbitrary third parties. Keep that
allowlist — never narrow it to `'none'` and never remove it.

### 9. Validate Server Function Inputs

`createServerFn` code runs server-only, but its inputs arrive from the client over the network. The client can send any shape of data.

```ts
// BAD -- trusts client input shape
const getUser = createServerFn({ method: 'GET' })
  .handler(async ({ data }: { data: { userId: string } }) => {
    return db.prepare('SELECT * FROM users WHERE id = ?').bind(data.userId).first();
  });

// GOOD -- validate before use
const getUser = createServerFn({ method: 'GET' })
  .validator((data: unknown) => {
    if (!data || typeof data !== 'object' || !('userId' in data)) throw new Error('Invalid input');
    const { userId } = data as { userId: string };
    if (typeof userId !== 'string' || userId.length > 36) throw new Error('Invalid userId');
    return { userId };
  })
  .handler(async ({ data }) => {
    return db.prepare('SELECT * FROM users WHERE id = ?').bind(data.userId).first();
  });
```

Use TanStack Start's `.validator()` chain or manual checks. For complex shapes, use zod.

### 10. No Secrets in React Props

React component props serialize into the client HTML during SSR. Any value passed as a prop is visible in the page source.

```ts
// BAD -- API key appears in client HTML
function Dashboard({ apiKey }: { apiKey: string }) {
  return <Widget config={{ key: apiKey }} />;
}

// GOOD -- fetch server data in a server function, return only safe data
const getDashboardData = createServerFn({ method: 'GET' })
  .handler(async () => {
    const result = await fetch(API_URL, { headers: { Authorization: `Bearer ${env.API_KEY}` } });
    return result.json(); // only the response data reaches the client
  });
```

This includes `env` bindings, database results containing sensitive columns, and internal URLs.

### 11. Cookie Security

Custom cookies set in server routes or API handlers must use secure attributes.

```ts
// GOOD
const cookie = `session=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=86400`;
return new Response(null, {
  status: 302,
  headers: {
    'Set-Cookie': cookie,
    'Location': '/dashboard',
  },
});
```

- `HttpOnly` -- prevents JavaScript access (XSS can't steal it)
- `Secure` -- HTTPS only (always true on Cloudflare)
- `SameSite=Strict` -- blocks cross-site sends (use `Lax` for OAuth redirect flows)

The platform handles auth cookies automatically. This rule applies to any additional cookies the website sets.

### 12. CORS Only When Needed

Workers don't add CORS headers by default -- this is the secure default. Only add `Access-Control-Allow-Origin` when the site genuinely serves API responses to a different origin.

```ts
// BAD -- allows any origin with credentials
headers.set('Access-Control-Allow-Origin', '*');
headers.set('Access-Control-Allow-Credentials', 'true'); // browser ignores * with credentials, but intent is wrong

// GOOD -- specific origin, only on API routes that need it
if (request.headers.get('Origin') === 'https://trusted-app.example.com') {
  headers.set('Access-Control-Allow-Origin', 'https://trusted-app.example.com');
  headers.set('Access-Control-Allow-Credentials', 'true');
}
```

Never add CORS headers to page routes. Only add them to `/api/*` routes consumed by external clients.

---

## Anti-Patterns to Flag

| Pattern | Risk | Fix |
|---------|------|-----|
| `Math.random()` for IDs/tokens | Predictable values, session hijacking | `crypto.randomUUID()` or `crypto.getRandomValues()` |
| `let x = ...` at module scope | Cross-request data leakage | Move to function params or request-scoped context |
| `await response.text()` on external fetch | OOM crash on large response | Stream with `Response(upstream.body)` |
| Hardcoded string resembling a key (`sk-`, `ghp_`, `Bearer`) | Secret in source code / git history | `higgsfield website secrets set <id> --name … --value …` + `bindings().SECRET_NAME` server-side |
| `===` comparing secrets/tokens | Timing side-channel leaks secret | `crypto.subtle.timingSafeEqual()` |
| `ctx.passThroughOnException()` | Bypasses all Worker security on error | `try/catch` with explicit error response |
| Missing `await` on async call | Silent error loss, data leak | `await`, `return`, or `ctx.waitUntil()` |
| Secret value in JSX prop `<Comp token={env.KEY}>` | Secret in client HTML source | Fetch in server function, return only safe data |
| `Access-Control-Allow-Origin: *` | Any origin reads responses | Allowlist specific origins or omit CORS |
| `eval()` / `new Function()` | Arbitrary code execution | Remove; use static logic or JSON parsing |

---

## Pitfalls

1. **`const` objects are still mutable.** `const cache = {}` at module scope is mutable state -- properties can be added/modified across requests. Use `Object.freeze()` for true immutability, or scope caches to the request.

2. **`crypto.subtle.timingSafeEqual` requires equal-length buffers.** If the two buffers differ in length, it throws. Always check `.byteLength` equality first and return `false` on mismatch (do not pad to equal length -- that leaks info about which is shorter).

3. **`ctx.waitUntil()` does not extend memory limits.** Deferred work still shares the 128 MB isolate memory. Don't use it to process large payloads after responding.

4. **CSP `'unsafe-inline'` for scripts weakens XSS protection.** It's included above for compatibility with SSR hydration scripts. Prefer hash-based or nonce-based CSP when the framework supports it. Track TanStack Start CSP nonce support.

5. **Security headers on redirects matter.** A `302 Found` response still needs `X-Content-Type-Options` and `Strict-Transport-Security`. Apply `applySecurityHeaders()` to all responses, not just 200s.

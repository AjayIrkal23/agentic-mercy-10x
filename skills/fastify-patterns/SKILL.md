---
name: fastify-patterns
description: 'Fastify server patterns: schema-first routes, Ajv coercion and removeAdditional defaults, preHandler auth and tenant scoping, one central error handler mapping a typed AppError, rate limiting and route tests with inject().'
when_to_use: Use when adding or changing Fastify routes, route schemas, plugins, hooks, preHandlers, the error handler or rate limits.
metadata:
  schema: 1
  category: backend
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - fastify
    - fastify route
    - fastify plugin
    - fastify schema
    - prehandler
    - onrequest hook
    - setErrorHandler
    - json schema
    - ajv
    - coercetypes
    - rate limit
    - fastify inject
    - typed routes
    intents: []
---
# Fastify patterns

Project contract first: the repo's `CLAUDE.md`, `CODEX.md` and `server_docs/` win over
anything here. site-sync-vista specifics: routes register through
`typedGet/typedPost/...` from `server/src/utils/typed-routes`, layering is
`*.routes.ts -> *.schema.ts -> *.controller.ts -> service -> model`, Ajv runs with
`coerceTypes: true` (set in `server/src/app.ts`), errors are `AppError(message,
statusCode, code)` from `server/src/utils/errors.ts`, and the central handler returns
the flat `{ success:false, message, code }`.

## Routes are schema-first

- Every route declares `schema.params`, `schema.querystring`, `schema.body` (as
  applicable) and `schema.response` for the success codes. Response schemas both document
  the contract and strip fields you did not list (fast-json-stringify serialises only
  declared properties), so a missing property in the schema silently disappears from the
  response.
- Reuse the repo's route helper (typed routes) instead of raw `fastify.get` so types flow
  from the schema to the handler.
- Keep handlers thin: validate (schema) -> controller -> service -> reply. No DB calls in
  routes.

## Ajv defaults you must know

Fastify's default Ajv options are `coerceTypes: 'array'`, `useDefaults: true`,
`removeAdditional: true`, `allErrors: false`:
- query and path strings are coerced to the declared type (`"10"` -> `10`), so declare
  numbers and booleans as such instead of parsing by hand;
- with `additionalProperties: false`, unknown body fields are **removed**, not rejected.
  Set `additionalProperties: false` deliberately and do not rely on it as a security
  check;
- `useDefaults` fills `default:` values before the handler runs.
Check the repo's `ajv.customOptions` in the app factory before assuming the defaults.

## Auth, tenancy, hooks

- Authentication runs in an `onRequest` or `preHandler` hook (e.g. `verifyJWT`) attached
  per route or per encapsulated plugin. A route without the hook is public: say so in the
  review if that is not intended.
- Tenant scope comes from the verified token (`req.user`), never from a query param or
  body field. Pass it explicitly into services.
- Decorate the request in a plugin (`fastify.decorateRequest`) instead of mutating it in
  handlers; register plugins with `fastify-plugin` only when the decoration must escape
  encapsulation.

## Errors

- Throw the repo's typed error (`AppError`) from services and controllers; never throw a
  raw `Error` or reply with ad hoc shapes.
- One `setErrorHandler` maps `AppError` -> its status and envelope, schema validation
  errors (`error.validation`) -> 400, and everything else -> 500 with a generic message.
  Log the full error server-side; never send stack traces or driver messages.
- `reply.code(n).send(...)` once per request; in async handlers either `return` the
  payload or `send` it, not both.

## Rate limits and payloads

- Public and auth endpoints get `@fastify/rate-limit` (globally or per route via
  `config.rateLimit`); keys come from the user id when authenticated, IP otherwise.
- Set `bodyLimit` for upload-adjacent routes; stream large files instead of buffering.

## Tests without a server

Build the app with the repo's factory and call `app.inject({ method, url, headers,
payload })` in vitest; no `listen()`, no port. Cover: schema rejection (400), auth
missing (401), tenant isolation (another company's id -> 404/403), and the success shape
against the response schema. Close the app in `afterAll`.

## Not this skill

Mongo query and index design (`mongoose-patterns`), envelope design
(`api-contract-standards`), list endpoint semantics (`backend-api-standards`).

---
name: backend-error-handling
description: Use when defining backend error taxonomy, centralized handler behavior, safe logging, redaction,
  or client-safe error mapping.
disable-model-invocation: false
schema: 1
category: backend
surfaces:
- backend
platforms:
- linux
- darwin
- windows
token-cost: 482
triggers:
  keywords:
  - backend
  - behavior
  - centralized
  - client-safe
  - defining
  - error
  - handler
  - handling
  - logging
  - mapping
  - redaction
  - safe
  - taxonomy
  paths: []
  intents:
  - backend
---
# Backend Error Handling

## Overview

Backend failures must be structured, safe, and predictable.

This skill owns the error taxonomy, centralized handler behavior, and the rule that clients never see raw internal failures.

## Use When

- Defining or reviewing backend error classes.
- Mapping domain errors to HTTP status codes.
- Designing centralized error handling.
- Reviewing safe logging and redaction behavior.

## Do Not Use

- Service/controller boundary questions by themselves.
- API query semantics by themselves.
- Performance tuning without error-handling impact.

## Standard Error Envelope

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe user-facing message",
    "details": {}
  }
}
```

Rules:

- `success` must be `false`
- `error.code` is required
- `message` must be safe for clients
- `details` is optional and should stay narrow

## Status Code Rules

- `400` validation
- `401` unauthorized
- `403` forbidden
- `404` not found
- `409` conflict
- `429` rate limited
- `500` internal error

## Centralized Handler Rules

- Normalize internal errors into the public error envelope.
- Log safely.
- Hide stack traces and internal implementation details from clients.
- Keep controllers from building ad hoc error payloads unless they are only delegating to a shared formatter.

## Service Rules

- Services throw typed domain errors.
- Services do not send transport responses.
- Services do not swallow failures silently.

## Logging Rules

- Log enough context to debug.
- Do not log secrets, tokens, or sensitive payloads carelessly.
- Redact internal details before anything can surface to clients.

## Combine With

- `api-contract-standards` for envelope compatibility.
- `service-layer-standards` for where errors should originate.

## References

- Use `references/full-guide.md` for the longer strict version with class patterns and more detailed rules.

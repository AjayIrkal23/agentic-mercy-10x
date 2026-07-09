---
name: backend-error-handling
description: Use when defining backend error taxonomy, centralized handler behavior, safe logging, redaction, or client-safe error mapping.
metadata:
  version: "1.0"
  compliance: "Architectural Standards and Modular Development Protocol"
---

# Backend Error Handling Standards (STRICT)

## 0. Purpose
All backend services must implement **consistent, structured, and safe error handling** to ensure:
- Predictable API behavior
- Easier debugging
- No sensitive data leaks
- Production stability

Never expose internal errors or stack traces to clients.

---

# 1. Standard Error Response Format

All errors MUST return:

{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "details": {}
  }
}

Rules:
- success must be false
- error.code is mandatory
- message must be safe for frontend
- details optional (validation errors only)

Never return:
- stack traces
- raw database errors
- internal file paths

---

# 2. HTTP Status Code Rules

Use standard HTTP codes only:

| Scenario | Code |
|--------|--------|
| Validation Error | 400 |
| Unauthorized | 401 |
| Forbidden | 403 |
| Not Found | 404 |
| Conflict | 409 |
| Rate Limited | 429 |
| Server Error | 500 |

Never return 200 for failures.

---

# 3. Centralized Error Handler (MANDATORY)

All applications must have a global error handler.

Responsibilities:
- Normalize errors
- Map internal errors to response format
- Log errors safely
- Hide stack traces from clients

Controllers must NOT handle errors individually unless transforming domain errors.

---

# 4. Error Class Pattern (Recommended)

Use custom error classes:

Example types:
- ValidationError
- NotFoundError
- UnauthorizedError
- ConflictError
- DatabaseError
- ExternalServiceError

Each error class should define:
- statusCode
- errorCode
- safeMessage

---

# 5. Controller Rules (STRICT)

Controllers must:
- catch unexpected errors
- pass errors to centralized handler
- never return raw exceptions

Controllers must NOT:
- build custom error responses manually
- swallow errors silently

---

# 6. Service Layer Rules

Services must:
- throw domain errors (NotFound, Validation, Conflict)
- not send responses directly
- not depend on HTTP objects

Services must NOT:
- log excessively
- return inconsistent error structures

---

# 7. Validation Errors

Validation errors must include:

{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request",
    "details": {
      "field": "reason"
    }
  }
}

Rules:
- Field-level errors allowed
- Do not include raw validator output

---

# 8. Database Errors

Rules:
- Never return raw Mongo/Postgres errors
- Map DB errors to:
  - ConflictError (duplicate keys)
  - DatabaseError (generic DB failures)

---

# 9. Logging Rules

Server logs must include:
- route
- method
- requestId (if available)
- error message
- stack trace (server only)

Clients must NOT receive:
- stack traces
- internal IDs
- DB queries

---

# 10. External API Errors

When calling external services:
- wrap errors in ExternalServiceError
- never pass raw HTTP library errors to clients

---

# 11. Async Handling Rules

Never:
- leave unhandled promise rejections
- ignore await
- suppress errors silently

Always:
- await async calls
- wrap risky operations in try/catch

---

# 12. Security Rules

Never expose:
- tokens
- internal URLs
- database connection info
- system paths

Error messages must be safe for end users.

---

# 13. Anti-Patterns (Strictly Forbidden)

❌ Returning raw error.message directly  
❌ Returning stack trace to frontend  
❌ Catching errors and doing nothing  
❌ Logging entire request bodies with secrets  
❌ Mixing response logic and error logic  

---

# 14. Verification Checklist

Before merging:

- [ ] Central error handler exists
- [ ] All controllers delegate errors
- [ ] Services throw typed errors
- [ ] Error response format consistent
- [ ] No stack traces exposed
- [ ] DB errors mapped properly
- [ ] Validation errors structured
- [ ] Logs contain context

---

# 15. Golden Rule

Users see safe messages.  
Developers see full logs.  
Systems remain predictable.

---
description: Review a FastAPI application for architecture, async correctness, dependency injection, Pydantic schemas, security, performance, and testability.
---
<!-- ecc:commands/fastapi-review.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# FastAPI Review

Invoke the `fastapi-reviewer` agent for a focused FastAPI review.

## Usage

```text
/fastapi-review [file-or-directory]
```

## Review Areas

- App factory, router boundaries, middleware, and exception handlers.
- Pydantic request and response schema separation.
- Dependency injection for database sessions, auth, pagination, and settings.
- Async database and external HTTP patterns.
- CORS, auth, rate limits, logging, and secret handling.
- OpenAPI metadata and documented response models.
- Test client setup and dependency overrides.

## Expected Output

```text
[SEVERITY] Short issue title
File: path/to/file.py:42
Issue: What is wrong and why it matters.
Fix: Concrete change to make.
```

## Related

- Agent: `fastapi-reviewer`
- Skill: `fastapi-patterns`
- Command: `/python-review`
- Skill: `security-scan`

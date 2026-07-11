# Security review checklist

- Input validation + output encoding on every untrusted boundary (OWASP A03).
- AuthN/AuthZ enforced server-side per request; no client-trust for access control (A01).
- Secrets never logged, hardcoded, or returned in errors; use env/secret store.
- SQL/command/template injection: parameterised queries, no string-built queries.
- Sensitive data encrypted in transit + at rest; PII redacted in logs.
- Dependencies scanned; no known-vuln versions shipped.
- Deep dive: invoke `owasp-security` (OWASP Top 10:2025 / ASVS / LLM / agentic).

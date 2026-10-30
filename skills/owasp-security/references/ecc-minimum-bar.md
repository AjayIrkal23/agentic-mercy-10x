<!-- ecc:skills/security-review, rules/common/security.md, the-security-guide.md#minimum-bar-checklist @25278e7d -->
# Minimum bar (ECC graft)

Every change that touches a request path meets all six before review:

1. No secrets in source, config committed to git, or logs (redact tokens, keys, passwords).
2. Parameterised queries only; no string-built SQL, NoSQL filters or shell commands.
3. Input validated at the boundary (schema per route: type, length, format, allowed values).
4. Authorization checked on every route and every object access, not only authentication.
5. Dependencies audited (`npm audit` / `pip-audit` / `govulncheck`); a known critical blocks.
6. CSRF protection on every state-changing endpoint that uses cookie auth.

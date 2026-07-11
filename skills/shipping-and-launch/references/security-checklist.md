# Pre-launch security checklist

- Secrets rotated out of history; prod secrets in a vault, not env files in git.
- AuthN/AuthZ, rate limiting, and input validation verified on public endpoints.
- TLS everywhere; secure headers (HSTS, CSP) set.
- Dependency + container scan clean; least-privilege IAM.
- Full model: `owasp-security`.

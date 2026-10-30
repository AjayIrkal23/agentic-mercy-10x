<!-- ecc:skills/docker-patterns, the-security-guide.md#sandbox-isolation @25278e7d -->
# Container hardening (ECC graft)

- **Internal-only networks:** databases and caches sit on a network with `internal: true`;
  only the edge service publishes ports.
- **Non-root user:** every image sets `USER` to an unprivileged uid.
- **Read-only filesystem:** `read_only: true` plus explicit `tmpfs` / volume mounts for the
  paths that must be writable.
- **No host docker socket:** never mount `/var/run/docker.sock` into a service.
- Drop capabilities (`cap_drop: [ALL]`) and add back only what a service needs.

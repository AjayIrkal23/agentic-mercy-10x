# Performance review checklist

- No N+1 queries; batched/joined DB access; indexes cover the query shape.
- No unbounded loads; pagination + limits on list endpoints.
- Hot paths avoid repeated work; cache where correctness allows.
- Async/streaming for large payloads; no blocking I/O on the request path.
- Frontend: memoise expensive renders, code-split, lazy-load heavy assets.
- Measure before optimising — see `performance-optimization`.

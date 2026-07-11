# Pre-launch performance checklist

- Load-tested to expected peak + headroom; p95/p99 within SLO.
- DB indexed for prod query shapes; no N+1 on hot paths.
- CDN/caching for static assets; Core Web Vitals green on key pages.
- Autoscaling + resource limits configured; graceful degradation.
- Deep dive: `performance-optimization`.
